# User configuration

Edit benchmark user inputs here. Their loaders and validators live separately
in [`../configuration/`](../configuration/).

| Input | Purpose | Selection |
| --- | --- | --- |
| [`benchmark_profiles/`](benchmark_profiles/README.md) | Model, budgets, tools, skills and experimental conditions | `--benchmark-config PATH` |
| [`operational_configs/`](operational_configs/standard.json) | Scheduling, evidence, output locations and credential selection | `--operational-config PATH` |
| [`credential_profiles.json`](credential_profiles.json) | Named credentials, secret-variable references and paired provider settings | `credential.registry_file` and optional `credential.profile` in the operational config |
| [`model_capabilities.json`](model_capabilities.json) | Verified per-provider/model output/context limits and explicit aliases | `condition_profile.overrides.generation.max_output_tokens` |

Benchmark profiles determine the resolved experimental configuration hash.
Operational settings and the secret-free credential registry have separate
provenance records. Keep these input formats separate when combining them
for a run. The operational JSON Schema is maintained with the implementation
at [`../configuration/schemas/schema_v1.json`](../configuration/schemas/schema_v1.json).

## Configure a run

### Model output limits

New experiments default to this **semantic experimental condition**, approved
on 2026-09-16 (not an operational throughput setting):

```json
"generation": {"max_output_tokens": "model_max"}
```

This fragment belongs inside `condition_profile.overrides` in a complete profile.
Use `"native"` to retain the harness/provider's previous limits, or a positive
integer for an explicit output budget. Omitting the field in an old frozen
profile means native, not the new default. It never changes temperature,
thinking mode, step counts, deadline, tools, or solver settings. Larger output
allowances can change behavior, cost and context packing; do not merge these
results with a previous native-output study without an explicit comparison.

The registry contains exact provider/model keys, explicit aliases, context
windows, output limits, accounting semantics, source URLs and verification
dates. It initially covers Gemini 3.1 Flash Lite, DeepSeek V4 Flash and the
Qwen 3.8-27B self-hosted route. Unknown models fail configuration resolution;
add a reviewed entry/alias or explicitly select native. No substring guessing,
online auto-update, or fallback to 8192. A numeric selection must not exceed a
known finite model output ceiling. This is a per-call upper bound, not a target
length, an aggregate benchmark budget, or a separate thinking-token allowance.

Cloud entries use the documented output cap. Their provider remains the
authority for total-context validation: without a reliable token-counting path
we do not guess input size, truncate messages or silently reduce the cap.
For self-hosted Qwen, 262144 is a **context window**, not an output guarantee.
`remaining_context` uses the selected vLLM server's `/tokenize` endpoint and
chat template for each logical request, including messages/tool definitions;
the wire output cap is frozen context minus counted input (or the smaller
explicit numeric limit). The count is reused across physical model retries.
This requires a compatible tokenizer endpoint and deployment context at least
as large as the frozen context. Use `generation_config=vllm` to exclude hidden
model-repository generation ceilings. No model weights/tokenizer are copied to
the controller. The inference endpoint retains final context validation;
custom parsers/templates which transform prompts differently from `/tokenize`
need deployment validation before a campaign. We do not treat a provider input
or length error as permission to resample.

The same policy applies to all five harnesses and Minimum through the gateway;
Direct API uses the shared request mapper. Native config fields are populated
where supported (Nanobot `maxTokens`, Hermes model `max_tokens`, Generic config
`max_tokens`, ZeroClaw provider `max_tokens`, OpenClaw model `maxTokens`). For
`remaining_context`, native context packing retains an 8192 carrier/reserve
instead of reserving the entire window for output; the gateway replaces that
request hint with the computed allowance. Nanobot's context window and
OpenClaw's model catalog also reflect the selected model's actual context.
The gateway's recorded wire value, not this carrier hint, is the output limit.

