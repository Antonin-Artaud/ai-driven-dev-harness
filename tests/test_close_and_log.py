"""Close step, decision log, heartbeat and hook configuration smoke test."""

import json
import os
import subprocess
import sys
import unittest

from support import BRANCH, CLOSE_WORKFLOW, PLUGIN_ROOT, PRE_TOOL_USE, SLUG, TempGitRepo, load_module, run_script

wg = load_module("pre_tool_use", PRE_TOOL_USE).wg
HOOKS_FILE = PLUGIN_ROOT / "com.github.copilot" / "hooks" / "hooks.json"


class CloseWorkflowTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.repo = TempGitRepo()

    def tearDown(self) -> None:
        self.repo.cleanup()

    def close(self, *args: str):
        proc = subprocess.run(
            [sys.executable, str(CLOSE_WORKFLOW), "--repo", str(self.repo.path), *args],
            capture_output=True,
            env=self.repo.env,
            timeout=60,
        )
        return proc.returncode, json.loads(proc.stdout.decode("utf-8"))

    def test_close_archives_and_clears_current(self) -> None:
        self.repo.write_workflow(phase="pr-open", pull_request=7)
        code, result = self.close("--reason", "PR completed")
        self.assertEqual(code, 0, result)
        self.assertEqual(result["archived_to"], f".ai/archive/{SLUG}")
        archived = self.repo.path / ".ai" / "archive" / SLUG
        state = json.loads((archived / "state.json").read_text(encoding="utf-8"))
        self.assertEqual(
            (state["phase"], state["closed_from"], state["close_reason"]), ("done", "pr-open", "PR completed")
        )
        self.assertFalse((self.repo.path / ".ai" / "current").exists())
        self.assertFalse((self.repo.path / ".ai" / SLUG).exists())
        self.assertIsNone(wg.load_workflow(self.repo.path))
        self.repo.write_workflow(phase="challenge")
        code, result = self.close()
        self.assertEqual(code, 0)
        self.assertTrue(result["archived_to"].startswith(f".ai/archive/{SLUG}-"))

    def test_nothing_to_close(self) -> None:
        code, result = self.close()
        self.assertEqual(code, 1)
        self.assertFalse(result["ok"])


class LogAndHeartbeatTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.repo = TempGitRepo()
        self.repo.git("switch", "-c", BRANCH)
        self.repo.write_workflow(phase="build")

    def tearDown(self) -> None:
        self.repo.cleanup()

    def shell(self, command: str) -> dict:
        payload = {"cwd": str(self.repo.path), "tool_name": "run_in_terminal", "tool_input": {"command": command}}
        return run_script(PRE_TOOL_USE, payload, self.repo.env)

    def test_decisions_are_logged_without_credentials(self) -> None:
        self.shell("git push https://user:s3cr3t@dev.azure.com/o/p/_git/r --force")
        self.shell("git status")
        entries = self.repo.log_entries()
        self.assertEqual(len(entries), 1, "only decisions are logged")
        entry = entries[0]
        for key in ("at", "hook", "tool", "decision", "reason", "head", "phase"):
            self.assertIn(key, entry)
        self.assertEqual((entry["hook"], entry["decision"], entry["phase"]), ("PreToolUse", "deny", "build"))
        self.assertEqual(entry["head"], self.repo.head())
        self.assertNotIn("s3cr3t", json.dumps(entries))

    def test_redaction(self) -> None:
        for secret in (
            "https://user:s3cr3t@dev.azure.com/o",
            "--token s3cr3t",
            "--password=s3cr3t",
            "Authorization: Basic s3cr3t",
            "AZURE_DEVOPS_EXT_PAT=s3cr3t",
            "Bearer s3cr3t",
        ):
            with self.subTest(secret=secret):
                self.assertNotIn("s3cr3t", wg.redact(f"curl {secret} x"))

    def test_heartbeat_is_written_by_the_first_call(self) -> None:
        self.shell("git status")
        heartbeat = self.repo.hook_state()["heartbeat"]
        self.assertEqual(
            heartbeat["version"], json.loads((PLUGIN_ROOT / "plugin.json").read_text(encoding="utf-8"))["version"]
        )
        self.assertIn("at", heartbeat)

    def test_web_tool_use_is_logged(self) -> None:
        payload = {
            "cwd": str(self.repo.path),
            "tool_name": "fetch_webpage",
            "tool_input": {"urls": ["https://example.com"]},
        }
        self.assertEqual(run_script(PRE_TOOL_USE, payload, self.repo.env), {})
        self.assertEqual(self.repo.log_entries()[-1]["decision"], "observed")


class HooksConfigSmokeTestCase(unittest.TestCase):
    """Runs every command of hooks.json through a real shell with PLUGIN_ROOT set."""

    def test_hook_commands_run(self) -> None:
        config = json.loads(HOOKS_FILE.read_text(encoding="utf-8"))
        repo = TempGitRepo()
        try:
            repo.write_workflow(phase="design")
            env = dict(repo.env, PLUGIN_ROOT=str(PLUGIN_ROOT))
            key = "powershell" if os.name == "nt" else "bash"
            for event, entries in config["hooks"].items():
                for entry in entries:
                    with self.subTest(event=event):
                        command = entry[key].replace("${PLUGIN_ROOT}", str(PLUGIN_ROOT))
                        if os.name == "nt":
                            argv = ["powershell", "-NoProfile", "-Command", command]
                        else:
                            argv = ["bash", "-c", entry[key]]
                        payload = {
                            "cwd": str(repo.path),
                            "hook_event_name": event,
                            "tool_name": "read_file",
                            "tool_input": {},
                        }
                        proc = subprocess.run(
                            argv,
                            input=json.dumps(payload).encode(),
                            capture_output=True,
                            env=env,
                            timeout=60,
                            cwd=str(repo.path),
                        )
                        self.assertEqual(proc.returncode, 0, proc.stderr.decode("utf-8", "replace"))
                        self.assertIsInstance(json.loads(proc.stdout.decode("utf-8") or "{}"), dict)
        finally:
            repo.cleanup()


if __name__ == "__main__":
    unittest.main()
