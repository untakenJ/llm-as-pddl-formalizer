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

The canonical native baseline enables it for evaluation and for solver tools
when explicitly added to a derived profile. Frozen custom profiles, including
Minimum with fixed solver feedback, must select this override explicitly.
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
| HTTP 400/415/422 | Return the actual request rejection | These statuses alone do not prove a service/configuration failure. |
| HTTP 404/405 on the fixed upstream route; anchored missing required API argument or missing/uninstalled package | Invalidate immediately | Fixed gateway protocol/routing could not access the service. |
| `Adaptor Not Found`, generic `does not exist` / `does not contain` / `not configured correctly` errors | Classify as unexplained service error, not automatically configuration failure | Poll-stage ambiguous terminal failures can be returned after bounded re-solves; these phrases may describe input-dependent adaptation. |
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
| Runner `FileNotFoundError`, `PermissionError` | Invalidate runtime/configuration failure |
| Runner `ValueError`, `KeyError` | Ambiguous worker failure, not configuration proof; poll-stage repeated terminal failures return the last diagnostic |
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

The following describes the **legacy** escrow path; the current OpenClaw
checkpoint implementation is described below. Legacy solver gateway calls are
serialized within one execution's sidecar. Before the
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

This historical timing mode is selected by
`condition_profile.overrides.external_call_timing: "logical-deadline-v1"`.
It is a semantic setting, not an operational knob. Its former bundled preset
is now a test-only fixture. New experiments start from the
[canonical baseline](../configs/benchmark_profiles/README.md), which uses
`call-checkpoint-v1`; changing that condition requires an explicit experimental
choice. Frozen profiles/results and Direct API/evaluation are not rewritten.

`external_calls/control.py` supplies the acknowledged call protocol;
`timing/logical_time.py` owns deadline leases; `timing/deadline_integration.py` owns
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

The [canonical native baseline](../configs/benchmark_profiles/native_baseline_v1.json)
selects `condition_profile.overrides.external_call_timing: "call-checkpoint-v1"`.
This is a **semantic condition**, implemented for the five locked native
harnesses in revision `native-concurrency-v5-native-exit`. Unlisted adapters,
native source drift and custom gateway transports fail preflight; existing
profiles, executions and running campaigns are unchanged.
The baseline retains local evaluation, v5 streaming and the same budgets;
agent solver tools require an explicitly derived solver-as-tool condition.
Solver backend selection and existing error classification/retry limits remain
independent of this timing mechanism.

### Checkpoint participant lifecycle (`native-concurrency-v5-native-exit`)

Send errors, receive errors/EOF and missing acknowledgements share one bounded
disconnect adjudication. The registry lock is not held across socket I/O or
exit confirmation; per-connection ordering preserves hello/command/ACK sequence
identity. Disconnection is resolved once per connection. Without a terminal
notice, there is at most 0.5 seconds to confirm an exiting process, not a new
wait on every successful call. Process
identity includes Linux start time: PID reuse means the original peer exited;
unreadable or malformed process evidence is unknown, not proof of exit.
Transient unknown samples can be rechecked within that same 0.5-second bound;
only positive process-identity evidence permits retirement as a native outcome.

The locked Node runtime sends one versioned `participant_exit` record on its
existing checkpoint connection at native `exit`, **not** `beforeExit` or a model
final message. Node can close socket handles while its PID remains alive during
C++/isolate cleanup for longer than 0.5 seconds. This notice permits
`native_exiting` retirement in that interval, bound to the connection identity
from hello and the host-observed PID/start time. It is not a successful result,
does not stop the execution clock/container or other participants, and does not
replace ordinary process-exit supervision, artifact collection or evaluation.
Nonzero native exits remain native outcomes, not automatic infra failures.

The exit hook performs one small synchronous write to the version-bound Node
socket FD only when no Node writes are queued; it never awaits an ACK, keeps
the event loop alive, or retries a blocked write. Missing/truncated notices
retain conservative EOF/protocol handling. A separate `control_failure` origin
preserves adapter failure followed by `process.exit(70)`; it cannot be washed
away by a subsequent native exit hook. Terminal messages are not checkpoint
ACKs, and acknowledgements after a terminal notice are protocol faults.

