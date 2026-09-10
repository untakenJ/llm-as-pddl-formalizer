# Automatic invalidation audit — 2026-09-07

The OpenClaw `call-checkpoint-v1` implementation audited initially, revision
`native-concurrency-v2`, no longer invalidates a healthy execution because its
native tools run asynchronously. This audit covers the external-call classifiers,
gateway/host timing controller, native checkpoint driver, and the enclosing
runner invalidators. It is a code/fixture audit, not a retrospective change to
any campaign result or a claim that every future infrastructure failure can be
identified perfectly.

最初审计的 OpenClaw `call-checkpoint-v1` / `native-concurrency-v2` 实现不再因为正常后台
工具执行而无效化 execution。本次审计覆盖外部调用分类、gateway/宿主计时控制器、原生
checkpoint 驱动和外层 runner 的无效化入口；不修改历史实验结果，也不保证能完美识别
所有未来故障。

## Findings and corrections

| Finding | Correction |
| --- | --- |
| Healthy model/solver overlap triggered `external_call_stream_overlap`; model calls shared a singleton control file/lock | Per-request control files; no checkpoint-path serialization lock; healthy overlap uses running wall time, not summed call durations |
| Model state sampled before Docker inspection could be combined with newer call state | Refresh model state after inspection and before choosing timing mode; an old stream snapshot alone never invalidates a healthy call |
| Native exit/cancellation and cleanup could be mistaken for missing control/ACK | Explicit done/cancelled states; native cancellation remains valid; no requirement that a native cleanup handler exits or removes its lease |
| A three-second Node ACK timeout rejected a legitimately busy event loop | Host progress keeps the transport channel alive; ordinary busy time is charged, with the benchmark budget as outer bound |
| An undeclared 128-Node-participant limit could reject native process parallelism | Removed this adapter-only invalidation threshold; existing configured execution/container budgets remain |
| Cyclic context serialization or a throwing native timeout callback could enter the protocol-failure path | Healthy cyclic contexts are allowed; unsupported snapshots matter only during actual recovery; native callback exceptions retain native exception semantics |
| Generic HTTP/request and error-text matches were too broad | HTTP 400/415/422 return their actual rejection; generic “does not exist/contain”, “Adaptor Not Found”, and local ValueError/KeyError are not immediate configuration proof |

以上修复分别解决：正常并发被拦截、跨时刻状态混读、正常退出/清理被误判、原生忙碌被
误判、上下文/回调的正常语言行为被归入协议异常，以及 solver 错误文本过度归因。

## Current checkpoint automatic invalidators

| Top-level reason | Required evidence / decision | Native behavior that must **not** trigger it |
| --- | --- | --- |
| `provider_transient_exhausted` | Direct upstream transient HTTP/transport failures exhaust the versioned physical retry budget | Benchmark-owned 429 call/action limits; invalid request/context/schema responses |
| `post_commit_stream_failure` | Direct upstream/gateway failure after semantic stream delivery; or explicit successful Docker inspection showing the gateway has exited during an active stream | Downstream cancellation first, benchmark deadline first, ambiguous termination order, or an unsuccessful Docker inspect alone |
| `external_call_unrecoverable` | A solver policy invalidation with its exact classification and response/transport evidence retained; see below | PDDL syntax/type errors, no-plan results, unsupported requirements, capability limits, warnings accompanying a plan |
| `external_call_control_failed` | Failure of benchmark-owned control/transport/protocol or gateway bookkeeping that prevents faithful accounting/delivery | Healthy concurrency, ordinary native timeout/exit, slow cleanup, or a merely busy Node loop |
| `external_call_recovery_unsafe` | A nonzero rollback count from an actual external failure crosses an overlapping group already running on wall time; or an actual recovery fails the native context/concurrent-work check | Overlap or context changes with zero discarded physical requests |

`external_call_recovery_unsafe` does **not** mean the agent misbehaved. It means
an actual external failure needs time/context recovery that this adapter cannot
prove transparent. It is not proof that every ambiguous solver timeout was an
infrastructure failure. This is a conservative fairness fallback, not a reason
to sample again until the agent chooses a synchronous strategy.

