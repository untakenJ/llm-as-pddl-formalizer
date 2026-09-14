# Agent harness PDDL formalizer

This package benchmarks OpenClaw, Hermes, NanoBot, ZeroClaw, GenericAgent, and
the benchmark-owned Minimum Formalizer Agent as PDDL formalizers. The five
native harnesses run in Docker, receive the canonical workspace task prompt, and author
`domain.pddl` and `problem.pddl` in `/workspace`. The minimum baseline instead
uses a repository-owned standard-library host process, an explicit
condition-owned conversation template, and a fixed reflection loop. It has no
shell, file, plugin, memory, or model-selectable tool surface, so it does not
start an agent container. Its adapter parses the last model response and writes
the same two official files. The runner then copies official files byte-for-byte
to the existing solver/VAL-compatible layout.

## Code organization

### Execution-end process lifecycle

Agent and gateway containers use Docker `--init`. Native asynchronous tools
remain untouched while an execution is active. At completion the official PDDL
is snapshotted under container pause, the entire agent PID namespace is stopped,
and only its inert init/tail is restarted for evidence collection. Native jobs
are never resumed after this boundary. Verified owned-container/network removal
still follows collection; cleanup errors block further admission.

Host minimum/runtime services use the dedicated subreaper supervisor in
`runtime/process_lifecycle.py`, not process-wide subreaping in a threaded runner.
Detached descendants are reaped on normal exit and cancellation. VAL has a
120-second infrastructure watchdog; timeout is explicitly diagnosed, not called
PDDL unsolvability. An owner-dead managed container may be stopped while keeping
its uncollected crash evidence; unowned legacy containers are never auto-pruned.

These are lifecycle implementation changes, not changes to native tool timeout,
checkpoint recovery, prompt, model, skill, or semantic baseline configuration.

`orchestrator.py` and `workspace.py` retain the shared execution flow and
workspace lifecycle. Feature-specific implementation lives in:

- [`configs/`](configs/README.md): user-editable benchmark, operational and
  credential configurations.
- [`configuration/`](configuration/): configuration loaders, validation,
  schemas and selected skill bundles.
- [`compute_platforms/`](compute_platforms/README.md): platform integrations;
  `compute_platforms/logits/` contains the Logits protocol bridge and entrypoint.
- [`gateways/`](gateways/): shared model and controlled-web proxy services.
- [`results/`](results/): execution validity, provenance, optional evidence and
  reporting code. Experiment outputs still use the configured output location.
- [`runtime/`](runtime/): pinned environment installer, lock and requirements.
- [`docker/`](docker/): container image and shared network resource management.
- [`prompts/`](prompts/): canonical templates and task text handling.
- [`skills/`](skills/README.md): opt-in experimental skill content.
- [`timing/`](timing/): logical deadlines, call checkpoints, native integration
  and the deployable files in `timing/runtime/`.
- [`external_calls/`](external_calls/): shared recovery policies, classifiers
  and acknowledged request control.
- [`claws/`](claws/): harness adapters; `claws/minimum/` contains the Minimum
  adapter, host workspace and standalone standard-library runtime.

Host imports use these package paths. Sidecars still receive the same narrowly
selected files at their existing container paths. Source relocation changes
implementation hashes; existing frozen studies keep their recorded identities.
When the ZeroClaw timing overlay is missing or its inputs change, build it with
`PYTHONPATH=source python -m agent_formalizer.timing.zeroclaw_deadlines`
before running that timing condition. Existing matching overlays are reusable.

## Configuration model

Start with the [user configuration guide](configs/README.md). The single
maintained baseline in [`configs/benchmark_profiles/`](configs/benchmark_profiles/),
[`native_baseline_v1.json`](configs/benchmark_profiles/native_baseline_v1.json),
implements the agreed four layers:

1. `native_clean`: the pinned harness's official clean initialization or a
   version-bound equivalent;
2. `benchmark_envelope`: hard safety, isolation, artifact, evidence, and budget
   semantics;
3. `condition_profile`: a small set of controlled experiment overrides;
4. adapter translation: the auditable mapping from resolved semantics to each
   harness's native config/CLI surfaces.

Benchmark-owned fields have a strict schema. Native harness config is recorded
but is not forced into one cross-harness schema. `native_clean` is itself the
first comparative baseline: native tools, skills, prompts, memory, and inner
limits are not reduced to a shared subset. Only rules explicitly added by the
envelope/condition require cross-harness mappings. Every run records the config
name, full resolved config, SHA-256, translation ledger, task hash, runtime
closure, image identity, and validation evidence.

The default `native-safety-v5-streaming` envelope and native condition use:

- model: `google-vertex/gemini-3.1-flash-lite`;
- harness active-time deadline: 1800 seconds, excluding benchmark-owned
  provider-transient recovery pauses;
- control-model request guard: 50 logical calls; gateway physical retries do
  not consume additional slots;
- action-step guard: 200, where
  `action_steps = model_calls + tool_calls`; all three values are recorded
  separately by the common gateway;
- fixed `external-transient-v2` routing: all upstream 429 plus safe
  408/502/503/504,
  selected CDN/overload statuses, and pre-response transport faults are hidden
  and retried up to five times with `[1, 2, 4, 8, 16]` second backoff;
- network: `model_only`;
- interaction/state: noninteractive execution with per-attempt state and no
  personal or cross-attempt harness state;
- state validation: every attempt inspects its live container mounts and fails
  if any writable host bind is not exactly declared as attempt-private;
