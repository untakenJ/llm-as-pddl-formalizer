# agent_formalizer — LLM-as-Formalizer via an agent harness

This package is the **agentic** counterpart to `source/llm-as-formalizer-api.py`.
Instead of issuing a single structured LLM API call, it:

1. Builds/starts a **Docker container** for each problem.
2. Runs a full **agent harness** ("claw", e.g. [OpenClaw]) *inside* the
   container. The agent uses its own tools (shell, file edit, ...) to author
   the PDDL `domain.pddl` and `problem.pddl`.
3. Reads those files back out, **records the full execution trace** (including
   tool calls) as JSONL, and writes the result in the **same output layout**
   the other formalizer pipelines use — so `source/run_solver.py` and
   `source/run_val.py` consume it unchanged.

The design closely follows [`opensquilla/claw-swe-bench`][claw]: the
`BaseClawAdapter` interface, the `OpenClawAdapter`, and the container workspace
abstraction are ported and adapted from there.

[OpenClaw]: https://github.com/opensquilla/claw-swe-bench
[claw]: https://github.com/opensquilla/claw-swe-bench/tree/main/claw_swebench/claws

## Layout

```
agent_formalizer/
  run_formalizer_agent.py   # CLI entry point (analogue of llm-as-formalizer-api.py)
  orchestrator.py           # run_one_problem / run_batch + trace recording
  workspace.py              # Docker container lifecycle for one problem
  prompt.py                 # prompt builder + PDDL extraction fallback
  config.py                 # paths, defaults, naming helpers
  result_types.py           # AgentResult / FormalizerResult
                            # (named result_types, not types, to avoid
                            #  shadowing the stdlib `types` module)
  util.py                   # Tracer (JSONL) + batch helpers (self-contained)
  claws/
    base.py                 # BaseClawAdapter — implement this for a new harness
    openclaw.py             # OpenClawAdapter
    __init__.py             # CLAWS registry + get_adapter()
  prompts/default.txt       # prompt template
  docker/Dockerfile         # base image the agent runs inside
```

## Prerequisites

- **Docker** available to the current user (`docker` on PATH).
- A **base image**:
  ```bash
  docker build -t pddl-agent-base:latest source/agent_formalizer/docker
  ```
  Override via `--image` or `$PDDL_AGENT_IMAGE`.
- The **OpenClaw runtime on the host** (only for `--claw openclaw`): the
  `openclaw` CLI, Node.js, the openclaw module dir. Benchmark runs use an
  **isolated state dir** (`OPENCLAW_BENCHMARK_STATE_DIR`, default
  `{repo}/.cache/openclaw-benchmark-state`) — not your personal `~/.openclaw` —
  so tool policy is pinned by the formalizer and not affected by host config.
  Override runtime paths via `OPENCLAW_NODE_BIN`, `OPENCLAW_MODULE_DIR`,
  `OPENCLAW_BENCHMARK_STATE_DIR`.
- **API keys** come **only** from `_private/.env` (loaded as the highest-priority
  source — it overrides the inherited shell environment). The benchmark never
  reads your personal `~/.openclaw` credential store, and `_private/key.txt` is
  no longer used. Put one key per provider in `_private/.env`, e.g.:
  ```dotenv
  OPENAI_API_KEY=sk-...
  OPENROUTER_API_KEY=sk-or-...
  ```
- **Model / key decoupling.** Each model resolves its key from one env var:
  by default the provider prefix of the model id (`openai/...` → `OPENAI_API_KEY`,
  see `PROVIDER_API_KEY_ENV` in `config.py`). Override per model in a harness's
  `model_api_keys` map in `CLAW_DEFAULTS`, or for a single run with
  `--api-key-env`. The chosen key is injected into the container under the
  provider's canonical env var name, so the `.env` variable name, the model id,
  and the harness are fully independent and freely combinable. Example:
  ```bash
  # model openai/gpt-5.4-mini, key taken from a custom-named env var
  python3 source/agent_formalizer/run_formalizer_agent.py \
      --claw openclaw --model openai/gpt-5.4-mini \
      --api-key-env OPENAI_API_KEY_BENCH ...
  ```
- Tool policy defaults: `tools.profile: coding` plus the claw-swe-bench deny list
  (`OPENCLAW_DENY_TOOLS` in `config.py` — blocks web, memory, cross-session,
  cron, image, etc.). Override per run with `--tools-profile`, `--tools-allow`,
  `--tools-deny`.

The pipeline itself has **no Python package dependencies** (standard library
only); see `requirements.txt`.

## Usage

```bash
# Generate PDDL with the OpenClaw agent
python3 source/agent_formalizer/run_formalizer_agent.py \
    --claw openclaw \
    --domain blocksworld \
    --data Heavily_Templated_BlocksWorld-100 \
    --index_start 1 --index_end 11

# Or pick a specific model + explicit problem indices
python3 source/agent_formalizer/run_formalizer_agent.py \
    --claw openclaw --domain blocksworld \
    --data Heavily_Templated_BlocksWorld-100 \
    --model openrouter/anthropic/claude-opus-4.6 --indices 1,2,3
```

Output for each problem lands in (identical shape to `llm-as-formalizer-api`):

```
output/llm-as-formalizer-agent/<domain>/<data>/<model_label>/<problem>/
    <problem>_<model_label>_df.pddl      # PDDL domain
    <problem>_<model_label>_pf.pddl      # PDDL problem
    <problem>_<model_label>_trace.jsonl  # unified trace (start/agent/tool_exec/final)
    prompt.txt                           # exact prompt sent to the agent
    agent_stdout.log / agent_stderr.log  # raw harness output
    sessions/*.jsonl                     # raw harness session transcript(s)
    metadata.json                        # summary (status, finish_reason, usage, ...)
```

`<model_label>` is the model id with `/` collapsed to `__` (so the multi-slash
OpenRouter ids don't break `run_solver.py` / `run_val.py`, which split on `/`).

## Evaluation (solver + VAL)

Use the existing scripts with `--prediction_type llm-as-formalizer-agent` and
the **sanitized** model label:

```bash
python3 source/run_solver.py \
    --domain blocksworld --data Heavily_Templated_BlocksWorld-100 \
    --model openrouter__anthropic__claude-opus-4.6 \
    --prediction_type llm-as-formalizer-agent --indices 1,2,3

python3 source/run_val.py \
    --domain blocksworld --data Heavily_Templated_BlocksWorld-100 \
    --model openrouter__anthropic__claude-opus-4.6 \
    --prediction_type llm-as-formalizer-agent --indices 1,2,3 --csv_result
```

## Adding another harness

1. Create `claws/<name>.py` implementing `BaseClawAdapter` (override
   `container_run_args`, `create_agent`/`delete_agent`, `send_task`,
   `backup_session`, and `iter_tool_calls` as needed).
2. Register it in `claws/__init__.py` `CLAWS` and add a `CLAW_DEFAULTS[name]`
   entry in `config.py`.

No orchestrator or workspace changes are required — they are claw-agnostic.

## Trace format

The `*_trace.jsonl` file uses the same line schema as the API pipelines
(`{"event": ..., "ts": ..., ...}`). Event sequence per problem:

`start` → `container_started` → `request` → `agent_result` → (`usage`) →
`tool_exec` (one per recovered tool call) → `final` (or `error`).
