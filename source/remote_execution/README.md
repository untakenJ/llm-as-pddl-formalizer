# Execution nodes (opt-in, protocol v1)

Run benchmark cells on either this machine or a remote GPU machine, using the
same `agent_formalizer` runner, adapters, gateways, timers, solver and VAL. The
controller sends frozen code/data/configuration and receives evidence. Model
weights and GPU inference stay on the execution node.

This component uses only the Python standard library; the benchmark itself uses
the project's existing **uv** environment. No new dependencies or default
benchmark/operational profile changes are required. The original local CLI path
does not import this component and remains available.

## Boundaries and guarantees

- **One job owns one fixed comparison cell**: one harness, model/complete
  profile, domain/dataset and explicit fixed indices. The controller decides
  the matrix; the node executes each cell using the existing pipeline's worker
  counts. Do not split one cell into competing jobs or replicate it across
  nodes and then choose the better results. Use a stable, unique job ID.
- A release contains code, inputs, complete profiles and `uv.lock`, addressed by
  a content manifest SHA-256. Packaging takes explicit includes, refuses links,
  and excludes `_private`, `.env*`, output, caches, virtualenvs and common model
  weight formats. It is **not a secret scanner**: review explicitly included
  files before upload. A trusted controller can deploy executable code; the
  control token has execution authority, not merely monitoring authority.
- Submission is transactional/idempotent. Repeating the same request returns
  its existing state. Reusing its ID with different inputs is rejected. A lost
  HTTP acknowledgement is **not** permission to create a replacement job.
- Accepted jobs are stored in SQLite. Per-job owner processes are detached
  from the control server/SSH session. Restarting the control worker adopts live
  owners; it does not restart agents. Owner locks also protect a surviving
  benchmark subprocess, and process-group checks block unsafe relaunch.
- Reboot, an uncertain dispatch or missing ownership becomes `needs_attention`.
  There is no guessed exactly-once recovery after arbitrary crashes. Inspect
  processes, containers, evidence and native leases before explicit `resume`.
  Resume records a mandatory reason and a generation compare-and-swap token.
  It retains the original release/request/node configuration and output, then
  lets **native benchmark validity/resume checks** choose unfinished slots.
- `completed` means the cell pipeline completed, **not** that every PDDL passed.
  Valid wrong answers never cause automatic job resampling. `failed` can mean
  incomplete/infra-invalid slots or evaluator infrastructure failure; inspect
  the native records. No retry loop is added around model/tool calls here.
- Gateway, `external_calls`, checkpoint controls, container lifecycle and agent
  clocks stay on the execution node. Control transport/deployment/queue time
  and result copying are outside the agent execution. Ordinary model inference
  latency still counts according to the unchanged benchmark profile.
- No remote `DOCKER_HOST`, global Docker context change, timer RPC, live
  cross-machine checkpoint migration, model-weight transfer or GPU access for
  agent containers is added. Self-hosted inference is a service, not an agent
  tool. Enabling additional agent capabilities requires an explicit condition.

## Files and responsibilities

| File | Responsibility |
| --- | --- |
| `protocol.py` | Strict versioned job/node schemas, paths and integrity helpers |
| `bundle.py` | Create-only packaging, bounded safe installation, release verification and node bindings |
| `store.py` | Durable queue/events, ownership guards and sealed evidence snapshots |
| `worker.py` | Loopback authenticated API, admission, detached owners and read-only progress |
| `benchmark.py` | Profile identity/service preflight; call the existing formalizer → solver → VAL pipeline |
| `client.py`, `__main__.py` | Controller API/CLI, resumable transfer, verified read-only mirrors |

The node does not independently maintain experiment logic. Deploy a pinned
copy of this component and install each benchmark release from the controller.
Do not edit a deployed worker installation underneath active node jobs.

## Preserve an already running local campaign

Development is allowed alongside a frozen campaign, but a Git branch alone
does not isolate installed runtimes. For the existing frozen campaign:

1. Keep its output, launcher/recovery script, frozen source/data/profile/VAL,
   shared runtime targets, Docker images, global Node/OpenClaw and solver
   service unchanged. Its resume must use the frozen source, not this branch.
2. Reuse the current `.venv` without syncing/upgrading dependencies. During
   concurrent development run `uv run --no-sync --offline python -B ...`.
   Do not change `uv.lock` or install the CUDA extra on the campaign host.
3. Use fresh test directories (the tests use `TemporaryDirectory`) or new
   output subdirectories. Do not use an existing campaign directory for a node
   state root, download mirror or release archive.
4. Mock tests below make no Docker, real model, public solver or running local
   solver calls. Heavy builds/GPU/container canaries wait for the remote node.