- skills/bundles: pinned official clean baseline;
- added agent tools: none; solver/VAL evaluation still uses the local solver
  with `solver-transient-v1` recovery;
- transparent recovery timing: `call-checkpoint-v1` across the five native
  harnesses;
- official-delivery-file success; final-message recovery disabled.

CLI budget changes are recorded as `experimental_budget`, rather than being
misrepresented as a harness-native default.

The default `native-safety-v5-streaming` envelope has a distinct study identity
from historical buffered v4 profiles.
It forwards the first complete semantic event immediately, uses bounded
incremental tool observers, commits tool calls only after normal completion,
allows a complete final tool batch to overshoot the action admission threshold,
and rejects the next request. Direct post-commit stream failures discard the
whole clean execution try and recover up to five times; true silence, client
cancellation, and benchmark deadlines remain valid native outcomes. It must not
be mixed with buffered v4 results.

Start each new experimental profile from this baseline, apply only the user's
requested differences, record its baseline provenance and freeze the complete
derived profile. Baseline changes themselves require explicit user approval;
see the root `AGENTS.md` and the [derivation guide](configs/benchmark_profiles/README.md).
Resume/repair keeps the study's original frozen profile, not the current default.

## Runtime closure

Build the agent image once; benchmark runs use `--pull never`:

```bash
docker build -t pddl-agent-base:latest source/agent_formalizer/docker
```

Install repository-local runtimes:

```bash
bash source/agent_formalizer/runtime/install_harnesses.sh all
```

The installer uses exact Python distribution manifests. The runtime lock also
checks the actual harness payload, bundled native assets, and locked base-image
ID. Python 3.12.13 and Node v22.23.1 executable identities are locked as part
of the relevant harness closures:

- Hermes 0.18.2 and its 60-distribution closure;
- NanoBot 0.2.2 and its 115-distribution closure;
- GenericAgent commit `e6bbc916…` and its Python closure;
- ZeroClaw 0.8.2, commit `42fa1971…`, and `Cargo.lock`;
- OpenClaw `2026.6.10 (aa69b12)`, its installed Node distribution manifest,
  runtime payload, and 83 bundled skill assets.
- Minimum Formalizer Agent's benchmark-owned, standard-library Python host
  runtime entrypoint. It has no Docker dependency, external harness
  distribution, native tools, skills, or memory.
- Logits' shared provider transport has its own locked tokenizer-only Python
  closure. Qwen3.5 tokenizer assets are revision- and hash-locked separately
  from the dynamic provider model catalog.

OpenClaw remains host-installed at the repository-defined paths, but its
personal state/config is never used. A mismatch is an infra invalidator, not an
agent failure. The image ID is resolved once per command so every case in that
command uses the same image even if a tag later changes.

## Credentials and host environment

[`configs/credential_profiles.json`](configs/credential_profiles.json) is the secret-free
credential registry. Each named profile binds one API-key variable reference to
the auxiliary provider values needed by that key. For Vertex this means the key
and project are selected as one unit. Resolution uses an exact model default
first, then a provider default; `models` on a profile constrains the model pool
in which it may be selected.

The bundled Vertex profiles are:

- `google-vertex-default`: `GOOGLE_CLOUD_API_KEY` + `GOOGLE_CLOUD_PROJECT`;
- `google-vertex-fallback`: `FALLBACK_GOOGLE_CLOUD_API_KEY` +
  `FALLBACK_GOOGLE_CLOUD_PROJECT`.

The bundled `logits-default` profile binds `LOGITS_API_KEY` to `logits/*`.
Logits model availability is read from the authenticated provider capability
response at runtime; model-family chat/tool conventions remain explicit and
audited. See the [Logits adapter guide](compute_platforms/logits/README.md).

The runner reads only those referenced values from the git-ignored
`_private/.env` (or `--secrets-env-file`); it does not load the file into the
process environment or import personal harness configuration. Explicitly named
process variables remain a CI-compatible fallback. The dotenv file is never
mounted. A selected key is staged in a per-Gateway `0600` temporary secret file,
so its plaintext does not appear in `docker run` arguments. Harness processes
and agent containers receive only placeholder credentials and cannot mount or
inspect the Gateway secret.

Example:

```bash
.venv/bin/python source/agent_formalizer/run_formalizer_agent.py \
  --claw hermes \
  --model google-vertex/gemini-3.1-flash-lite \
  --credential-profile google-vertex-fallback \
  --domain blocksworld \
  --data Heavily_Templated_BlocksWorld-100 \
  --indices 1,2,3
```

Credential profiles are operational availability configuration, not experiment
profiles. Their name, registry hash, variable references, and redacted route are
recorded as provenance, but the key, project, location, and origin in a
credential profile do not enter `resolved_config_sha256`, output labels, or
resume identity. Switching primary/fallback therefore continues the same
experiment. If a study intends region or endpoint to be an experimental
variable, model it explicitly as a condition rather than changing credentials.

`--api-key-env`, `--vertex-project`, `--vertex-project-env`, and
`--vertex-location` remain compatibility overrides; new runs should add/select
a named profile instead. A custom secret-free registry can be supplied with
`--credential-profiles-file`.

Image, runtime path, experimental provider route, tool policy, budget, and
harness config environment variables are deliberately ignored. Use the
benchmark/condition profile for experimental variables and a credential profile
only for provider availability material.

## Operational configuration

