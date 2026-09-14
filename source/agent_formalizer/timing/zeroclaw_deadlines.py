"""Build a content-addressed, narrowly patched ZeroClaw runtime.

Never changes the installed binary/source or its runtime lock. The derived
binary retains the recorded original release/default-feature build settings.
Named shell/model-gateway deadlines and propagation of the non-secret runtime
into the env-cleared child are adapted. A separate passive host-only audit sink
observes native tool outcomes without changing their value or model context.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[3]
SOURCE = (ROOT / '.cache/harness-runtimes/zeroclaw-source').resolve()
PREFIX = (ROOT / '.cache/harness-runtimes/zeroclaw').resolve()
RUNTIME = Path(__file__).with_name('runtime')
AUDIT_MODULE = Path(__file__).resolve().parents[1] / 'results/native_audit.py'
SHELL = 'crates/zeroclaw-runtime/src/tools/shell.rs'
HELPER = 'crates/zeroclaw-runtime/src/tools/benchmark_deadline.rs'
REQWEST = PREFIX / '.cargo/registry/src/index.crates.io-1949cf8c6b5b557f/reqwest-0.12.28'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def identity():
    files = sorted(p for p in SOURCE.rglob('*') if (p.is_file() or p.is_symlink()) and
                   '.git' not in p.relative_to(SOURCE).parts and 'target' not in p.relative_to(SOURCE).parts)
    manifest = {}
    for path in files:
        if path.is_symlink():
            if not path.resolve().is_relative_to(SOURCE):
                raise RuntimeError('ZeroClaw snapshot link escapes source')
            manifest[str(path.relative_to(SOURCE))] = 'symlink:' + os.readlink(path)
        else:
            manifest[str(path.relative_to(SOURCE))] = sha(path)
    digest = hashlib.sha256(json.dumps(manifest, sort_keys=True).encode() +
                            Path(__file__).read_bytes() + (RUNTIME / 'zeroclaw-deadline.rs').read_bytes() +
                            AUDIT_MODULE.read_bytes() +
                            b''.join((REQWEST / p).read_bytes() for p in ('src/async_impl/client.rs', 'src/async_impl/body.rs', 'src/async_impl/response.rs'))).hexdigest()
    return digest, manifest


def transform(source):
    old = 'tokio::time::timeout(Duration::from_secs(timeout_secs), child.wait())'
    if source.count(old) != 1 or source.count('cmd.env_clear();') != 1:
        raise RuntimeError('ZeroClaw native shell timeout source mismatch')
    source = source.replace(old, 'benchmark_deadline::timeout(Duration::from_secs(timeout_secs), child.wait())')
    source = source.replace('cmd.env_clear();', '''cmd.env_clear();
        // Only propagate the adapter's non-secret timing runtime, not ambient
        // credentials or unrelated host variables. Native safe env stays intact.
        for name in ["BENCHMARK_DEADLINE_DIR", "BENCHMARK_DEADLINE_HARNESS",
                     "BENCHMARK_EXTERNAL_CALL_TIMING", "PYTHONPATH", "LD_PRELOAD"] {
            if let Some(value) = std::env::var_os(name) { cmd.env(name, value); }
        }''')
    # Module is adjacent to shell.rs; no upstream workspace dependency changes.
    return source + '\n#[path = "benchmark_deadline.rs"]\nmod benchmark_deadline;\n'


def location():
    digest, manifest = identity()
    return ROOT / '.cache/zeroclaw-deadlines' / digest, manifest


def patch_reqwest(checkout):
    """Keep reqwest's own TimedOut errors and response/body cancellation code.

    Only the timer future for model-gateway's total request deadline changes;
    streaming/connect-only clients and every other endpoint keep native timers.
    """
    vendor = checkout / 'benchmark-reqwest'
    shutil.copytree(REQWEST, vendor)
    helper = (RUNTIME / 'zeroclaw-deadline.rs').read_text()
    helper += '''
pub(crate) type Timer = std::pin::Pin<Box<dyn std::future::Future<Output = ()> + Send + Sync>>;
pub(crate) fn model_timer(duration: Duration, url: &url::Url) -> Timer {
    if std::env::var("BENCHMARK_EXTERNAL_CALL_TIMING").ok().as_deref() == Some("call-checkpoint-v1")
        && url.host_str() == Some("model-gateway") && url.port() == Some(8766) {
        Box::pin(async move { let _ = timeout(duration, std::future::pending::<()>()).await; })
    } else {
        Box::pin(tokio::time::sleep(duration))
    }
}
'''
    (vendor / 'src/benchmark_deadline.rs').write_text(helper)
    lib = vendor / 'src/lib.rs'
    lib.write_text(lib.read_text() + '\n#[cfg(not(target_arch = "wasm32"))]\nmod benchmark_deadline;\n')
    client = vendor / 'src/async_impl/client.rs'
    text = client.read_text()
    old = '.copied()\n            .map(tokio::time::sleep)\n            .map(Box::pin);'
    if text.count(old) != 1:
        raise RuntimeError('reqwest total deadline source mismatch')
    text = text.replace(old, '.copied()\n            .map(|duration| crate::benchmark_deadline::model_timer(duration, &url));')
    # Only total timeout's field/accessor changes type. Native read timeout
    # remains Sleep, including its per-chunk reset behavior.
    for old, new in [
        ('total_timeout: Option<Pin<Box<Sleep>>>', 'total_timeout: Option<crate::benchmark_deadline::Timer>'),
        ('fn total_timeout(self: Pin<&mut Self>) -> Pin<&mut Option<Pin<Box<Sleep>>>>',
         'fn total_timeout(self: Pin<&mut Self>) -> Pin<&mut Option<crate::benchmark_deadline::Timer>>'),
    ]:
        if text.count(old) != 1:
            raise RuntimeError('reqwest total deadline field mismatch')
        text = text.replace(old, new)
    client.write_text(text)
    body = vendor / 'src/async_impl/body.rs'
    text = body.read_text()
    if text.count('Pin<Box<Sleep>>') != 3:
        raise RuntimeError('reqwest body total deadline source mismatch')
    body.write_text(text.replace('Pin<Box<Sleep>>', 'crate::benchmark_deadline::Timer'))
    response = vendor / 'src/async_impl/response.rs'
    text = response.read_text()
    if text.count('total_timeout: Option<Pin<Box<Sleep>>>') != 1:
        raise RuntimeError('reqwest response total deadline source mismatch')
    text = text.replace('total_timeout: Option<Pin<Box<Sleep>>>', 'total_timeout: Option<crate::benchmark_deadline::Timer>')
    response.write_text(text.replace('use tokio::time::Sleep;\n', ''))
    cargo = checkout / 'Cargo.toml'
    cargo.write_text(cargo.read_text() + '\n[patch.crates-io]\nreqwest = { path = "benchmark-reqwest" }\n')
    # Replace only this registry entry by a same-version local patch. No
    # dependency versions are resolved or upgraded during the offline build.
    lock = checkout / 'Cargo.lock'
    text = lock.read_text()
    prefix = 'name = "reqwest"\nversion = "0.12.28"\n'
    before, after = text.split(prefix, 1)
    lines = after.splitlines(keepends=True)
    if not lines[0].startswith('source = ') or not lines[1].startswith('checksum = '):
        raise RuntimeError('reqwest lock entry mismatch')
    lock.write_text(before + prefix + ''.join(lines[2:]))


def prepared():
    directory, _ = location()
    manifest_path = directory / 'manifest.json'
    if not manifest_path.is_file():
        raise RuntimeError('Build the locked ZeroClaw checkpoint overlay first: python -m agent_formalizer.timing.zeroclaw_deadlines')
    manifest = json.loads(manifest_path.read_text())
    binary = directory / 'zeroclaw'
    if not binary.is_file() or sha(binary) != manifest['binary_sha256']:
        raise RuntimeError('ZeroClaw checkpoint overlay binary mismatch')
    return binary, manifest


def build():
    from agent_formalizer.results.native_audit import instrument_zeroclaw
    directory, source_manifest = location()
    if (directory / 'manifest.json').exists():
        return prepared()
    directory.mkdir(parents=True, exist_ok=True)
    checkout = directory / 'source'
    if not checkout.exists():
        shutil.copytree(SOURCE, checkout, symlinks=True, ignore=shutil.ignore_patterns('.git', 'target', '__pycache__'))
        shell = checkout / SHELL
        shell.write_text(transform(shell.read_text()))
        shutil.copy2(RUNTIME / 'zeroclaw-deadline.rs', checkout / HELPER)
        patch_reqwest(checkout)
        tool_source = checkout / 'crates/zeroclaw-runtime/src/agent/tool_execution.rs'
        tool_source.write_text(instrument_zeroclaw(tool_source.read_text()))
    else:
        if (checkout / SHELL).read_text() != transform((SOURCE / SHELL).read_text()):
            raise RuntimeError('Derived source changed; refusing unsafe build resume')
        tool_relative = 'crates/zeroclaw-runtime/src/agent/tool_execution.rs'
        if (checkout / tool_relative).read_text() != instrument_zeroclaw((SOURCE / tool_relative).read_text()):
            raise RuntimeError('Derived audit source changed; refusing unsafe build resume')
    # Python-only audit collector changes need not recompile identical Rust.
    # Reuse is allowed only after comparing the ENTIRE derived source closure
    # (including patched reqwest, Cargo.lock and all build inputs), not just a
    # tool marker or an unverified cached binary. Retain the original build
    # provenance and explicitly record this byte-identical reuse.
    def closure(root):
        return {str(p.relative_to(root)): ('symlink:' + os.readlink(p) if p.is_symlink() else sha(p))
                for p in sorted(root.rglob('*')) if (p.is_file() or p.is_symlink())
                and not {'.git', 'target', '__pycache__'}.intersection(p.relative_to(root).parts)}
    wanted = None
    for previous_path in sorted(directory.parent.glob('*/manifest.json')):
        if previous_path.parent == directory:
            continue
        previous = json.loads(previous_path.read_text())
        if previous.get('source_sha256') != source_manifest:
            continue
        previous_binary = previous_path.parent / 'zeroclaw'
        previous_source = previous_path.parent / 'source'
        if not previous_source.is_dir() or not previous_binary.is_file() or sha(previous_binary) != previous.get('binary_sha256'):
            continue
        if wanted is None:
            wanted = closure(checkout)
        if closure(previous_source) != wanted:
            continue
        binary = directory / 'zeroclaw'
        shutil.copy2(previous_binary, binary)
        if sha(binary) != previous['binary_sha256']:
            raise RuntimeError('Reused ZeroClaw binary copy mismatch')
        manifest = {**previous, 'adapter_sha256': sha(__file__),
                    'native_audit_sha256': sha(AUDIT_MODULE),
                    'equivalent_compiled_source_reuse': str(previous_path),
                    'verified_derived_source_sha256': hashlib.sha256(json.dumps(wanted,sort_keys=True).encode()).hexdigest()}
        temporary = directory / 'manifest.json.tmp'
        temporary.write_text(json.dumps(manifest,indent=2) + '\n')
        temporary.replace(directory / 'manifest.json')
        return binary, manifest
    env = {**os.environ, 'CARGO_HOME': str(PREFIX / '.cargo'), 'RUSTUP_HOME': str(PREFIX / '.rustup'),
           'PATH': str(PREFIX / '.cargo/bin') + os.pathsep + os.environ.get('PATH', '')}
    target = ROOT / '.cache/zeroclaw-deadlines/build-target'
    command = [str(PREFIX / '.cargo/bin/cargo'), 'build', '--release', '--locked', '--offline',
               '--bin', 'zeroclaw', '--jobs', '2', '--target-dir', str(target)]
    # The original installed artifact uses release/default features. Do not
    # choose a smaller harness feature set or optimize its behavior for the task.
    subprocess.run(command, cwd=checkout, env=env, check=True)
    binary = directory / 'zeroclaw'
    shutil.copy2(target / 'release/zeroclaw', binary)
    manifest = {'implementation': 'zeroclaw-shell-checkpoint-v1',
                'source_sha256': source_manifest, 'binary_sha256': sha(binary),
                'adapter_sha256': sha(__file__), 'deadline_helper_sha256': sha(RUNTIME / 'zeroclaw-deadline.rs'),
                'native_audit_sha256': sha(AUDIT_MODULE),
                'build_command': command, 'original_binary_sha256': sha(PREFIX / '.cargo/bin/zeroclaw'),
                'physical_clocks_modified': False,
                'coverage': ['native Rust shell timeout', 'GNU timeout in shell children',
                             'reqwest model-gateway total request/body timeout (same native error)'],
                'reqwest_source_sha256': {p: sha(REQWEST / p) for p in ('src/async_impl/client.rs', 'src/async_impl/body.rs', 'src/async_impl/response.rs')},
                'limitations': ['provider streaming has native connect timeout only, unchanged',
                                'arbitrary user timers and non-gateway HTTP timers unchanged']}
    temporary = directory / 'manifest.json.tmp'
    temporary.write_text(json.dumps(manifest, indent=2) + '\n')
    temporary.replace(directory / 'manifest.json')
    return binary, manifest


if __name__ == '__main__':
    argparse.ArgumentParser(description=__doc__).parse_args()
    binary, _ = build()
    print(binary)
