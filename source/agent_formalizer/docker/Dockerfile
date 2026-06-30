# Base image the agent harness runs inside.
#
# Kept deliberately minimal: it only needs a Linux userland with a shell, a
# workspace directory, and enough common tooling for the agent to author and
# sanity-check PDDL files. The OpenClaw runtime itself (Node.js binary, the
# openclaw module dir, and an isolated benchmark ~/.openclaw state dir) is bind-mounted
# (see OpenClawAdapter.container_run_args), so it is NOT installed here.
#
# glibc note: OpenClaw bind-mounts the *host* Node.js binary into the
# container, so the base image must be glibc-compatible with the host. A
# Debian/Ubuntu-derived image (as below) matches typical host setups.
#
# Build:
#   docker build -t pddl-agent-base:latest source/agent_formalizer/docker
#
# Override the image name via $PDDL_AGENT_IMAGE or --image.

FROM python:3.12-slim-bookworm

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        bash ca-certificates coreutils findutils grep sed gawk git curl \
    && rm -rf /var/lib/apt/lists/*

# Workspace the agent authors PDDL into (matches config.CONTAINER_WORKSPACE).
RUN mkdir -p /workspace/input
WORKDIR /workspace

# Default command is overridden by the workspace manager with `tail -f /dev/null`.
CMD ["bash"]
