# Execution nodes (opt-in, protocol v1)

Run benchmark cells on either this machine or a remote GPU machine, using the
same `agent_formalizer` runner, adapters, gateways, timers, solver and VAL, or
the existing standalone API-only formalizer. The
controller sends frozen code/data/configuration and receives evidence. Model
weights and GPU inference stay on the execution node.

The control/transport layer uses only the Python standard library; the benchmark bridges use
the project's existing **uv** environment. No new dependencies or default
benchmark/operational profile changes are required. The original local CLI path
does not import this component and remains available.

## Boundaries and guarantees

- **One job owns one fixed comparison cell**: one harness (including `minimum`),
  model/complete profile, domain/dataset and explicit fixed indices, or an
  `api_cell` with its explicit standalone model/evaluation settings. The controller decides
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
| `api.py` | Reuse the standalone API formalizer; immutable generation records, first-valid resume and separate solver/VAL generations |
| `client.py`, `__main__.py` | Controller API/CLI, resumable transfer, verified read-only mirrors |
| `checkpoints.py` | Per-terminal-execution sealing, durable receipts, explicit node-loss recovery |
| `deploy.py` | Read-only update plans, isolated code/uv preparation and explicit deployment checks; no automatic service activation |
| `vllm.py`, `deploy/` | GPU-agnostic BF16/FP8 model-service recipe and supervision templates |

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
4. The default regression suite makes no real model/public solver/running local
   solver calls. Real GCC and systemd parser checks use temporary files. Native
   Docker smoke tests require a separate explicit opt-in; never run them against
   existing case identities. GPU/real-model canaries wait for explicit approval.
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
3. Install the locked harness versions/commits and a compatible **per-problem
   agent container** image. New execution-node releases explicitly select
   `source/agent_formalizer/runtime/runtime_lock_text_v1.json`; see the contract
   below. Solver/model service checks are separate and are not relaxed.
   Provision OpenClaw and Node at the paths required by the current runtime
   lock (`/usr/lib/node_modules/openclaw`, `/usr/bin/node`). Bind the node-local
   harness cache into release workspaces. Local runs and historical frozen
   releases retain their original byte-strict policy. Images are provisioned
   once, not sent per task.
