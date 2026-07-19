# Base image the agent harness runs inside.
#
# Kept deliberately minimal: it only needs a Linux userland with a shell, a
# workspace directory, and enough common tooling for the agent to author and
# sanity-check PDDL files. Harness runtimes and benchmark-owned state/config are
# bind-mounted or provisioned by their adapters, so they are NOT installed here.
#
# glibc note: adapters bind-mount host Node.js/Python/Rust binaries into the
# container, so the base image must be glibc-compatible with those runtimes.
#
# Build:
#   docker build -t pddl-agent-base:latest source/agent_formalizer/docker
#
# The host-side runtime lock selects and verifies the image ID; the container
# itself does not read an ambient image-name override.

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
