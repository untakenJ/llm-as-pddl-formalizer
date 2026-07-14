# agent_formalizer — LLM-as-Formalizer via an agent harness

This package is the **agentic** counterpart to `source/llm-as-formalizer-api.py`.
Instead of issuing a single structured LLM API call, it:

1. Builds/starts a **Docker container** for each problem.
2. Runs a full **agent harness** (OpenClaw, Hermes, NanoBot, ZeroClaw, or
   GenericAgent) *inside* the
   container. The agent uses its own tools (shell, file edit, ...) to author
   the PDDL `domain.pddl` and `problem.pddl`.
3. Reads those files back out, records the execution trace and any tool/session
   data exposed by that harness, and writes the result in the **same output layout**
   the other formalizer pipelines use — so `source/run_solver.py` and
   `source/run_val.py` consume it unchanged.

The design closely follows [`opensquilla/claw-swe-bench`][claw]. The adapters
were updated against the current upstream CLIs and config schemas rather than
copying the reference repository's older host config files.

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
    common.py               # provider auth, Python runtime mounts, JSONL traces
    openclaw.py             # OpenClawAdapter
    hermes.py               # HermesAdapter
    nanobot.py              # NanoBotAdapter
    zeroclaw.py             # ZeroClawAdapter (config schema V3)
    generic.py              # GenericAgentAdapter
    __init__.py             # CLAWS registry + get_adapter()
  install_harnesses.sh      # pinned, repository-local runtime installer
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
- Install the non-OpenClaw runtimes into the ignored repository cache:
  ```bash
  bash source/agent_formalizer/install_harnesses.sh all
  ```
  Install one runtime with `hermes`, `nanobot`, `zeroclaw`, or `generic`
  instead of `all`. The installer currently pins Hermes 0.18.2, NanoBot 0.2.2,
  ZeroClaw 0.8.2, and GenericAgent commit `e6bbc916`. It writes only under
  `.cache/harness-runtimes`; no activation, `PATH` edit, or personal harness
  setup is needed. Override the root with `PDDL_HARNESS_RUNTIME_ROOT`.
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
  ANTHROPIC_API_KEY=sk-ant-...
  OPENROUTER_API_KEY=sk-or-...
  GEMINI_API_KEY=...
  DEEPSEEK_API_KEY=...
  DASHSCOPE_API_KEY=...
  ```
- **Model / key decoupling.** Each model resolves its key from one env var:
  by default the provider prefix of the model id (`openai/...` → `OPENAI_API_KEY`,
  see `PROVIDER_API_KEY_ENV` in `config.py`). Override per model in a harness's
  `model_api_keys` map in `CLAW_DEFAULTS`, or for a single run with
  `--api-key-env`. The chosen key is injected into the container under the
  provider's canonical env var name, so the `.env` variable name, the model id,
  and the harness are fully independent and freely combinable. Example:
  ```bash
  # Model openai/gpt-5.4-mini, key taken from a custom-named env var.
  uv run python source/agent_formalizer/run_formalizer_agent.py \
      --claw hermes --model openai/gpt-5.4-mini \
      --api-key-env OPENAI_API_KEY_BENCH ...
  ```

Supported model prefixes for the four new adapters are `openai`, `anthropic`,
`openrouter`, `gemini`/`google`, `deepseek`, and `dashscope`/`qwen`. Always use
`provider/model` form; nested gateway ids such as
`openrouter/anthropic/claude-sonnet-4.6` are preserved. Provider endpoint
overrides can be set in `_private/.env` with `OPENAI_BASE_URL`,
`ANTHROPIC_BASE_URL`, `OPENROUTER_BASE_URL`, `GEMINI_BASE_URL`,
`DEEPSEEK_BASE_URL`, or `DASHSCOPE_BASE_URL`.

## Isolation and tool policy

Harness runtime code is mounted read-only. Credentials are injected from the
selected environment variable and are never written to a host config file.

| Harness | Benchmark-owned behavior |
| --- | --- |
| OpenClaw | Uses `.cache/openclaw-benchmark-state`; host `~/.openclaw` is not read. Web, memory, cross-session, cron, image, and subagent tools are denied by default. |
| Hermes | Creates a problem-specific `HERMES_HOME` inside each throwaway container, enables only `terminal,file`, ignores repository rules/memory, and disables plugins. After each run, a WAL-aware SQLite backup is saved in that problem's `sessions/state.db`; aggregate usage is saved in `sessions/usage.json` and `metadata.json`. |
| NanoBot | Generates config inside the container, restricts paths to `/workspace`, disables web/MCP/skills/bootstrap memory, and removes non-file/shell tools (including `spawn`) from the live registry. |
| ZeroClaw | Generates a V3 config inside the container with one agent, memory disabled, workspace-only access, and an explicit six-tool allowlist. The API key is supplied through a schema-mirror env override. |
| GenericAgent | Generates `mykey.py` without a key value, overlays filtered tool schemas, disables plugins, and gives every problem a fresh writable copy of bundled memory plus a separate temp directory. |

`--tools-profile`, `--tools-allow`, and `--tools-deny` apply only to OpenClaw.
The other policies are intentionally pinned in this repository. GenericAgent
0.1.0 hardcodes 180 agent turns; the adapter records 180 as the effective
limit even if another `--max_turns` value is requested.

## Usage

```bash
# Generate PDDL with any registered harness.
uv run python source/agent_formalizer/run_formalizer_agent.py \
    --claw hermes \
    --domain blocksworld \
    --data Heavily_Templated_BlocksWorld-100 \
    --index_start 1 --index_end 11