`external_call_recovery_unsafe` 不表示 agent 违规，而表示实际外部失败发生后，适配器
无法保证恢复对并发计时和上下文透明；它也不证明每次不明原因 solver timeout 都确属
infra。这个兜底不能变成“不断重跑直到 agent 恰好不使用后台工具”。

The Node detail `checkpoint_business_state_changed`, participant transport
details, and `call_checkpoint_control_failed` are diagnostic causes, not
additional independent sampling policies. `external_call_cancelled`,
`native_deadline`, `native_done`, and `native_busy_deadline` are **not** automatic
infra invalidators. The checkpoint resolved invalidator list contains the
recovery-specific guard instead of the old unconditional overlap reason.

Node 的 context/participant 细分字段是诊断原因，不是额外采样策略。
`external_call_cancelled`、`native_deadline`、`native_done` 和 `native_busy_deadline`
均不是自动 infra 无效化理由。当前 checkpoint 的 resolved 配置列表已使用恢复专用
guard，不再使用无条件 overlap guard。

## Solver classifications behind `external_call_unrecoverable`

| Classification | Handling and rationale |
| --- | --- |
| `solver_rate_limited`, `solver_service_unavailable` | Bounded retry, then invalidation: no usable service access; HTTP 408/504 are not themselves planner CPU timeout evidence |
| `solver_transport_error`, `solver_response_protocol_error` | Bounded same-stage/same-task retry, then invalidation: network/HTTP/JSON protocol not restored |
| `solver_certificate_error`, `solver_authentication_error` | Immediate invalidation: fixed service authentication/trust unavailable; do not bypass TLS or switch credentials |
| `solver_untrusted_redirect`, `solver_untrusted_task_url` | Immediate invalidation: cannot follow an unconfigured origin; no request sent to it |
| `solver_protocol_configuration_error` | Fixed-route 404/405 or anchored required-argument/package absence; not arbitrary PDDL-related text |
| `solver_runtime_configuration_error` | Fixed runtime/file/permission/package failure, not parser rejection |
| `solver_worker_service_error` | Bounded retry, then invalidation for worker protocol/service failure without input-dependent terminal evidence |
| `solver_unexplained_service_error`, `solver_server_side_error`, `solver_http_error` | Submit-stage failures have no confirmed terminal solve evidence and can invalidate after retries; poll-stage ambiguous terminal errors use the repeated-input rule |
| `solver_recovery_deadline` | Actual recovery exhausts its outer wall budget; result remains unresolved |
| `solver_task_wait_exhausted` | The same accepted task remains PENDING for the configured wait bound; queue/lost-task/stuck-worker state is not evidence of bad PDDL; do not submit duplicate tasks |
| Ambiguous terminal reason with mixed retry exhaustion | E.g. two network failures then one planner timeout: invalidate unresolved, because network failures cannot count as three repeated input-dependent failures |

These are infrastructure/unresolved-service decisions, not deductions that an
agent's PDDL is right or wrong. HTTP 400/415/422 and 413 are returned to the agent.
Parser/typing errors, unsupported PDDL features and completed no-plan searches
are returned immediately. Repeated terminal planner timeout/Planutils error,
OOM-like failure, crash, missing terminal result or local ValueError/KeyError
is ambiguous: after the required terminal repetitions, return the final actual
diagnostic and charge only its solve, provided isolated transparent recovery
was possible. An existing usable plan takes precedence over timeout/warnings.

这些是基础设施或服务未决状态裁定，不是 PDDL 正误裁定。400/415/422、413、语法/类型
错误、能力限制和明确无解结果应交给 agent。重复出现的终端 timeout、Planutils error、
疑似 OOM、崩溃、缺失终态或本地 ValueError/KeyError 仍属不明原因；在可安全透明恢复
的前提下，达到规定重复次数后只返回最后一次真实诊断并计其耗时。已有可用 plan 时
不得因附带 warning/timeout 将其隐藏。

## Enclosing runner reasons

