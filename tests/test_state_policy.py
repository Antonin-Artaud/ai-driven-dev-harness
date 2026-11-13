"""state.json transitions, hook-owned files and role boundaries (ADR 0006)."""

import json
import time
import unittest

from support import BRANCH, PRE_TOOL_USE, SLUG, USER_PROMPT, TempGitRepo, load_module, run_script

hook = load_module("pre_tool_use", PRE_TOOL_USE)
wg = hook.wg
sp = hook.sp
STATE = f".ai/{SLUG}/state.json"
VALIDATED = {"at": "2026-11-13T10:00:00Z", "head": "abc1234"}


class StatePolicyTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.repo = TempGitRepo()
        self.repo.git("switch", "-c", BRANCH)

    def tearDown(self) -> None:
        self.repo.cleanup()

    # helpers -------------------------------------------------------------------------------

    def evaluate(self, tool: str, tool_input: dict, **extra):
        payload = {"cwd": str(self.repo.path), "tool_name": tool, "tool_input": tool_input, **extra}
        (decision, reason), effects = hook.evaluate(wg.parse_input(payload))
        if decision != "deny":
            sp.apply_effects(wg.load_workflow(self.repo.path), effects)
        return decision, reason

    def write_state(self, state: dict, path: str = STATE, **extra):
        return self.evaluate("create_file", {"filePath": path, "content": json.dumps(state)}, **extra)

    def state(self, **changes) -> dict:
        current = self.repo.state()
        current.update(changes)
        return current

    def artifact(self, name: str, written_at: float, prompt_at: float) -> None:
        (self.repo.path / ".ai" / SLUG / name).write_text("# x\n", encoding="utf-8")
        data = self.repo.hook_state()
        data.setdefault("written_at", {})[name] = written_at
        data["user_prompt_at"] = prompt_at
        self.repo.set_hook_state(**data)

    def assert_denied(self, result, expected: str) -> None:
        self.assertEqual(result[0], "deny", result[1])
        self.assertIn(expected, result[1])

    # creation and direct jumps ---------------------------------------------------------------

    def test_new_workflow_starts_in_challenge(self) -> None:
        (self.repo.path / ".ai").mkdir()
        (self.repo.path / ".ai" / "current").write_text("other\n", encoding="utf-8")
        (self.repo.path / ".ai" / "other").mkdir()
        (self.repo.path / ".ai" / "other" / "state.json").write_text('{"phase": "challenge"}', encoding="utf-8")
        new = {"slug": "new-thing", "phase": "challenge", "branch": "ai/new-thing"}
        self.assertEqual(self.write_state(new, ".ai/new-thing/state.json")[0], None)
        self.assert_denied(self.write_state({**new, "phase": "build"}, ".ai/new-thing/state.json"), "challenge")

    def test_done_only_through_the_close_step(self) -> None:
        self.repo.write_workflow(phase="pr-open", pull_request=7)
        self.assert_denied(self.write_state(self.state(phase="done")), "close step")
        replace = {"filePath": STATE, "oldString": '"phase": "pr-open"', "newString": '"phase": "done"'}
        self.assertEqual(self.evaluate("replace_string_in_file", replace)[0], "deny")

    def test_unlisted_transitions_are_denied(self) -> None:
        self.repo.write_workflow(phase="build")
        for phase in ("design", "challenge", "feedback", "triage", "unknown"):
            with self.subTest(phase=phase):
                self.assertEqual(self.write_state(self.state(phase=phase))[0], "deny")

    def test_identity_fields_are_fixed(self) -> None:
        self.repo.write_workflow(phase="pr-open", pull_request=7, record_thread=3)
        self.assert_denied(self.write_state(self.state(branch="main")), "ai/")
        self.assert_denied(self.write_state(self.state(pull_request=8)), "set once")
        self.assert_denied(self.write_state(self.state(record_thread=4)), "set once")
        self.assert_denied(self.write_state(self.state(base_branch="release")), "base_branch")
        self.assert_denied(self.write_state(self.state(slug="other")), "slug")

    def test_unsimulable_edits_and_invalid_json_are_denied(self) -> None:
        self.repo.write_workflow(phase="build")
        self.assert_denied(self.evaluate("insert_edit_into_file", {"filePath": STATE, "code": "..."}), "create_file")
        self.assert_denied(self.evaluate("create_file", {"filePath": STATE, "content": "{oops"}), "valid JSON")
        patch = (
            f'*** Begin Patch\n*** Update File: {STATE}\n@@\n-  "phase": "build",\n+  "phase": "done",\n*** End Patch'
        )
        self.assertEqual(self.evaluate("apply_patch", {"input": patch})[0], "deny")

    # validations -----------------------------------------------------------------------------

    def test_brief_validation_needs_a_user_message_after_the_brief(self) -> None:
        self.repo.write_workflow(phase="challenge")
        now = time.time()
        self.assert_denied(self.write_state(self.state(phase="design")), "brief.md is not validated")
        self.assert_denied(self.write_state(self.state(brief_validated=VALIDATED)), "does not exist")
        self.artifact("brief.md", written_at=now, prompt_at=now - 10)
        self.assert_denied(self.write_state(self.state(brief_validated=VALIDATED)), "wait for their validation")
        self.artifact("brief.md", written_at=now - 10, prompt_at=now)
        self.assertEqual(self.write_state(self.state(phase="design", brief_validated=VALIDATED))[0], None)
        self.assertIn("brief.md", self.repo.hook_state()["validated_at"])
        self.assert_denied(self.write_state(self.state(brief_validated="yes")), '"at"')

    def test_build_entry_needs_both_validations_and_an_unchanged_plan(self) -> None:
        now = time.time()
        self.repo.write_workflow(phase="design", brief_validated=VALIDATED)
        self.artifact("brief.md", written_at=now - 100, prompt_at=now - 50)
        self.assert_denied(self.write_state(self.state(phase="build")), "plan.md is not validated")
        self.artifact("plan.md", written_at=now - 40, prompt_at=now - 30)
        self.repo.set_hook_state(validated_at={"brief.md": now - 60, "plan.md": now - 20})
        self.assertEqual(self.write_state(self.state(plan_validated=VALIDATED))[0], None)
        self.repo.write_workflow(phase="design", brief_validated=VALIDATED, plan_validated=VALIDATED)
        self.repo.set_hook_state(written_at={"brief.md": now - 100, "plan.md": time.time() + 5})
        self.assert_denied(self.write_state(self.state(phase="build", plan_validated=VALIDATED)), "changed after")
        self.repo.set_hook_state(written_at={"brief.md": now - 100, "plan.md": now - 40})
        (self.repo.path / "notes.txt").write_text("user notes\n", encoding="utf-8")
        result = self.write_state(self.state(phase="build", plan_validated=VALIDATED, review_iterations=0))
        self.assertEqual(result[0], None, result[1])
        self.assertEqual(self.repo.hook_state()["untracked_baseline"], ["notes.txt"])

    def test_triage_validation_before_feedback(self) -> None:
        now = time.time()
        self.repo.write_workflow(phase="triage", pull_request=7)
        self.assert_denied(self.write_state(self.state(phase="feedback")), "feedback.md")
        self.artifact("feedback.md", written_at=now, prompt_at=now - 5)
        self.assert_denied(self.write_state(self.state(phase="feedback")), "not validated")
        self.artifact("feedback.md", written_at=now - 5, prompt_at=now)
        self.assertEqual(self.write_state(self.state(phase="feedback", review_iterations=0))[0], None)

    # review loop and escalation ----------------------------------------------------------------

    def test_review_iterations_are_bounded(self) -> None:
        self.repo.write_workflow(phase="build", review_iterations=1)
        self.assert_denied(self.write_state(self.state(review_iterations=0)), "never decreases")
        self.assert_denied(self.write_state(self.state(review_iterations=3)), "by one")
        self.assertEqual(self.write_state(self.state(review_iterations=2))[0], None)
        self.repo.write_workflow(phase="build", review_iterations=2)
        self.assert_denied(self.write_state(self.state(review_iterations=3)), "limit")

    def test_lots_done_is_append_only(self) -> None:
        self.repo.write_workflow(phase="build", lots_done=[{"lot": 1, "commit": "abc"}])
        self.assertEqual(self.write_state(self.state(lots_done=[{"lot": 1, "commit": "abc"}, {"lot": 2}]))[0], None)
        self.assert_denied(self.write_state(self.state(lots_done=[])), "append-only")

    def test_escalation_and_its_exits(self) -> None:
        self.repo.write_workflow(phase="build", review_iterations=2)
        self.assert_denied(self.write_state(self.state(phase="escalated")), "escalation")
        escalation = {"from": "build", "reason": "two reviews still request changes"}
        self.repo.set_hook_state(user_prompt_at=time.time() - 60)
        self.assertEqual(self.write_state(self.state(phase="escalated", escalation=escalation))[0], None)
        self.assertIn("escalated_at", self.repo.hook_state())
        self.repo.write_workflow(
            phase="escalated",
            review_iterations=2,
            escalation=escalation,
            brief_validated=VALIDATED,
            plan_validated=VALIDATED,
        )
        for name in ("brief.md", "plan.md"):
            (self.repo.path / ".ai" / SLUG / name).write_text("# x\n", encoding="utf-8")
        self.assert_denied(self.write_state(self.state(phase="build", review_iterations=0)), "user's decision")
        self.repo.set_hook_state(user_prompt_at=time.time() + 1)
        self.assert_denied(self.write_state(self.state(phase="build")), "review_iterations to 0")
        self.assertEqual(self.write_state(self.state(phase="build", review_iterations=0))[0], None)
        self.assert_denied(self.write_state(self.state(phase="done")), "close step")

    def test_pr_open_needs_the_pr_and_an_approved_review(self) -> None:
        sha = self.repo.commit_file("src/app.py", "x = 1\n", "feat: lot 1")
        self.repo.write_workflow(phase="build", review_iterations=1)
        self.assert_denied(self.write_state(self.state(phase="pr-open")), "pull_request")
        self.assert_denied(self.write_state(self.state(phase="pr-open", pull_request=7)), "review.md is missing")
        self.repo.write_workflow(
            phase="build", review_iterations=1, review={"verdict": "APPROVED", "reviewed_sha": sha, "iteration": "1"}
        )
        self.assertEqual(self.write_state(self.state(phase="pr-open", pull_request=7))[0], None)

    def test_reviewer_writes_the_current_iteration(self) -> None:
        self.repo.write_workflow(phase="build", review_iterations=1)
        path = f".ai/{SLUG}/review.md"

        def review(iteration: str, verdict: str = "APPROVED"):
            content = f"---\nverdict: {verdict}\nreviewed_sha: abc1234\niteration: {iteration}\n---\n"
            return self.evaluate("create_file", {"filePath": path, "content": content}, agent_type="reviewer")

        self.assertEqual(review("1")[0], None)
        self.assert_denied(review("2"), "iteration")
        self.assert_denied(review("1", "LGTM"), "verdict")
        self.repo.write_workflow(phase="build", review_iterations=0)
        self.assert_denied(review("0"), "increments review_iterations")

    # .ai/current and hook-owned files ------------------------------------------------------------

    def test_current_cannot_switch_away_from_a_gated_phase(self) -> None:
        current = {"filePath": ".ai/current", "content": "other-work\n"}
        for phase, expected in (("build", "deny"), ("pr-open", "deny"), ("design", None), ("escalated", None)):
            with self.subTest(phase=phase):
                self.repo.write_workflow(phase=phase)
                self.assertEqual(self.evaluate("create_file", current)[0], expected)
        self.repo.write_workflow(phase="design")
        self.assert_denied(self.evaluate("create_file", {"filePath": ".ai/current", "content": "Not A Slug"}), "kebab")

    def test_hook_owned_files_are_never_written_by_agents(self) -> None:
        self.repo.write_workflow(phase="design")
        for name in (".hooks.json", "log.jsonl", ".implementer-active", ".reviewer-active"):
            with self.subTest(name=name):
                result = self.evaluate("create_file", {"filePath": f".ai/{SLUG}/{name}", "content": "{}"})
                self.assertEqual(result[0], "deny")

    def test_shell_never_writes_workflow_files(self) -> None:
        self.repo.write_workflow(phase="build")
        for command in (
            f"echo '{{}}' > {STATE}",
            "Set-Content .ai/current other",
            f"python -c \"import json; json.dump({{'phase': 'done'}}, open('{STATE}', 'w'))\"",
            f"cp /tmp/x .ai/{SLUG}/.hooks.json",
        ):
            with self.subTest(command=command):
                self.assertEqual(self.evaluate("run_in_terminal", {"command": command})[0], "deny")
        self.assertEqual(self.evaluate("run_in_terminal", {"command": f"cat {STATE}"})[0], None)

    # role boundaries -----------------------------------------------------------------------------

    def test_role_boundaries(self) -> None:
        self.repo.write_workflow(phase="build")
        source = {"filePath": "src/app.py", "content": "x = 1\n"}
        plan = {"filePath": f".ai/{SLUG}/plan.md", "content": "# plan\n"}
        self.assertEqual(self.evaluate("create_file", source, agent_id="a1", agent_type="reviewer")[0], "deny")
        self.assertEqual(self.evaluate("create_file", plan, agent_id="a1", agent_type="reviewer")[0], "deny")
        self.assertEqual(self.evaluate("create_file", plan, agent_id="a1", agent_type="implementer")[0], "deny")
        self.assertEqual(self.evaluate("create_file", source, agent_id="a1", agent_type="implementer")[0], None)
        self.assertEqual(self.evaluate("create_file", source)[0], "ask", "the builder does not code")
        self.assertEqual(self.evaluate("create_file", plan)[0], None)
        marker = self.repo.path / ".ai" / SLUG / ".implementer-active"
        marker.write_text("1\n", encoding="utf-8")
        self.assertEqual(self.evaluate("create_file", source)[0], None, "implementer marker fallback")
        self.assertEqual(self.evaluate("create_file", plan)[0], "deny")
        marker.unlink()
        for phase, expected in (("challenge", "ask"), ("design", "ask"), ("escalated", None)):
            with self.subTest(phase=phase):
                self.repo.write_workflow(phase=phase)
                self.assertEqual(self.evaluate("create_file", source)[0], expected)

    def test_no_workflow_no_rule(self) -> None:
        self.assertEqual(self.evaluate("create_file", {"filePath": STATE, "content": "{}"})[0], None)