5. On campaign disconnect/resume, retain the native shared network guard. It
   cleans only ownership-verified, safely collectible resources. Never prune
   globally, delete live resources, delete the shared registry, or remove the
   solver network. Evidence-uncollected crash survivors need review, not blind
   cleanup to make capacity warnings disappear.

## Remote prerequisites (configure only the new machine)

1. Linux with `/proc`, `flock`, Docker and systemd. A dedicated account needs
   access to its **local** Docker socket. Docker access is effectively host
   administrative access; do not grant the worker to untrusted clients.
2. A pinned worker/benchmark installation, for example `/opt/formalizer-node`,
   with this project's `source`, `pyproject.toml` and `uv.lock`. Provision its
   Python environment once using `uv sync --locked`. Running the worker uses
   that `.venv`; the GPU model server can use a separate pinned container and
   need not install PyTorch in the benchmark environment.
3. Install the locked harness runtimes and exact agent/solver image identities.
   Provision OpenClaw and Node at the paths required by the current runtime
   lock (`/usr/lib/node_modules/openclaw`, `/usr/bin/node`). Bind the node-local
   harness cache into release workspaces. The original runtime lock remains
   authoritative; a different build is not silently treated as equivalent.
   If a locked image has no registry source, provision it once by an explicitly
   approved image export/import. Images are not sent per task.
4. Install VAL with its expected `build/linux64/Release/bin` tree. The `val`
   binding below points to the **VAL project root**, not just the binary.
5. For GPU inference, provision NVIDIA drivers/container runtime and a pinned
   compatible server such as vLLM. Download a pinned model/tokenizer revision
   directly on the remote node and keep its weight cache there. Select the
   actual parser/template/precision for the model; do not copy an arbitrary
   example model's settings. Pin and record these before starting a study.
