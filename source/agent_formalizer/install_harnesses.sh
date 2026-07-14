#!/usr/bin/env bash
# Install pinned harness runtimes into the repository's ignored .cache tree.

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
RUNTIME_ROOT="${PDDL_HARNESS_RUNTIME_ROOT:-${ROOT_DIR}/.cache/harness-runtimes}"

HERMES_VERSION="0.18.2"
NANOBOT_VERSION="0.2.2"
GENERIC_COMMIT="e6bbc91631b42026a2bc1e91cb51537d1151aa14"
ZEROCLAW_COMMIT="42fa19711e769d9aa142592bf7c52d43628277e2"

if ! command -v uv >/dev/null 2>&1; then
    printf 'uv is required. Install it first: curl -LsSf https://astral.sh/uv/install.sh | sh\n' >&2
    exit 1
fi

mkdir -p "${RUNTIME_ROOT}"

ensure_venv() {
    local path="$1"
    if [[ ! -x "${path}/bin/python" ]]; then
        uv venv --python 3.12 "${path}"
    fi
}

checkout_commit() {
    local url="$1" path="$2" commit="$3"
    if [[ ! -d "${path}/.git" ]]; then
        if [[ -e "${path}" ]]; then
            printf 'Refusing to replace non-git path: %s\n' "${path}" >&2
            exit 1
        fi
        git clone --filter=blob:none --no-checkout "${url}" "${path}"
    fi
    # A fresh --no-checkout clone has no index and reports every tracked file
    # as deleted. Only apply the dirty-tree guard after the first checkout.
    if [[ -f "${path}/.git/index" ]]; then
        if ! git -C "${path}" diff --quiet || ! git -C "${path}" diff --cached --quiet; then
            printf 'Refusing to overwrite local changes in %s\n' "${path}" >&2
            exit 1
        fi
    fi
    git -C "${path}" fetch --depth 1 origin "${commit}"
    git -C "${path}" checkout --detach "${commit}"
}

install_hermes() {
    local env_path="${RUNTIME_ROOT}/hermes"
    ensure_venv "${env_path}"
    uv pip install --python "${env_path}/bin/python" "hermes-agent==${HERMES_VERSION}"
}

install_nanobot() {
    local env_path="${RUNTIME_ROOT}/nanobot"
    ensure_venv "${env_path}"
    uv pip install --python "${env_path}/bin/python" "nanobot-ai==${NANOBOT_VERSION}"
}

install_generic() {
    local root="${RUNTIME_ROOT}/genericagent"
    checkout_commit \
        "https://github.com/lsdefine/GenericAgent.git" \
        "${root}/repo" \
        "${GENERIC_COMMIT}"
    mkdir -p "${root}/repo/temp"
    ensure_venv "${root}/venv"
    uv pip install --python "${root}/venv/bin/python" "${root}/repo"
}

install_zeroclaw() {
    local source_path="${RUNTIME_ROOT}/zeroclaw-source"
    checkout_commit \
        "https://github.com/zeroclaw-labs/zeroclaw.git" \
        "${source_path}" \
        "${ZEROCLAW_COMMIT}"
    sh "${source_path}/install.sh" \
        --prefix "${RUNTIME_ROOT}/zeroclaw" \
        --prebuilt \
        --without-tui \
        --skip-quickstart \
        --no-modify-path
}

if [[ $# -eq 0 ]]; then
    set -- all
fi
for target in "$@"; do
    case "${target}" in
        all)
            install_hermes
            install_nanobot
            install_zeroclaw
            install_generic
            ;;
        hermes) install_hermes ;;
        nanobot) install_nanobot ;;
        zeroclaw) install_zeroclaw ;;
        generic|genericagent) install_generic ;;
        *)
            printf 'Unknown harness %s (expected all, hermes, nanobot, zeroclaw, generic)\n' "${target}" >&2
            exit 2
            ;;
    esac
done

printf 'Harness runtimes installed under %s\n' "${RUNTIME_ROOT}"
