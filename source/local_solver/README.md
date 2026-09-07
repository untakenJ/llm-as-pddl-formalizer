# Lightweight local Planutils solver

This directory provides a small planning.domains-compatible solver service for
the repository. It intentionally omits Flask, Celery, Redis, MySQL, and Flower.
The HTTP process owns a bounded queue and a fixed pool of Planutils worker
containers. Each worker executes one task at a time under an independent Docker
cgroup.

The worker imports Planutils' installed package/service manifest and uses its
declared command and output glob. This keeps `dual-bfws-ffparser` execution
aligned with the package mechanism used by the public planning-as-a-service
deployment.

The compatibility boundary intentionally mirrors the two relevant official
implementation points rather than copying the full service: the official
[`docker-compose.yml`](https://github.com/AI-Planning/planning-as-a-service/blob/main/server/docker-compose.yml)
runs its Celery worker as privileged, and official
[`tasks.py`](https://github.com/AI-Planning/planning-as-a-service/blob/main/server/celery-queue/tasks.py)
materializes the Planutils manifest before invoking `timeout ... planutils
run`. This local service imports Planutils for that manifest and preserves the
same HTTP task/result shape, while replacing the database, broker, Celery, and
Flask processes with a standard-library HTTP server and bounded thread pool.

## Build the worker image

```bash
docker build -t pddl-local-solver:planutils-v1 source/local_solver
```

The default image installs only `dual-bfws-ffparser`, which is the benchmark
default. To add the optional `lama-first` compatibility path:

```bash
docker build --build-arg INSTALL_LAMA=1 \
  -t pddl-local-solver:planutils-v1 source/local_solver
```

Then start the service with both packages explicitly allowed:

```bash
python3 source/local_solver/server.py \
  --solver dual-bfws-ffparser --solver lama-first
```

The Dockerfile follows the public service's construction, but pins the
`aiplanning/planutils` base by manifest digest instead of consuming mutable
`latest`. It installs Planutils packages with `planutils install -f -y`.
Record the final built image ID/digest with benchmark results; updating either
the base digest or installed package artifacts is a new solver runtime revision.

## Start the service

```bash
python3 source/local_solver/server.py
```

For a campaign, run this foreground process under the host's process supervisor
(for example systemd with restart-on-failure). The server handles SIGTERM and
SIGINT by draining its queue and removing only the worker containers it owns.

Defaults:

- one worker and therefore one simultaneous solve;
- 4096 MiB memory and no additional swap per worker;
- one CPU and 256 PIDs per worker;
- 60 second planner deadline;
- port 8769;
- only loopback and Docker-private client addresses are accepted.
- `privileged` worker compatibility, matching the official
  `planning-as-a-service` Celery worker so Planutils SIF packages can mount and
  run reliably. The privilege changes only the container runtime permission;
  it does not change the planner, manifest, input, deadline, or cgroup limits.

This mode has materially greater host security exposure than an ordinary
container. The service therefore gives workers no network, accepts only an
allowlisted solver package, and never invokes a caller-provided shell command.
`--worker-security restricted` or `userns` reduce privilege, but SIF-backed
planners may fail to start on the host; such a failure is infrastructure
failure, not evidence that a PDDL problem is unsolvable.

Example with two workers and a 90 second deadline:

```bash
python3 source/local_solver/server.py \
  --workers 2 \
  --memory 4096m \
  --memory-swap 4096m \
  --timeout 90
```

The host evaluator uses `http://127.0.0.1:8769`. The per-attempt solver gateway
uses `http://host.docker.internal:8769`; the agent container still sees only
`http://solver-gateway:8768` and requires no behavioral or command change.

## Campaign lifecycle contract

For every new or resumed campaign, first resolve and freeze the benchmark
profile. If its effective `solver_backend` is `local`, the campaign launch has
the following fixed infrastructure steps:

1. Ensure exactly one compatible, long-lived local solver service is available
   on port 8769. Run it under systemd or an equivalent host supervisor with
   restart-on-failure; do not tie it to an interactive terminal or Codex process,
   and do not start one service per case.
2. Before scheduling the first case, require a successful response from
   `http://127.0.0.1:8769/__benchmark__/health`. Verify its backend, image ID,
   allowed solver set (whose installation service startup has already verified),
   worker count, planner timeout, worker security mode, and CPU/memory/PID limits
   against the campaign's intended operational setup.
3. Save the complete secret-free health response with a UTC observation time as
   `<campaign-output>/local_solver_preflight/<UTC-timestamp>.json`. Campaign
   launch notes or the operational manifest should reference this file. This is
   operational provenance; it does not replace or alter
   `resolved_config_sha256`.
4. Use the same selected backend for agent-visible solver tools and
   post-generation `run_solver.py` evaluation. A health or reachability failure
   is solver infrastructure failure. Never silently route affected requests to
   public planning.domains and never score evaluator unavailability as an
   incorrect PDDL result.
5. On resume, repeat the health check and append or preserve new immutable
   preflight evidence rather than overwriting the original observation. A
   supervisor restart is acceptable only when the effective image and resource
   configuration still match the frozen campaign setup.
6. At campaign completion, stop the service only if it was created exclusively
   for that campaign. A deliberately shared host service may remain running;
   do not terminate it merely because one campaign finished.

If the resolved profile explicitly selects `public`, this local-service
prerequisite does not apply. Backend selection remains experimental identity;
service lifecycle and resource realization are operational provenance.

## Select the backend

Local is the repository default for `run_solver.py`,
`agent_formalizer/run_formalizer_agent.py`, `sweep_agent_pipeline.py`, and the
formalizer-API evaluation path. Bundled benchmark profiles explicitly resolve
`solver_backend: "local"`, and the mode is always included in resolved benchmark
identity because solver responses can affect agent behavior. Start this service
before a run; local health failure is reported as infrastructure failure.

Historical frozen profiles that omit `solver_backend` retain their original
public-backend interpretation and hashes. This compatibility rule exists only
for old study resume; new bundled profiles do not rely on an implicit mode.

Use `--solver-backend public` to opt into the public planning.domains service
for a new, separately identified experiment. Custom URLs remain available via
`--solver-base-url` for host evaluation and `--solver-container-base-url` for
the per-attempt solver-gateway sidecar.

The non-agent `sweep_pipeline.py` applies the same default to its formalizer-API
evaluation stage.
