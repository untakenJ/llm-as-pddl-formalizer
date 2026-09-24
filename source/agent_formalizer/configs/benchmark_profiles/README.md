# Canonical native benchmark baseline

[`native_baseline_v1.json`](native_baseline_v1.json) is the only maintained
campaign preset and the loader default when `--benchmark-config` is omitted.
The root [`AGENTS.md`](../../../../AGENTS.md#canonical-benchmark-baseline)
governs its designation and changes: agents may propose changes, but applying
any baseline change requires explicit user approval of that specific change.

## Baseline contract

This baseline comes from the v5 streaming / call-checkpoint solver-as-tool
configuration, with the agent solver tool and its startup invalidator removed.
It retains:

- `google-vertex/gemini-3.1-flash-lite`;
- pinned official clean initialization and the existing benchmark-filtered
  official tools/skills, with no added experimental skills;
- `native-safety-v5-streaming`: native streaming, first-event commitment and
  soft complete-tool-batch action admission;
- `external_call_timing: "call-checkpoint-v1"` for transparent recovery;
- safety guards of 1800 active seconds, 50 logical model calls and 200 action
  steps; one attempt per case, up to five infra execution tries, first valid
  execution selected;
- model-only network, per-attempt isolation and byte-preserving official
  `domain.pddl` / `problem.pddl` delivery;
- `solver_backend: "local"` and `solver_error_routing: "solver-transient-v1"`
  for post-generation evaluation.

`agent_tools: []` means no **benchmark-added** solver tool, solver prompt or
agent solver sidecar. It does not disable the harness's ordinary native tools.
Evaluation still uses solver/VAL. Temperature and thinking mode remain native.
The user-approved default output-limit condition is now
`generation.max_output_tokens: "model_max"`; this deliberately overrides native
output ceilings, not native loops or tools. See the
[output-limit contract](../README.md#model-output-limits).

The five native harnesses use their locked checkpoint adaptations. In
particular, ZeroClaw needs its content-addressed timing overlay when missing:
`PYTHONPATH=source python -m agent_formalizer.timing.zeroclaw_deadlines`.
See [timing coverage and limitations](../../external_calls/README.md#call-boundary-checkpoints-call-checkpoint-v1).
This is a benchmark-constrained native baseline, not a claim that the original
harness runs without benchmark isolation or timing adapters.

## Approved implementation baseline

On 2026-09-10 the user approved adopting the repaired timing implementation
after verification: `call-checkpoint-v1`, implementation revision
`native-concurrency-v5-native-exit`. New experiments use this implementation
baseline, retaining native async behavior, real control-failure invalidation and
unsafe-recovery guards. Changes to this designation require explicit user
approval; choosing a different model or solver is not permission to restore the
old EOF/alive-after-0.5-second misclassification.

The repair was checked by 105 offline tests, six Docker integration tests, two
zero-API native OpenClaw reproductions, and the four owner-authorized real
OpenClaw Logistics repairs (p39, p41, p42, p100) under sweep `20260907-202510`,
revision `20260910-103911-native-exit4`. All four obtained valid first executions
with native-exit evidence and no control-failure invalidation; all four also
passed solver/VAL. The implementation checks, not answer correctness, justify
adoption. Exact source hashes and verification references are retained in that
revision's `baseline_adoption.json` and frozen manifests.

That 2026-09-10 adoption changed implementation code, not the semantic profile.
At that adoption the baseline JSON was unchanged (historical SHA-256
`2062f7f5ce36be7782b7e88af9bde27f79301ac116fec8e4b76bd860e422dcc7`):
Gemini 3.1 Flash Lite, local evaluation solver and no benchmark-added agent solver
tool remain the defaults. Models, backends and solver-as-tool remain selectable
through derived profiles. New campaigns still record/freeze their actual runtime
and adapter hashes; existing frozen campaigns are not hot-updated by this
designation.

## Approved output-limit default (2026-09-16)

The user explicitly approved implementing model-dependent output limits and
changing the experiment default to `"model_max"`. The canonical JSON therefore
now sets `condition_profile.overrides.generation.max_output_tokens` accordingly.
The earlier baseline hash above is historical, not the current file hash.
Gemini 3.1 Flash Lite, local evaluation solver, no benchmark-added agent tools,
and the approved timing implementation remain unchanged. This is a new semantic
condition for new studies; never hot-apply it to existing frozen campaigns.

The capability registry is `configs/model_capabilities.json`. Freeze its evidence
with the campaign profile; per-model resolved limits and context handling enter
the resolved experiment identity. Registry/alias changes require review and a
new frozen condition when they change a selected model's semantics.

## Derive an experiment, do not mutate the baseline

1. Copy the complete baseline JSON to a campaign-specific path. There is no
   runtime inheritance/implicit JSON merge: each input is independently complete
   and strict-schema validated.
2. Apply only the user-requested differences, give the profile and condition
   distinct descriptive IDs, and inspect the diff. Do not use a previous
   derived profile as the starting point.
3. Record the baseline path and SHA-256, requested differences (including CLI
   semantic overrides), and the derived profile in campaign provenance.
   This is a campaign authoring rule, not a new field in the strict profile
   schema. Keep worker counts, credentials and diagnostics in operational config.
4. Load/resolve the profile for each selected harness, pass it explicitly as
   `--benchmark-config PATH`, then freeze it using the sweep's existing
   `study_benchmark_profile.json` mechanism. Do not edit the authoring profile
   during execution.

For a user-requested **solver-as-tool** experiment, retain the baseline envelope,
recovery/timing, model and backend unless the user requests other changes.
Set `condition_profile.overrides.agent_tools` to `["pddl_solver"]` and append
`"solver_gateway_start_failed"` to `infra_retry.invalidators`.
For example, use profile ID `pddl-native-baseline-v1-solver-as-tool` and condition
ID `solver-as-tool--call-checkpoint-v1`. All five harnesses receive the same
benchmark solver interface and task instructions; their native loops are not
optimized for success.

A model or temperature ablation changes its named model/generation fields.
Experimental skills use `condition_profile.overrides.experiment_skills`;
unselected skills remain absent. See the [skill guide](../../skills/README.md).
The benchmark-owned `minimum` adapter is not a native harness: its host loop,
prompt templates, reflection count and timing compatibility require a separately
reviewed explicit `minimum_agent` condition. The native baseline intentionally
cannot be passed to `--claw minimum` without that configuration.

A public solver study must explicitly select `solver_backend: "public"`.
A `"public_then_local"` study additionally requires the wrapper policy and a
healthy supervisor-managed shared local service with a 90-second planner limit.
Both agent tools (when enabled) and evaluation consume the selected backend.
Do not silently change backends when resuming. See the
[local-solver campaign contract](../../../local_solver/README.md#campaign-lifecycle-contract)
and [wrapper contract](../../external_calls/README.md#optional-public-then-local-solver-wrapper).

## Historical compatibility

The former buffered v4, streaming variants, temperature, unlimited, minimum and
legacy logical-deadline presets have been removed from this production directory.
Their exact inputs remain only in
[`tests/fixtures/benchmark_profiles/`](../../../../tests/fixtures/benchmark_profiles/README.md)
for regression coverage. They are not alternative starting points for campaigns.

Existing studies retain their original frozen JSON and execution evidence.
Explicit/frozen legacy profiles still load; missing old production filenames
fail instead of being silently redirected to the new baseline. Resume/repair
uses the original frozen identity, not this new default. A changed baseline or
experimental condition requires a new study, not rewriting old results.
