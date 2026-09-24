"""Explicit, GPU-model-agnostic vLLM deployment; not a benchmark profile.

Run under systemd on the execution node. No automatic quantization, context
reduction, GPU selection, downloads, package installs or parallelism fallback.
The project uv environment needs neither CUDA nor a vLLM Python dependency.
"""

from __future__ import annotations

import argparse
import csv
import ipaddress
import json
import os
from pathlib import Path
import re
import subprocess
import uuid

from .protocol import digest, exact, file_hash, identifier, positive, private_json, read_json, sha256


def validate(config):
    exact(config, {"schema_version", "container_name", "image", "server_version", "gpu_devices",
          "model_path", "model_repository", "model_id", "model_revision", "tokenizer_revision", "chat_template_sha256",
          "precision", "tensor_parallel_size", "pipeline_parallel_size", "max_model_len", "max_num_seqs",
          "gpu_memory_utilization", "listen_host", "port", "api_env_file", "shm_gib",
          "tool_call_parser", "reasoning_parser", "generation_config", "enable_prefix_caching"},
          {"fp8_mode", "request_log_flag"})
    if type(config["schema_version"]) is not int or config["schema_version"] != 1:
        raise ValueError("Unsupported vLLM deployment schema")
    identifier(config["container_name"])
    if not re.fullmatch(r"[A-Za-z0-9./:_-]+@sha256:[0-9a-f]{64}", config["image"]):
        raise ValueError("Pin the vLLM container by registry digest, not a mutable tag")
    for key in ("server_version", "model_id", "model_repository"):
        if not isinstance(config[key], str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9./+_-]*", config[key]):
            raise ValueError("Invalid server version/model ID")
    for key in ("model_path", "api_env_file"):
        path = config[key]
        if not isinstance(path, str) or not Path(path).is_absolute() or any(c in path for c in (",", "\n", "\r", "\x00")):
            raise ValueError("Deployment paths must be absolute and mount-safe")
    for key in ("model_revision", "tokenizer_revision"):
        if not isinstance(config[key], str) or not re.fullmatch(r"[0-9a-f]{40}", config[key]):
            raise ValueError("Pin model and tokenizer to full revision commits")
    if config["tokenizer_revision"] != config["model_revision"]:
        raise ValueError("This recipe serves tokenizer and weights from the same pinned local snapshot")
    sha256(config["chat_template_sha256"])
    devices = config["gpu_devices"]
    if not isinstance(devices, list) or not devices or any(
            not isinstance(d, str) or not re.fullmatch(r"[0-9]+|GPU-[A-Za-z0-9-]+", d) for d in devices):
        raise ValueError("Select explicit NVIDIA GPU indices or UUIDs")
    if len(set(devices)) != len(devices):
        raise ValueError("Duplicate GPU selections")
    for key in ("tensor_parallel_size", "pipeline_parallel_size", "max_model_len", "max_num_seqs", "port", "shm_gib"):
        positive(config[key], 10**7 if key == "max_model_len" else 65535)
    if config["tensor_parallel_size"] * config["pipeline_parallel_size"] != len(devices):
        raise ValueError("TP times PP must equal the number of selected GPUs")
    utilization = config["gpu_memory_utilization"]
    if type(utilization) not in {float, int} or not 0 < utilization < 1:
        raise ValueError("GPU memory utilization must be between zero and one")
    if config["precision"] not in {"bf16", "fp8"}:
        raise ValueError("Only BF16 and explicit FP8 are supported")
    if config["precision"] == "fp8":
        if config.get("fp8_mode") not in {"checkpoint", "online"}:
            raise ValueError("FP8 requires explicit checkpoint or online quantization mode")
    elif config.get("fp8_mode") is not None:
        raise ValueError("BF16 cannot declare FP8 quantization")
    if not isinstance(config["listen_host"], str):
        raise ValueError("listen_host must be an explicit IP string")
    address = ipaddress.ip_address(config["listen_host"])
    if address.version != 4 or address.is_unspecified or not (address.is_private or address.is_loopback):
        raise ValueError("Bind vLLM to an explicit private/loopback IPv4 interface, never public/all interfaces")
    for key in ("tool_call_parser", "reasoning_parser"):
        if config[key] is not None:
            identifier(config[key])
    if config["generation_config"] not in {"auto", "vllm"}:
        raise ValueError("generation_config must be explicitly auto or vllm")
    if type(config["enable_prefix_caching"]) is not bool:
        raise ValueError("Prefix caching must be explicit")
    if config.get("request_log_flag") not in {None, "--disable-log-requests", "--no-enable-log-requests"}:
        raise ValueError("request_log_flag must explicitly disable request logging")
    return config


