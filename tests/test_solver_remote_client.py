from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

SOURCE_DIR = Path(__file__).resolve().parents[1] / "source"
if str(SOURCE_DIR) not in sys.path:
    sys.path.insert(0, str(SOURCE_DIR))

from agent_formalizer.tools.solver import remote_client


class FakeUrlopenResponse:
    status = 200

    def __init__(self, body: bytes):
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self) -> bytes:
        return self.body


class RemoteSolverDiagnosticTests(unittest.TestCase):
    def test_non_json_response_body_is_preserved_in_failure(self):
        response = FakeUrlopenResponse(b"upstream proxy error")
        with patch.object(remote_client.urllib.request, "urlopen", return_value=response):
            passed, diagnostic = remote_client.solve_pddl(
                "(define (domain mock))",
                "(define (problem mock-problem) (:domain mock))",
            )

        self.assertFalse(passed)
        self.assertIn("stage: submit", diagnostic)
        self.assertIn("response was not valid JSON", diagnostic)
        self.assertIn("response_body:\nupstream proxy error", diagnostic)


if __name__ == "__main__":
    unittest.main()
