"""GPU-independent deployment validation; no Docker/model/GPU is invoked."""

import subprocess
import unittest
from unittest.mock import patch

from test_remote_execution import TemporaryCase
from remote_execution import vllm
from remote_execution.protocol import file_hash, private_json


class DeploymentTests(TemporaryCase):
    def fixture(self):
        model = self.root / "model"; model.mkdir()
        (model / "chat_template.jinja").write_text("{{ messages }}")
        private_json(model / "config.json", {"torch_dtype": "bfloat16"})
        env = self.root / "vllm.env"; env.write_text("VLLM_API_KEY=" + "s" * 48); env.chmod(0o600)
        return {"schema_version": 1, "container_name": "benchmark-vllm", "image": "vllm/vllm-openai@sha256:" + "a" * 64,
                "server_version": "test-pinned-version", "gpu_devices": ["0", "1"], "model_path": str(model),
                "model_repository": "Qwen/Qwen3.8-27B", "model_id": "qwen-bf16", "model_revision": "b" * 40,
                "tokenizer_revision": "b" * 40, "chat_template_sha256": file_hash(model / "chat_template.jinja"),
                "precision": "bf16", "tensor_parallel_size": 2, "pipeline_parallel_size": 1,
                "max_model_len": 32768, "max_num_seqs": 4, "gpu_memory_utilization": 0.9,
                "listen_host": "172.17.0.1", "port": 8000, "api_env_file": str(env), "shm_gib": 8,
                "tool_call_parser": "qwen3_coder", "reasoning_parser": "qwen3", "generation_config": "auto",
                "enable_prefix_caching": False}

    def test_single_multi_gpu_tp_pp_no_gpu_model_assumption(self):
        config = self.fixture()
        for devices, tp, pp in ((["0"], 1, 1), (["0", "1"], 2, 1), (["0", "1"], 1, 2),
                                (["0", "1", "2", "3"], 2, 2)):
            c = config | {"gpu_devices": devices, "tensor_parallel_size": tp, "pipeline_parallel_size": pp}
            argv = vllm.command(c)
            self.assertEqual(argv[argv.index("--tensor-parallel-size") + 1], str(tp))
            self.assertEqual(argv[argv.index("--pipeline-parallel-size") + 1], str(pp))
            self.assertNotIn("--quantization", argv)
            self.assertNotIn("L40", " ".join(argv))
            self.assertNotIn("s" * 48, " ".join(argv))

    def test_only_explicit_fp8_no_lower_precision(self):
        config = self.fixture()
        for precision in ("int4", "awq", "int8", "gptq", "auto"):
            with self.assertRaises(ValueError):
                vllm.command(config | {"precision": precision})
        with self.assertRaisesRegex(ValueError, "explicit"):
            vllm.command(config | {"precision": "fp8"})
        argv = vllm.command(config | {"precision": "fp8", "fp8_mode": "checkpoint"})
        self.assertEqual(argv[argv.index("--quantization") + 1], "fp8")
        self.assertEqual(argv[argv.index("--kv-cache-dtype") + 1], "auto")

    def test_reject_drift_public_bind_and_ambient_overrides(self):
        config = self.fixture()
        for change in ({"image": "vllm/vllm-openai:latest"}, {"model_revision": "main"},
                       {"gpu_devices": ["0", "0"]}, {"tensor_parallel_size": 4}, {"max_num_seqs": True},
                       {"listen_host": "0.0.0.0"}, {"listen_host": "8.8.8.8"}, {"extra_args": ["--quantization", "awq"]}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                vllm.validate(config | change)

    def test_hardware_and_precision_checks_without_gpu(self):
        config = self.fixture()
        def output(argv, **kwargs):
            if "--query-gpu=index,uuid,name,memory.total,compute_cap,driver_version" in argv:
                text = "0, GPU-a, NVIDIA L40, 46068, 8.9, 570.0\n1, GPU-b, NVIDIA L40, 46068, 8.9, 570.0\n"
            elif "topo" in argv:
                text = "GPU0 GPU1 PHB\n"
            else:
                text = "sha256:image\n"
            return subprocess.CompletedProcess(argv, 0, text, "")
        with patch("remote_execution.vllm.subprocess.run", side_effect=output):
            evidence = vllm.inspect(config)
            self.assertEqual(len(evidence["gpus"]), 2)
            vllm.inspect(config | {"precision": "fp8", "fp8_mode": "online"})
            with self.assertRaisesRegex(ValueError, "checkpoint"):
                vllm.inspect(config | {"precision": "fp8", "fp8_mode": "checkpoint"})
        self.assertNotIn("s" * 48, str(evidence))
        service = vllm.service_config(config)
        self.assertEqual(service["provenance"]["dtype"], "bfloat16")
        self.assertIsNone(service["provenance"]["quantization"])

    def test_fp8_cannot_silently_emulate_on_older_gpu(self):
        config = self.fixture()
        inventory = "0, GPU-a, NVIDIA A100, 81920, 8.0, 570.0\n1, GPU-b, NVIDIA A100, 81920, 8.0, 570.0\n"
        with patch("remote_execution.vllm.subprocess.run", return_value=subprocess.CompletedProcess([], 0, inventory)), \
                self.assertRaisesRegex(ValueError, "native hardware"):
            vllm.inspect(config | {"precision": "fp8", "fp8_mode": "online"})

    def test_quantized_nested_source_not_accepted_as_bf16(self):
        config = self.fixture()
        private_json(self.root / "model/config.json", {
            "text_config": {"torch_dtype": "bfloat16", "quantization_config": {"quant_method": "awq"}}})
        with self.assertRaisesRegex(ValueError, "unquantized"):
            vllm.inspect(config)


if __name__ == "__main__":
    unittest.main()