# Harness and model are independent.
uv run python source/agent_formalizer/run_formalizer_agent.py \
    --claw nanobot --domain blocksworld \
    --data Heavily_Templated_BlocksWorld-100 \
    --model openai/gpt-5.4-mini --indices 1,2,3

# Other harness names: openclaw, zeroclaw, generic
```

Run a comparable multi-harness generation/solver/VAL sweep with the repository
sweep driver:

```bash
uv run python source/sweep_agent_pipeline.py \
    --claw openclaw,hermes,nanobot,zeroclaw,generic \
    --model openai/gpt-5.4-mini \
    --domain blocksworld \
    --data Heavily_Templated_BlocksWorld-100 \
    --index_start 1 --index_end 11
```

Each claw/model job receives its own harness-prefixed output label.

Output for each problem lands in (identical shape to `llm-as-formalizer-api`):

```
output/llm-as-formalizer-agent/<domain>/<data>/<model_label>/<problem>/
    <problem>_<model_label>_df.pddl      # PDDL domain
    <problem>_<model_label>_pf.pddl      # PDDL problem
    <problem>_<model_label>_trace.jsonl  # unified trace (start/agent/tool_exec/final)
    prompt.txt                           # exact prompt sent to the agent
    agent_stdout.log / agent_stderr.log  # raw harness output
    sessions/*                           # raw transcript/state when exposed
                                         # Hermes: state.db + usage.json per problem
    metadata.json                        # summary (status, finish_reason, usage, ...)
```

By default, `<model_label>` is `<harness>__<model>`, with model `/` characters
collapsed to `__`. This prevents different harnesses using the same model from
overwriting one another. Override it with `--model_label`; pass the resulting
label unchanged to `run_solver.py` and `run_val.py`. To continue an older
OpenClaw output tree, pass its previous model-only label explicitly.

## Evaluation (solver + VAL)

Use the existing scripts with `--prediction_type llm-as-formalizer-agent` and
the **sanitized** model label:

```bash
uv run python source/run_solver.py \
    --domain blocksworld --data Heavily_Templated_BlocksWorld-100 \
    --model hermes__openai__gpt-5.4-mini \
    --prediction_type llm-as-formalizer-agent --indices 1,2,3

uv run python source/run_val.py \
    --domain blocksworld --data Heavily_Templated_BlocksWorld-100 \
    --model hermes__openai__gpt-5.4-mini \
    --prediction_type llm-as-formalizer-agent --indices 1,2,3 --csv_result
```

## Adding another harness

1. Create `claws/<name>.py` implementing `BaseClawAdapter` (override
   `container_run_args`, `create_agent`/`delete_agent`, `send_task`,
   `backup_session`, and `iter_tool_calls` as needed).
2. Register it in `claws/__init__.py` `CLAWS` and add a `CLAW_DEFAULTS[name]`
   entry in `config.py`.

No orchestrator or workspace changes are required — they are claw-agnostic.

## Verification

```bash
# Unit tests plus installed-runtime config validation.
PYTHONPATH=source uv run python -m unittest discover -s tests -v

# Docker mount/config smoke tests (no model request).
RUN_HARNESS_CONTAINER_TESTS=1 PYTHONPATH=source \
    uv run python -m unittest tests/test_container_harnesses.py -v

# Full adapter/orchestrator path through a local fake API (no API cost).
RUN_HARNESS_E2E_TESTS=1 PYTHONPATH=source \
    uv run python -m unittest tests/test_harness_end_to_end.py -v
```

## Trace format

The `*_trace.jsonl` file uses the same line schema as the API pipelines
(`{"event": ..., "ts": ..., ...}`). Event sequence per problem:

`start` → `container_started` → `request` → `agent_result` → (`usage`) →
`tool_exec` (one per recovered tool call) → `final` (or `error`).
