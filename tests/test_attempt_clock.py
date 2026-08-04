from __future__ import annotations

import unittest
from unittest.mock import patch

from agent_formalizer.claws.base import AttemptClock


class AttemptClockTests(unittest.TestCase):
    def test_infrastructure_pause_does_not_spend_active_time(self):
        now = [100.0]
        with patch(
            "agent_formalizer.claws.base.time.monotonic",
            side_effect=lambda: now[0],
        ):
            clock = AttemptClock(10)
            now[0] = 103.0
            clock.pause(retroactive_seconds=1.0)
            remaining_when_paused = clock.remaining()
            now[0] = 108.0
            self.assertEqual(clock.remaining(), remaining_when_paused)
            clock.resume()
            now[0] = 115.0
            snapshot = clock.snapshot()
            remaining = clock.remaining()

        self.assertEqual(snapshot["wall_duration_seconds"], 15.0)
        self.assertEqual(snapshot["infra_pause_seconds"], 6.0)
        self.assertEqual(snapshot["active_duration_seconds"], 9.0)
        self.assertEqual(remaining, 1.0)


if __name__ == "__main__":
    unittest.main()
