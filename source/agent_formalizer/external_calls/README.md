# External calls

`external_calls` is dependency-free infrastructure **inside `agent_formalizer`**.
It does not import harness adapters, datasets, golden PDDL, evaluation, Docker,
credentials or campaign state. `retry.py` owns bounded recovery; `model.py` and
`solver.py` own API-specific interpretation. Gateways own IO integration and
evidence; workspaces own process control; the orchestrator owns execution
validity. No repair prompt, PDDL rewrite, planner substitution or backend
fallback is performed.

## Enablement and experiment identity

Unless opting into logical deadlines below, model gateway calls use the common controller with the existing
`external-transient-v2` policy. Existing model routing, counters, buffered/v5
streaming boundaries and time accounting are preserved.

Solver recovery is selected by the **semantic** condition override:

```json
{"solver_error_routing": "solver-transient-v1"}
```

The three bundled solver-as-tool profiles enable it. For a custom profile,
including Minimum with fixed solver feedback, add this override explicitly.
It applies to either `solver_backend: "local"` or `"public"`. The resolver
includes the policy and its invalidators in the resolved config hash. This is
not an operational configuration setting: changing results visible to agents
requires a new experiment identity. Frozen profiles without this field retain
the legacy solver behavior and hash; do not inject this policy into an ongoing
historical sweep. Native-clean profiles without a solver are unaffected.

Changing retry counts, deadlines, classification or exhaustion semantics in
`solver.py` requires a policy version bump and new experiment results. This
README is the review checklist, not an independently interpreted config file.

## Shared contract

`Decision` has an action, reason, exhaustion action, and replay scope:

| Action | Meaning |
| --- | --- |
| `RETURN` (a) | Deliver the actual API result, including an input-related failure, to the caller. This does **not** certify that the PDDL is valid or invalid. |
| `INVALIDATE` (b) | Do not deliver a synthetic failure into agent context. Stop this execution and retain its evidence as invalid; never select its output for scoring. |
| `RETRY` (c) | Retry the same logical call with bounded backoff, keeping previous failures outside agent context. On exhaustion use the decision's explicit terminal action. |

One `RetryController` spans submission, polling and new solves. Nested adapters
must not independently multiply its retry budget. `Retry-After` supports seconds
and HTTP dates, with a bounded cap. Streaming or side-effecting APIs must declare
whether replay is safe; `replay_safe=False` prevents a retry. `wait()` checks
cancellation in short intervals. Model streaming retains its existing loop and
stream observer rather than buffering responses in a generic wrapper.

## Model policy: compatibility, not new model behavior

| Observable response / failure | Handling | On retry exhaustion |
| --- | --- | --- |
| HTTP 408, 429, 502, 503, 504, 520–525, 529 | Retry before commitment | Invalidate: `provider_transient_exhausted` |
| HTTP 500 with a structured `code`, `error_code`, `reason` or `type` of `internal_error`, `overloaded`, `server_error`, `service_unavailable`, `temporarily_unavailable` | Retry before commitment | Same invalidator |
| Connection reset/refused, DNS failure, no route, timeout, broken pipe, premature EOF / malformed HTTP, retryable non-certificate TLS errors | Retry only where the existing gateway considers replay safe | Same invalidator |
| Other HTTP responses, including unstructured 500, authentication/permission and input errors | Preserve the existing agent-facing response; no newly invented model policy | No common-controller retry |
| Certificate verification / nonretryable transport failure | Preserve existing gateway handling | No common-controller retry |
| v5 failure after stream commitment | Do not replay a partially observed response; retain existing `post_commit_stream_failure` execution invalidation | Existing profile-level execution retry, not an extra model call in the same execution |

The model profile retains five retries after the first call, delays
`[1, 2, 4, 8, 16]` seconds and a 60-second `Retry-After` cap. The original
failed model request's latency remains charged; the existing recovery pause
starts when the first transient is recognized and excludes recovery wall time.
Logical model/tool/action counters are unchanged. Provider reasoning capture
and streaming bytes still follow the pre-existing gateway contract.

