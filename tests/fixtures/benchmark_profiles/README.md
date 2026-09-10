# Historical profile fixtures

These are byte-preserved inputs for legacy configuration, timing, and minimum
adapter regression tests. They are not supported campaign presets and must not
be selected as the starting point of a new experiment.

The only maintained campaign baseline is
`source/agent_formalizer/configs/benchmark_profiles/native_baseline_v1.json`.
Frozen study profiles remain authoritative for resuming their own studies.
Do not modernize these fixtures when updating the production baseline: their
purpose is to verify that existing explicit/frozen configurations still load.
