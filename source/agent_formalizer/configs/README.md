# User configuration

Edit benchmark user inputs here. Their loaders and validators live separately
in [`../configuration/`](../configuration/).

| Input | Purpose | Selection |
| --- | --- | --- |
| [`benchmark_profiles/`](benchmark_profiles/README.md) | Model, budgets, tools, skills and experimental conditions | `--benchmark-config PATH` |
| [`operational_configs/`](operational_configs/standard.json) | Scheduling, evidence, output locations and credential selection | `--operational-config PATH` |
| [`credential_profiles.json`](credential_profiles.json) | Named credentials, secret-variable references and paired provider settings | `credential.registry_file` and optional `credential.profile` in the operational config |

Benchmark profiles determine the resolved experimental configuration hash.
Operational settings and the secret-free credential registry have separate
provenance records. Keep the three input formats separate when combining them
for a run. The operational JSON Schema is maintained with the implementation
at [`../configuration/schemas/schema_v1.json`](../configuration/schemas/schema_v1.json).

## Configure a run

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