An operational config is the secret-free outer configuration for realizing an
already-defined benchmark study. It collects settings that may change where or
how quickly a run is executed, or what maintenance telemetry is retained,
without changing the benchmark condition. The runnable example is
[`configs/operational_configs/standard.json`](configs/operational_configs/standard.json); its
strict JSON Schema is
[`configuration/schemas/schema_v1.json`](configuration/schemas/schema_v1.json).

The top-level sections have deliberately narrow roles:

| Section | Controls | Does not control |
| --- | --- | --- |
| `credential` | secret-free credential registry path, optional profile name, and runner-only dotenv path | secret values or benchmark model semantics |
| `scheduling` | formalizer/solver/VAL worker counts and recorded sweep-resume intent | attempts, execution tries, budgets, or result selection |
| `evidence_collection` | the existing per-problem agent trace switch | provider reasoning semantics or formalization scoring |
| `infra_diagnostics` | optional provider, transport, and gateway maintenance telemetry | retry classification, backoff, or attempt validity |
| `results` | result-root placement | experiment identity or model labels |

Use the same file with either entry point:

```bash
uv run python source/agent_formalizer/run_formalizer_agent.py \
  --operational-config source/agent_formalizer/configs/operational_configs/standard.json \
  --claw hermes \
  --domain blocksworld \
  --data Heavily_Templated_BlocksWorld-100 \
  --indices 1,2,3

uv run python source/sweep_agent_pipeline.py \
  --operational-config source/agent_formalizer/configs/operational_configs/standard.json \
  --claw hermes \
  --domain blocksworld \
  --data Heavily_Templated_BlocksWorld-100 \
  --index_start 1 --index_end 4
```

Relevant explicit CLI options override the loaded operational value and the
effective operational config receives a new SHA-256. For example,
`--credential-profile`, `--workers`, `--trace`/`--no-trace`, and `--out_dir`
override the corresponding file values; the sweep also supports stage-specific
worker and resume overrides. Benchmark-affecting options such as model,
network condition, budgets, attempts, and execution tries remain benchmark
profile/condition inputs and are not absorbed into this file.

`scheduling.resume` preserves the sweep's operational resume setting and
provenance. It cannot force a completed fixed attempt to be resampled: the core
runner always reuses only an atomic completion whose benchmark-config and task
hashes match, as required by the benchmark lifecycle.

The effective operational SHA is audit metadata only. It is recorded separately
and never replaces or enters `resolved_config_sha256`, output labels, or valid
completion/resume identity. A sweep freezes the exact effective file as
`study_operational_config.json` beside `study_benchmark_profile.json`, and
writes lifecycle state to `operational_manifest.json`. A direct formalizer run
writes a secret-free lifecycle manifest under `<results.root>/.operational/`.
Supplying no operational file preserves the previous CLI defaults and leaves
infrastructure diagnostics disabled.

### Infrastructure diagnostics

When `infra_diagnostics.enabled` is true, the model gateway emits an independent
maintenance stream for each execution. With the bundled config, its usual path
is:

```text
.cache/infra-diagnostics/<run-id>/<domain>/<dataset>/<model>/<problem>/
  attempt-001/execution-001/runtime-<id>/events.jsonl
  attempt-001/execution-001/runtime-<id>/diagnostics_manifest.json
```

Every event carries run, case, attempt, execution-try, logical-call, and
physical-upstream-attempt correlation where those identifiers exist. This makes
several 429 responses retried inside one logical call distinguishable from a new
execution try or a new benchmark attempt. Provider bodies are not added to the
benchmark report, completion record, or request ledger.

`provider_diagnostics.mode` controls provider-response detail:

- `off`: do not record provider responses; separately enabled transport and
  gateway-error events can still be recorded;
- `metadata`: record HTTP/routing/timing/request-correlation metadata without
  parsing the response body;
- `structured`: use the selected provider handler and retain its redacted,
  normalized diagnostic projection;
- `raw`: also retain a bounded, redacted raw projection for short-term
  investigation. JSON is parsed before redaction; non-text binary bodies are
  represented only by their hash and size. Use this only when structured
  parsing is insufficient.

The explicit handler registry is
[`infra_diagnostics/registry.py`](infra_diagnostics/registry.py), while
provider-specific implementations live in
[`infra_diagnostics/providers/`](infra_diagnostics/providers/). Gemini through
Google Vertex uses `builtin:google_vertex@1`; DeepSeek uses
`builtin:deepseek@1`. If `handlers` does not select an override, these defaults
are chosen from the canonical provider ID. Other providers use
`builtin:generic_http@1` until a versioned handler is registered. Configuration
never imports an arbitrary file path, so adding a provider is an explicit code
and registry change rather than dynamic execution from JSON.

Diagnostics are bounded and fail open: gateway request handling does not wait
for the JSONL writer, queue overflow and run-size exhaustion drop diagnostic
events, and an unavailable diagnostic sink does not invalidate the measured
execution. An unknown configured handler or malformed operational config fails
before the run because it is a declared configuration error. Safe response
headers are allowlisted, sensitive keys and bearer/query credentials are
redacted, files are private by default, and event/run byte limits prevent an
unbounded debug sink. `retention_days` is recorded as the maintenance retention
policy; collection itself intentionally performs no destructive automatic
deletion, so an external maintenance job may enforce that policy safely.

## Network isolation

The five native agents always stay on an internal Docker network. The minimum
agent instead runs benchmark-owned code on the host and is restricted by its
code/config surface: it receives only a fixed per-attempt loopback gateway URL,
has no arbitrary-I/O or tool API, and never receives the gateway credential.
In `model_only`, the fixed-route model gateway is the only model transport. It:

- accepts only the configured model and provider path;
- replaces placeholder auth with the real gateway-only credential;
- for Logits, runs the public-REST/OpenAI translator in the same credential
  sidecar before the common fixed-route budget gateway;
- reserves the configured logical model-call and total action-step budgets;
- follows the selected envelope's delivery contract: v4 buffers successful
  responses for exact complete-batch admission; v5 tees successful bytes to
  the harness after one semantic event while incrementally observing OpenAI,
  Anthropic, Gemini, and OpenAI Responses tool formats;
- classifies errors by source and structured reason, so an upstream rate-limit
  429 is retried while the gateway's own `benchmark_model_call_limit` 429 is
  never retried;
- pauses the agent container and active-time clock during transparent retry;
- records every failed physical attempt and its selected backoff in a
  secret-free logical/physical request ledger, including failures that later
  recover;
- for the five native harnesses (not `minimum`), independently captures any
  readable reasoning that a supported provider actually returns, without
  changing the bytes delivered to the harness or inferring whether the harness
  exposes that reasoning to its agent. Gemini and DeepSeek are implemented;
  additional providers register their own wire-format extractors.

Invalid input and other model-addressable errors are returned unchanged so the
native harness can adjust using its official policy. The gateway deliberately
does not infer whether an upstream 429 means a short rate limit, long-term
quota, or depleted funds: every upstream 429 uses the same bounded retry
policy. If retries are exhausted, the execution is terminated as
`attempt_valid=false`/`status=infra_invalid`; it is not counted as a
formalization failure and no valid `completion.json` is written. A human uses
the ledger to decide whether a persistent 429 warrants stopping or rerunning a
case or batch.

For v5, `source/agent_formalizer/results/streaming_report.py` keeps selected-valid
overshoot statistics separate from discarded execution operations:

```bash
PYTHONPATH=source .venv/bin/python \
  source/agent_formalizer/results/streaming_report.py OUTPUT_ROOT
```

`controlled_web` is the optional web condition. It requires a non-empty hostname
allowlist in the condition profile and adds an HTTP/HTTPS allowlist proxy. The
agent remains on the internal network, so shell code cannot bypass the proxy.
There is no unrestricted-egress mode.

Before harness timing begins, required presets verify the runtime lock,
environment/secret isolation, direct IPv4 and domain blocking, host-gateway and
CONNECT rejection, model-gateway reachability, and the gateway action-step
guard.

Each execution also receives a random runtime ID. Docker container names retain
a digest of both the logical task and that runtime ID in a fixed suffix; model,
web, and solver sidecars plus the internal network derive their own names from
the complete parent name. Therefore two sweeps may execute the same
claw/domain/problem concurrently without sharing names or removing one
another's resources. The runtime ID is operational isolation metadata and does
not change task, experiment, or resume identity.

### Docker network lifecycle and capacity

The five Docker harnesses share `network_resources.py`; `minimum` is host-only.
Each execution still receives a fresh internal network. No network is shared
between executions, and no subnet size, daemon config, model/tool behavior or
agent budget is silently changed by this operational infrastructure.

Three safeguards are enabled by default:

1. **Verified teardown.** After evidence collection, remove only containers and
   the network whose exact names, IDs and versioned ownership labels match the
   execution record. Every Docker operation has a finite timeout. Container
   references (including stopped/created containers) and removal are inspected;
   a failed removal stops cleanup and is never silently reported as success.
   This operational failure does not overwrite an already-collected agent
   result. New admissions pause until the residue is resolved.
2. **Conservative recovery.** Before batch admission and before each network
   allocation, inspect the shared local registry. Boot ID, PID and process start
   ticks protect live owners and PID reuse. After a grace period, reclaim a
   dead owner's entirely unreferenced network, or resources for which the owner
   already recorded `cleanup_ready` after collection. A crash survivor with
   containers and no collection authorization is retained and reported as
   `orphan_preserved_uncollected_evidence`. Unlabeled legacy resources, foreign
   references and unrecognized ownership are never pruned automatically.
3. **Capacity admission.** Before dispatching pending batch jobs, check the
   requested worker count plus a safety margin against default-pool capacity,
   subtracting all existing networks and overlapping host IPv4 routes. Each
   subsequent create is rechecked and serialized with cleanup under a short
   host lock. Allocation is the actual reservation; the batch preflight is not
   a permanent reservation of every requested worker slot. Other campaigns
   can reduce available capacity, in which case new executions wait. Docker
   allocation remains authoritative if an unrelated client races the estimate.

Configuration belongs only to the **operational config**:

```json
"network_resources": {
  "safety_margin": 2,
  "docker_timeout_seconds": 20,
  "poll_seconds": 10,
  "orphan_grace_seconds": 60
}
```

Older operational files resolve these defaults explicitly in new operational
provenance. No existing frozen output/profile is rewritten. Adapter code identity
still changes with a code update; this is not permission to bypass frozen-run
identity checks when resuming historical campaigns.

Capacity/cleanup waits happen before the agent clock and within the same pending
startup, without a new model call or repeated infra-invalid execution. The
runner logs `Docker network admission paused` and checks again every 10 seconds;
already-running agents continue. Once resources are available, admission resumes.
There is no periodic work on the model streaming path and no standalone janitor
service. Recovery runs on launch/resume/allocation and while admission is waiting;
after an abrupt stop with no surviving runner, cleanup waits until the next run.