6. Run one compatible shared solver under systemd; see
   [the local-solver lifecycle contract](../local_solver/README.md#campaign-lifecycle-contract).
   Typical limits are one planner worker, 4096 MiB and 90 seconds. Service
   health must match the declared image and complete resource configuration.
   The worker only checks services; it never reconfigures/restarts shared ones.
7. Provision an owner-only runner `_private/.env` on the node separately.
   Releases never upload it. Only selected named credentials go to gateways;
   agent containers retain placeholder credentials and the existing isolation.

The gateway sidecar must be able to reach the model service: its `127.0.0.1`
is **not** the node host. For Docker harnesses an explicitly configured origin
such as `http://host.docker.internal:8000/v1` can use the existing host-gateway
mapping. Bind/firewall the model port for that private interface, not the public
Internet. If using host-only `minimum`, select an origin also resolvable from
the host (e.g. an appropriate private interface address).

## Node configuration and supervision

Create an owner-only node directory and a random owner-only control-token file.
The same token is provisioned separately on the controller for the tunnel;
never put token values in JSON, argv, Git, an archive or benchmark output.

Example node JSON (replace paths/image ID; this is not an installed service):

```json
{
  "schema_version": 1,
  "node_id": "gpu-1",
  "state_dir": "/srv/formalizer-node/state",
  "python": "/opt/formalizer-node/.venv/bin/python",
  "token_file": "/srv/formalizer-node/private/control-token",
  "max_jobs": 1,
  "max_formalizer_workers": 4,
  "allow_probe": false,
  "bindings": {
    "harness_runtimes": "/opt/formalizer-node/.cache/harness-runtimes",
    "zeroclaw_deadlines": "/opt/formalizer-node/.cache/zeroclaw-deadlines",
    "val": "/opt/VAL",
    "secrets_env_file": "/srv/formalizer-node/private/model.env"
  },
  "services": {
    "solver": {
      "health_url": "http://127.0.0.1:8769/__benchmark__/health",
      "systemd_unit": "pddl-local-solver-benchmark.service",
      "expected": {
        "status": "ok",
        "backend": "local-planutils",
        "pool": {"image_id": "sha256:REPLACE_WITH_PINNED_IMAGE_ID"},
        "config": {
          "workers": 1,
          "memory": "4096m",
          "memory_swap": "4096m",
          "cpus": 1.0,
          "pids_limit": 256,
          "timeout_seconds": 90,
          "worker_security": "privileged",
          "allowed_solvers": ["dual-bfws-ffparser"]
        }
      }
    }
  }
}
```

Bindings are node-local paths, never controller-provided arbitrary mount
instructions. Do not mutate bindings, Python dependencies or services during
active jobs. An explicitly requested changed node configuration requires a new
job/study review, not silently repairing old results under new conditions.

`max_jobs` defaults to 1; the cell's existing operational config controls
formalizer/solver/VAL workers. A formalizer count above the node ceiling is
rejected, not silently lowered. Provision CPU/RAM/PID/disk limits for the whole
node with systemd/cgroups as well as the existing per-container limits. There
is no GPU scheduler in this component; the model service owns GPU admission.

Example systemd unit:

```ini
[Unit]
Description=Benchmark execution-node control service
After=network-online.target docker.service

[Service]
Type=simple
User=benchmark
WorkingDirectory=/opt/formalizer-node
Environment=PYTHONPATH=/opt/formalizer-node/source
Environment=PYTHONDONTWRITEBYTECODE=1
ExecStart=/opt/formalizer-node/.venv/bin/python -B -m remote_execution.worker --config /srv/formalizer-node/node.json --port 8876
Restart=on-failure
RestartSec=3
UMask=0077
# Control-service restart must not kill detached accepted jobs.
# Consequently, stopping this unit alone does NOT stop a campaign.
KillMode=process

[Install]
WantedBy=multi-user.target
```

Use a dedicated SSH key and verified `known_hosts`. Forward only the loopback
worker port, for example:

```bash
ssh -N -o ExitOnForwardFailure=yes -o ServerAliveInterval=30 \
  -L 127.0.0.1:18876:127.0.0.1:8876 benchmark@gpu-host
```

The worker binds only `127.0.0.1`; the client refuses non-loopback control
origins. Use this tunnel, not an unauthenticated public worker or Docker port.
An SSH interruption only interrupts control/transfer. Accepted jobs continue.
Supervise the tunnel separately if persistent controller access is desired.

## Self-hosted model routing

The new explicit provider prefix is `self-hosted/<served-model-id>`. Add a
credential profile **to the new experiment's frozen registry**, not to the
canonical baseline or an old sweep:

```json
{
  "provider": "self-hosted",
  "api_key_env": "SELF_HOSTED_API_KEY",
  "provider_options": {
    "self_hosted": {"base_url": {"env": "SELF_HOSTED_BASE_URL"}}
  }
}
```

Select its name through the operational config's `credential.profile`, or add
the provider default in that frozen registry. Set the two named variables in
the node-only secret file. An explicit endpoint is mandatory; ambient
`OPENAI_BASE_URL` is ignored. This does not change native provider defaults.

For a self-hosted job also declare/select a `model` service. Its authenticated
health URL should return `/v1/models` JSON, with `expected: {"object":"list"}`,
`systemd_unit` naming the supervised model server and optional
`api_key_env: "SELF_HOSTED_API_KEY"`. The selected served model must appear in
the returned `data`. Its `provenance` must record `model_revision`,
`tokenizer_revision`, `server_version`, `dtype`, `quantization`,
`chat_template_sha256`, `generation_config`, `max_model_len`, `tool_call_parser`
and `reasoning_parser` (use explicit null where genuinely inapplicable).
This deployment description is operator-provided provenance, not automatic
attestation of model weights. Keep it consistent with the actual service.

The five harnesses retain their own OpenAI-compatible native routes. No model
request rewrite, output improvement or new retry policy is introduced. The
shared gateway records usage and readable `reasoning_content` plus the current
vLLM `choices[].message/delta.reasoning` field, without modifying delivery.
See [vLLM reasoning output documentation](https://docs.vllm.ai/en/latest/features/reasoning_outputs/).
Local GPU costs are not invented as API prices: unpriced usage remains unpriced.
Real-model parser/tool-call compatibility still requires a remote canary.

## Controller workflow

Use the existing uv environment, without synchronizing it during another sweep:

```bash
PYTHONPATH=source uv run --no-sync --offline python -B -m remote_execution --help
```

1. Derive a **new complete profile from the canonical baseline**, with only the
   user's requested changes. Keep operational configuration separate; set its
   desired worker counts, `resume: true`, and `agent_trace: true`. Its credential
   registry path must be release-relative and the secret path `_private/.env`.
   Place these non-secret files under a new release input directory such as
   `campaign_inputs/gpu-study/`. Never repurpose an old output as the input tree.
2. Package selected trees. Include golden inputs too: evaluation stays remote.

```bash
PYTHONPATH=source uv run --no-sync --offline python -B -m remote_execution bundle \
  --root . --include source --include pyproject.toml --include uv.lock \
  --include campaign_inputs/gpu-study \
  --include data/textual_barman/Heavily_Templated_Barman-100 \
  --include data/textual_barman/Barman-100_PDDL \
  --archive output/NEW_REMOTE_RELEASE.tar.gz
```

3. Use the returned release ID to upload, then create a cell request with the
   `job` command. It computes the resolved config SHA from the specified profile
   without calling Docker, a model or a solver. Replace `RELEASE_SHA256` below.

```bash
PYTHONPATH=source uv run --no-sync --offline python -B -m remote_execution \
  --endpoint http://127.0.0.1:18876 --token-file /path/to/private/control-token \
  upload --archive output/NEW_REMOTE_RELEASE.tar.gz --release-id RELEASE_SHA256

PYTHONPATH=source uv run --no-sync --offline python -B -m remote_execution job \
  --job-id gpu-study-openclaw-barman --release-id RELEASE_SHA256 \
  --harness openclaw --domain barman --dataset Heavily_Templated_Barman-100 \
  --indices 1,2,3 --profile campaign_inputs/gpu-study/profile.json \
  --operational campaign_inputs/gpu-study/operational.json \
  --service solver --service model --destination output/NEW_REMOTE_JOB.json
```

4. With the same endpoint/token options, run `submit --job ...`,
   `status JOB_ID`, `progress JOB_ID`, or `events JOB_ID --after SEQUENCE`.
   Upload, submit and status calls are independent; no long-lived controller
   session is required. `progress` reads native validity snapshots without
   modifying them. It is partial progress, not a correctness score.
5. Run `collect JOB_ID --destination output/NEW_REMOTE_RESULTS`. Interrupted
   uploads/downloads resume at a verified offset on the next invocation. The
   same destination can be reused; matching evidence is skipped, different
   existing files are refused. Use `--generation N` to fetch an older snapshot.
6. For a stopped `failed`/`needs_attention` job, inspect the native diagnostics
   and ownership first, then use `resume JOB_ID --generation N --reason ...`.
   This is a recorded native resume, not a new sampling attempt or a new profile.

## Evidence, resources and recovery

Node layout:

```text
state/
  queue.sqlite3                    durable requests/state and append-only events
  releases/<content-sha>/           frozen workspace + node runtime bindings
  jobs/<job-id>/
    node.json                      frozen node config (paths/references, no keys)
    owner.lock, process-owner.json  live ownership evidence
    output/                        original native benchmark results
    logs/, evidence/               generation-specific pipeline/config/health evidence
    snapshots/<generation>/        immutable copies; never hardlinks to mutable output
    artifacts-<generation>.json    path/size/SHA-256 inventory
```

`collect` creates `DEST/JOB_ID/generation-N/`, with original bytes plus
`transport-manifest.json` and `collection-receipt.json`. It does **not** import
results into an existing local sweep or rewrite absolute paths in completion or
validity records. For read-only analysis, use
`remote_execution.client.resolve_evidence_path(mirror, recorded_path)` to map a
remote evidence reference to the verified local copy. Native resume/repair and
write-oriented validity commands must operate on the authoritative node output,
not on this mirror. Cross-node/manual validity editing is not an RPC in v1.

Networking stays inside the existing benchmark runner. A completed execution
collects its evidence and tears down its own containers/networks **before** the
outer job snapshot or controller transfer. Therefore a lost controller does
not keep a completed task's Docker network occupied. During a capacity pause,
the same native registry/ownership recovery rules apply as for a local sweep.
Uncollected crash survivors are preserved and reported; operators must collect
evidence and authorize appropriate cleanup/invalidation before proceeding.

Node disk usage still needs monitoring: immutable snapshots duplicate output
once per explicit job generation. There is no automatic deletion/retention,
global janitor or unbounded automatic execution retry. Downloading a snapshot
does not delete the remote copy. Disk exhaustion or snapshot failure becomes
`needs_attention`, not a silent successful collection. Nonregular files are
listed as exclusions; no symlinks or device files are followed into secrets.

The v1 control API is for a small trusted research deployment over SSH, not a
multi-tenant public service. There is no arbitrary shell-command endpoint,
automatic hardware provisioning, public TLS termination, GPU scheduler, live
migration or direct-API-only campaign adapter. Add future tools to the existing
agent tool registry and optionally name their supervised services here;
installing a service alone never grants the agent access to it.

## Tests and remaining validation

```bash
PYTHONPATH=source:tests uv run --no-sync --offline python -B -m unittest \
  test_remote_execution test_self_hosted_model -v
```

These tests use temporary directories and loopback random ports, including real
detached **simulation** processes and a synthetic model behind the existing
gateway. No Docker container, model API, production solver or service is started
or modified. Probe jobs require explicit `allow_probe: true` and emit
`not_a_benchmark_result: true`; keep them disabled on production nodes.

Before a real remote sweep, validate SSH, driver/GPU compatibility, pinned
runtime/image locks, model parsing/tool support, shared solver health, native
network cleanup and complete evidence with a small separately identified
canary for each selected harness. CPU-only tests cannot certify those physical
deployment properties or hardware-equivalent inference performance.