def command(config):
    validate(config)
    # Do not assume a renamed boolean flag is accepted by historical images.
    # Other pinned versions can declare their spelling; check-cli parses the
    # entire generated serve command using the actual image before any run.
    log_flag = config.get("request_log_flag") or (
        "--no-enable-log-requests" if config["server_version"] == "0.29.0" else "--disable-log-requests")
    args = ["/usr/bin/docker", "run", "--rm", "--init", "--pull", "never", "--name", config["container_name"],
            "--label", "org.agentic-formalizer.component=model-service", "--network", "host",
            "--gpus", '"device=' + ",".join(config["gpu_devices"]) + '"',
            "--shm-size", f"{config['shm_gib']}g", "--env-file", config["api_env_file"],
            "--env", "HF_HUB_OFFLINE=1", "--env", "TRANSFORMERS_OFFLINE=1", "--env", "VLLM_NO_USAGE_STATS=1",
            "--mount", f"type=bind,source={config['model_path']},target=/model,readonly",
            "--entrypoint", "vllm", config["image"], "serve", "/model",
            "--served-model-name", config["model_id"], "--tokenizer", "/model", "--dtype", "bfloat16",
            "--chat-template", "/model/chat_template.jinja", "--kv-cache-dtype", "auto",
            "--distributed-executor-backend", "mp", "--generation-config", config["generation_config"],
            "--host", config["listen_host"], "--port", str(config["port"]), log_flag]
    for key in ("tensor_parallel_size", "pipeline_parallel_size", "max_model_len", "max_num_seqs", "gpu_memory_utilization"):
        args.extend(["--" + key.replace("_", "-"), str(config[key])])
    args.append("--enable-prefix-caching" if config["enable_prefix_caching"] else "--no-enable-prefix-caching")
    if config["precision"] == "fp8":
        args.extend(["--quantization", "fp8"])
    if config["tool_call_parser"]:
        args.extend(["--enable-auto-tool-choice", "--tool-call-parser", config["tool_call_parser"]])
    if config["reasoning_parser"]:
        args.extend(["--reasoning-parser", config["reasoning_parser"]])
    return args


CLI_PROBE = '''
import importlib.metadata, json, sys
version = importlib.metadata.version("vllm")
if version != sys.argv[1]:
    raise ValueError("Installed vLLM version differs from server_version: " + version)
# As in vLLM's CPU-only CLI utilities: constructing parser defaults can otherwise
# fail device inference on a GPU-less probe. This process never creates an engine.
from vllm import platforms
if getattr(platforms.current_platform, "is_unspecified", lambda: False)():
    from vllm.platforms.cpu import CpuPlatform
    platforms.current_platform = CpuPlatform()
from vllm.entrypoints.cli.serve import ServeSubcommand
try:
    from vllm.utils.argparse_utils import FlexibleArgumentParser
except ImportError:
    from vllm.utils import FlexibleArgumentParser
parser = FlexibleArgumentParser()
subparsers = parser.add_subparsers(dest="subcommand", required=True)
command = ServeSubcommand()
command.subparser_init(subparsers)
args = parser.parse_args(json.loads(sys.argv[2]))
if not (getattr(args, "disable_log_requests", False) or
        getattr(args, "enable_log_requests", None) is False):
    raise ValueError("Request logging was not disabled")
# Never invoke cmd/validate/create_engine_config: no engine, weights or listener.
print("BENCHMARK_CLI_PROBE=" + json.dumps({"status": "pass", "server_version": version}))
'''