The shared registry is `/tmp/pddl-benchmark-networks-<uid>-<daemon-id-hash>/`:
per-execution records plus `events.jsonl`, protected by a cross-process `flock`.
This coordinates cooperating runners of the same Unix UID using the same local
Docker daemon, including different working copies. It does not lock unrelated
Docker clients or other Unix users. Remote daemons are refused because local
PID and routing evidence cannot establish their safety. Do not remove/replace
registry or lock files while runners are active. If `/tmp` is lost, unknown
surviving resources are retained for manual review, not inferred to be safe.

Batch preflight evidence is copied to `<output>/network_preflight/`; execution
lifecycle evidence is copied to `executions/execution-NNN/network-lifecycle-*.jsonl`.
The shared audit records deletion targets before changes, verified cleanup,
preserved orphans, capacity and paused admission. It never reads container
environments, commands or credentials. If a delete fails, inspect the exact
record/IDs and resolve the cause manually. Read-only reconciliation unblocks
admission after those resources disappear; it never escalates to global prune.

To expand capacity, an operator can separately configure smaller default Docker
subnets after checking host/VPN routing and planning daemon maintenance. Merely
increasing capacity does not replace lifecycle cleanup. Never use a shared agent
network or blanket `docker system prune` as a workaround.

Tests (neither calls a model or public solver):

```bash
PYTHONPATH=source .venv/bin/python -m unittest discover -s tests -p 'test_network_resources.py'
RUN_NETWORK_RESOURCE_DOCKER_TESTS=1 PYTHONPATH=source .venv/bin/python -m unittest discover -s tests -p 'test_network_resources_docker.py'
```

## Native clean tools and skills

- OpenClaw uses a fresh state root and workspace for every attempt. Only those
  two directories are mounted; its session, memory, agent config, and `.Trash`
  cannot be seen by another case. Teardown hard-deletes the complete attempt
  root after OpenClaw's native recoverable deletion.
- Hermes uses a fresh `HERMES_HOME`, official clean-home rules and native tool
  selection; no `--ignore-rules` rewrite is used.
- NanoBot uses pinned official bootstrap/skills and its clean-install registry,
  including native web, CLI-app, and self-inspection tools. `model_only` leaves
  those tools visible and restricts their external effects at the network
  boundary; clean-install MCP configuration remains empty.
- ZeroClaw uses its native unfiltered registry with noninteractive approvals,
  an ephemeral clean workspace/state, and no adapter-level six-tool allowlist.
- GenericAgent copies its official tool schemas unchanged, uses official
  repository plugins and a per-attempt clean copy of pinned memory. Its temp
  and memory mounts use collision-resistant full-instance hashes. Its official
  `--no-user-tools` switch implements the noninteractive envelope.

Only fully isolated state is implemented by these profiles. A future
controlled cross-case sharing experiment should add a separate profile-hashed
condition and an explicit allowlist of shared content; it must not reuse an
incidental cache, session directory, or recycle bin.

Harness-native internal stopping counters remain part of each pinned
`native_clean` baseline. They are not rewritten into a shared `turns` metric;
cross-harness accounting uses only the gateway-defined `model_calls`,
`tool_calls`, and `action_steps`.

## Solver-as-tool condition

Derive an optional `solver-as-tool` condition from the canonical native baseline.
Keep its `native_clean`, v5 envelope and call-checkpoint timing; set
`agent_tools: ["pddl_solver"]` and add `solver_gateway_start_failed` to
`infra_retry.invalidators`. The baseline already selects
`solver_error_routing: "solver-transient-v1"`. Tool implementations live under
`agent_formalizer/tools/<tool>/` (solver is the first optional tool).

There is no separate maintained solver-as-tool preset. Give the derived profile
distinct profile/condition IDs and follow the
[baseline derivation contract](configs/benchmark_profiles/README.md).

Every harness then receives:

- a read-only `/usr/local/bin/pddl-solver` CLI on `PATH`
  (`tools/solver/pddl-solver`);
- a per-attempt `solver-gateway` sidecar with bridge egress
  (`tools/solver/gateway.py` + `remote_client.py`);
- a prompt that documents the CLI (`tools/solver/prompt.txt`).

The CLI posts workspace PDDL to the sidecar, which calls the same selected
planning.domains-compatible package API used by `source/run_solver.py`
(default package `dual-bfws-ffparser`). The agent container itself stays on the
internal network and does not get open internet. The default backend is the
lightweight local Planutils service documented in `source/local_solver/README.md`;
the resolved profile routes both the agent tool and post-generation evaluator
to it. Use `--solver-backend public` only as an explicit, separately identified
condition.

The solver gateway uses the shared `external_calls` infrastructure for bounded,
agent-invisible retries and acknowledged active-clock accounting. Permanent
service failures invalidate execution; repeated ambiguous planner failures
return the final actual diagnostic. See the full
[per-error routing table, timing and evidence contract](external_calls/README.md).
This policy changes the resolved hash; frozen profiles without it remain legacy.
The standalone evaluation client opts into recovery explicitly and does not
invalidate completed agent executions on evaluation-only failures.

