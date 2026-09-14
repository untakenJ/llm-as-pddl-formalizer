# llm-as-pddl-formalizer
**llm-as-pddl-formalizer** is a set of data and pipeline that uses LLMs to generate PDDL.

## Environment

Python dependencies are managed by [uv](https://docs.astral.sh/uv/). The
project uses Python 3.12 and records the complete resolved environment in
`uv.lock`.

Install uv once, then create the project environment. On a CPU-only machine,
use the CPU PyTorch extra:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
uv sync --locked --extra cpu
```

On an NVIDIA GPU machine using CUDA 13.0, select the CUDA build instead:

```bash
uv sync --locked --extra cuda
```

The `cpu` and `cuda` extras are mutually exclusive. For API-only, agent, solver,
or evaluation workflows that do not load a local Hugging Face model, a plain
`uv sync --locked` omits the PyTorch stack entirely.

`uv sync` creates `.venv` automatically. Run project commands through `uv run`,
so no manual environment activation is required. For example:

```bash
uv run python source/llm-as-formalizer.py --help
```

An active Conda environment does not replace the project environment for a
normal `uv run`; uv resolves and runs against this repository's `.venv`.
Deactivate Conda when convenient to keep the shell less ambiguous, but the old
environment does not need to be deleted. Avoid `uv run --active`, which
explicitly opts into the currently active environment.

The local Hugging Face pipelines use bitsandbytes quantization and require a
compatible NVIDIA GPU/driver for practical model execution; the CPU extra is
useful for CPU-side development and dependency checks. The agent pipeline also
requires Docker. Its Hermes, NanoBot, ZeroClaw, and GenericAgent runtimes can be
installed into the ignored repository cache with
`bash source/agent_formalizer/runtime/install_harnesses.sh all`; OpenClaw keeps its
existing host installation. VAL is an external binary;
install it separately and configure its executable through `source/run_val.py`.

OpenAI scripts read their API key from `_private/key.txt`. The API-based Gemini
scripts load credentials from `_private/.env`; see their module documentation
for the required variables. Logits uses `LOGITS_API_KEY` and explicit dynamic
model ids such as `logits/Qwen/Qwen3.5-4B`; see the
[Logits adapter documentation](source/agent_formalizer/compute_platforms/logits/README.md).

## Agent Harness Formalizer

Optional local/remote execution nodes are documented in
[source/remote_execution/README.md](source/remote_execution/README.md). The
controller can dispatch frozen benchmark cells to a GPU node while the existing
runner, gateways, solver and VAL execute there. This is opt-in; existing local
commands and frozen-campaign resume paths are unchanged. Development alongside
a running sweep must use `uv run --no-sync` and preserve its installed runtimes,
shared services and frozen output.

The agent pipeline supports `openclaw`, `hermes`, `nanobot`,
`zeroclaw`, `generic` (GenericAgent), and the benchmark-owned `minimum`
baseline. Non-OpenClaw harness configuration, tool policy, memory, and session
state are created by this repository for each benchmark run; personal harness
config directories are not read. The `minimum` adapter exposes no tools or
workspace access to its model and follows a profile-defined fixed generation
and reflection sequence in a benchmark-owned host subprocess. It alone skips
Docker; all native third-party agents retain their isolated container path.

Each execution also writes a content-free
`analysis_evidence_manifest.json`. It records adapter collection outcomes and
an integrity inventory of adapter-declared raw session/analysis files using
relative paths, sizes, SHA-256 hashes, and format-aware record counts. Missing
analysis is therefore separated from collection failure or an unimplemented
native capture path without placing reasoning text in metadata.

For the five native harnesses, a shared gateway also stores provider-returned
readable reasoning in a separate restricted optional artifact. Gemini and
DeepSeek response formats are currently supported. This observation layer does
not alter the response seen by a harness, does not decide whether reasoning is
visible inside the agent, and reports unsupported providers explicitly so new
provider-specific extractors can be added without model-name allowlists.

```bash
bash source/agent_formalizer/runtime/install_harnesses.sh all

uv run python source/agent_formalizer/run_formalizer_agent.py \
    --claw hermes \
    --domain blocksworld \
    --data Heavily_Templated_BlocksWorld-100 \
    --model openai/gpt-5.4-mini \
    --indices 1,2,3
```

New studies use the single v5 streaming / call-checkpoint native baseline by
default. Derive user-requested experimental differences from this baseline;
changing the baseline itself requires explicit user approval, as recorded in
the root `AGENTS.md`. To select the baseline explicitly:

```bash
uv run python source/agent_formalizer/run_formalizer_agent.py \
  --claw hermes \
  --domain blocksworld \
  --data Heavily_Templated_BlocksWorld-100 \
  --model openai/gpt-5.4-mini \
  --benchmark-config source/agent_formalizer/configs/benchmark_profiles/native_baseline_v1.json \
  --indices 1
```

Streaming v5 preserves real provider progress, records final-batch action-step
overshoot, and uses up to five clean tries only for directly evidenced
post-commit infrastructure failures. Its results must not be merged with v4.

Optional experimental skills live in
[`source/agent_formalizer/skills/`](source/agent_formalizer/skills/README.md).
Select them explicitly with `condition_profile.overrides.experiment_skills` in a
benchmark profile. The five native harnesses receive the same on-demand catalog
and read-only selected files; the current benchmark-filtered official skills
remain the default baseline. No additional skills are enabled by default.
Selected content is hashed and frozen for ablation/resume; see the linked guide
for package format, configuration, and evidence.

For Logits, install the locked translator/tokenizer runtime and use the full
provider model id:

```bash
bash source/agent_formalizer/runtime/install_harnesses.sh logits
uv run python source/agent_formalizer/run_formalizer_agent.py \
  --claw hermes \
  --domain barman \
  --data Heavily_Templated_Barman-100 \
  --model logits/Qwen/Qwen3.5-4B \
  --indices 1
```

The agent runner selects a secret-free named credential profile and reads only
its referenced provider inputs from the git-ignored `_private/.env` (or an
explicit alternative); it never loads or mounts the whole file into an agent
container. The default Vertex profile binds `GOOGLE_CLOUD_API_KEY` to
`GOOGLE_CLOUD_PROJECT`; the bundled `google-vertex-fallback` profile binds the
corresponding `FALLBACK_*` variables and is selected with
`--credential-profile google-vertex-fallback`. The real API key is passed to the
model Gateway through a private temporary secret file, never plaintext CLI
arguments. Credential profiles, including Vertex project, are operational
provenance and do not change the experiment config hash, label, or resume
identity. The versioned default model is
`google-vertex/gemini-3.1-flash-lite`.

### Campaign prerequisite: local solver

The canonical benchmark baseline uses the local Planutils solver for both an
enabled agent solver tool and post-generation PDDL evaluation. Starting or
resuming a campaign therefore includes ensuring one long-lived local solver is
running under a host process supervisor before the first case. It is shared by
the campaign; it is not started independently inside every case.

The launch preflight must verify
`http://127.0.0.1:8769/__benchmark__/health`, confirm the expected image,
solver allowlist, worker count, planner timeout, and resource limits, and save
the returned evidence in the campaign output. A failed preflight stops launch;
it must never trigger an implicit fallback to public planning.domains. See the
complete [local-solver campaign lifecycle contract](source/local_solver/README.md#campaign-lifecycle-contract).

Bundled solver-as-tool profiles now select the versioned `solver-transient-v1`
policy: input diagnostics are returned, temporary failures receive transparent
bounded retries, and unrecoverable infrastructure invalidates the execution.
This semantic policy changes the resolved experiment hash; old frozen profiles
retain their previous behavior. See the complete
[external-call error routing and timing contract](source/agent_formalizer/external_calls/README.md).

User-editable benchmark, operational and credential inputs are centralized in
[`source/agent_formalizer/configs/`](source/agent_formalizer/configs/README.md),
separate from their Python loaders and validators.

Credentials, worker counts, trace collection, result placement, and independent
infrastructure diagnostics can now be grouped in the strict, secret-free
[`operational config`](source/agent_formalizer/configs/operational_configs/standard.json)
and selected with `--operational-config`. Its effective SHA is recorded for
operations auditing but is excluded from the benchmark config SHA and resume
identity. The diagnostics stream has structured Google Vertex/Gemini and
DeepSeek handlers, so provider 429 details can be retained outside experiment
reports without changing gateway retry or scoring behavior. See the
[`agent harness documentation`](source/agent_formalizer/README.md#operational-configuration)
for schema, precedence, storage, redaction, and extension rules.

The agent always remains on an
internal Docker network. The default permits only model traffic; the optional
`controlled_web` condition uses a hostname-allowlist proxy and never grants
ordinary egress. See
[`source/agent_formalizer/README.md`](source/agent_formalizer/README.md) for
runtime pins, supported provider prefixes, isolation details, and evaluation
commands.

Campaigns also use shared [Docker network lifecycle and capacity
guards](source/agent_formalizer/README.md#docker-network-lifecycle-and-capacity):
verified per-execution cleanup, ownership-aware orphan recovery, and capacity
admission before worker dispatch/allocation. Capacity shortages pause new work
outside agent time instead of consuming repeated execution retries. This does
not change Docker daemon configuration or delete unowned historical resources.

The benchmark-owned fixed `minimum` adapter requires a separately reviewed
derived profile with explicit host-loop and prompt settings; the native
baseline does not silently configure it. See the
[minimum adapter contract](source/agent_formalizer/README.md#minimum-formalizer-agent-baseline)
and [profile derivation guide](source/agent_formalizer/configs/benchmark_profiles/README.md).

## Datasets
All datasets can be found in the `/data` folders.

In `/data` the following folders can be found:
- `/textual_blocksworld/`: textual descriptions from BlocksWorld domain
    * `BlocksWorld-100_PDDL`: Groundtruth PDDL for BlocksWorld-100 data.
    * `Heavily_Templated_BlocksWorld-100`: Templated domain and problem descriptions that sound the most similar to PDDL.
    * `Moderately_Templated_BlocksWorld-100`: Templated domain and problem descriptions that sounds natural but still explicitly list all preconditions and effects.
    * `Natural_BlocksWorld-100`: Domain and problem descriptions that sound the most natural/human-like.
-  `/textual_mystery_blocksworld`: textual descriptions from Mystery BlocksWorld domain
    *  `Heavily_Templated_Mystery_BlocksWorld-100`: Templated domain and problem descriptions that sound the most similar to PDDL. Answer files are also included (`p*_answer.txt`)
    *  `Mystery_BlocksWorld-100_PDDL`: Groundtruth PDDL for Mystery-BlocksWorld-100 data.
- `/textual_barman`: textual descriptions from Barman domain
    * `Heavily_Templated_Barman-100`: Templated domain and problem descriptions that sound the most similar to PDDL
    * `Barman-100_PDDL`: Groundtruth PDDL for Barman-100 data.
- `/textual_logistics`: textual descriptions from Logistics domain
    * `Logistics-100_PDDL`: Groundtruth PDDL for Logistics-100 data.
    * `Heavily_Templated_Logistics-100`: Templated domain and problem descriptions that sound the most similar to PDDL.
    * `Moderately_Templated_Logistics-100`: Templated domain and problem descriptions that sounds natural but still explicitly list all preconditions and effects.
    * `Natural_Logistics-100`: Domain and problem descriptions that sound the most natural/human-like.


All PDDL folders contain domain file (`domain.pddl`) and problem files (`p*.pddl`).
All folders containing textual descriptions contain domain descriptions (`p*_domain.txt`) and problem descriptions (`p*_problem.txt`)

## LLM-as-Formalizer
To generate PDDL files from textual descriptions, run the following:
```
uv run python source/llm-as-formalizer.py --domain DOMAIN --model MODEL --data DATA --index_start INDEX_START --index_end INDEX_END
```
where
- `DOMAIN` is which domain to evaluate (`blocksworld`, `mystery_blocksworld`, `barman` or `logistics`)
- `MODEL` is which model to run (`["gpt-3.5-turbo", "gpt-4o-mini", "gpt-4o", "o1-preview", "google/gemma-2-9b-it", "google/gemma-2-27b-it", "meta-llama/Meta-Llama-3.1-8B-Instruct", "meta-llama/Llama-3.1-70B-Instruct", "meta-llama/Llama-3.1-405B-Instruct", "meta-llama/Llama-3.3-70B-Instruct", "deepseek-ai/DeepSeek-R1-Distill-Qwen-32B", "deepseek-ai/DeepSeek-R1-Distill-Llama-70B", "o3-mini", "deepseek-ai/DeepSeek-R1-Distill-Llama-8B"]`)
- `DATA` is which dataset to use (`["Heavily_Templated_BlocksWorld-100", "Moderately_Templated_BlocksWorld-100", "Natural_BlocksWorld-100", "Heavily_Templated_Mystery_BlocksWorld-100", "Heavily_Templated_Barman-100", "Heavily_Templated_Logistics-100", "Moderately_Templated_Logistics-100", "Natural_Logistics-100"]`)
- `INDEX_START` is which index to start running from. This number is inclusive (eg. `1` means starting from `p01`)
- `INDEX_END` is which index to end running at. This number is exclusive (eg. `112` means stop after finishing `p111`)

After generating the PDDL, we can run the solver with the following:
```
uv run python source/run_solver.py --domain DOMAIN --model MODEL --data DATA --index_start INDEX_START --index_end INDEX_END --solver SOLVER
```
where 
- `DOMAIN`, `MODEL`, `DATA`, `INDEX_START` and `INDEX_END` are the same as above
- `SOLVER` is optional and is which solver to use (`["lama-first", "dual-bfws-ffparser"]`). The default solver is `"dual-bfws-ffparser"`.
- Solver requests use the repository's local Planutils service by default. Start it as described in `source/local_solver/README.md`; pass `--solver-backend public` only when intentionally using public planning.domains.

Evaluation uses bounded transparent recovery for `local`, `public`, and the
optional `--solver-backend public_then_local` wrapper. Timeouts, Planutils and
temporary network errors are retried on unchanged PDDL; exhausted failures are
recorded with diagnostics without invalidating the agent execution or blocking
the remaining batch indefinitely. The wrapper tries public first, then local;
the local service defaults to a 90-second planner deadline, one worker and
4096 MiB. See the [evaluation policy](source/agent_formalizer/external_calls/README.md#deterministic-evaluation-recovery-solver-evaluation-transient-v1)
and [campaign service prerequisite](source/local_solver/README.md#campaign-lifecycle-contract).

output will be written in `/outputs/llm-as-formalizer/DOMAIN/DATA/MODEL/`

## LLM-as-Planner
To run the LLM-as-Planner baseline, run the following:
```
uv run python source/llm-as-planner.py --domain DOMAIN --model MODEL --data DATA --index_start INDEX_START --index_end INDEX_END
```
where `DOMAIN`, `MODEL`, `DATA`, `INDEX_START` and `INDEX_END`are the same as above.

output will be written in `/output/llm-as-planner/DOMAIN/DATA/MODEL/`

## Evaluation
To evaluate the result of LLM-as-Formalizer or LLM-as-Planner using VAL, run the following:
```
uv run python source/run_val.py --domain DOMAIN --model MODEL --data DATA --index_start INDEX_START --index_end INDEX_END --prediction_type PREDICTION_TYPE --csv_result
```

where
- `DOMAIN`, `MODEL`, `DATA`, `INDEX_START` and `INDEX_END`are the same as above.
- `PREDICTION_TYPE` is which pipeline to use (`["llm-as-formalizer", "llm-as-planner"]`)
- `--csv_result` is an optional flag that outputs all results (plans and errors) in a csv file. The csv file will be saved to `/output/PREDICTION_TYPE/DOMAIN/DATA/MODEL/`