| Evidence | Handling |
|---|---|
| Confirmed peer exit at an ordinary boundary | Retire its connection and timer lease; preserve the native exit/tool outcome and continue with remaining participants. |
| Native exit notice followed by EOF while the same PID is still cleaning up | Retire as `native_exiting`; do not mistake cleanup exceeding 0.5 seconds for a live control failure. Unknown process identity still fails closed. |
| Live or unidentifiable peer with a broken control channel | `external_call_control_failed`; do not reconnect with a fresh checkpoint or silently continue without timer protection. |
| Explicit protocol/adapter fault followed by exit | Keep the fault; a later exit never clears the recorded invalidator. |
| Previously acknowledged checkpoint participant lost before recovery validation | `external_call_recovery_unsafe`, classification `checkpoint_participant_lost_during_recovery`; retirement cannot erase a required business-state check. |
| Owner cleanup | Stop the checkpoint monitor without creating a new invalidation. |

Retired checkpoint membership is retained until that call's resume/new checkpoint,
not across the whole execution. The existing context-change/concurrency guards,
native timeouts and API retry policies remain in force. There is no new heartbeat,
per-stream-event IPC, command replay, model resampling or physical-clock change.
`gateway/call_checkpoints.jsonl` records participant ID, PID/start time, operation,
sequence, terminal notice origin/exit code, disconnect source/error type,
initial/final process status, confirmation duration and disposition (no payload).
The implementation revision appears in new runtime manifests; this source change
does not modify frozen campaign runtimes, historical traces or validity records.
Tests: `test_checkpoint_lifecycle.py`, plus the existing Python, Node and native
concurrency checkpoint suites; no external API is required.

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
to obtain a more convenient execution. A healthy context change, cyclic context,
parallel tools or background process is **not** an invalidator. The context
check is only enforced after an actual external physical request was discarded.
There is no filesystem rollback here:
the supported model and solver boundary has no agent-visible writes before
delivery. Arbitrary shell background jobs, external side effects and hidden
untracked concurrent work are **not** claimed to be safely recoverable.

This is a guarded call transaction, **not** a general process/transcript restore
API. It cannot resurrect an already killed process, undo an external write, or
recover a committed partial model stream. The v5 post-commit stream-failure
invalidation rule remains in force. Extending recovery across any of those
boundaries needs additional adapter-specific support and a new policy version.

### Native concurrency revision (`native-concurrency-v2`)

The current checkpoint implementation uses independent model/solver call-control
files and no per-execution model/solver serialization lock. OpenClaw's native
`exec` default 10-second background yield, explicit background execution,
`process` polling, and overlapping healthy model calls remain enabled. The old
`external_call_stream_overlap` test is not used by this checkpoint path.
The driver also no longer imposes an undeclared 128-Node-participant invalidator.
Model ledger and solver request records include `timing_control_call_id`; delivery
records identify `running_wall` versus `isolated_escrow` for later audit.

An isolated external call still escrows deadlines. When native concurrency is
observed, its healthy elapsed prefix is charged once and the clock resumes
normal wall-time advancement for the overlapping group. Call durations are not
added together, ordinary native callbacks remain active, and no response/error
is injected to force the agent to run serially. Separate control files prevent
requests overwriting one another. Model state is re-read after Docker/filesystem
checks; a stale stream snapshot alone cannot invalidate a healthy execution.

If an actual failed physical request needs transparent recovery after that
group has advanced on the running clock, the current implementation cannot
promise retrospective rollback of all concurrent native deadlines/context.
It records `external_call_recovery_unsafe`, with affected call IDs and nonzero
rollback counts, and invalidates instead of refunding concurrent useful work or
silently accepting a potentially biased result. The same reason is used when
an actual serial recovery fails the native business-state check. This is a
remaining recovery limitation, **not** a ban on asynchronous agent behavior.

