import unittest

from support import BRANCH, STOP, TempGitRepo, run_script


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
        self.assertEqual(result["hookSpecificOutput"], {"hookEventName": "Stop", "decision": "block", "reason": result["reason"]})
        self.assertIn(expected, result["reason"])

    def test_no_workflow_allows_stop(self) -> None:
        self.repo.commit_file("src/app.py", "x = 1\n", "feat: lot 1")
        self.assertEqual(self.stop(), {})

    def test_non_gated_phases_allow_stop(self) -> None:
        self.repo.commit_file("src/app.py", "x = 1\n", "feat: lot 1")
        for phase in ("challenge", "design", "pr-open", "escalated", "done"):
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

    def test_stop_hook_active_allows_stop(self) -> None:
        self.repo.commit_file("src/app.py", "x = 1\n", "feat: lot 1")
        self.repo.write_workflow(phase="build")
        self.assertEqual(self.stop(stop_hook_active=True), {})
        copilot_payload = {"cwd": str(self.repo.path), "stopHookActive": True}
        self.assertEqual(run_script(STOP, copilot_payload, self.repo.env), {})

    def test_missing_base_branch_still_gates_commits(self) -> None:
        self.repo.commit_file("src/app.py", "x = 1\n", "feat: lot 1")
        self.repo.write_workflow(phase="build", base_branch=None)
        self.assert_blocked(self.stop(), "review.md is missing")

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
