import unittest

from support import BRANCH, SUBAGENT, TempGitRepo, run_script


class SubagentHookTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.repo = TempGitRepo()
        self.repo.git("switch", "-c", BRANCH)
        self.marker = self.repo.write_workflow(phase="build") / ".reviewer-active"

    def tearDown(self) -> None:
        self.repo.cleanup()

    def run_event(self, event: str, payload: dict) -> dict:
        return run_script(SUBAGENT, {"cwd": str(self.repo.path), **payload}, self.repo.env, args=[event])

    def test_reviewer_run_creates_then_removes_the_marker(self) -> None:
        self.assertEqual(self.run_event("start", {"agentName": "reviewer"}), {})
        self.assertTrue(self.marker.exists())
        self.assertEqual(self.run_event("stop", {"agent_id": "a1", "agent_type": "reviewer"}), {})
        self.assertFalse(self.marker.exists())

    def test_implementer_run_has_its_own_marker(self) -> None:
        implementer = self.marker.parent / ".implementer-active"
        self.assertEqual(self.run_event("start", {"agentName": "ai-driven-dev-harness:implementer"}), {})
        self.assertTrue(implementer.exists())
        self.assertFalse(self.marker.exists())
        self.assertEqual(self.run_event("stop", {"agentName": "implementer"}), {})
        self.assertFalse(implementer.exists())

    def test_every_workflow_subagent_has_a_marker(self) -> None:
        for name in ("ui-ux-designer", "security-architect", "performance-architect"):
            with self.subTest(agent=name):
                marker = self.marker.parent / f".{name}-active"
                self.run_event("start", {"agentName": name})
                self.assertTrue(marker.exists())
                self.run_event("stop", {"agentName": name})
                self.assertFalse(marker.exists())

    def test_other_subagents_leave_no_marker(self) -> None:
        self.assertEqual(self.run_event("start", {"agentName": "explore"}), {})
        self.assertEqual(sorted(path.name for path in self.marker.parent.glob(".*-active")), [])

    def test_no_active_workflow_leaves_no_marker(self) -> None:
        self.repo.write_workflow(phase="done")
        self.assertEqual(self.run_event("start", {"agentName": "reviewer"}), {})
        self.assertFalse(self.marker.exists())


if __name__ == "__main__":
    unittest.main()