Freeze with `BenchmarkProfile.frozen_raw()` / the sweep's existing
`study_benchmark_profile.json`. The snapshot embeds registry evidence; resolved
identity includes only the selected model's semantic capability, so unrelated
entries and documentary URL/date edits do not change the selected resolved
hash. The registry itself is excluded from the implementation hash for this
reason. Resume using the frozen profile, not a newly resolved authoring profile.
Per-request ledger `request_overrides_applied.output_tokens` records the mapped
parameter and allowance; Direct API records `output_token_budget` trace events.
Native length/max-token finish reasons are preserved, not transparently retried.
Tokenizer transport/temporary HTTP failures use existing bounded transient
recovery. Missing/incompatible tokenizer responses or an undersized deployment
produce `model_output_configuration_failed` in the agent gateway, invalidating
the execution rather than accepting an answer with a silently altered budget.
Input that exhausts the frozen context is returned as a normal context error;
this policy does not expand benchmark retries for genuine input/length failures.

Standalone API CLI and `remote_execution api-job` accept
`--max-output-tokens model_max|native|N`, defaulting to this baseline, and an
optional `--model-capabilities PATH` registry. API batch cells freeze
`api_output_policy.json` before generation; `--resume` reuses it and rejects
incompatible explicit selections or legacy-result mixing. Remote API jobs
embed the resolved policy in their immutable request. Existing programmatic API
callers and old remote requests which omit the policy retain native behavior.

### Profiles and operations

Start every new experiment from `benchmark_profiles/native_baseline_v1.json`.
Copy it to a campaign-specific JSON file (for example, in `.cache/campaigns/`),
apply only user-requested differences, and select it explicitly. Do not edit
the baseline or select a historical fixture as a shortcut. Baseline changes
require explicit user approval; see the root `AGENTS.md` and the
[baseline/derivation contract](benchmark_profiles/README.md).
Select skills through
`condition_profile.overrides.experiment_skills`; skill content remains in
[`../skills/`](../skills/README.md).

Copy `operational_configs/standard.json` to choose scheduling, diagnostics and
output settings. Its `credential.registry_file` points to this directory's
registry. Set `credential.profile` to a named profile when needed; otherwise
the registry's model/provider defaults select it. Actual secrets remain in the
runner-only `_private/.env`, referenced by variable name in the registry.

For example, from the repository root:

```bash
.venv/bin/python source/agent_formalizer/run_formalizer_agent.py \
  --claw hermes \
  --domain blocksworld \
  --data Heavily_Templated_BlocksWorld-100 \
  --benchmark-config source/agent_formalizer/configs/benchmark_profiles/native_baseline_v1.json \
  --operational-config source/agent_formalizer/configs/operational_configs/standard.json \
  --indices 1
```

The same configuration flags are accepted by `source/sweep_agent_pipeline.py`.
See the [runner guide](../README.md) for runtime installation, local-solver
campaign prerequisites and full execution options.

## Defaults and paths

- Without `--benchmark-config`, the runner loads
  `benchmark_profiles/native_baseline_v1.json` from this directory.
- Without `--operational-config`, the runner retains its existing compatibility
  defaults. It does **not** implicitly enable the diagnostics and resume
  settings in `operational_configs/standard.json`.
- The default credential registry is this directory's `credential_profiles.json`.
  `--credential-profiles-file` can select another registry, and
  `--credential-profile` can select a named entry. Supported explicit CLI
  overrides are recorded in the effective operational configuration.
- Explicit benchmark/operational file paths on the command line are resolved
  against the current working directory. Default configuration locations are
  resolved from the package location.
- Paths inside operational configs, including registry, secrets, output and
  diagnostic storage paths, are relative to the repository root unless absolute.
  `--credential-profiles-file` uses this same operational path rule.
- A relative `experiment_skill_library.path` is resolved against the selected
  benchmark profile's directory. Without that field, the bundled `../skills/`
  library is used.

Moving a custom profile must preserve what its relative paths resolve to.
Completed or frozen studies retain their recorded inputs and runtime identity;
edit authoring configurations for new runs without rewriting frozen snapshots.