Normal native cancellation/exit, a timeout callback that throws, and slow native
cleanup are valid outcomes. Busy Node event loops do not fail a fixed three-second
ACK bound: the host reports progress while waiting, charges that work as active
time, and the benchmark budget remains the outer limit. A dead/stalled host
control channel still has a 15-second no-progress transport watchdog.

This revision is recorded in `logical_deadline_manifest.json`. Its resolved
checkpoint invalidator list now names the recovery-specific guard, so new
resolved identities are distinct. Existing campaign frozen runtimes, executions,
validity decisions and completions are not rewritten or silently resumed.
See [the invalidation audit](INVALIDATION_AUDIT.md) for classification details
and the explicit scope of the legacy paths.

### Five-harness native sites (`native-concurrency-v3-multiharness`)

The same business-state contract applies to all five harnesses. A hidden retry
keeps the original request and suspended continuation; only its accepted final
physical request consumes business time. We do not replay a preceding shell
command, rewrite a prompt, change a native timeout value, remove tools, force
sequential execution, or change native retry/cleanup behavior.

| Harness | Named native business deadlines | Native behavior deliberately retained |
| --- | --- | --- |
| OpenClaw | Existing model idle/run/abort and foreground exec deadlines | Default background yield, process polling and parallel tools |
| Generic | `ga.code_run` deadline; gateway socket read deadline | Native generator, output, process signals and tool arguments |
| Hermes | Environment process deadline, `process.wait`, concurrent tool batch deadline; gateway SDK reads | Native concurrent pool, completion events, timeout errors, heartbeat and cleanup |
| Nanobot | Foreground `ExecTool`, non-streaming runner request timeout, session hard deadline at native poll, `write_stdin` wait-for-output deadline; HTTPX reads | Streaming runner's native absence of an outer request timeout; background yield and passive expiry |
| ZeroClaw | Native Rust shell timeout; locked reqwest total request/body deadline only for model-gateway | Native timeout values, `Elapsed`/reqwest error construction, process cleanup, parallel-tools setting; connect-only streaming client |

Python uses a persistent background control channel and local deadline objects.
There is no per-chunk/per-read synchronous registration RPC. AST overlays are
restricted to exact, counted source sites and never mutate installed packages.
Python contexts are fingerprinted in-process only at call boundaries: Generic's
model payload, Hermes tool batch messages and Nanobot's runner messages. Changed
context or observed concurrent tool activity is only a recovery-safety check
after an actual discarded request; healthy activity remains valid.

ZeroClaw uses an isolated derived release binary built from its pinned source,
default features and locked dependencies. The only dependency patch is its
same-version reqwest deadline future, scoped to the model gateway endpoint;
other HTTP endpoints keep native timers. The helper uses one lease per named
deadline and an in-process asynchronous 20 ms poll, not stream-event IPC.
Physical `Instant`, `SystemTime`, `time.time`, and `time.monotonic` stay physical.
The build command, original/derived binary hashes, native source hashes and
overlay identity are recorded, and preflight verifies the derived artifact.

Background yields, output-drain grace, PID liveness/cleanup waits, arbitrary
user-program timers and physical elapsed-time metadata are **not** normalized.
We do not claim arbitrary background filesystem effects can be reverted.
Actual recovery across observed parallel business progress remains
`external_call_recovery_unsafe`; an explicit adapter control failure is
`external_call_control_failed`. Genuine native cancellation is still a valid
measured result, even if it happens before the benchmark envelope expires.

These adaptations concern transient external calls only. They do not harmonize
different harnesses' native budgets or increase their success rate by design.

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
control channel fails closed; ordinary native event-loop work does not become
an infrastructure failure solely because it exceeds three seconds. There are no retry-controlled state
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

## Optional public-then-local solver wrapper

`solver_backend: "public_then_local"` selects the separate, versioned
`solver-public-then-local-v1` mechanism in `solver_fallback.py`. It is **opt-in**:
existing `public` and `local` modes and frozen studies are unchanged. Both agent
solver tools and post-generation evaluation support it. The resolved agent
configuration includes the backend and wrapper policy in its semantic hash;
do not resume a public-only study with this different solver condition.

