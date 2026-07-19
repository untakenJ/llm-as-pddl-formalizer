# Agent harness PDDL formalizer

This package benchmarks OpenClaw, Hermes, NanoBot, ZeroClaw, and GenericAgent
as PDDL formalizers. Each harness receives the same canonical task prompt and
must deliver `domain.pddl` and `problem.pddl` in `/workspace`. The runner copies
those files byte-for-byte to the existing solver/VAL-compatible layout.

## Configuration model

[`benchmark_profile.json`](benchmark_profile.json) implements the agreed four
layers:

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

The default `native-safety-v1` envelope uses:

- model: `google-vertex/gemini-3.1-flash-lite`;
- harness execution deadline: 1800 seconds;
- control-model request guard: 50 accepted attempts;
- native iteration guard: 200 (recorded as not inherently cross-harness
  comparable);
- network: `model_only`;
- interaction/state: noninteractive execution with per-attempt state and no
  personal or cross-attempt harness state;
- skills/bundles: pinned official clean baseline;
- official-delivery-file success; final-message recovery disabled.

CLI budget changes are recorded as `experimental_budget`, rather than being
misrepresented as a harness-native default.

## Runtime closure

Build the agent image once; benchmark runs use `--pull never`:

```bash
docker build -t pddl-agent-base:latest source/agent_formalizer/docker
```

Install repository-local runtimes:

```bash
bash source/agent_formalizer/install_harnesses.sh all
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

OpenClaw remains host-installed at the repository-defined paths, but its
personal state/config is never used. A mismatch is an infra invalidator, not an
agent failure. The image ID is resolved once per command so every case in that
command uses the same image even if a tag later changes.

## Credentials and host environment

The runner may read explicitly named provider inputs from the git-ignored
`_private/.env` (or `--secrets-env-file`); it does not load that file into the
process environment and does not import personal harness configuration. For a
Vertex run these inputs are the selected API-key variable and, when absent from
the profile, `GOOGLE_CLOUD_PROJECT`. An explicitly named process variable is a
CI-compatible fallback. The API-key value is passed only to the model gateway.
The dotenv file is never mounted, and harness processes and agent containers
receive only placeholder credentials, so the agent cannot inspect the real key.

Example:

```bash
export BENCHMARK_MODEL_KEY='...'

.venv/bin/python source/agent_formalizer/run_formalizer_agent.py \
  --claw hermes \
  --model openai/gpt-5.4-mini \
  --api-key-env BENCHMARK_MODEL_KEY \
  --domain blocksworld \
  --data Heavily_Templated_BlocksWorld-100 \
  --indices 1,2,3
```

Vertex routing is materialized configuration, not ambient harness state. Set
`providers.google_vertex.project` in a benchmark profile, pass
`--vertex-project`, or define `GOOGLE_CLOUD_PROJECT` in the runner-only dotenv
file. A sweep resolves this once and writes it into the frozen study profile so
the route participates in the configuration hash. Location remains profile/CLI
configuration and can be set with `--vertex-location`.

Image, runtime path, provider base URL, tool policy, budget, and harness config
environment variables are deliberately ignored. Use the benchmark profile or
explicit CLI fields instead.

## Network isolation

The agent always stays on an internal Docker network. In `model_only`, only the
fixed-route model gateway has egress. It:

- accepts only the configured model and provider path;
- replaces placeholder auth with the real gateway-only credential;
- reserves at most the configured model-call budget;
- records a secret-free per-request ledger.

`controlled_web` is the optional web condition. It requires a non-empty hostname
allowlist in the condition profile and adds an HTTP/HTTPS allowlist proxy. The
agent remains on the internal network, so shell code cannot bypass the proxy.
There is no unrestricted-egress mode.

Before harness timing begins, required presets verify the runtime lock,
environment/secret isolation, direct IPv4 and domain blocking, host-gateway and
CONNECT rejection, model-gateway reachability, and the gateway call guard.

## Native clean tools and skills

- OpenClaw uses isolated state, its official clean `coding` profile and bundled
  skill discovery; condition-level allow/deny fields are optional.
- Hermes uses a fresh `HERMES_HOME`, official clean-home rules and native tool
  selection; no `--ignore-rules` rewrite is used.
- NanoBot uses pinned official bootstrap/skills and its clean-install registry,
  including native web, CLI-app, and self-inspection tools. `model_only` leaves
  those tools visible and restricts their external effects at the network
  boundary; clean-install MCP configuration remains empty.
- ZeroClaw uses its native unfiltered registry with noninteractive approvals,
  an ephemeral clean workspace/state, and no adapter-level six-tool allowlist.
- GenericAgent copies its official tool schemas unchanged, uses official
  repository plugins and a clean copy of pinned memory. Its official
  `--no-user-tools` switch implements the noninteractive envelope, and the
  version-bound wrapper implements the native-iteration guard.

## Solver-as-tool condition

The optional condition profile `solver-as-tool` keeps the same `native_clean` +
`native-safety-v1` envelope as the default profile and only adds
`agent_tools: ["pddl_solver"]`. Tool implementations live under
`agent_formalizer/tools/<tool>/` (solver is the first optional tool).

Every harness then receives:

- a read-only `/usr/local/bin/pddl-solver` CLI on `PATH`
  (`tools/solver/pddl-solver`);
- a per-attempt `solver-gateway` sidecar with bridge egress
  (`tools/solver/gateway.py` + `remote_client.py`);
- a prompt that documents the CLI (`tools/solver/prompt.txt`).

The CLI posts workspace PDDL to the sidecar, which calls the same
`solver.planning.domains` package API used by `source/run_solver.py`
(default package `dual-bfws-ffparser`). The agent container itself stays on the
internal network and does not get open internet.

Use the frozen study profile:

```bash
.venv/bin/python source/sweep_agent_pipeline.py \
  --benchmark-config source/agent_formalizer/benchmark_profiles/native_safety_solver_as_tool.json \
  --claw openclaw --model google-vertex/gemini-3.1-flash-lite \
  --index_start 1 --index_end 3 ...
```

## Attempt semantics

The hierarchy is `case → fixed attempts → infra execution tries`.

- `attempts_per_case` is fixed before execution (default 1).
- Every non-infra outcome is a valid attempt: timeout, harness crash, missing
  files, invalid PDDL, exhausted model budget, and provider errors included.
- Only predeclared infra invalidators may start another execution try.
- There is no result-based retry and no best-of-N selection.
- A matching atomic `completion.json` (config + task + runtime hashes) is the
  only resume signal; a per-attempt lease prevents concurrent writers.

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
    model_call_ledger.jsonl
    *_trace.jsonl
    sessions/...
```

Empty delivery files count as generated; content correctness is evaluated later.
When N>1, each attempt gets a solver-compatible label suffix
`__attempt_001`, `__attempt_002`, and so on. `case.json` lists them, and the
sweep runs every attempt through solver and VAL.

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