The pre-existing `container_start_failed`, `gateway_start_failed`,
`solver_gateway_start_failed`, `task_seed_failed`, `runtime_lock_mismatch`,
`required_evidence_failed`, `runner_internal_error` and `gateway_pause_failed`
refer to benchmark startup/isolation/collection/control failures. Ordinary
native nonzero exit, timeout, invalid tool arguments, missing/bad PDDL and
solver/VAL failure are not synonyms for these reasons. Required-validation
failure or an artifact-copy hash mismatch is runner evidence failure; optional
reasoning/session collection failure remains a warning. Post-generation
evaluation failure remains separately re-evaluable and does not invalidate
agent generation.

这些既有 runner 错误对应启动、隔离、输入部署、runtime 身份、必要证据或控制失败。
原生非零退出、timeout、工具参数错误、未生成/生成错误 PDDL 和 solver/VAL 失败不应
自动映射为这些原因。可选 reasoning/session 采集失败仍只告警；事后 evaluation 失败
仍应在相同 PDDL 上重评，不反向无效化 agent execution。

## Verification and scope

Regression fixtures exercise independent overlapping controls, two model calls
plus a solver, once-only wall charging, a stale model snapshot across Docker
inspection, actual-retry unsafe recovery, ordinary cancellation, long native
cleanup, a busy Node event loop, cyclic native context and throwing native
callbacks. Docker fixtures use the installed OpenClaw `exec`, its unchanged
default background yield and `process` poll tool, real streaming SDK/native
watchdogs, and fake local model/solver servers. They also retain serial model
429 and solver timeout recovery and genuine deadline tests. No real model key,
public solver traffic, historical completion or validity override is required.

测试覆盖独立并发调用、并行墙钟只计一次、跨 Docker 检查的旧状态、真实恢复不安全、
正常取消/清理/忙碌/循环上下文/回调异常，以及真实 OpenClaw exec 默认后台执行、
process 查询、流式 SDK 和原生 watchdog；保留串行 429/solver timeout 恢复测试。
后端均为本地模拟服务，没有调用真实模型或公共 solver，也不修改历史 completion 或
有效性裁定。

The old `logical-deadline-v1` and no-native-timer legacy escrow paths retain their
versioned single-owner/Docker-pause behavior; they are **not certified here as
transparent for arbitrary asynchronous work** and are not the fixed checkpoint
path. At that v2 revision, other harnesses fail checkpoint preflight until native timer
coverage exists. Do not transfer the OpenClaw result to Hermes/Nanobot/Generic/
ZeroClaw or silently treat an old frozen campaign as upgraded. The new resolved
invalidator list and implementation hashes require an explicit new run/revision.

旧 `logical-deadline-v1` 和不适配原生 timer 的 legacy escrow 路径保留其版本化行为，
本审计**不认证它们支持任意异步行为的透明恢复**，也不将它们视为已修复的 checkpoint
路径。在该 v2 修订中其他 harness 尚不能通过 checkpoint preflight；不能将 OpenClaw 的验证结论
直接推广到其他 harness，或静默升级旧 campaign。新的 resolved 无效化列表和实现
hash 必须通过明确的新运行/修订启用。

Recorded verification: the final relevant regression selection ran 93 tests, with
91 passing and two existing opt-in skips. All six OpenClaw Docker checkpoint
tests passed; the default-background fixture was additionally rerun with two
simultaneous SDK model requests during the pending solver call and passed.
The final background rerun observed a 10.353 s native background yield and 15.011 s command/
model/poll sequence, with no invalidation and no duplicate wall charging.
These are fixture timings, not a 200-case campaign speed estimate.

验证记录：最终相关回归选择共 93 项，91 项通过、2 项按原有 opt-in 条件跳过；六项
OpenClaw Docker checkpoint 测试全部通过。默认后台 fixture 另以 solver 未结束时
并发两次 SDK 模型请求复测并通过，最终观察到 10.353 秒自动转后台、15.011 秒完成命令/
模型/查询序列，无无效化或墙钟重复扣减。这些是 fixture 耗时，不是 200 题 campaign
速度估算。

One later broad rerun exposed an existing GNU-timeout fixture race: the test
could suspend the process group before the child actually entered `sleep`.
The fixture now waits for the child's kernel sleep before suspension (production
GNU-timeout code unchanged); three consecutive isolated reruns passed.

