from __future__ import annotations

import re
import subprocess
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from agent_formalizer.config import (
    DOCKER_RESOURCE_NAME_MAX,
    container_name,
)
from agent_formalizer.workspace import AgentWorkspace


DOCKER_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")


class DockerResourceNameTests(unittest.TestCase):
    def _container(self, runtime_id: str) -> str:
        return container_name(
            "zeroclaw",
            "blocksworld",
            "Heavily_Templated_BlocksWorld-100",
            (
                "zeroclaw__google-vertex__gemini-3.1-flash-lite__"
                "native-safety-v3--solver-as-tool--38aac4a75e0f"
            ),
            "p100-a1-e1",
            runtime_id=runtime_id,
        )

    def test_same_task_in_concurrent_runs_gets_distinct_names(self):
        first = self._container("run-one")
        second = self._container("run-two")

        self.assertNotEqual(first, second)
        self.assertLessEqual(len(first), DOCKER_RESOURCE_NAME_MAX)
        self.assertLessEqual(len(second), DOCKER_RESOURCE_NAME_MAX)
        self.assertRegex(first, DOCKER_NAME)
        self.assertRegex(second, DOCKER_NAME)

    def test_runtime_id_makes_name_reproducible_when_explicit(self):
        self.assertEqual(self._container("same-run"), self._container("same-run"))

    def test_default_runtime_id_is_unique(self):
        args = (
            "zeroclaw",
            "blocksworld",
            "Heavily_Templated_BlocksWorld-100",
            "model-label",
            "p1-a1-e1",
        )
        self.assertNotEqual(container_name(*args), container_name(*args))

    def test_sidecars_and_network_preserve_parent_uniqueness(self):
        first = AgentWorkspace("case-one", self._container("run-one"), SimpleNamespace())
        second = AgentWorkspace("case-two", self._container("run-two"), SimpleNamespace())

        first_names = {
            first.container_name,
            first.network_name,
            first.gateway_name,
            first.web_gateway_name,
            first.solver_gateway_name,
        }
        second_names = {
            second.container_name,
            second.network_name,
            second.gateway_name,
            second.web_gateway_name,
            second.solver_gateway_name,
        }

        self.assertEqual(len(first_names), 5)
        self.assertEqual(len(second_names), 5)
        self.assertTrue(first_names.isdisjoint(second_names))
        for name in first_names | second_names:
            self.assertLessEqual(len(name), DOCKER_RESOURCE_NAME_MAX)
            self.assertRegex(name, DOCKER_NAME)

    def test_stale_cleanup_cannot_target_another_run(self):
        first = AgentWorkspace("case-one", self._container("run-one"), SimpleNamespace())
        second = AgentWorkspace("case-two", self._container("run-two"), SimpleNamespace())
        second_names = {
            second.container_name,
            second.network_name,
            second.gateway_name,
            second.web_gateway_name,
            second.solver_gateway_name,
        }

        completed = subprocess.CompletedProcess([], 0, "", "")
        with patch(
            "agent_formalizer.workspace.subprocess.run",
            return_value=completed,
        ) as run:
            first._remove_stale_resources()

        targets = {
            command.args[0][-1]
            for command in run.call_args_list
        }
        self.assertTrue(targets.isdisjoint(second_names))

    def test_non_ascii_and_invalid_characters_are_sanitized(self):
        name = container_name(
            "坏/claw",
            "domain with spaces",
            "dataset:one",
            "model@label",
            "p1",
            runtime_id="runtime",
        )

        self.assertRegex(name, DOCKER_NAME)
        self.assertNotIn("坏", name)
        self.assertNotIn("/", name)
        self.assertNotIn(" ", name)


if __name__ == "__main__":
    unittest.main()