Use `--solver-backend public_then_local` on a new agent run/sweep, with an
explicit profile derived from the [canonical baseline](../configs/benchmark_profiles/README.md).
Enable `agent_tools: ["pddl_solver"]` and its startup invalidator in that
derived profile if the user requests solver-as-tool. The CLI passes the backend
to evaluation too; the native baseline alone does not expose a solver tool.
For evaluation alone, add `--solver-backend public_then_local` to the usual
`source/run_solver.py` command. Tool profiles must explicitly select
`solver_error_routing: "solver-transient-v1"`; without recovery/timing control,
the wrapper fails preflight. It does not alter native harness tools or prompts.

### Limits and lifecycle

| Layer | Public phase | Local fallback phase |
| --- | --- | --- |
| Planner deadline | Public service's native **30 seconds** | Service configured to **90 seconds** |
| Recovery budget | Initial operation plus at most 2 retries | A fresh budget: initial operation plus at most 2 retries |
| Backoff | 5 then 15 seconds; `Retry-After` bounded to 60 seconds | Same |
| HTTP exchange timeout | At most 30 seconds, clamped to remaining guards | Same; **not** the planner limit |
| One submitted task's pending wait cap | 180 seconds | 180 seconds, including queue wait |
| Backend wall guard | 210 seconds | 360 seconds |