def check_cli(config):
    """Parse in the pinned image, without GPUs, secrets, weights or network.

    This verifies CLI syntax, NOT CUDA/engine startup or inference. Resources
    have unique ownership; a timed-out client cannot leave its container behind.
    """
    argv = command(config)
    serve_args = argv[argv.index(config["image"]) + 1:]
    name = "bench-vllm-cli-" + uuid.uuid4().hex
    label = "org.agentic-formalizer.component=vllm-cli-probe"
    args = ["/usr/bin/docker", "run", "--rm", "--init", "--pull", "never", "--name", name,
            "--label", label, "--network", "none", "--cpus", "1", "--memory", "2g", "--pids-limit", "256",
            "--env", "NVIDIA_VISIBLE_DEVICES=void",
            "--env", "HF_HUB_OFFLINE=1", "--env", "TRANSFORMERS_OFFLINE=1", "--env", "VLLM_NO_USAGE_STATS=1",
            "--entrypoint", "python3", config["image"], "-c", CLI_PROBE, config["server_version"], json.dumps(serve_args)]
    try:
        result = subprocess.run(args, capture_output=True, text=True, timeout=120)
        if result.returncode:
            raise ValueError("Pinned vLLM CLI parsing failed (no engine started): " + result.stderr[-8000:])
        lines = [s.removeprefix("BENCHMARK_CLI_PROBE=") for s in result.stdout.splitlines()
                 if s.startswith("BENCHMARK_CLI_PROBE=")]
        if len(lines) != 1:
            raise ValueError("Pinned vLLM parser returned no unique acceptance record")
        row = json.loads(lines[0])
        if row != {"status": "pass", "server_version": config["server_version"]}:
            raise ValueError("Pinned vLLM CLI evidence mismatch")
        return row | {"scope": "actual serve parser only; engine startup not verified",
                      "serve_argv": serve_args, "image": config["image"]}
    finally:
        remaining = subprocess.run(["/usr/bin/docker", "container", "inspect", name],
                                   capture_output=True, text=True, timeout=15)
        if remaining.returncode == 0:
            objects = json.loads(remaining.stdout)
            if (len(objects) != 1 or objects[0].get("Name") != "/" + name or
                    objects[0].get("Config", {}).get("Labels", {}).get(label.split("=")[0]) != "vllm-cli-probe"):
                raise ValueError("Unexpected CLI probe ownership; refuse cleanup")
            container_id = objects[0]["Id"]
            if not re.fullmatch(r"[0-9a-f]{64}", container_id):
                raise ValueError("Invalid CLI probe container ID")
            subprocess.run(["/usr/bin/docker", "rm", "-f", container_id],
                           check=True, capture_output=True, text=True, timeout=30)
        elif "No such" not in remaining.stderr:
            raise ValueError("Cannot verify CLI probe cleanup; inspect Docker before retrying")


def inspect(config):
    """Read-only node checks; not a substitute for real engine/model canaries."""
    validate(config)
    env_file = Path(config["api_env_file"])
    info = env_file.lstat()
    import stat
    if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
        raise ValueError("vLLM env file must be owner-only")
    lines = [line.strip() for line in env_file.read_text().splitlines() if line.strip() and not line.lstrip().startswith("#")]
    if len(lines) != 1 or not re.fullmatch(r"VLLM_API_KEY=[A-Za-z0-9_-]{32,}", lines[0]):
        raise ValueError("vLLM env file must contain only VLLM_API_KEY=<32+ URL-safe characters>")
    model = Path(config["model_path"])
    if file_hash(model / "chat_template.jinja") != config["chat_template_sha256"]:
        raise ValueError("Chat template hash differs from the declared deployment")
    model_config = read_json(model / "config.json")
    text = model_config.get("text_config", {})
    quantizations = [value for value in (model_config.get("quantization_config"), text.get("quantization_config")) if value]
    mode = config.get("fp8_mode")
    if config["precision"] == "bf16" or mode == "online":
        if quantizations or model_config.get("compression_config") or text.get("compression_config"):
            raise ValueError("Expected unquantized BF16 source checkpoint")
        dtype = model_config.get("dtype", model_config.get("torch_dtype"))
        dtype = text.get("dtype", text.get("torch_dtype", dtype))
        if dtype != "bfloat16":
            raise ValueError("Source checkpoint must declare bfloat16; no implicit precision conversion")
    elif not quantizations or any(not isinstance(q, dict) or q.get("quant_method") != "fp8" for q in quantizations):
        raise ValueError("FP8 checkpoint mode requires a native fp8 checkpoint configuration")
    result = subprocess.run(["nvidia-smi", "--query-gpu=index,uuid,name,memory.total,compute_cap,driver_version",
                             "--format=csv,noheader,nounits"], check=True, capture_output=True, text=True, timeout=15)
    inventory = [dict(zip(("index", "uuid", "name", "memory_mib", "compute_capability", "driver_version"),
                         (v.strip() for v in row))) for row in csv.reader(result.stdout.splitlines())]
    selected = []
    for device in config["gpu_devices"]:
        matches = [gpu for gpu in inventory if device in (gpu["index"], gpu["uuid"])]
        if len(matches) != 1 or any(gpu["uuid"] == matches[0]["uuid"] for gpu in selected):
            raise ValueError("Selected GPU unavailable or duplicated by index/UUID alias")
        selected.append(matches[0])
    minimum = (8, 9) if config["precision"] == "fp8" else (8, 0)
    if any(tuple(map(int, gpu["compute_capability"].split("."))) < minimum for gpu in selected):
        raise ValueError("Selected precision lacks native hardware support; no silent emulation/fallback")
    topology = subprocess.run(["nvidia-smi", "topo", "-m"], check=True, capture_output=True, text=True, timeout=15)
    image = subprocess.run(["/usr/bin/docker", "image", "inspect", config["image"], "--format", "{{.Id}}"],
                           check=True, capture_output=True, text=True, timeout=15)
    return {"deployment_sha256": digest(config), "deployment": config, "gpus": selected,
            "topology": topology.stdout, "image_id": image.stdout.strip(),
            "model_config_sha256": file_hash(model / "config.json"),
            "weights_revision_attestation": "operator-pinned-local-snapshot; not a full weight hash",
            "canary_required": True}


