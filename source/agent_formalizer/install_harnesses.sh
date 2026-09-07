#!/usr/bin/env bash
# Install pinned harness runtimes into the repository's ignored .cache tree.

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
RUNTIME_ROOT="${ROOT_DIR}/.cache/harness-runtimes"
LOCK_ROOT="${ROOT_DIR}/source/agent_formalizer/runtime_requirements"

HERMES_VERSION="0.18.2"
NANOBOT_VERSION="0.2.2"
GENERIC_COMMIT="e6bbc91631b42026a2bc1e91cb51537d1151aa14"
# Unreleased official fix for Gemini thought_signature round-trip (PR #8935).
# No beta/release tag contains 85e0cfaf yet; pin the PR tip and annotate VERSION_NOTE.
ZEROCLAW_COMMIT="85e0cfafbe677590e4fe5947f83673bb49ba0fc2"  # unreleased-pr8935+gemini-thought-signature
ZEROCLAW_VERSION_NOTE="unreleased-pr8935+gemini-thought-signature"
QWEN35_TOKENIZER_REVISION="851bf6e806efd8d0a36b00ddf55e13ccb7b8cd0a"

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
    uv pip sync --python "${env_path}/bin/python" \
        "${LOCK_ROOT}/hermes.txt"
}

install_nanobot() {
    local env_path="${RUNTIME_ROOT}/nanobot"
    ensure_venv "${env_path}"
    uv pip sync --python "${env_path}/bin/python" \
        "${LOCK_ROOT}/nanobot.txt"
}

install_logits() {
    local root="${RUNTIME_ROOT}/logits-bridge"
    local env_path="${root}/venv"
    local model_path="${root}/models/Qwen--Qwen3.5-4B/${QWEN35_TOKENIZER_REVISION}"
    ensure_venv "${env_path}"
    uv pip sync --python "${env_path}/bin/python" \
        "${LOCK_ROOT}/logits-bridge.txt"
    if [[ ! -f "${model_path}/tokenizer.json" ]]; then
        mkdir -p "${model_path}"
        "${env_path}/bin/hf" download Qwen/Qwen3.5-4B \
            config.json tokenizer.json tokenizer_config.json \
            chat_template.jinja vocab.json merges.txt \
            --revision "${QWEN35_TOKENIZER_REVISION}" \
            --local-dir "${model_path}"
    fi
}

install_generic() {
    local root="${RUNTIME_ROOT}/genericagent"
    checkout_commit \
        "https://github.com/lsdefine/GenericAgent.git" \
        "${root}/repo" \
        "${GENERIC_COMMIT}"
    mkdir -p "${root}/repo/temp"
    ensure_venv "${root}/venv"
    uv pip sync --python "${root}/venv/bin/python" \
        "${LOCK_ROOT}/generic.txt"
    uv pip install --python "${root}/venv/bin/python" --no-deps "${root}/repo"
}

install_zeroclaw() {
    local source_path="${RUNTIME_ROOT}/zeroclaw-source"
    local prefix="${RUNTIME_ROOT}/zeroclaw"
    checkout_commit \
        "https://github.com/zeroclaw-labs/zeroclaw.git" \
        "${source_path}" \
        "${ZEROCLAW_COMMIT}"
    # --prebuilt always downloads GitHub releases/latest (still without the fix).
    # Build the pinned PR checkout from source so the binary matches ZEROCLAW_COMMIT.
    (
        cd "${source_path}"
        sh ./install.sh \
            --prefix "${prefix}" \
            --source \
            --without-tui \
            --skip-quickstart \
            --no-modify-path
    )
    printf '%s\n' "${ZEROCLAW_VERSION_NOTE}" > "${prefix}/VERSION_NOTE"
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
            install_logits
            ;;
        hermes) install_hermes ;;
        nanobot) install_nanobot ;;
        logits|logits-bridge) install_logits ;;
        zeroclaw) install_zeroclaw ;;
        generic|genericagent) install_generic ;;
        *)
            printf 'Unknown harness %s (expected all, hermes, nanobot, zeroclaw, generic)\n' "${target}" >&2
            exit 2
            ;;
    esac
done

printf 'Harness runtimes installed under %s\n' "${RUNTIME_ROOT}"
