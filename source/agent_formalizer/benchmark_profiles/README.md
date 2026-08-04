# Benchmark profiles

Every runnable experiment profile lives in this directory and contains the
complete strict-schema input: `native_clean`, `benchmark_envelope`, one
`condition_profile`, sampling, infrastructure retry, provider defaults, and
harness overrides.

Bundled profiles:

- `native_safety_native_clean.json` — default native-clean baseline;
- `native_clean_practical_unlimited.json` — native-clean case-study profile
  with the timeout, model-call, and action-step budgets set to
  `2147483647`;
- `native_safety_solver_as_tool.json` — native-clean plus the `solver-as-tool`
  condition.
- `native_safety_temperature_0_1.json` — native-clean with a condition-level
  `temperature=0.1` model-gateway override;
- `native_safety_solver_as_tool_temperature_0_1.json` — solver-as-tool plus the
  same condition-level temperature override.
- `native_safety_minimum_agent.json` — benchmark-owned fixed-loop baseline:
  one initial structured PDDL response, one configured reflection, no
  model-selectable tools, and no solver feedback by default. It runs in a
  benchmark-owned host subprocess and does not inspect or start Docker. Its
  strict `minimum_agent` block owns the host execution backend, reflection
  count, optional fixed solver call, feedback limit, and all prompt templates.

Generation overrides are applied by the benchmark model gateway so the
effective sampling setting is identical across native OpenAI-compatible and
native Gemini transports. The gateway records the exact applied field in each
request ledger; harness prompts, tools, thinking defaults, and control loops
remain unchanged.

The minimum adapter is intentionally runnable only with a profile that contains
`condition_profile.overrides.minimum_agent` and
`execution_backend: "host"`. Set `reflection_count` to any
non-negative integer. Set `solver_feedback.enabled=true` to run exactly one
benchmark solver call through a per-attempt loopback service before each
reflection and append its result to the next model context. These fixed solver
calls are reported separately and are not model-selected structured
`tool_calls`.

Use filenames of the form `<envelope>_<condition>.json` for new profiles. The
runner uses `native_safety_native_clean.json` when `--benchmark-config` is
omitted. A sweep copies the selected JSON to
`study_benchmark_profile.json` before starting its first case.

`native_clean_practical_unlimited.json` is practically, not mathematically,
unlimited. It uses a very large integer so the adapters and pinned harnesses
retain their ordinary integer configuration paths. The public action metric is
always `action_steps = model_calls + tool_calls`; the two components are also
recorded separately. Harness-native internal stopping counters are preserved
from `native_clean` and are not treated as this shared budget. This profile is
intended for manually supervised case studies, where an operator terminates a
pathological run; it must not be described as having a literally infinite
budget.
