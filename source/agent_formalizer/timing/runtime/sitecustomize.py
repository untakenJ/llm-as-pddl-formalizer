"""Explicit logical-deadline-v1 bootstrap; never changes physical clocks."""
import os
if os.environ.get("BENCHMARK_DEADLINE_DIR"):
    from native_deadlines import install
    install()