4. Build VAL from the official [KCL-Planning/VAL](https://github.com/KCL-Planning/VAL)
   repository, pinning the source revision and recording the executable hash.
   Follow its Linux build instructions (`scripts/linux/build_linux64.sh`) and
   retain the expected `build/linux64/Release/bin/Validate` tree. The `val`
   binding below points to the **VAL project root**, not just the binary.
   For the Hyperstack layout this can be
   `/home/ubuntu/agentic-formlizer/VAL`; `/opt` is not required.
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
Internet. API-only and `minimum` run in host subprocesses on the execution node;
select an origin resolvable from that host (`http://127.0.0.1:8000/v1` for a
host-local service, or an appropriate private interface address). Do not assume
the Docker-only `host.docker.internal` alias resolves in those subprocesses.

## Updating an existing execution node

Use `python -m remote_execution.deploy` **on the execution node**, either in an
SSH session or invoked over SSH from Contabo. It is a repository-maintained
deployment tool, not a campaign script. Run it from the proposed new checkout
(or a received release workspace), using Python 3.12; its planning/preparation
code needs only the standard library and an installed `uv` supporting `sync
--check`. Do not run `uv run` without `--no-sync` just to invoke this tool: that
could update the installation you meant to preserve.

### When to use it

| Change | Required action |
| --- | --- |
| Only task data, complete profiles, prompts or ordinary benchmark Python code; dependencies unchanged | Usually package/upload a new campaign release. The job already runs release-local code; no worker reinstall is required. A deployment plan is an optional compatibility check. |
| `remote_execution` worker/queue/transport/checkpoint implementation or protocol | Prepare/check a new worker installation, review old/new protocol compatibility, then explicitly activate it during a maintenance window. |
| `pyproject.toml` / `uv.lock` | Run the tool. A lockfile in an uploaded archive does **not** install dependencies. Reuse an actually compatible environment, otherwise prepare an isolated one. |
| Pinned harness, agent Dockerfile, native timing source/overlay | Run checks before new cases. Provision the mismatched component separately; do not regenerate a lock from whatever happens to be installed. |
| Solver/VAL/model-server code, model revision or inference settings | Review and explicitly update that service separately, then check its declared health/limits. This tool never restarts or changes shared services. |
| README-only or unrelated source change | No remote environment update is normally necessary. |

Keep the existing live worker source checkout untouched; obtain the candidate
code in a **separate** checkout/directory. Do not `git pull` beneath an active
worker, run `uv sync` in its shared environment, or reinstall its harness cache.
The optional `--installed-source` reports per-component **source differences**,
not proof that the installed environment matches. No Git branch/commit equality
is required; the actual selected files are hashed with the release packager's
existing rules.

### Plan → prepare → check → explicit activation

Example Hyperstack paths below are illustrative; use the **existing node's**
real config/state paths and service name. Run as the account that owns its queue
and Docker resources, not as root. The destination is a new, dedicated directory
on the persistent volume, **outside** node state and results. The script refuses
to adopt an unrelated existing directory. It does not initialize a brand-new
node's queue; complete initial provisioning first.

1. Run a read-only plan; this is allowed while the worker is running:

```bash
PYTHONPATH=source python3 -B -m remote_execution.deploy plan \
  --source /home/ubuntu/agentic-formlizer/candidate-checkout \
  --config /home/ubuntu/agentic-formlizer/formalizer-state/node.json \
  --destination /home/ubuntu/agentic-formlizer/formalizer-deployments \
  --installed-source /home/ubuntu/agentic-formlizer/formalizer-node
```

The JSON contains `plan_sha256`, environment reuse/preparation, component
fingerprints and queued/running job states. Default checks cover all five native
harnesses, API-only, minimum and all configured services. Narrow an intended
installation with repeated `--harness` and `--service` arguments, for example
`--harness openclaw --service solver`. API/minimum checks are host import checks,
not native Docker validation or validation of every possible n/profile/model.

2. Stop submissions, let jobs finish, synchronize their evidence, then stop the
**control worker service only** using its actual service name. This is an
operator step, not performed by the script. `KillMode=process` deliberately lets
detached jobs survive, so a stopped service is not proof of an idle node.
`apply`/`check` acquire the existing `worker.lock`, hold per-job owner locks,
check surviving process groups, and refuse queued/launching/running/
`needs_attention` jobs. Resolve uncertain work using normal evidence/recovery
procedures, never by editing queue state to pass deployment checks. The guard
covers this node's queue, not unrelated campaigns sharing the same machine.

3. Apply the reviewed plan, with the same options and the printed SHA:

```bash
PYTHONPATH=source python3 -B -m remote_execution.deploy apply \
  --source /home/ubuntu/agentic-formlizer/candidate-checkout \
  --config /home/ubuntu/agentic-formlizer/formalizer-state/node.json \
  --destination /home/ubuntu/agentic-formlizer/formalizer-deployments \
  --expect-plan PLAN_SHA256
```

This packages only `source`, `pyproject.toml`, `uv.lock` and `README.md`; campaign
inputs/data are still sent with campaign releases, not the worker deployment.
It uses create-only releases and writes:

- `releases/<source-sha>/workspace/`: pinned candidate worker/benchmark code;
- `environments/<dependency-sha>/venv/`: only when the current Python environment
  fails an offline, non-mutating locked compatibility check; reused across code
  revisions with the same dependency inputs. No CUDA extras or weights are installed;
- `prepared/<plan-sha>/request.json`, `original-node.json`, `node.json`,
  `worker.service`: original configuration snapshot and candidate configuration/
  unit, not replacements for live files.

An existing compatible environment is never synchronized. A previously prepared
environment that has drifted is rejected, not repaired in place. Interrupted
new-environment installation may be retried before its ready marker is written.
Failed/partial artifacts are retained for inspection; there is no automatic
prune or deletion. Repeating a successful preparation is idempotent. New source,
config or dependency compatibility changes require reviewing a new plan SHA.

4. Verify the returned `prepared` path:

```bash
PYTHONPATH=source python3 -B -m remote_execution.deploy check \
  --prepared /home/ubuntu/agentic-formlizer/formalizer-deployments/prepared/PLAN_SHA256
```

This runs **the staged code with the staged/selected Python**, verifies frozen
files and dependencies, checks selected `remote-text-v1` harness closures and
the actual agent image, checks the matching ZeroClaw checkpoint overlay when
selected, probes each selected supervised service, and checks that the expected
VAL executable exists. It also runs the host's **real `systemd-analyze verify`**
against the generated unit, and calls the actual `deadline_integration.prepare`
for each selected native harness in a fresh temporary build/state directory.
This recompiles `timeout_deadline.c` with the production GCC flags even if old
`.so` caches exist, validates/builds the native overlays, starts/closes the
preparation brokers, and retains their source/binary hashes in the check report.
Installed harnesses/ZeroClaw overlays are read, not rebuilt or overwritten.
The isolated preparation uses a dummy OpenAI-compatible route and no real key;
it does not attest a future job's model route or change an experiment's profile.
It writes a new `checks/<time>.json` on every invocation.
Runtime diagnostics are separate from service errors. Nonzero exit means the
candidate must not be activated. The bounded Docker capability probes are not
agent executions; no inference request or planning solve is made.

Read the individual `stages`, not just the top-level `status`:

| Stage | What `check` establishes |
| --- | --- |
| `deployment_preflight` | Aggregate of the selected prerequisites, not production readiness |
| `unit_parsing` | Real host parser accepts the **candidate** unit; no installation or start |
| `native_timing_preparation` | Fresh C build and actual native preparation for the selected harnesses |
| `service_activation` | `not_verified`; operator-managed activation is separate |
| `native_startup_acceptance` | `not_verified`; run the opt-in zero-model smoke below |
| `real_model_canary` | `not_verified`; submit a new experiment release separately |

Missing verification tools (`gcc` or `systemd-analyze`) report `not_verified`,
never `pass`; this also makes required preflight/check exit nonzero. Selecting
only API/minimum leaves native timing `not_verified` without making their host
import preflight fail. A compile error is `fail` with local build diagnostics.
Neither imports nor timing preparation imply that a full native agent ran.

If a harness/image/overlay fails, use the existing pinned installer/builders in
an explicitly provisioned **new** runtime location, then create a new candidate
node config/plan pointing to it; do not overwrite a runtime still needed by an
old study. For ZeroClaw see the overlay instructions in
[the formalizer README](../agent_formalizer/README.md). This first version
automates worker code and Python environment preparation, **not** full machine
provisioning, automatic harness installation, image rebuilding, or GPU setup.
Service checks do not independently attest model weights or VAL semantics.
After deployment checks pass, run an explicit, separately authorized small
real-model/solver/VAL canary with fresh job IDs before a formal sweep.

5. Review and retain the previous systemd unit/config. Explicitly install the
candidate `worker.service` as the **existing** control-service unit and start
that unit; never start a second worker against the same queue/port. The generated
unit uses the invoking account, pinned source/Python/config paths, loopback port
8876 and `KillMode=process`. `WorkingDirectory` is an **unquoted path directive**;
`Environment`/`ExecStart` use quoted words, with literal `%` escaped as `%%`.
Absolute paths with internal spaces and Unicode are supported. Control characters
(including DEL), double quotes, backslashes and leading/trailing whitespace are
rejected. `ExecStart=:` still disables environment expansion. This is not a
generic JSON-to-systemd quoting mechanism.

Preserve the existing unit name and its `.service.d/` directory: site-specific
`RequiresMountsFor`, volume UUID/`ExecStartPre` checks, private-ingress/listener
overrides and resource supervision are **not** disposable generated defaults.
Review the composed unit with `systemctl cat EXISTING.service`, verify the
installed candidate plus retained drop-ins using
`systemd-analyze verify --man=no --generators=no /etc/systemd/system/EXISTING.service`,
and then explicitly `daemon-reload`/start that same service. The candidate-only
parser check does not attest site drop-ins. Adjust/review site-specific supervision before
installation. The script never invokes `sudo`, installs a unit, or starts,
stops or restarts a service. Check the control endpoint and perform the canary.

### Deployment regression and Hyperstack re-acceptance

Run the following from the candidate checkout using its compatible existing
Python 3.12 environment (no dependency sync). They use temporary files/queues and
local test sockets, and do **not** install/start a systemd service or call models:

```bash
PYTHONPATH=source:tests .venv/bin/python -B -m unittest \
  test_remote_deploy test_runtime_text_lock test_remote_execution \
  test_remote_api test_remote_checkpoints test_remote_vllm test_logical_deadlines
```

`SystemdUnitTests` invokes the real parser on ordinary and space/Unicode/percent
paths, and requires rejection of the old quoted `WorkingDirectory`. The native
C tests compile from scratch with the original strict flags and additionally
with `_FORTIFY_SOURCE=2`; the latter **also compiles a temporary copy with the
old faulty statement and requires an `unused-result` failure**. They exercise
failure notification, missing connections, EOF and nonresponsive peers: one
best-effort notice, bounded wait, and exit 125. The production helper retains
its original socket limits, native timer semantics and `-Werror`.

After `plan/apply/check`, separately opt in to actual native startup, using the
**prepared workspace's source and selected Python**, and this checkout's tests.
Replace these illustrative absolute paths with the paths returned by `apply`:

```bash
PYTHONPATH=/absolute/prepared/workspace/source:/absolute/candidate-checkout/tests \
RUN_NATIVE_STARTUP_SMOKE=1 \
/absolute/selected-venv/bin/python -B -m unittest \
  test_logical_deadlines_docker.NativeStartupSmokeTests
```

This sequentially exercises all five harnesses' `AgentWorkspace.start()`, actual
native CLI/import entry points, GNU timeout/exit, and owned Docker cleanup, with
fresh isolated timing builds. Any accidental model request is routed to a local
fake server and fails the zero-request assertion. It is **not** a full task or
real-model canary. No existing case/container/network is targeted. Docker/native
runtimes are required; without the opt-in the tests are explicitly skipped,
which is not acceptance. Retain the test log outside historical results.

For this compatibility fix, the Hyperstack acceptance sequence is:

1. Obtain the new code in a separate checkout; do not edit an active deployment.
   Run the default tests on its GCC 13.3/systemd 255 host. Contabo's GCC 12.2 /
   systemd 252 result cannot substitute for this cross-environment check.
2. Follow `plan → idle node → apply → check` above, then the native smoke command.
   Required preflight, all five timing checks and smoke results must pass.
3. Verify the pinned vLLM CLI using `check-cli` below, retaining the existing
   image/model/dtype/budgets. A parser pass is not GPU engine acceptance.
4. Explicitly activate the candidate **same** worker service while retaining
   site drop-ins, mount checks and private ingress. Check its health.
5. On Contabo, package/upload a **new experiment release containing the C fix**,
   keeping the reviewed model/profile/operational settings and new job IDs.
   Follow [controller workflow](#controller-workflow) to submit a small native
   canary (then collect its traces, PDDL, solver and VAL evidence). Review before
   any formal sweep. An old minimum 600-second timeout remains a separate issue.

The worker deployment release and experiment release are different objects.
Updating the worker alone does **not** replace `timeout_deadline.c` in an old
job's frozen release. Never patch that old release or rewrite its identity;
new source naturally gets a new release and derived timing bundle identity.

### Old jobs, rollback and retention

Existing releases, results, original `node.json`, runtime bindings, secrets,
solver/VAL and vLLM are never rewritten. If `old_job_config_compatible` is false
(for example a new Python path), new jobs may use the candidate, but resuming an
old job under the changed node config will deliberately fail the existing drift
guard. To resume old work, restore its original worker unit/config and retained
environment during an idle maintenance window; never rewrite its saved config
or release. Retain previous code/environments until no historical job needs them.
Even when the config is unchanged, protocol/checkpoint-format compatibility of a
new worker with an old queue requires review; a successful deployment probe is
not a blanket compatibility guarantee.

These managed directories/records are node-local operational artifacts, not
source-controlled files. The reusable script, tests and these instructions
belong in Git. Neither preparing nor checking a deployment modifies the local
benchmark CLI, canonical baseline, or a frozen Contabo sweep.

## Remote agent-runtime comparability (`remote-text-v1`)

This is an explicit, versioned **remote-only default**, approved on 2026-09-15.
`benchmark.py` passes the release-local `runtime_lock_text_v1.json` through the
pipeline's `runtime_lock_path` to the formalizer's `--runtime-lock` option.
Ordinary local CLI calls omit that option and still select the original
`runtime_lock.json`; neither that file nor the canonical benchmark profile was
changed. There is no environment-variable fallback or automatic lock rewriting.
API-only retains its existing host implementation; minimum is also host-only
and does not require the Docker capability probe.

The exact finite set of required checks is the new lock file's `harnesses`,
`provider_transports` and `container` sections. Empty/missing/unknown checks fail:

| Scope | Required match |
| --- | --- |
| Hermes / Nanobot | Exact distribution/version; CPython 3.12 family; sorted installed dependency name/version manifest; actual package/data text manifest; native assets |
| OpenClaw | Exact release/build version; Node 22 family; installed npm name/version manifest; entrypoint/package.json/dist text manifest; native assets |
| GenericAgent | Exact commit, no tracked working-tree changes; CPython 3.12 family; installed dependency name/version manifest; native assets |
| ZeroClaw | Exact `0.8.2` and PR #8935 commit `85e0cfafbe677590e4fe5947f83673bb49ba0fc2`; no tracked working-tree changes; Cargo.lock text; native assets |
| Minimum | Existing benchmark-owned runtime source identity and native-assets declaration |
| Logits, only when selected | CPython 3.12 family, dependency versions, bridge/gateway source and tokenizer assets |
| Per-problem agent image | Repository Dockerfile text and an actual Linux/CPython 3.12 capability probe with sh, bash, python3, git, curl, timeout, grep, sed, awk, find, head, tail |

"Text manifest" means SHA-256 over relative filenames and unmodified UTF-8
source/resource contents, sorted deterministically. It is not AST equivalence
or removal of whitespace, prompts or paths inside application code. Installed
Python package roots and wheel data (including Hermes locales) are scanned;
missing declared text and added source files cannot silently disappear from
the check. `.dist-info/RECORD`, installer metadata, generated bytecode and the
unused pip/uv `bin` launchers are not compared. These adapters import their CLI
using the selected Python rather than executing those path-bearing launchers.
Plugin entry-point declarations remain checked. Source/resource suffixes are
explicitly listed in `runtime_lock.py`; binary files are not reinterpreted as text.

Interpreter patch/build differences, ELF hashes and agent image IDs are
**observed, not compared across machines**. The image probe runs once per batch
preflight, before agent timing, with `--pull never`, no network, read-only root,
128 MiB/1 CPU/64 PIDs and a 30-second bound; its unique container is removed on
completion or timeout. It does not replace a problem container or change that
container's frozen resource/network/timing settings. The mounted harness
runtime is checked separately. Missing executables/ABI or overlay errors still
fail at their existing runtime/configuration checks.

This establishes an operational comparability contract, not proof of universal
behavioral equivalence or equal speed. It deliberately does not enforce every
OS package version, interpreter build flag or dependency binary hash. Fixed
source/versions alone cannot attest how an arbitrary binary was compiled:
install from the pinned source/recipe and preserve build provenance. Existing
checks that protect release/archive transfer, selected timing-overlay artifacts
and result files remain byte-strict. Solver/VAL, model-service configuration,
precision, prompts, budgets and isolation are unchanged.

Each execution retains the full observed artifact hashes and selected checks.
Only the comparison projection plus adapter implementation identity enter the
new runtime identity; image/build/install-location differences no longer poison
resume. Configuration evidence records the selected lock path/hash/ID/policy.
Old releases/jobs/completions are not migrated or silently accepted under this
rule. Build a **new release/job** to use it; existing local campaigns keep their
frozen code, images, services and policy.

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

### Configurable vLLM deployment (single or multiple NVIDIA GPUs)

Use [deploy/vllm.example.json](deploy/vllm.example.json) as a **deployment
example**, not a benchmark baseline. Two L40 On-Demand GPUs are one possible
starting host; neither GPU model nor count is hardcoded. The model service is
shared by agent workers, not replicated once per case. The launch helper runs
the pinned vLLM container and leaves the existing uv environment unchanged.

Before use, copy the example to `/srv/formalizer-node/vllm.json` on the **new
execution node** and replace every placeholder. Pin the image's registry digest,
exact vLLM version, Hugging Face model/tokenizer commit and actual template hash.
Download that revision directly on the GPU node into `model_path` (for example,
with `hf download REPOSITORY --revision FULL_COMMIT --local-dir MODEL_DIRECTORY`
using a separately provisioned downloader). Weights and tokenizer must be in
the same local snapshot, with a regular `chat_template.jinja`. Do not mount an
HF snapshot whose weight symlinks resolve outside the mounted directory. Pull
the pinned engine image once; service starts use `--pull never` and offline HF
mode. No model weights pass through Contabo or a per-job release archive.

The placeholder template intentionally fails validation until pins are filled.
Its 32K context and four sequence slots are **illustrative deployment choices**,
not a guarantee that all benchmark requests fit or that every GPU has sufficient
memory. Select and canary these settings before freezing an experiment. They
are not copied into the canonical benchmark profile or silently reduced on OOM.

Supported configuration includes:

- Explicit GPU indices/UUIDs and `tensor_parallel_size * pipeline_parallel_size
  == number of selected GPUs`. TP1/PP1 works for one card; TP2/PP1, TP1/PP2,
  TP4/PP1 or other valid splits are explicit alternatives. Inspect topology and
  verify the pinned model implementation supports the chosen split. No NVLink
  or homogeneous GPU model is assumed; successful distributed startup still
  requires compatible drivers, kernels and peer communication.
- BF16 is the example's default: `precision: "bf16"`, no quantization flag.
  FP8 is explicit: set `precision: "fp8"` plus `fp8_mode: "checkpoint"` for a
  native FP8 checkpoint, or `"online"` to explicitly request vLLM's runtime FP8
  conversion of BF16 weights. Checkpoint and online FP8 are distinct conditions.
  Current scope excludes INT8/INT4/AWQ/GPTQ/NVFP4 and mixed lower-bit checkpoints.
  Activations use `bfloat16` where the engine is not applying its FP8 kernels;
  KV-cache uses `auto` with BF16 dtype, **not implicit FP8 KV quantization**.
- GPU memory utilization, maximum model length, maximum concurrent sequences,
  private bind address, shared memory size, tool/reasoning parsers and generation
  defaults are explicit. Prefix caching is explicitly off in the example to
  avoid cross-case cache timing effects; changing it needs an experiment decision.
  No speculative/draft model is enabled. Preserve native harness prompts/tools.

The helper checks BF16 native compute capability >= 8.0, and FP8 >= 8.9; this is
a coarse hardware gate, not proof of support for every model/kernel combination.
It records actual GPU names, UUIDs, memory, driver, topology, Docker image ID and
deployment hash at startup. Model revision is operator-attested from the pinned
download; this is not a full weight-content attestation. Hardware or engine
failure never triggers a hidden BF16-to-FP8 switch or a smaller context.

References: [vLLM multi-GPU guidance](https://docs.vllm.ai/en/stable/serving/parallelism_scaling/),
[FP8 implementation](https://github.com/vllm-project/vllm/blob/main/docs/features/quantization/llm_compressor/fp8.md),
[Qwen3.8 recipe](https://recipes.vllm.ai/Qwen/Qwen3.8-27B).
The example uses `qwen3` reasoning and `qwen3_coder` tool parsing from that recipe;
these are model-specific selectable settings, not generic defaults for other models.

Provision `/srv/formalizer-node/private/vllm.env` as an owner-only file containing
**only** `VLLM_API_KEY=<32+ URL-safe random characters>`. Put the same value under
`SELF_HOSTED_API_KEY` in the separate benchmark runner secret file. Do not put
keys in JSON, shell argv, images or release archives. Configure the runner's
`SELF_HOSTED_BASE_URL` to reach the model from the gateway, e.g.
`http://host.docker.internal:8000/v1` when that resolves to the configured private
bind address. Verify the actual host interface: `172.17.0.1` is an example,
not a promise about the node's Docker topology. Keep the port firewalled from
the Internet; vLLM authentication does not cover every non-API endpoint.

Commands below are **on the GPU node**:

```bash
PYTHONPATH=source uv run --no-sync --offline python -B -m remote_execution.vllm plan --config /srv/formalizer-node/vllm.json
PYTHONPATH=source uv run --no-sync --offline python -B -m remote_execution.vllm check-cli --config /srv/formalizer-node/vllm.json
PYTHONPATH=source uv run --no-sync --offline python -B -m remote_execution.vllm inspect --config /srv/formalizer-node/vllm.json
PYTHONPATH=source uv run --no-sync --offline python -B -m remote_execution.vllm service --config /srv/formalizer-node/vllm.json
```

`plan` is pure configuration validation and prints secret-free argv. `check-cli`
uses a bounded, uniquely owned container from the pinned image to run its actual
`ServeSubcommand` parser on the **entire generated serve argv**, and verifies the
installed vLLM version. It has no GPU access, model mount, secrets or network;
it never dispatches the engine. It cleans only its own container, including on
failure/timeout. Its parser compatibility is required by CLI `inspect` and before
`run`; unavailable/failed checks prevent startup, not a silent flag fallback.
The GPU-less parser process selects vLLM's CPU platform for constructing parser
defaults when no platform is detected; this never changes the GPU server argv.
CPU-only parser/import checks may themselves reveal image incompatibilities;
they do not attest CUDA kernels, model loading or inference.

For `server_version: "0.29.0"`, command generation disables request logging with
`--no-enable-log-requests`, matching the
[v0.29.0 CLI](https://docs.vllm.ai/en/v0.29.0/cli/serve/#--enable-log-requests).
Other versions keep the legacy `--disable-log-requests` default. Where needed,
explicitly set optional `request_log_flag` to either spelling in the deployment
JSON; both mean logging disabled. The pinned image's real parser must accept it.
This selects spelling only, never upgrades the image or changes inference.

`inspect` also performs read-only local hardware/image/model-config checks.
`service` emits the
`node.json` `services.model` entry from this same config, including precision,
parallelism, model identity and deployment hash; avoid separately hand-maintained
copies. Install/adapt [benchmark-vllm.service](deploy/benchmark-vllm.service),
then start it explicitly. If renaming `container_name`, update both the unit name
and its exact `ExecStop` target. An existing same-name container is not forcibly
deleted by the launcher; inspect ownership if it prevents restart. vLLM startup
logs are available in the service journal; per-start GPU evidence is retained
under `model-launches`. Retain both for deployment audit.

Keep a distinct served ID/profile/study for BF16 versus FP8, even when the base
model is the same. No change is made to the canonical Gemini/local baseline.
Freeze engine/model/precision/parallelism/parser settings before the real sweep;
canary tool calls, readable thinking, usage, long-context requests and concurrent
inference for **each selected harness** before claiming deployment compatibility.

To repeat provisioning, reuse pinned container images, downloaded snapshot cache
and these small config/unit files (or automate them with cloud-init). Never bake
credentials, node identities, old job queues, leases or agent memory into images.
No GPU driver installation, cloud account operations or remote service startup
is performed by editing or testing this repository.

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
   `.local/campaign-inputs/gpu-study/` (Git-ignored). These are per-study frozen
   inputs, not reusable source or another benchmark baseline: retain them with
   the study's release archive/provenance for reproducibility, but do not commit
   them. Never repurpose an old output as the input tree. Keep real secrets in
   `_private/`, not here. This dedicated directory can be explicitly packaged;
   `.cache/` and `output/` remain excluded from release inputs.
   For this example, set the operational credential registry path to
   `.local/campaign-inputs/gpu-study/credentials.json`.

   Moving controller-side staging files does not relocate files inside an
   already submitted release. Preserve old archives, job specifications and
   their release-relative paths/hashes; only new releases use the new layout.
2. Package selected trees. Include golden inputs too: evaluation stays remote.

```bash
PYTHONPATH=source uv run --no-sync --offline python -B -m remote_execution bundle \
  --root . --include source --include pyproject.toml --include uv.lock \
  --include .local/campaign-inputs/gpu-study \
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
  --indices 1,2,3 --profile .local/campaign-inputs/gpu-study/profile.json \
  --operational .local/campaign-inputs/gpu-study/operational.json \
  --service solver --service model --destination output/NEW_REMOTE_JOB.json
```

4. With the same endpoint/token options, run `submit --job ...`,
   `status JOB_ID`, `progress JOB_ID`, or `events JOB_ID --after SEQUENCE`.
   Upload, submit and status calls are independent; no long-lived controller
   session is required. `progress` reads native validity snapshots without
   modifying them. It is partial progress, not a correctness score.
5. While the job runs, use `sync JOB_ID --destination output/NEW_REMOTE_RESULTS
   --follow --interval 5` under a controller supervisor (see below). It saves
   terminal executions without waiting for other cases or evaluation. After
   pipeline completion it also collects the final full-generation snapshot.
   Alternatively run `collect JOB_ID --destination output/NEW_REMOTE_RESULTS`. Interrupted
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
    checkpoints/<content-sha>/     immutable per-execution evidence + manifest
    checkpoint-index.json          atomic catalog of available checkpoints
    checkpoint-acks/               idempotent controller receipt acknowledgements
    checkpoint-status.json         latest sealing health (not agent validity)
```

`collect` creates `DEST/JOB_ID/generation-N/`, with original bytes plus
`transport-manifest.json` and `collection-receipt.json`. It does **not** import
results into an existing local sweep or rewrite absolute paths in completion or
validity records. For read-only analysis, use
`remote_execution.client.resolve_evidence_path(mirror, recorded_path)` to map a
remote evidence reference to the verified local copy. Native resume/repair and
write-oriented validity commands must operate on the authoritative node output,
not on this mirror. Cross-node/manual validity editing is not an RPC in v1.

### Incremental results and node-loss recovery

The detached owner polls for native `execution_result.json` / `infra_invalid.json`
every two seconds (`node.checkpoint_interval_seconds`, configurable 1–60). These
markers are written after native collection and cleanup. It copies each terminal
execution's entire regular-file tree plus its execution-specific infra diagnostics
and available frozen job/config/service evidence. It does **not** copy a live
execution, process lease, mutable cell view, or another case's live session DB.
Invalid and valid-but-wrong executions are preserved equally. Append-only manual
adjudication ledgers are captured as separate versioned snapshots under the
native cell lock; materialized validity is rebuilt on recovery.

Contabo's `sync` verifies SHA-256 and fsyncs the files/directories before writing
a durable receipt and sending its idempotent ACK. Lost ACKs only repeat ACKs;
interrupted file downloads resume, never trigger another model call. Existing
different evidence is refused, not overwritten. `progress` reports sealed and
acknowledged checkpoint counts independently of agent success. The owner records
sealing errors in `checkpoint-status.json` and retries the same evidence without
changing agent validity. Monitor both owner sealing health and controller sync
service: a terminal pipeline status alone does not prove off-node durability.

Run this **on Contabo**, with an independently supervised SSH tunnel:

```bash
PYTHONPATH=source uv run --no-sync --offline python -B -m remote_execution \
  --endpoint http://127.0.0.1:18876 --token-file /path/to/private/control-token \
  sync JOB_ID --destination output/NEW_REMOTE_RESULTS --follow --interval 5
```

For terminal/Codex independence, adapt and enable
[benchmark-result-sync@.service](deploy/benchmark-result-sync@.service) for the
job instead of relying on an interactive terminal. `--follow` reconnects after
transport failures, stops on `needs_attention` without guessing ownership, and
collects the final snapshot on `completed`/`failed`. Installing a unit template
does not automatically supervise the SSH tunnel. The controller needs disk
capacity; there is no promise of surviving loss of the controller disk itself.

**Durability boundary:** only a complete, verified controller receipt is a
guarantee of off-node preservation. A just-completed execution within the polling,
copy or transfer window can still be lost. As approved, unsynchronized executions
may be discarded and rerun after confirmed node loss. There is no fsync/ACK barrier
in the agent loop and no pause of other agents waiting for Contabo. Thus during a
long network outage the unsynchronized backlog is NOT bounded by worker count.

Agent generation is checkpointed independently of evaluation. Solver/VAL results
are retained in the final full-generation collection; if the node disappears
before that, recovery reruns evaluation on the preserved PDDL, not the agent.
No completed wrong answer is resampled. The original native terminal JSON bytes
are preserved; incremental recovery can use `execution_result.json` without
manufacturing or rewriting the compatibility `completion.json`.

If the **old VM is actually terminated/fenced** (not merely unreachable):

1. On Contabo, export only fully collected checkpoints. Partial download files
   and unconfirmed executions are excluded automatically. If no executions have
   arrived yet, the recorded job origin still permits an empty recovery bundle
   that will rerun all slots with the same frozen request:

```bash
PYTHONPATH=source uv run --no-sync --offline python -B -m remote_execution \
  recovery-bundle --mirror output/NEW_REMOTE_RESULTS/JOB_ID \
  --archive output/NEW_RECOVERY.tar.gz
```

2. Provision the replacement VM with the same paths, frozen release, runtime
   locks, images, model/solver configuration and dependencies. Keep
   `state_dir`, job ID, and all absolute output paths identical so original
   evidence references remain valid without rewriting. A different `node_id`
   and rotated control token are allowed. Upload/install the original release
   with the ordinary upload command. Transfer the recovery archive using SSH;
   it contains result evidence, not model weights. Stop the replacement worker
   before the offline import; it must have an empty queue and no old job owners.

```bash
PYTHONPATH=source uv run --no-sync --offline python -B -m remote_execution \
  restore --config /srv/formalizer-node/node.json --archive /path/to/NEW_RECOVERY.tar.gz \
  --source-node-retired --reason "Old VM confirmed terminated; restore controller-acknowledged executions"
```

3. Start the replacement worker/tunnel/collector. The import queues a new job
   generation with the **same** frozen request and preserved execution numbers.
   Native identity/validity checks reuse valid results and run missing/invalid
   slots, followed by solver and VAL. Recovery archive hash, retirement
   attestation, reason, prior node and all checkpoint manifests remain in
   `evidence/node-loss-recovery.json`; no old lease or queue is copied. A failed
   import does not admit a partially restored job. Keep the Contabo mirror and
   original archive as authoritative recovery evidence.

This is deliberate coarse recovery, not live process migration, automatic cloud
reprovisioning or permission to race two live nodes and select better outcomes.
New deployments use this implementation; historical releases remain unchanged.

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
migration. Add future tools to the existing
agent tool registry and optionally name their supervised services here;
installing a service alone never grants the agent access to it.

## API-only and minimum-agent cells

Remote execution location and model location are independent. All five native
harnesses, minimum agents and API-only cells can run on the remote node while
calling either its vLLM service **or a supported external provider**. vLLM/GPU
installation is not required for an external-provider-only node. Provider
support still follows each existing adapter: this is not automatic compatibility
with arbitrary wire protocols (e.g. minimum does not implement direct Anthropic
Messages transport).

For external Vertex/DeepSeek/OpenAI agent cells, retain the ordinary
`google-vertex/...`, `deepseek/...`, or `openai/...` profile model, provision the
selected credentials on the execution node, and allow outbound HTTPS to that
provider. API-only uses its existing standalone model names described below.
Omit `--service model` from these job requests: the node does not require or
contact a local vLLM service unless explicitly requested. `--service solver`
is still mandatory when evaluation or a tool selects local/public_then_local;
the choice of model provider does not change the solver backend. Both provider
paths use the same release, evidence transfer, resume and evaluation mechanics.

Both paths also support self-hosted models. The model route is
`self-hosted/SERVED_MODEL_ID`; the suffix must match the server's `/v1/models`
ID, not necessarily its Hugging Face repository name. Weights are downloaded
once on the GPU node and are never included in job or result transfers.
Use the same pinned model/tokenizer revision, dtype, parser/template and
generation configuration across the comparison cells. BF16 and FP8 are
separate conditions, not transparent alternatives.

### API-only

`api-job` creates an `api_cell`, which calls the existing
`source/llm-as-formalizer-api.py::run_formalizer_gpt`, then `run_solver.py` and
`run_val.py`. It has one valid generation per problem, no model-selectable or
hosted tools, no reflection loop, and the standalone prompt and retry policy.
Agent profile time/action budgets are **not** silently applied to this distinct
baseline. Its condition is frozen by the request and release hashes; operational
worker counts and credentials use the same operational-config schema as agents.

After including `configs/node-ops.json` and its credential registry in the
release, create a request on the controller (replace `RELEASE_SHA256` with the
actual `bundle` result):

```bash
PYTHONPATH=source uv run --no-sync python -m remote_execution api-job \
  --root . --job-id qwen-api-barman-bf16 --release-id RELEASE_SHA256 \
  --model self-hosted/qwen-bf16 --domain barman \
  --dataset Heavily_Templated_Barman-100 --indices 1,2,3 \
  --operational configs/node-ops.json --solver-backend local \
  --service model --service solver --destination qwen-api-barman.job.json
```

Cloud API names remain supported, e.g. `gemini-3.1-flash-lite` or
`deepseek-v4-flash` (the standalone spelling, without the agent provider prefix).
Node credentials are explicitly selected from the release's registry; they are
not included in the job. For self-hosted cells, the registry's
`provider_options.self_hosted.base_url` and named secret configure the client.
The supervised model and local solver preflight requirements still apply.

Use the existing `upload`, `submit`, `progress`, `sync --follow`, `collect`, and
explicit `resume` commands, with no separate controller service:

```bash
PYTHONPATH=source uv run --no-sync python -m remote_execution \
  --endpoint http://127.0.0.1:18876 --token-file /PRIVATE/CONTROL-TOKEN \
  submit --job qwen-api-barman.job.json
PYTHONPATH=source uv run --no-sync python -m remote_execution \
  --endpoint http://127.0.0.1:18876 --token-file /PRIVATE/CONTROL-TOKEN \
  sync qwen-api-barman-bf16 --destination output/remote-qwen --follow
```

Generation evidence is sealed under
`output/llm-as-formalizer-api/DOMAIN/DATASET/MODEL/pNN/executions/execution-NNNNNN/`.
The directory contains original prompts, full provider responses (including
available reasoning/thinking, token usage and generated file contents), PDDL
artifacts, `api_request.json`, and `execution_result.json` or `infra_invalid.json`.
A malformed or empty delivered assistant response is a valid failed generation:
resume does not draw a replacement answer. Exhausted provider transients or
unknown runner/protocol failures (including a missing assistant message) retain
an invalid execution; a subsequent explicit job
resume fills the missing valid slot. Interrupted, uncommitted executions are
not advertised as completed checkpoints. Input/identity mismatch or evidence
corruption stops recovery rather than triggering another sample.

Terminal API executions use the same periodic sealing, incremental transfer,
durable receipt/ACK and node-loss recovery protocol as agent executions. They
can reach the controller before the rest of the cell or its evaluation finishes.
After restore, received valid outcomes are reused; unreceived work may run again.
Evaluation uses verified copies of selected PDDL in
`output/evaluation-GENERATION/llm-as-formalizer-api/...`, then the existing
solver/VAL routines with independent `solver_workers` and `val_workers` counts.
It does not alter generation records or previous evaluation generations.
`cell-summary-GENERATION.json` identifies the selected executions and current
evaluation root; the latter contains the ordinary result CSV. Evaluation is
rerunnable after node loss without recalling the model. This additional
execution management is specific to remote `api_cell`; legacy standalone CLI
resume/layout remain available unchanged.

For local-model costs, provider-measured token usage is retained when supplied.
An unknown self-hosted token price is not evidence of zero cost: compute GPU
cost separately using deployment/runtime records. No reasoning text that the
server omits can be reconstructed from token counts.

### Minimum agent, configurable n

No new runtime is needed: submit `job --harness minimum --profile ...` using a
complete, reviewed minimum profile derived from the maintained baseline. Follow
the [minimum adapter contract](../agent_formalizer/README.md#minimum-formalizer-agent-baseline)
for the explicit host-loop prompt and compatible timing settings; do not use a
historical test profile as a campaign preset or assume Docker call-checkpoint
settings automatically apply to the host loop. This change does not modify the
maintained native baseline or the minimum runtime's semantics.

In each separate derived profile select:

- `benchmark_envelope.control_model: "self-hosted/qwen-bf16"`;
- `condition_profile.overrides.minimum_agent.reflection_count: n`;
- `minimum_agent.solver_feedback.enabled: true` or `false`;
- local evaluation via `condition_profile.overrides.solver_backend: "local"`;
- no `agent_tools` and no experiment skills for this fixed-loop baseline.

Here **n means reflection rounds after the initial generation**: n=0/1/10 gives
1/2/11 logical model calls. It is not `attempts_per_case`; changing n requires a
different frozen profile and job ID. With solver feedback enabled, the harness
makes exactly n fixed solver calls, each before the corresponding reflection.
The model itself does not choose these tool calls. Keep the profile's model-call
and action guards large enough for n+1; excessive n is rejected, never truncated.
Full reasoning, complete replacement PDDL, provider usage and fixed solver
observations remain in the ordinary minimum transcript/step evidence. Minimum
cells use the existing agent-cell checkpoint and first-valid recovery path.

For initial Hyperstack acceptance, test API-only, minimum n=1 and n=10 (with
and without fixed solver feedback), and each of the five native harnesses on a
small fixed index set before a full matrix. Validate at least one delivered
pair through local solver **and VAL**, and inspect incremental receipt/restore.
These deployment tests must use separate job IDs/output, never an old campaign.

## Tests and remaining validation

```bash
PYTHONPATH=source:tests uv run --no-sync --offline python -B -m unittest \
  test_remote_execution test_remote_api test_self_hosted_model test_remote_checkpoints test_remote_vllm test_minimum_agent -v
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
