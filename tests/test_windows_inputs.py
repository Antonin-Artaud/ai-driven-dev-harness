"""Windows-style inputs, exercised on every OS: CRLF files, backslash and upper-case paths,
coarse clocks (a file time slightly ahead of time.time()), cp1252 files."""

import json
import os
import time
import unittest

from support import BRANCH, PRE_TOOL_USE, SLUG, TempGitRepo, load_module

hook = load_module("pre_tool_use", PRE_TOOL_USE)
wg = hook.wg
sp = hook.sp


class WindowsInputsTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.repo = TempGitRepo()
        self.repo.git("switch", "-c", BRANCH)

    def tearDown(self) -> None:
        self.repo.cleanup()

    def evaluate(self, tool: str, tool_input: dict, **extra):
        payload = {"cwd": str(self.repo.path), "tool_name": tool, "tool_input": tool_input, **extra}
        (decision, reason), _effects = hook.evaluate(wg.parse_input(payload))
        return decision, reason

    def crlf_state(self, **state) -> str:
        directory = self.repo.write_workflow(**state)
        path = directory / "state.json"
        text = path.read_text(encoding="utf-8").replace("\r\n", "\n").replace("\n", "\r\n")
        path.write_bytes(text.encode("utf-8"))
        return str(path)

    def test_marker_slightly_in_the_future_is_fresh(self) -> None:
        directory = self.repo.write_workflow(phase="build", review_iterations=1)
        marker = directory / ".reviewer-active"
        marker.write_text("1\n", encoding="utf-8")
        ahead = time.time() + 1.5
        os.utime(marker, (ahead, ahead))
        self.assertTrue(wg.marker_active(marker), "file clock ahead of time.time() on Windows")
        content = "---\nverdict: APPROVED\nreviewed_sha: abc1234\niteration: 1\n---\n"
        result = self.evaluate("create_file", {"filePath": f".ai/{SLUG}/review.md", "content": content})
        self.assertEqual(result[0], None, result[1])
        far = time.time() + 3600
        os.utime(marker, (far, far))
        self.assertFalse(wg.marker_active(marker), "a marker far in the future is not trusted")

    def test_replacement_in_a_crlf_state_file(self) -> None:
        path = self.crlf_state(phase="build", review_iterations=0)
        edit = {"filePath": path, "oldString": '"review_iterations": 0', "newString": '"review_iterations": 1'}
        self.assertEqual(self.evaluate("replace_string_in_file", edit)[0], None)
        multi_line = {
            "filePath": path,
            "oldString": '"phase": "build",\n  "path": "standard"',
            "newString": '"phase": "done",\n  "path": "standard"',
        }
        decision, reason = self.evaluate("replace_string_in_file", multi_line)
        self.assertEqual(decision, "deny")
        self.assertIn("close step", reason, "the LF edit is simulated on the CRLF file, not rejected as unknown")

    def test_patch_on_a_crlf_state_file(self) -> None:
        path = self.crlf_state(phase="build")
        patch = (
            f"*** Begin Patch\r\n*** Update File: {path}\r\n@@\r\n"
            '-  "phase": "build",\r\n+  "phase": "done",\r\n*** End Patch\r\n'
        )
        decision, reason = self.evaluate("apply_patch", {"input": patch})
        self.assertEqual(decision, "deny")
        self.assertIn("close step", reason)

    def test_windows_paths_with_other_case(self) -> None:
        self.repo.write_workflow(phase="pr-open", pull_request=7)
        state = self.repo.state()
        state["phase"] = "done"
        upper = str(self.repo.path / ".AI" / SLUG.upper() / "STATE.JSON").replace("/", "\\")
        decision, reason = self.evaluate("create_file", {"filePath": upper, "content": json.dumps(state)})
        self.assertEqual(decision, "deny")
        self.assertIn("close step", reason)
        review = f"C:\\repo\\.ai\\{SLUG}\\Review.md"
        self.assertEqual(self.evaluate("create_file", {"filePath": review, "content": "x"})[0], "deny")

    def test_cp1252_brief_and_crlf_current(self) -> None:
        directory = self.repo.write_workflow(phase="challenge")
        (self.repo.path / ".ai" / "current").write_bytes((SLUG + "\r\n").encode("ascii"))
        (directory / "brief.md").write_bytes("# Brief — café\r\n".encode("cp1252"))
        workflow = wg.load_workflow(self.repo.path)
        self.assertIsNotNone(workflow)
        self.assertEqual(workflow.slug, SLUG)


if __name__ == "__main__":
    unittest.main()