The wrapper starts no processes or services. Before a campaign starts, provision
one supervisor-managed local service with `--timeout 90`; retain the usual
single-worker/4096 MiB defaults unless the study specifies otherwise. Follow
the [campaign lifecycle contract](../../local_solver/README.md#campaign-lifecycle-contract)
and save the health/resource evidence. The gateway requires healthy local
fallback infrastructure even if its first public request succeeds. The wrapper
also validates the local health response before its first local submission:
backend, actual planner timeout, and installed/allowed requested package.
A 60-second service is rejected; an HTTP timeout or ignored request parameter
cannot turn it into a 90-second planner. Do not reconfigure a service being used
by another frozen study. Public 30 seconds is the upstream planner policy, not a
client guarantee about public queue or response latency.

Both phases reuse the existing `solver-transient-v1` classifier and controller;
health failures use the local controller rather than a nested retry loop. The
210 + 360 second wall guards leave nominal room under the existing 600-second
tool transport/control guards. They are checked between IO/waits and clamp
individual HTTP timeouts, not a kernel-level guarantee against pathological
slow-drip network peers. A shorter native tool deadline still applies to
accepted work; this wrapper does not extend it. Too much local queueing can hit
the pending cap: that is unknown infrastructure latency, not a proven hard PDDL.

### Routing and visibility

| Outcome | Public phase | Local phase / final tool decision |
| --- | --- | --- |
| Plan, empty plan, explicit unsolvable/search exhaustion, syntax/semantic input error, capability/request-size limit, HTTP 400/415/422 | Return immediately; no fallback | Return actual result |
| Terminal planner timeout, Planutils error, ambiguous OOM/crash/missing terminal result | Retry; on exhausted ambiguous budget discard the public result and switch | Retry; after three ambiguous terminal failures return **last actual local diagnostic** |
| 429, temporary HTTP/service/transport/protocol failure | Retry; exhaustion switches | Retry; exhaustion raises `ExternalCallInvalid` |
| Pending/recovery/backend wall cap; exhausted mixed failure budget | Switch without duplicating a known pending task | Invalidate; not evidence of repeated input-dependent timeout |
| Authentication/certificate error, redirect/untrusted task URL, fixed route or missing runtime/package error | Invalidate immediately; do not switch to bypass a security/configuration failure | Invalidate immediately |
| Local health missing/wrong backend, wrong planner deadline, unavailable requested package | Not applicable | `solver_fallback_configuration_error`; no solve under wrong settings |
| Benchmark cancellation or timing/control failure | Stop; no fallback | Stop; no fallback |

In evaluation, wrapper exhaustion is recorded as an evaluation failure with
the final diagnostic, without another outer set of retries or automatic agent
invalidation. The evaluation policy below enables the same bounded recovery
for standalone public/local evaluation too (`EVAL-001`).

One logical tool call/checkpoint spans both phases. Hidden retries and the
public-to-local switch discard their results and restore logical call/timer
state using the existing timing protocol. All discarded solves, retry backoff,
and abandoned public-phase time are excluded from the benchmark clock. Only
the final delivered solve is charged (including its successful submission,
ordinary polling/waiting and result retrieval). If the final local timeout is
returned, its 90-second solve is charged, not zero. For example, three public
31-second solves and three local 91-second solves with 5 + 15 seconds backoff
per phase take 406 seconds physically, but charge only **91 seconds**.
No additional agent action steps, fabricated plans, or public-error messages
are injected by fallback. PDDL bytes and requested planner package are identical
across both backends. Existing checkpoint recovery-safety checks remain: native
asynchronous progress is allowed, but an unsafe rollback invalidates rather
than contaminates an execution. Physical time and external jobs are not reverted.

Restricted solver evidence adds `backend_start`, `backend_health`, physical
requests/retries with backend tags, `backend_return`, `fallback`, final `return`
or `wrapper_invalid`, plus input hashes and actual charge. An inner public
`backend_return` is only a candidate, **not delivery to the agent**. The gateway's
`outcome.json` remains authoritative for acknowledged delivery. Evaluation
appends `<problem>_<model>_solver_events.jsonl` with UTC timestamps and a unique
evaluation request ID; historical evidence is not overwritten. No new broad
model/trace ledger is introduced.

Known boundary: public API has no reliable cancellation/idempotency endpoint.
Abandoning a pending public task (or losing submit acknowledgement) can leave an
orphan job. Retrying a failed poll preserves its task ID. Local fallback changes
resources/deadline and therefore is its own experimental condition, not a claim
that local 90 seconds exactly equals public 30 seconds in solving power.

## Deterministic evaluation recovery (`solver-evaluation-transient-v1`)

`source/run_solver.py` always enables the shared solver controller for `public`,
`local` and `public_then_local`. This is an evaluator implementation revision,
not a change to historical agent profiles, completion records or tool policies.
It solves the selected effective-valid execution's exact frozen PDDL; it never
regenerates, repairs or invalidates an agent answer. Frozen older runtimes must
be explicitly versioned/replaced for a resumed evaluator to use this revision.

The complete classifier tables above apply unchanged. In particular:

| Evaluation outcome | Handling |
| --- | --- |
| Plan/empty plan, explicit no-plan/search exhaustion, input/capability rejection | Return immediately; VAL decides plan correctness |
| Terminal timeout, Planutils error, ambiguous crash/OOM | Up to two retries with 5/15-second backoff; retain only the final outcome for scoring |
| Temporary network/HTTP/429/protocol failure | Same bounded controller; poll failures retry the same task ID |
| Persistent `PENDING` | Poll the same task for at most 180 seconds, then record an infrastructure failure; no duplicate known pending job |
| `public_then_local` exhausted public recovery or pending limit | Switch to the 90-second local backend with its own bounded budget and health check |
| Final infrastructure/guard failure | Write this problem's `_error.txt` with the actual reason/evidence and continue the batch; never call it proven unsolvable |

There is no additional outer retry loop for `ExternalCallInvalid`, so evaluator
retry budgets do not multiply. Missing PDDL causes no solver request. Each
evaluation appends restricted `*_solver_events.jsonl` evidence with a request
ID, policy, backend, input paths/hashes, physical responses, retry/fallback,
accepted solve charge and final evaluator outcome. Task-wait guard failures
retain the last observed response and task URL even without a formatted error.
Evaluation runs after the agent clock has stopped: no retry/backoff is added to
agent time or action metrics. Physical evaluator wall time is recorded separately.
Successful re-evaluation replaces a stale error; failure removes a stale plan.
Campaign operators must archive replaced evaluation artifacts as appropriate;
immutable agent completions/traces are never overwritten by evaluation.

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
PYTHONPATH=source:tests .venv/bin/python -m unittest test_solver_fallback test_external_calls_gateway
```

The integration tests require loopback socket permission and use simulated
services, not real model credits or public solver capacity. Optional live smoke
tests must be explicitly authorized and run only after these pass.