class EndToEndValidationTestCase(unittest.TestCase):
    """The real hook scripts record the brief write and the user prompt, then accept the validation."""

    def setUp(self) -> None:
        self.repo = TempGitRepo()
        self.repo.write_workflow(phase="challenge")

    def tearDown(self) -> None:
        self.repo.cleanup()

    def pre_tool_use(self, tool: str, tool_input: dict) -> dict:
        return run_script(
            PRE_TOOL_USE, {"cwd": str(self.repo.path), "tool_name": tool, "tool_input": tool_input}, self.repo.env
        )

    def test_brief_then_prompt_then_validation(self) -> None:
        brief = {"filePath": str(self.repo.path / ".ai" / SLUG / "brief.md"), "content": "# Brief\n"}
        self.assertEqual(self.pre_tool_use("create_file", brief), {})
        (self.repo.path / ".ai" / SLUG / "brief.md").write_text("# Brief\n", encoding="utf-8")
        state = self.repo.state()
        state.update(phase="design", brief_validated=VALIDATED)
        update = {"filePath": STATE, "content": json.dumps(state)}
        hook_state = self.repo.hook_state()
        self.assertIn("brief.md", hook_state["written_at"])
        self.assertEqual(
            hook_state["heartbeat"]["version"], json.loads((hook.wg.PLUGIN_ROOT / "plugin.json").read_text())["version"]
        )
        self.repo.set_hook_state(user_prompt_at=hook_state["written_at"]["brief.md"] - 1)
        self.assertEqual(self.pre_tool_use("create_file", update).get("permissionDecision"), "deny")
        time.sleep(0.01)
        self.assertEqual(run_script(USER_PROMPT, {"cwd": str(self.repo.path), "prompt": "ok"}, self.repo.env), {})
        self.assertEqual(self.pre_tool_use("create_file", update), {})


if __name__ == "__main__":
    unittest.main()