The historical `external_call_timing: "logical-deadline-v1"` condition provides
versioned logical-deadline compatibility: hidden physical retries do not
spend supported native tool/SDK deadlines, while accepted-call time still does.
Physical clocks and original native timeout handling are preserved. Currently
Generic, Nanobot foreground exec, Hermes and OpenClaw are supported; other harnesses and
custom transports fail preflight for this condition. See
[coverage, remaining limitations and evidence](external_calls/README.md#opt-in-native-logical-deadlines-logical-deadline-v1).
This has a new semantic identity and must not resume legacy-timing results.

The current baseline uses `call-checkpoint-v1` across the five locked native
harnesses: immutable pending requests, pre-delivery business-context
checks and call-boundary budget settlement. Node stream events no longer make
synchronous deadline RPCs and the host does not freeze the container per call.
This supports uncommitted model/solver calls, not
arbitrary workspace/process rollback or partial-stream replay. See the
[checkpoint contract and limitations](external_calls/README.md#call-boundary-checkpoints-call-checkpoint-v1).
Use a new result condition; do not transparently mix it into an old sweep.

After creating and validating your derived solver-as-tool profile, select it
explicitly (the sweep freezes it before starting cases):

```bash
uv run python source/sweep_agent_pipeline.py \
  --benchmark-config .cache/campaigns/my-solver-as-tool.json \
  --claw openclaw --model google-vertex/gemini-3.1-flash-lite \
  --index_start 1 --index_end 3 ...
```

## Minimum Formalizer Agent baseline

`minimum` is a separate adapter for a deliberately small, fixed control loop.
It does not give the model a shell, file API, workspace view, or tool schema.
It executes directly as a host Python subprocess; Docker image discovery,
container startup, and container cleanup are skipped only for this adapter.
The five native adapters retain their existing Docker path unchanged.
A separately reviewed profile derived from the canonical baseline must
explicitly define `condition_profile.overrides.minimum_agent`, including:

- `execution_backend: "host"` (the only supported minimum backend);
- `reflection_count`: non-negative `n`; the run makes exactly `n + 1` logical
  model calls;
- `solver_feedback.enabled`: when true, exactly one fixed solver call occurs
  before each reflection and its output is appended to the next user message;
- `solver_feedback.solver` and `max_chars`;
- `prompt_template.before_task`, `after_task`, and `reflection`, with a strict
  placeholder allowlist.

Every model response must be exactly one JSON object with string fields
`reasoning`, `domain_file`, and `problem_file`. The complete assistant response,
including its reasoning, remains in all later conversation context. A
reflection returns complete replacement files, not a diff. Only the last
response is eligible for official delivery; if that response cannot be parsed,
the attempt produces no PDDL even if an earlier response was valid.

Fixed solver observations are recorded as `fixed_solver_calls`, not as
model-selected `tool_calls`; therefore the public metric remains
`action_steps = model_calls + tool_calls`. Full per-call request messages,
responses, parsed fields, usage, and solver observations are stored in
`executions/execution-*/minimum_agent_session/transcript.json`.
Normalized provider-measured token buckets and raw per-call usage are also
stored in `minimum_agent_session/usage.json`, so cost reports can apply their
chosen model price table without rerunning a case. Every model call is emitted
to the ordinary `*_agent_steps.jsonl` trace with its phase, reflection index,
complete response, parsed PDDL, provider usage, and `reasoning` field.

The native baseline intentionally rejects `--claw minimum` without that block.
The native call-checkpoint integration does not apply to this host loop; review
and explicitly select its compatible timing settings when deriving the minimum
condition. After creating and validating such a profile, run the complete
formalize/solver/VAL pipeline with:

```bash
uv run python source/sweep_agent_pipeline.py \
  --benchmark-config .cache/campaigns/my-minimum-condition.json \
  --claw minimum \
  --model google-vertex/gemini-3.1-flash-lite \
  --domain barman \
  --data Heavily_Templated_Barman-100 \
  --index_start 1 --index_end 101
```

Derive a separate versioned condition from the canonical baseline when changing
`reflection_count`, solver feedback, or prompt text. The strict schema rejects
unknown fields/placeholders and configurations whose `n + 1` calls exceed the
resolved model/action budgets.

## Attempt semantics

The hierarchy is `case → fixed attempts → infra execution tries`.

- `attempts_per_case` is fixed before execution (default 1).
- Every non-infra outcome is a valid attempt: timeout, harness crash, missing
  files, invalid PDDL, exhausted benchmark model/action budget, and errors
  deliberately routed to the harness are included.
- Gateway-confirmed external transient exhaustion is an invalid attempt,
  distinct from a valid attempt that fails to generate PDDL.
- Only predeclared infra invalidators may start another execution try.
- There is no result-based retry and no best-of-N selection.
- Resume requires matching config, task, and runtime hashes plus a selected
  effective-valid execution; a per-attempt lease prevents concurrent writers.

### Auditable manual execution invalidation

Each comparison-cell directory contains only two validity records:

```text
<model_label>/
  execution_validity.json
  execution_validity_events.jsonl
  p01/...
  p02/...
```

`execution_validity.json` is an atomically written, hashed materialized view.
For every `{problem, attempt}` it lists immutable execution tries, automatic
validity, effective validity after manual events, the chronologically first
effective-valid selection, and whether repair is required. Consumers rebuild
the view from terminal execution records and the event ledger, so direct edits
are rejected and never become selection authority.

`execution_validity_events.jsonl` is an append-only hash chain. A manual
invalidation is permitted only for an automatically valid execution when an
agent-visible tool/infrastructure fault may have changed behavior. Every event
requires an operator, structured reason code, explanation, one or more evidence
files with SHA-256, and whether results were visible during adjudication.
Reinstatement appends another event; it never removes history and cannot make an
automatically invalid execution valid.
Ordinary invalidation reason codes use the `tool_infra.*` namespace;
reinstatement may use either the original `tool_infra.*` code or
`adjudication.*`.

If source/runtime maintenance occurred after the original execution, a
`tool_infra.*` event may additionally bind an exact replacement task and
runtime SHA-256 pair, but only as an explicitly evidenced infra-transparent
revision.  The replacement task hash must equal the invalidated execution's
task hash; prompt, input, resolved profile, model, budgets, and agent-visible
capabilities therefore cannot migrate through this path.  Omitting the pair
retains the ordinary same-runtime repair rule.

For an **automatically invalid** execution, `authorize_repair` records the
owner's permission to use an exact revised runtime without pretending to
invalidate it manually. This requires a pending problem/attempt with no valid
execution, a `tool_infra.*` reason, evidence, and both replacement hashes. The
task hash must match the existing invalid attempt. It changes neither the old
automatic verdict nor first-valid selection, and cannot authorize resampling a
valid result. Old and new runtime hashes remain visible in the cell audit.

An owner-authorized correction to a frozen dataset is the narrow exception.
Affected executions use `dataset_update.*` and bind the event to the exact
replacement task-input and runtime SHA-256 identities. The old completion and
execution remain immutable, and ordinary resume still refuses every identity
change not covered by such an event. The materialized cell state reports both
the historical cell runtime and all observed/authorized repair runtime hashes,
so a selectively revised study cannot be mistaken for a single-runtime study.

Use the management CLI rather than editing either record:

```bash
PYTHONPATH=source .venv/bin/python \
  source/agent_formalizer/results/manage_execution_validity.py audit \
  --cell OUTPUT/.../<model_label>

PYTHONPATH=source .venv/bin/python \
  source/agent_formalizer/results/manage_execution_validity.py invalidate \
  --cell OUTPUT/.../<model_label> --problem p82 --attempt 1 --execution 1 \
  --operator benchmark-owner \
  --reason-code tool_infra.solver_transport \
  --reason "Agent-visible solver transport failure confirmed by replay" \
  --evidence OUTPUT/.../execution-001/TRACE_OR_LEDGER \
  --result-visibility blind
```

The next ordinary resume audits every frozen attempt slot. A slot without an
effective-valid execution receives the next immutable execution number under
the same resolved config/task/runtime identity. The old `completion.json`,
PDDL, trace, and failure evidence are not manually changed. Repair executions
write their terminal result inside `execution-NNN/execution_result.json`.

Post-generation solver and VAL failures are evaluation infrastructure and do
not alter execution validity. They can be rerun deterministically against the
selected frozen PDDL. Solver input resolution and sweep statistics consult the
validity view; summary CSV/Markdown records its revision, state SHA-256, and
whether every frozen problem/attempt pair has a selection.

For N=1, output remains directly solver-compatible. `<model_label>` always
ends with the human-readable config name and resolved-config hash prefix, even
when a caller supplies a custom base label:

```text
output/llm-as-formalizer-agent/<domain>/<dataset>/<model_label>/<problem>/
  <problem>_<model_label>_df.pddl
  <problem>_<model_label>_pf.pddl
  completion.json
  metadata.json
  executions/execution-001/
    execution_result.json
    analysis_evidence_manifest.json
    model_call_ledger.jsonl
    gateway/
      provider_reasoning.jsonl
      provider_full_trace.jsonl
      reasoning_capture_status.json
    full_trace_audit.json
    native_audit/
      native_tools.jsonl
      files/<sha256>
    *_trace.jsonl
    sessions/...
```

Every execution try writes `analysis_evidence_manifest.json`, including
infra-invalid tries that end before normal collection. This optional,
content-free manifest declares what the native harness can expose, what the
adapter attempts to persist, and whether raw-session, usage, normalized-step,
and normalized-tool collection succeeded, failed, was empty, was disabled, or
was not implemented. Its attribution never treats a missing field as model
behavior unless a semantically authoritative direct record supports that
conclusion.

### Full readable-output audit and costs

The full-audit implementation adds a separate, restricted evidence surface to
the older reasoning-only capture. It does **not** put prompt/response bodies in
`model_call_ledger.jsonl` and does not modify model generation settings or the
native context/output budgets.

- `gateway/provider_full_trace.jsonl`: complete parsed provider response events
  (including ordinary text, readable reasoning, tool arguments and usage),
  incoming harness conversation bodies, and physical-attempt boundaries. This
  includes responses discarded by transparent retries. Credential headers and
  opaque signatures/encrypted replay are excluded. Provider-hidden thoughts
  cannot be reconstructed, and the gateway does not enable extra thinking.
- `native_audit/native_tools.jsonl`: tool results observed before subsequent
  history compression, even when no next model call occurs. Native output
  caps remain native; a tool that never returned bytes cannot have those bytes
  recovered from the model request. Generic additionally records its complete
  captured process stdout before its `smart_format` reduction.
  ZeroClaw additionally copies its existing `runtime-trace*.jsonl` into
  `sessions/`, covering native approval denials before tool dispatch. Its
  original log redaction/limits are unchanged; it is supporting evidence,
  not a replacement for the full provider/tool sinks.
- `native_audit/files/<sha256>`: text snapshots of workspace files and direct
  `/tmp` auxiliary `.py`, `.pddl`, `.sh`, `.txt` programs at tool boundaries.
  A manifest maps paths to these blobs. Binary files, symlink targets, private
  harness HOME and arbitrary files created/deleted entirely inside one command
  are not claimed as complete filesystem history. Written source/code also
  remains in the original model/tool arguments.
- `full_trace_audit.json`: collection/parse status, native event counts and
  per-physical-attempt normalized token/cost estimates. Cumulative streaming
  usage is counted once. Cached input is subtracted from ordinary input;
  Gemini candidate and thinking tokens are added, whereas OpenAI-compatible
  completion tokens already include their reasoning-token subset. Missing
  usage or an unpriced model yields `null`, not a zero-cost claim. The known
  subtotal includes discarded attempts; benchmark-clock credits are not
  billing credits.

Gemini 3.1 Flash Lite estimates use standard on-demand Vertex **Global** rates
verified on 2026-09-10: $0.25/M input, $0.025/M cached input, and $1.50/M output
including thinking. The exact rates, official URL and verification date are
embedded in the accounting record and should be frozen with campaign
provenance. These are estimates, not an invoice, and do not assume credits,
discounts, batch pricing or priority service.

The passive native instrumentation lives in `results/native_audit.py`; the
existing version-checked overlay builders load it without editing installed
harness sources. Its write-only request/acknowledgement socket sends evidence
to a host collector. Neither history nor file snapshots are mounted back into
the agent, so capture does not create an extra readable context-recovery file.
It does not decide retries, deadlines, invalidation or agent
continuations. Health metadata is throttled during streams; complete payload
records remain line-flushed. Verify capture on actual native loops before a
campaign, including outputs not reused in model context.

Minimum retains full rejected/malformed responses before parsing and uses the
same gateway evidence sink. The standalone API generator retains raw outputs,
SDK responses and accounting; interrupted reruns archive their previous trace
and files under `execution_history/`, and successful pairs get an
`api_completion.json` with output and trace hashes for resume checks.

`gateway/provider_reasoning.jsonl` is a restricted (`0600`) optional evidence
artifact and can contain verbatim provider-returned reasoning. It stores one
semantically identified fragment at a time, its provider field path and hash,
the logical/physical response identity, and a response boundary stating whether
the provider response was complete and whether it was delivered downstream.
The reasoning-only artifact does not copy the ordinary final answer. The
gateway does not request extra thinking or store opaque Gemini thought signatures.
In particular, Gemini capture covers
native `thought: true` text, Interactions thought-summary steps/deltas, and
explicit `reasoning_content` on compatibility responses; DeepSeek capture covers
Chat/Completions `reasoning_content` and Responses reasoning-text records/deltas.
Streaming fragments are appended as complete provider events arrive, so
fragments observed before a later stream failure remain available.

`reasoning_capture_status.json`, the model-call ledger, and
`analysis_evidence_manifest.json` remain content-free. They report capture
support, counts, hashes, write/parse health, complete versus partial response
boundaries, and downstream-delivery states. An unsupported provider is reported
as `not_implemented` rather than parsed heuristically. Missing provider
reasoning is never used to infer that the model omitted it, and agent visibility
continues to be governed solely by the native harness.

The raw-evidence inventory is limited to adapter-declared session/analysis
roots. Each regular file has an execution-relative path, byte size, SHA-256,
role, and a format-aware record count: JSONL line/parse counts, JSON event or
message counts, SQLite table row counts, or physical text lines. Symlinks are
not followed, evidence contents are not copied into the manifest, and
per-file/aggregate hashes make later loss or replacement detectable. The
manifest path and hash are also recorded under `evidence.optional_evidence` in
the selected execution metadata. This is not a full manifest of every output
artifact; official delivery files and model-call ledgers retain their existing
required-evidence contracts.

Empty delivery files count as generated; content correctness is evaluated later.
When N>1, each attempt gets a solver-compatible label suffix
`__attempt_001`, `__attempt_002`, and so on. `case.json` lists them, and the
sweep runs only attempts selected as effective-valid through solver and VAL.
Valid attempts without PDDL remain evaluation failures; infrastructure-invalid
attempts are excluded from the solver/VAL denominator and reported separately.
An invalid or five-try-incomplete attempt has no `completion.json`; its root `invalid_attempt.json`,
per-execution `infra_invalid.json`, `provider_infra_invalid.json`, and model-call
ledger preserve the reason and physical retry history. A later manual rerun uses
a new immutable execution number rather than overwriting that evidence.

## Evaluation and verification

The sweep performs formalization, solver, and VAL without treating missing or
incorrect PDDL as an infrastructure failure:

```bash
.venv/bin/python source/sweep_agent_pipeline.py \
  --claw openclaw,hermes,nanobot,zeroclaw,generic \
  --domain blocksworld \
  --data Heavily_Templated_BlocksWorld-100 \
  --index_start 1 --index_end 4
```

Tests:

```bash
PYTHONPATH=source .venv/bin/python -m unittest discover -s tests -v

RUN_HARNESS_CONTAINER_TESTS=1 PYTHONPATH=source \
  .venv/bin/python -m unittest tests.test_container_harnesses -v

RUN_HARNESS_E2E_TESTS=1 PYTHONPATH=source \
  .venv/bin/python -m unittest tests.test_harness_end_to_end -v
```

When adding an adapter, implement `BaseClawAdapter`, register it in
`claws/__init__.py`, add a strict harness override entry and runtime-lock
observer/pin, preserve the canonical prompt, and document its translation in
the adapter ledger.
