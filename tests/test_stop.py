import unittest

from support import BRANCH, STOP, USER_PROMPT, TempGitRepo, run_script


class StopHookTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.repo = TempGitRepo()
        self.repo.git("switch", "-c", BRANCH)

    def tearDown(self) -> None:
        self.repo.cleanup()

    def stop(self, **extra) -> dict:
        payload = {
            "timestamp": "2026-10-28T10:00:00Z",
            "hook_event_name": "Stop",
            "cwd": str(self.repo.path),
            "stop_hook_active": False,
        }
        payload.update(extra)
        return run_script(STOP, payload, self.repo.env)

    def assert_blocked(self, result: dict, expected: str) -> None:
        self.assertEqual(result.get("decision"), "block")
        self.assertEqual(
            result["hookSpecificOutput"], {"hookEventName": "Stop", "decision": "block", "reason": result["reason"]}
        )
        self.assertIn(expected, result["reason"])

    def test_no_workflow_allows_stop(self) -> None:
        self.repo.commit_file("src/app.py", "x = 1\n", "feat: lot 1")
        self.assertEqual(self.stop(), {})

    def test_non_gated_phases_allow_stop(self) -> None:
        self.repo.commit_file("src/app.py", "x = 1\n", "feat: lot 1")
        for phase in ("challenge", "design", "pr-open", "triage", "escalated", "done"):
            with self.subTest(phase=phase):
                self.repo.write_workflow(phase=phase)
                self.assertEqual(self.stop(), {})

    def test_nothing_implemented_yet_allows_stop(self) -> None:
        self.repo.write_workflow(phase="build")
        self.assertEqual(self.stop(), {})

    def test_commits_without_review_block(self) -> None:
        self.repo.commit_file("src/app.py", "x = 1\n", "feat: lot 1")
        self.repo.write_workflow(phase="build")
        self.assert_blocked(self.stop(), "review.md is missing")

    def test_stale_review_blocks(self) -> None:
        first = self.repo.commit_file("src/app.py", "x = 1\n", "feat: lot 1")
        self.repo.commit_file("src/app.py", "x = 2\n", "fix: review findings")
        self.repo.write_workflow(phase="feedback", review={"verdict": "APPROVED", "reviewed_sha": first})
        self.assert_blocked(self.stop(), "but HEAD is")

    def test_changes_requested_blocks(self) -> None:
        sha = self.repo.commit_file("src/app.py", "x = 1\n", "feat: lot 1")
        self.repo.write_workflow(phase="build", review={"verdict": "CHANGES_REQUESTED", "reviewed_sha": sha})
        self.assert_blocked(self.stop(), "CHANGES_REQUESTED")

    def test_uncommitted_changes_block(self) -> None:
        self.repo.write_workflow(phase="build")
        self.repo.write("src/app.py", "x = 1\n")
        self.assert_blocked(self.stop(), "uncommitted changes (src/app.py)")

    def test_approved_review_of_head_allows_stop(self) -> None:
        sha = self.repo.commit_file("src/app.py", "x = 1\n", "feat: lot 1")
        self.repo.write_workflow(phase="build", review={"verdict": "APPROVED", "reviewed_sha": sha})
        self.assertEqual(self.stop(), {})

    def test_workflow_files_are_not_dirty_even_without_exclude(self) -> None:
        sha = self.repo.commit_file("src/app.py", "x = 1\n", "feat: lot 1")
        self.repo.write_workflow(phase="build", review={"verdict": "APPROVED", "reviewed_sha": sha}, exclude=False)
        self.assertEqual(self.stop(), {})

    def test_consecutive_blocks_are_counted_then_released(self) -> None:
        self.repo.commit_file("src/app.py", "x = 1\n", "feat: lot 1")
        self.repo.write_workflow(phase="build")
        for attempt in range(3):
            with self.subTest(attempt=attempt):
                self.assert_blocked(self.stop(stop_hook_active=attempt > 0), "review.md is missing")
        self.assertEqual(self.stop(stop_hook_active=True), {}, "released after 3 consecutive blocks")
        self.assertIn("released", [entry["decision"] for entry in self.repo.log_entries()])
        self.assertEqual(self.repo.hook_state()["stop_blocks"], 0)
        self.assert_blocked(self.stop(), "review.md is missing")
        run_script(USER_PROMPT, {"cwd": str(self.repo.path)}, self.repo.env)
        self.assertEqual(self.repo.hook_state()["stop_blocks"], 0, "a user prompt resets the count")

    def test_review_limit_message_asks_to_escalate(self) -> None:
        sha = self.repo.commit_file("src/app.py", "x = 1\n", "feat: lot 1")
        self.repo.write_workflow(
            phase="build",
            review_iterations=2,
            review={"verdict": "CHANGES_REQUESTED", "reviewed_sha": sha, "iteration": "2"},
        )
        self.assert_blocked(self.stop(), "the limit. Escalate")

    def test_untracked_files_present_before_the_build_are_ignored(self) -> None:
        sha = self.repo.commit_file("src/app.py", "x = 1\n", "feat: lot 1")
        self.repo.write_workflow(phase="build", review={"verdict": "APPROVED", "reviewed_sha": sha})
        self.repo.write("notes.txt", "user notes\n")
        self.assert_blocked(self.stop(), "uncommitted changes (notes.txt)")
        self.repo.set_hook_state(untracked_baseline=["notes.txt"], stop_blocks=0)
        self.assertEqual(self.stop(), {})
        self.repo.write("src/new.py", "y = 2\n")
        self.assert_blocked(self.stop(), "uncommitted changes (src/new.py)")

    def test_missing_base_branch_still_gates_commits(self) -> None:
        self.repo.commit_file("src/app.py", "x = 1\n", "feat: lot 1")
        self.repo.write_workflow(phase="build", base_branch=None)
        self.assert_blocked(self.stop(), "review.md is missing")

    def test_open_pr_without_workflow_record_blocks(self) -> None:
        self.repo.write_workflow(phase="pr-open", pull_request=42)
        result = self.stop()
        self.assertEqual(result.get("decision"), "block")
        self.assertIn("Record gate", result["reason"])
        self.assertIn("Workflow record", result["reason"])

    def test_open_pr_with_workflow_record_allows_stop(self) -> None:
        self.repo.write_workflow(phase="pr-open", pull_request=42, record_thread=7)
        self.assertEqual(self.stop(), {})

    def test_stop_removes_the_subagent_markers(self) -> None:
        directory = self.repo.write_workflow(phase="design")
        for name in (".reviewer-active", ".implementer-active"):
            (directory / name).write_text("1\n", encoding="utf-8")
        self.assertEqual(self.stop(), {})
        for name in (".reviewer-active", ".implementer-active"):
            self.assertFalse((directory / name).exists())
        self.assertIn("heartbeat", self.repo.hook_state())

    def test_workflow_files_written_by_windows_powershell_are_read(self) -> None:
        sha = self.repo.commit_file("src/app.py", "x = 1\n", "feat: lot 1")
        directory = self.repo.write_workflow(phase="build")
        (self.repo.path / ".ai" / "current").write_text(directory.name + "\n", encoding="utf-16")
        self.assert_blocked(self.stop(), "review.md is missing")
        review = f"---\nverdict: APPROVED\nreviewed_sha: {sha}\n---\n# Revue — validée\n"
        for encoding in ("utf-16", "utf-8-sig", "cp1252"):
            with self.subTest(encoding=encoding):
                (directory / "review.md").write_text(review, encoding=encoding)
                self.assertEqual(self.stop(), {})


if __name__ == "__main__":
    unittest.main()