The standalone Direct API baseline is deliberately **not** made dependent on
`agent_formalizer`; this integration covers its model gateways, including the
host-only Minimum runtime and the Logits bridge's gateway path.

## Solver policy: `solver-transient-v1`

Default: **two retries, at most three submissions**, backoff `[5, 15]` seconds,
`Retry-After` cap 60 seconds, 30 seconds per HTTP exchange, 180 seconds maximum
waiting for one task, and 300 seconds recovery wall budget starting with the
first recoverable failure. These are client/infra bounds, **not** the planner's
CPU limit. The selected service still controls planner time/memory limits.

Classification uses HTTP/envelope fields and planner stdout/stderr, never
keywords in the submitted domain/problem. Public `status: "ok"` alone is not
proof of a valid plan; errors may arrive with HTTP 200. Last-result diagnostics
preserve stdout/stderr and the envelope using the legacy diagnostic formatter.
Earlier retry diagnostics stay in restricted evidence, not the tool response.

| Visible message / condition | Initial action | Exhaustion / final handling |
| --- | --- | --- |
| Nonempty plan artifact (including zero-cost actions or a plan left before an anytime planner's later timeout) | Return the plan; no retry | Later VAL decides correctness; raw timeout/warnings remain in evidence |
| `The empty plan solves it`, terminal `Plan found with cost: 0` | Return an empty plan | Later VAL decides correctness |
| `ff: ... No plan will solve it` / `Problem unsolvable` | Return actual no-plan diagnostic | No retry |
| Final `Plan found with cost: NOTFOUND` followed by **`BFS search completed in ...`** | Return completed-search failure | No retry. First-stage **`Fast-BFS`** NOTFOUND is not terminal by itself. |
| `syntax error in line N`; undeclared predicate/function/variable; unknown constant; type mismatch; incompatible variable type; duplicate/wrong-arity declarations; double metric specification | Return input diagnostic | No retry |
| Illegal initial state/goal/precondition/effect, equality in initial state/effect, unknown optimization method | Return input diagnostic | No retry |
| `increase MAX_*`, too many axioms, not an ADL/linear task, unsupported requirement | Return planner capability/size diagnostic, **not proof of illegal PDDL** | No retry |
| Warnings with a usable plan (e.g. empty types or first-phase search failure) | Return plan, retain raw warnings | Do not promote warnings to infrastructure failure |
| `Request Time Out`, `time limit exceeded`, local `timed_out: true` | Retry a **new solve of identical bytes** | After three ambiguous terminal failures, return only the last actual diagnostic and charge only that solve |
| Poll-stage `There was a server-side error trying to run a planutils package.` | Retry a new solve of identical bytes | Same as timeout; suspected input/resource difficulty, not established OOM or a proof of PDDL error |
| Segmentation fault, `std::bad_alloc`, `MemoryError`, assertion failure, `wrong specifier`, `debug me`, unknown exception, `Killed` in planner diagnostics | Ambiguous: retry a new solve | Same as timeout; planner defects and resource pressure remain possible |
| Missing terminal evidence, unexpected poll-stage service error, unexplained poll HTTP 500 | Ambiguous: retry a new solve | Same as timeout; preserve the last raw response for agent judgment |
| Submit-stage generic Planutils/service error | Retry submission | Invalidate: no confirmed planner execution from which to infer PDDL difficulty |
| HTTP 429 | Retry (respect capped `Retry-After`) | Invalidate: persistent rate limiting |
| HTTP 408, 502, 503, 504, 520–525, 529 | Retry | Invalidate: transport/proxy/service availability, **not planner timeout evidence** |
| Connection refused/reset, no route to host, DNS, socket timeout, truncated/malformed HTTP, non-certificate TLS transport errors | Retry submission or re-poll **the same task ID** | Invalidate: transport failure cannot diagnose the input |
| Invalid JSON, wrong envelope shape, missing submit task reference | Retry same stage/task | Invalidate: protocol failure |
| HTTP 401/403, certificate verification failure | Invalidate immediately | Do not disable TLS verification or switch credentials/backends |
| HTTP 400/404/405/415/422 from the upstream service; missing required API argument, missing package/endpoint/service, `not configured correctly`, `Adaptor Not Found` | Invalidate immediately | Gateway supplies the fixed protocol; these are not reliable PDDL diagnostics. `Adaptor Not Found` can also mask server adaptation exceptions. |
| HTTP 413 | Return request-size limit | No retry; capability constraint on this request |
| HTTP redirect, cross-origin task URL | Invalidate immediately | Never forward PDDL to an unconfigured origin |
| Missing runtime/operator/fact files, uninstalled/unexecutable package, missing Singularity command | Invalidate immediately | Missing service runtime, not PDDL syntax |
| Other HTTP errors | Bounded retry; poll HTTP 500 is ambiguous as above | Otherwise invalidate |
| `PENDING` | Poll same ID without consuming retries or duplicating a job | At task-wait limit invalidate; queue delay, lost job and stuck worker cannot be distinguished |
| Recovery wall deadline / mixed failure types exhaust the retry budget before three ambiguous terminal failures | Invalidate | Two network failures plus one planner timeout do not establish repeated input-dependent failure |

Local compatible-service additions (the server/runner remain uncoupled):

| Structured local evidence | Handling |
| --- | --- |
| Queue full | Retry; persistent exhaustion invalidates |
| `local_backend.worker.oom_killed` or `worker_control_timeout` | Ambiguous new solve; after three ambiguous terminal failures return final evidence |
| Runner `FileNotFoundError`, `PermissionError`, `ValueError`, `KeyError` | Invalidate runtime/configuration failure |
| Worker protocol failure, unexpected worker/server exception without input-dependent evidence | Retry; persistent exhaustion invalidates |
| Planner `local_backend.timed_out` | Same three-solve timeout rule as public terminal timeout |

Only ambiguous **terminal solve** failures count toward the three-failure
inference. They may be timeout/crash/generic-error variants for the same PDDL;
network failures do not count. There is no claim that repetition proves the
input is wrong. No successful plan is replaced by a speculative diagnostic.

Public API reference:
[API error envelopes](https://github.com/AI-Planning/planning-as-a-service/blob/main/server/api/app.py),
[worker execution](https://github.com/AI-Planning/planning-as-a-service/blob/main/server/celery-queue/tasks.py).
The public service exposes neither reliable task exit/OOM metadata nor an
idempotency/cancellation API. A lost submit acknowledgement may leave an orphan
job; bounded low-concurrency retries reduce, but cannot eliminate, that risk.
Do not duplicate a task merely because a poll transport failed or says PENDING.

## Clock, visibility and validity

Solver gateway calls are serialized within one execution's sidecar. Before the
first physical solve, an out-of-band acknowledged **timing escrow** pauses the
benchmark active clock and freezes the agent container. Minimum has a
synchronous host caller instead of a container. This escrow is needed because
retrospectively refunding time after a watchdog already killed the agent cannot
recover a fair execution.

On a deliverable terminal result, the host charges the final solve's elapsed
time **exactly once while still paused**, checks the active budget, then
acknowledges release. If the budget is exhausted, it stops the attempt as a
normal budget outcome before delivering the result. Earlier failed solves,
their backoff and failed transport exchanges are excluded. Successful submit,
normal polling waits and final result retrieval within the delivered solve
remain charged; failed poll transports retain the task ID but their recovery
time is excluded. Evidence distinguishes physical requests from submissions.

Example: three solve attempts of 31 seconds with 5 + 15 seconds backoff take
113 seconds wall time. If the third timeout is returned, **31 seconds**, not
113 or zero, is charged. The harness still made **one** logical tool call.
The already counted model-issued action is never deleted from the trace; its
internal physical retries do not add benchmark action steps.

Persistent solver failure maps to `external_call_unrecoverable`, with the exact
classification retained in `terminal_infra_error`. Clock/control failures map
to `external_call_control_failed`; freezing a concurrently committed model
stream maps to `external_call_stream_overlap`. All are automatic invalidators
in profiles selecting this policy. No agent-facing synthetic failure is sent.
Existing validity management records the invalid execution and preserves its
artifacts; completion/selected output is not fabricated. These permanent
conditions do not automatically replay the whole execution endlessly. Normal
result auditing can schedule a new execution after infrastructure is repaired.

The control/ack files and raw evidence are host/sidecar-only, never mounted in
the agent container. The recovery-enabled solver sidecar runs under the host
runner's UID/GID, so private 0600 bind-mounted files remain readable by the host
monitor; startup verifies control readability. A 15-second acknowledgement bound and a 600-second control
watchdog fail closed rather than leave the benchmark indefinitely paused.
Recovery-enabled Docker monitor commands have a five-second timeout; a stuck
control command cancels the host execution and records an infrastructure error.
Benchmark cancellation interrupts backoff and suppresses further submissions.

**Legacy boundary (without `external_call_timing`):** this compensates the benchmark active clock, not every native
harness/OS wall timer. Docker freeze does not virtualize `CLOCK_MONOTONIC`, shell
command deadlines or remote server clocks. Native timeout symptoms during long
recovery still require audit; this module must not claim those are impossible.
The agent-facing CLI's 600-second transport bound is unchanged. Concurrent
committed model streams are rejected rather than silently altered. There is no
promise of arbitrary parallel/background agent work remaining observationally
identical during a global infrastructure pause (the same general limitation
exists for the prior model pause mechanism).

## Opt-in native logical deadlines: `logical-deadline-v1`

Select
[`native_safety_streaming_solver_as_tool_logical_deadline.json`](../benchmark_profiles/native_safety_streaming_solver_as_tool_logical_deadline.json),
or add `condition_profile.overrides.external_call_timing: "logical-deadline-v1"`
to a **new** condition. This is a semantic setting, not an operational knob.
The bundled profile retains v5 streaming, native tool limits, budgets, solver
retry classification and the local solver backend. It does not update old
profiles/results or silently change Direct API/evaluation.

`external_calls/control.py` supplies the acknowledged call protocol;
`logical_time.py` owns deadline leases; `deadline_integration.py` owns
Docker/process control and native runtime setup. API classifiers remain
independent of harnesses and Docker.

### Accounting and delivery order

1. Obtain host acknowledgement of logical-clock/container pause **before the
   first physical request**. Real clocks, logs, API limits and the recovery
   watchdog continue to use physical time.
2. Exclude hidden failed physical requests, recovery waits and backoff. Existing
   API-specific retry limits/exhaustion rules remain unchanged.
3. Charge the accepted request/solve once, clipped at the earliest registered
   native deadline or benchmark budget. For streaming models, charge initial
   latency before the first semantic event and before headers/body delivery;
   after commitment, streaming time runs normally and is never replayed.
4. Unpause native watchdog execution while withholding the candidate response.
   A due native deadline must finish its original cancellation/timeout path
   before release. Discard a late response; a native timeout remains a **valid**
   measured outcome, not an infra invalidation or fabricated solver failure.
5. Otherwise release original response bytes. Hidden physical retries do not
   add logical model/tool/action steps.

Example: an outer tool has 140 seconds and nested GNU `timeout` has 120 seconds.
A hidden recovery taking 183 physical seconds followed by an accepted 51-second
solve spends about 51 seconds of both deadlines. An accepted 160-second solve
instead triggers the original 120-second timeout before delivery; it does not
also consume the outer deadline's remaining 20 seconds. Normal local work still
counts. Only logical deadlines change, not OS/language clocks or timestamps.

**Intentional difference from legacy model timing:** the first failed physical
model request's latency is now excluded too. The accepted request is charged
(first-event latency plus subsequent streaming time for v5). Classification,
backoff, prompts, request payloads and action counting are unchanged. This is
why old experiments must not transparently resume with this new condition.

### Coverage and limitations

| Runtime | Adapted native path |
| --- | --- |
| Generic | `ga.code_run` watchdog comparison, preserving native kill/output/error handling |
| Nanobot | Foreground `ExecTool.execute` communicate deadline, preserving native cleanup/error text |
| Hermes | `BaseEnvironment._wait_for_process` watchdog, preserving output drain/kill/result handling |
| OpenClaw (locked Node runtime) | LLM idle watchdog, run/agent-idle deadlines, foreground exec supervisor, fetch and installed OpenAI SDK abort deadlines |
| These Python runtimes | Sync socket/SSL reads on model/solver gateway ports; httpcore AnyIO read deadlines when installed |
| GNU `timeout` descendants retaining the timing environment | Relative one-shot POSIX timer/alarm scheduling, including native signals, exit status and `--kill-after` rearming |

Installed harness files are not overwritten. A targeted Python import loader
adapts inspected watchdog sites; source-pattern drift fails preflight. GNU
`timeout` remains the installed program: a Linux `LD_PRELOAD` driver changes
timer scheduling, not parsing, process groups, timeout text or clock functions.
Derived bundles live under `.cache/deadline-runtime/<source-hash>` and are
mounted read-only. This requires Linux, gcc and glibc/GNU timeout. Nanobot uses
its official `allowedEnvKeys` setting to pass only the non-secret timing runtime
to its shell, never provider credentials.

OpenClaw uses Node's synchronous module loader hooks with hashed, read-only source
overlays for the locked installed version. Only inspected cancellation sites
change: ordinary sleeps, logging and cleanup timers remain physical. Its shell
runtime receives only fixed non-secret timing environment variables after native
environment sanitization. `Date.now`, `performance.now` and global timers are
not replaced. Exact source-pattern mismatches fail closed. Native cancellation
evidence is acknowledged before sidecar cleanup, including discarded late replies.

**ZeroClaw, Minimum and custom/Logits gateway transports are not yet
adapted and are rejected by runtime preflight for this condition.** Legacy
profiles remain usable. This is not full five-harness coverage: ZeroClaw needs versioned Rust/Tokio
integration, not fake physical time or silently enlarged native timeouts.

Arbitrary agent-written timers, isolated Python mode/subprocesses stripping the
runtime environment, Nanobot background exec sessions, unlisted SDK backends,
remote clocks and arbitrary parallel/background observational equivalence are
not covered. OpenClaw local-provider startup guards and unlisted provider-specific
SDK watchdogs are not covered; the validated path is the OpenAI-compatible model
transport and the benchmark solver shell tool. Detected overlapping external calls or overlap with an already
committed model stream invalidate as `external_call_stream_overlap`; this is
not proof that every possible background race is detectable.

`time.time`, `time.monotonic`, event-loop time, OS time and file timestamps are
unchanged. Native physical elapsed-time strings can still include hidden pauses;
this adapts **deadlines**, not all timing metadata. Local polling/control costs
and a 150-ms cancellation grace are not microsecond-equivalent. Physical
safeguards remain: 15-second acknowledgements, 600-second recovery-control
watchdog, and 10 seconds for overdue native cleanup. Control failure invalidates
instead of silently delivering an unverified response or extending a limit.

### Evidence and isolation

Opted-in executions additionally record:

- `logical_deadline_manifest.json`: policy, native source/runtime hashes,
  coverage, limitations, and unchanged physical-clock declaration.
- `gateway/logical_time.jsonl`: accepted duration, actual clipped charge,
  due native lease IDs and benchmark-deadline disposition, once per call.
- Model ledger: `external_call_timing`, `accepted_call_seconds`,
  `charged_call_seconds`, and `native_deadline` where applicable.
- Solver outcome: `action: "native_deadline"`, `candidate_discarded: true`
  when native cancellation wins delivery.

The agent receives only its read-only logical-clock view and an owner-checked
Unix socket for deadline register/close. It cannot pause, charge, settle, access
other executions or obtain retry diagnostics via that socket. Settlement and
private control/evidence remain host/sidecar-only. New-condition sidecars use
the host UID/GID so 0600 control is readable without widening agent access.
This is instrumentation, not protection against an agent deliberately bypassing
its native timers or discovering that instrumentation exists.

Offline/loopback tests, using real native runtimes and Docker but no API keys:

```bash
PYTHONPATH=source .venv/bin/python -m unittest discover -s tests -p 'test_logical_deadlines.py'
RUN_EXTERNAL_CALLS_DOCKER_TESTS=1 PYTHONPATH=source:tests .venv/bin/python -m unittest test_logical_deadlines_docker -v
```

## Evidence and evaluation boundary

Each solver-enabled execution writes restricted evidence under
`gateway/solver_calls/call-NNNN/`:

- `request.json`: policy, backend, package, timestamp and input SHA-256 values.
- `domain.pddl`, `problem.pddl`: exact submitted strings, including intermediate
  PDDL that differs from final output.
- `events.jsonl`: physical submit/poll diagnostics, retry decisions/backoff,
  task identity, durations and final charged seconds.
- `outcome.json`: deliver/invalidate, result status or exact failure reason.

These records contain potentially sensitive task text, not API keys, and are
not optional diagnostics: inability to maintain recovery evidence fails closed.
They are not trimmed by the separate operational diagnostics budget. Recovery
attempt count is bounded per logical call, but this is not a disk quota: many
calls or large planner output can still take disk space.
The existing invalidation evidence file remains for compatibility; solver
failures additionally have `external_call_infra_invalid.json`. The cell's
existing execution-validity machinery remains the authority for selection.

Post-generation evaluation is different: it cannot alter an agent's completed
reasoning. This change does not alter `run_solver.py`'s default evaluation
policy or any historical result. Evaluators can explicitly reuse
`solve_pddl(..., recovery_policy="solver-transient-v1", event=...)`; handle
`ExternalCallInvalid` as **evaluation unresolved**, not invalid agent execution.
The shared client keeps its legacy `(ok, result)` return shape and defaults
when `recovery_policy` is omitted. There is no global process/environment switch
silently changing standalone Direct API or evaluation behavior.

## Call-boundary checkpoints (`call-checkpoint-v1`)

Opt in with
`benchmark_profiles/native_safety_streaming_solver_as_tool_call_checkpoint.json`.
This is a **new semantic condition**, initially implemented for the locked
OpenClaw runtime only. Other adapters and custom gateway transports fail
preflight; existing profiles, executions and running campaigns are unchanged.
The bundled example retains local solver, v5 streaming and the same budgets.
Solver backend selection and existing error classification/retry limits remain
independent of this timing mechanism.

### Business continuation and recovery boundary

The checkpoint is at the external request/delivery boundary, not at the start
of the previous reasoning turn. Model requests retain immutable request bytes
(including messages and pending tool IDs); solver recovery keeps the original
domain/problem and the existing submit-versus-poll replay rules. A solver retry
does **not** invoke the model again or rerun the shell command preceding it.
The native `await` continuation remains alive. Until candidate delivery, the
gateway owns the failed branch: no failed response is appended to the agent's
business context, and no downstream PDDL-writing step consumes that response.
Discarding that branch therefore preserves the original business state rather
than deleting messages after the agent has already reacted to an error.

OpenClaw's actual model/tool loop is overlaid to retain references to its
business context. At call entry, the runtime snapshots that context and native
remaining deadlines. Before accepting a recovered result it checks that the
context has not changed and that concurrent native tool execution has not
crossed the checkpoint. A mismatch fails closed as infrastructure invalidation;
the runtime does not serialize the agent's tools or generate another decision
to obtain a more convenient execution. There is no filesystem rollback here:
the supported model and solver boundary has no agent-visible writes before
delivery. Arbitrary shell background jobs, external side effects and hidden
untracked concurrent work are **not** claimed to be safely recoverable.

This is a guarded call transaction, **not** a general process/transcript restore
API. It cannot resurrect an already killed process, undo an external write, or
recover a committed partial model stream. The v5 post-commit stream-failure
invalidation rule remains in force. Extending recovery across any of those
boundaries needs additional adapter-specific support and a new policy version.

### Timer commit barrier and cost

Native cancellation is irreversible once its callback aborts the operation.
Consequently a small commit barrier is still installed in the inspected native
watchdog sites; purely retrospective accounting cannot restore an aborted
continuation. The host escrows the remaining budget at each call boundary and
settles only the accepted physical request's time. Failed requests/backoff are
discarded; if repeated solver timeouts become an accepted input-related result,
the final run's time is charged. The earliest genuine native/benchmark deadline
wins before delivery. Native cancellation callbacks and exit behavior are used,
not synthetic timeout results. Wall time, `Date.now`, `performance.now` and OS
clocks remain physical outside explicitly selected deadline calculations.

In contrast to `logical-deadline-v1`, the Node streaming hot path has no worker,
`Atomics.wait`, synchronous broker RPC, clock-file read or periodic timer poll.
Watchdog creation, cancellation and refresh use in-process state and ordinary
Node timers. A persistent asynchronous channel exchanges snapshots only at
call checkpoint/settlement/resume boundaries. The host does not Docker-pause or
unpause the agent at every call. Python socket/GNU `timeout` support continues
to use the existing low-frequency deadline leases; this is not a global clock
mock or an optimization of arbitrary user timers.

There is fixed per-call checkpoint/acknowledgement overhead, including context
serialization, and small event-loop scheduling differences. This is not a
claim of microsecond equivalence or a measured full-campaign speedup. A stalled
control channel fails closed (bounded three-second participant acknowledgement)
instead of silently disabling deadlines. There are no retry-controlled state
restores of retry counters, physical-call limits, recovery watchdogs, evidence
or action-step accounting.

### Evidence and tests

- `logical_deadline_manifest.json`: policy, immutable bundle/native overlay
  hashes and explicit coverage/limitations.
- `gateway/call_checkpoints.jsonl`: host budget checkpoint/settlement and
  rejected-recovery evidence. It never contains private API keys or raw context.
- Model call ledger `checkpoint_events`: request hash, rollback reasons/count,
  and commit; existing physical model attempts and reasoning evidence remain.
- Solver `solver_calls/call-NNNN/`: unchanged input PDDL and physical events,
  plus checkpoint/rollback/commit events and the final delivery outcome.

All these records are outside rollback. A checkpoint is in-memory execution
state, not a promise that an interrupted host process can resume mid-call.
Campaign restart continues to use the existing execution/attempt audit rules.

```bash
PYTHONPATH=source:tests python3 -m unittest test_call_checkpoints test_logical_deadlines
RUN_EXTERNAL_CALLS_DOCKER_TESTS=1 PYTHONPATH=source:tests python3 -m unittest \
  test_logical_deadlines_docker.CallCheckpointDockerTests
```

The tests use local fake services: 429 recovery, solver timeout recovery,
genuine nested native timeout, immutable requests, forbidden post-commit replay,
context/concurrency rejection, 25,000 timer operations without hot-path IO, and
the actual native Agent loop with 10,000 streamed events followed by a solver
tool. They require socket/Docker permission but no model credentials.

## Add a future API/tool

1. Add a pure API classifier returning `Decision`; document every class here.
2. Declare replay safety and terminal exhaustion routing. Do not retry
   side-effecting operations without a real idempotency guarantee.
3. Own one `RetryController` per logical call; keep physical requests out of
   harness action counters. Integrate domain-specific IO/evidence separately.
4. For tools, use the acknowledged clock/control protocol and host-owned
   invalidation path. Do not grant the agent access to that control channel.
5. Version semantic policy changes and add classification, exhaustion,
   cancellation, timing, frozen-profile and loopback integration regressions.

## Tests

```bash
PYTHONPATH=source .venv/bin/python -m unittest discover -s tests -p 'test_external_calls*.py'
PYTHONPATH=source .venv/bin/python -m unittest discover -s tests -p 'test*model_gateway.py'
```

The integration tests require loopback socket permission and use simulated
services, not real model credits or public solver capacity. Optional live smoke
tests must be explicitly authorized and run only after these pass.