后续一次全套复测暴露了旧 GNU-timeout fixture 的同步竞态：可能在子进程真正进入
sleep 前就暂停进程组。测试现改为先确认子进程进入内核 sleep，生产 GNU-timeout
代码未改；连续三次单独复测通过。

## Multiharness follow-up: native-concurrency-v3-multiharness

Generic, Hermes, Nanobot and ZeroClaw now have named, source-checked native
deadline adaptations; see the coverage table in README. Their native policies,
tool schemas, prompts, timeout values and scheduling defaults are retained.
Python deadline reads are local; its asynchronous transport overlay is scoped
to model/solver gateway peers. ZeroClaw uses a separately hashed derived binary
and unchanged dependency versions, not a replacement of the installed binary.

Generic、Hermes、Nanobot 和 ZeroClaw 现已加入具名且校验源代码的原生计时适配，
具体覆盖见 README。原生策略、工具 schema、prompt、timeout 数值和调度默认值
不变。Python 的时钟读取在进程内完成，异步传输层适配仅针对模型/solver gateway；
ZeroClaw 使用单独哈希的派生二进制，不替换既有安装，也不升级依赖版本。

Two native lifecycle races were found by the new tests. A native timeout
callback can close its socket just before its process exits: disconnect-only
handling now briefly confirms kernel exit before calling it a control fault.
More importantly, a native timeout can trigger the next model call before the
previous solver candidate finishes its delivery barrier. Its already-settled
`native_deadline` verdict now takes precedence and cannot be reclassified as a
healthy concurrent release. This preserves the rejected candidate and its
truncated time charge; it does not suppress the next native model decision.

新增测试发现了两个原生生命周期竞态：原生超时回调可能先关 socket、随后才退出
进程，因此只在异常断连路径短暂确认内核退出状态。另一个情况是原生超时立即引发
下一次模型调用，但旧 solver 候选结果还在交付屏障中；现已结算的 `native_deadline`
裁定不会再被误改为正常并发释放，保留丢弃结果和截断计时，也不禁止后续模型决策。

Verification includes pinned native model→solver→model loops for all four added
harnesses; hidden 429/solver timeout recovery; genuine Python/Rust cancellation;
Hermes/Nanobot native background process→model→poll sequences; and the prior six
OpenClaw Docker cases. All HTTP backends in these adapter fixtures are scripted
local services. Genuine ambiguous solver failures and unrecoverable concurrent
recovery still require the existing routing/validity rules: successful fixtures
do not certify arbitrary third-party SDKs, user-program timers or filesystem
rollback. Short timeout values occur only in explicit test fixtures, never in
the campaign profile.

验证包括四个新增 harness 的原生模型→solver→模型流程、隐藏 429/solver 超时恢复、
真实 Python/Rust 超时取消、Hermes/Nanobot 的后台进程→模型→查询流程，以及原有
六项 OpenClaw Docker 测试。上述适配测试的 HTTP 后端全部为本地模拟服务。测试
通过不表示支持任意第三方 SDK、用户程序计时器或文件系统回退；原因不明的 solver
失败和无法安全恢复的并发仍适用现有处理规则。缩短 timeout 仅用于显式测试 fixture，
不进入 campaign 配置。

Final default regression: 343 tests, 303 passed and 40 opt-in skips. Native
callback/exit boundary stress passed 50 consecutive iterations. The GNU
process-suspension fixture now waits for both the sleeping child and the armed
parent watchdog (not merely one); ten consecutive iterations passed. The
driver also handles signal-interrupted control reads and explicitly reports
adapter-control faults. Native deadline receipts are persisted before sidecar
teardown, and seconds/milliseconds conversions share a tiny due tolerance so
floating-point roundoff cannot leave an already-due native timer parked.

最终默认回归为 343 项：303 项通过、40 项按 opt-in 条件跳过。原生回调/退出边界
压力测试连续 50 次通过。GNU 暂停测试现同时等待子进程进入 sleep、父进程完成
watchdog 注册，连续 10 次通过。控制驱动处理被信号中断的读取，并明确记录自身
故障。原生超时回执会在 sidecar 清理前落盘；秒/毫秒换算采用一致的微小到期容差，
避免浮点舍入使已到期的 timer 长期停留在暂停状态。
