"""Real host descendants and execution-boundary cleanup; no provider calls."""
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

from agent_formalizer.claws.base import AttemptClock, run_process_with_attempt_clock
from agent_formalizer.runtime import process_lifecycle
from agent_formalizer.workspace import AgentWorkspace
from agent_formalizer.configuration.benchmark_profile import load_benchmark_profile
from agent_formalizer.claws.minimum.workspace import MinimumHostWorkspace


class ProcessLifecycleTests(unittest.TestCase):
    SCRIPT = '''
import os,signal,time
r,w=os.pipe()
pid=os.fork()
if pid==0:
    os.close(r); os.setsid(); signal.signal(signal.SIGTERM,signal.SIG_IGN)
    os.write(w,b'x'); os.close(w); time.sleep(60); os._exit(0)
os.close(w); os.read(r,1); os.close(r)
print(pid,flush=True)
ENDING
'''

    def test_normal_exit_reaps_detached_children_and_keeps_exit_status(self):
        proc = subprocess.run(process_lifecycle.command([sys.executable, "-c",
            self.SCRIPT.replace("ENDING", "os._exit(7)")]), capture_output=True,
            text=True, timeout=10)
        self.assertEqual(proc.returncode, 7, proc.stderr)
        self.assertFalse(Path(f"/proc/{int(proc.stdout)}").exists())

    def test_clock_timeout_reaps_detached_children(self):
        with self.assertRaises(subprocess.TimeoutExpired) as error:
            run_process_with_attempt_clock([sys.executable, "-c",
                self.SCRIPT.replace("ENDING", "time.sleep(60)")], clock=AttemptClock(.5))
        self.assertFalse(Path(f"/proc/{int(error.exception.output)}").exists())

    def test_cancel_supervisor_reaps_descendants(self):
        proc = subprocess.Popen(process_lifecycle.command([sys.executable, "-c",
            self.SCRIPT.replace("ENDING", "time.sleep(60)")]), stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, text=True, start_new_session=True)
        try:
            pid = int(proc.stdout.readline())
            process_lifecycle.terminate(proc)
            self.assertFalse(Path(f"/proc/{pid}").exists())
        finally:
            process_lifecycle.terminate(proc)
            proc.communicate(timeout=2)

    def test_monitor_exception_still_terminates_supervisor(self):
        clock = Mock()
        clock.cancellation_reason.side_effect = RuntimeError("monitor unavailable")
        process = Mock()
        with patch("agent_formalizer.claws.base.subprocess.Popen", return_value=process), \
             patch.object(process_lifecycle, "terminate") as terminate:
            with self.assertRaisesRegex(RuntimeError, "monitor unavailable"):
                run_process_with_attempt_clock(["unused"], clock=clock)
        terminate.assert_called_once_with(process)

    def test_minimum_monitor_failure_does_not_skip_process_cleanup(self):
        workspace = MinimumHostWorkspace.__new__(MinimumHostWorkspace)
        workspace.adapter = Mock()
        workspace.stop_model_gateway_monitor = Mock(side_effect=RuntimeError("monitor failure"))
        process = Mock()
        stream = Mock()
        workspace._processes = [process]
        workspace._log_streams = [stream]
        workspace._secret_dir = workspace._control_dir = None
        with patch.object(process_lifecycle, "terminate") as terminate, self.assertLogs(level="ERROR"):
            with self.assertRaisesRegex(RuntimeError, "monitor failure"):
                workspace.cleanup()
        terminate.assert_called_once_with(process)
        stream.close.assert_called_once()
        workspace.adapter.clear_host_execution.assert_called_once()

    def test_workspace_monitor_failure_does_not_skip_other_cleanup(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace = AgentWorkspace("test", "test-container", Mock(), artifact_dir=Path(directory))
            collector = workspace._native_audit_collector = Mock()
            broker = workspace._deadline_broker = Mock()
            record = workspace._network_record = {"token": "test"}
            workspace._network_resources = Mock()
            with patch.object(workspace, "stop_model_gateway_monitor", side_effect=RuntimeError("monitor failure")), \
                 self.assertLogs(level="ERROR"):
                workspace.cleanup()
            collector.close.assert_called_once()
            broker.close.assert_called_once()
            workspace._network_resources.cleanup.assert_called_once_with(record)

    def test_artifact_freeze_stops_tree_instead_of_resuming_background_jobs(self):
        adapter = Mock(resolved_config=load_benchmark_profile().resolve("hermes"))
        with tempfile.TemporaryDirectory() as directory:
            workspace = AgentWorkspace("test", "test-container", adapter, artifact_dir=Path(directory))
            def copy(_source, destination):
                Path(destination).write_bytes(b"original\r\n")
                return True
            commands = []
            running = True
            def run(cmd, **kwargs):
                nonlocal running
                commands.append(cmd)
                output = ""
                if cmd[:2] == ["docker", "inspect"]:
                    output = "true" if running else "false"
                if cmd[:2] == ["docker", "kill"]:
                    running = False
                return subprocess.CompletedProcess(cmd, 0, output, "")
            with patch.object(workspace, "copy_from_container", side_effect=copy), \
                 patch("agent_formalizer.workspace.subprocess.run", side_effect=run):
                result = workspace.freeze_pddl_outputs()
        self.assertEqual(result, {"domain": b"original\r\n", "problem": b"original\r\n"})
        self.assertNotIn(["docker", "unpause", "test-container"], commands)
        self.assertLess(commands.index(["docker", "kill", "test-container"]),
                        commands.index(["docker", "start", "test-container"]))


if __name__ == "__main__":
    unittest.main()