def service_config(config):
    """Secret-free node.services.model entry compiled from the SAME deployment."""
    validate(config)
    provenance = {key: config[key] for key in (
        "model_repository", "model_revision", "tokenizer_revision", "server_version", "chat_template_sha256",
        "generation_config", "max_model_len", "tool_call_parser", "reasoning_parser",
        "gpu_devices", "tensor_parallel_size", "pipeline_parallel_size", "max_num_seqs", "enable_prefix_caching")}
    provenance.update({"dtype": "bfloat16", "quantization": "fp8" if config["precision"] == "fp8" else None,
                       "fp8_mode": config.get("fp8_mode"), "kv_cache_dtype": "auto (bfloat16)",
                       "image": config["image"], "deployment_sha256": digest(config)})
    return {"health_url": f"http://{config['listen_host']}:{config['port']}/v1/models",
            "expected": {"object": "list"}, "systemd_unit": config["container_name"] + ".service",
            "api_key_env": "SELF_HOSTED_API_KEY", "provenance": provenance}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("plan", "service", "inspect", "check-cli", "run"))
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--evidence", type=Path, help="Create-only deployment evidence, required for run")
    parser.add_argument("--evidence-dir", type=Path, help="Write unique per-start evidence for supervised restarts")
    args = parser.parse_args()
    config = validate(read_json(args.config))
    if args.action == "service":
        print(json.dumps(service_config(config), indent=2))
        return
    argv = command(config)
    if args.action == "plan":
        print(json.dumps({"deployment_sha256": digest(config), "argv": argv}, indent=2))
        return
    if args.action == "check-cli":
        evidence = check_cli(config)
        if args.evidence is not None:
            private_json(args.evidence, evidence, replace=False)
        print(json.dumps(evidence, indent=2))
        return
    evidence = inspect(config)
    evidence["cli_compatibility"] = check_cli(config)
    if args.evidence is not None and args.evidence_dir is not None:
        parser.error("Choose --evidence or --evidence-dir")
    if args.action == "run" and args.evidence is None and args.evidence_dir is None:
        parser.error("run requires --evidence or --evidence-dir")
    if args.evidence_dir is not None:
        import uuid
        args.evidence = args.evidence_dir / ("deployment-" + uuid.uuid4().hex + ".json")
    if args.evidence is not None:
        # One fresh evidence file per supervised start; never replace a prior launch.
        private_json(args.evidence, evidence, replace=False)
    if args.action == "inspect":
        print(json.dumps(evidence, indent=2))
        return
    # Docker forwards signals to the foreground model server. Only the selected
    # service is launched; no Docker context/network cleanup/global mutation.
    os.execv(argv[0], argv)


if __name__ == "__main__":
    main()
