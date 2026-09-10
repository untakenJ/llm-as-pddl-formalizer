// Synchronous, version-bound loader. URLs/resolution/native files stay original.
import { registerHooks } from 'node:module';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';
const root = dirname(fileURLToPath(import.meta.url));
if (process.env.BENCHMARK_EXTERNAL_CALL_TIMING === 'call-checkpoint-v1') {
  const runtime = await import('./node-checkpoints.cjs');
  await runtime.default.ready();
}
const mapping = JSON.parse(readFileSync(join(root, 'node-overlays.json'), 'utf8'));
registerHooks({
  load(url, context, nextLoad) {
    const result = nextLoad(url, context);
    const replacement = mapping[url];
    if (!replacement) return result;
    return { ...result, source: readFileSync(join(root, replacement), 'utf8') };
  },
});
