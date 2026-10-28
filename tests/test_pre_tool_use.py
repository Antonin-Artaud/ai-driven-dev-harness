import json
import unittest

from support import BRANCH, PRE_TOOL_USE, TempGitRepo, run_script

MARKER = "\U0001F916"


class PreToolUseTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.repo = TempGitRepo()
        self.repo.git("switch", "-c", BRANCH)

    def tearDown(self) -> None:
        self.repo.cleanup()

    # helpers -------------------------------------------------------------------------------

    def local(self, tool_name: str, tool_input: dict) -> dict:
        return {
            "timestamp": "2026-10-28T10:00:00Z",
            "hook_event_name": "PreToolUse",
            "cwd": str(self.repo.path),
            "session_id": "s1",
            "tool_name": tool_name,
            "tool_input": tool_input,
            "tool_use_id": "t1",
        }

    def copilot(self, tool_name: str, tool_args: dict) -> dict:
        return {"timestamp": 1, "cwd": str(self.repo.path), "toolName": tool_name, "toolArgs": json.dumps(tool_args)}

    def decide(self, payload: dict):
        result = run_script(PRE_TOOL_USE, payload, self.repo.env)
        if not result:
            return None, ""
        specific = result["hookSpecificOutput"]
        self.assertEqual(specific["hookEventName"], "PreToolUse")
        self.assertEqual(specific["permissionDecision"], result["permissionDecision"])
        self.assertEqual(specific["permissionDecisionReason"], result["permissionDecisionReason"])
        return result["permissionDecision"], result["permissionDecisionReason"]

    def shell(self, command: str):
        return self.decide(self.local("run_in_terminal", {"command": command, "explanation": "x"}))

    def pr_write(self, **args):
        return self.decide(self.local("mcp_ado-write_repo_pull_request_write", args))

    def pr_create(self, **overrides):
        args = {
            "action": "create",
            "repositoryId": "acme-bank",
            "project": "Credit",
            "sourceRefName": f"refs/heads/{BRANCH}",
            "targetRefName": "refs/heads/main",
            "title": "fix(scoring): handle households without borrowers",
            "description": "Why: crash on empty borrowers.",
            "isDraft": True,
            "workItems": "1234",
        }
        args.update(overrides)
        return self.pr_write(**args)

    def approved_and_pushed(self, phase: str = "build") -> str:
        sha = self.repo.commit_file("src/app.py", "print('lot 1')\n", "feat(app): lot 1")
        self.repo.git("push", "-u", "origin", BRANCH)
        self.repo.write_workflow(phase=phase, review={"verdict": "APPROVED", "reviewed_sha": sha, "iteration": "1"})
        return sha

    # no active workflow ----------------------------------------------------------------------

    def test_no_workflow_means_no_decision(self) -> None:
        self.assertEqual(self.shell("git push --force origin main")[0], None)
        self.assertEqual(self.pr_create(isDraft=False)[0], None)

    def test_done_phase_is_inactive(self) -> None:
        self.repo.write_workflow(phase="done")
        self.assertEqual(self.shell("git push --force")[0], None)

    def test_unrelated_tools_have_no_decision(self) -> None:
        self.repo.write_workflow(phase="build")
        self.assertEqual(self.decide(self.local("read_file", {"filePath": "README.md"}))[0], None)
        self.assertEqual(self.decide(self.local("mcp_ado-read_wit_work_item", {"action": "get", "id": 1}))[0], None)
        self.assertEqual(self.shell("python -m unittest")[0], None)

    # git push -----------------------------------------------------------------------------------

    def test_forbidden_pushes_are_denied(self) -> None:
        self.repo.write_workflow(phase="build")
        for command in (
            "git push --force",
            "git push -f origin ai/x",
            "git push --force-with-lease",
            "git push --force-with-lease=ai/x:abc origin ai/x",
            "git push origin +ai/x",
            "git push origin :ai/x",
            "git push --delete origin ai/x",
            "git push -d origin ai/x",
            "git -C . push --mirror",
            "git status && git push -fu origin ai/x",
            'cmd /c "git push --force"',
        ):
            with self.subTest(command=command):
                decision, reason = self.shell(command)
                self.assertEqual(decision, "deny")
                self.assertIn("force push", reason)

    def test_regular_push_asks(self) -> None:
        self.repo.write_workflow(phase="feedback")
        for command in (
            f"git push -u origin {BRANCH}",
            "git add -A && git commit -m 'fix: x' && git push",
            "git --no-pager push --follow-tags",
        ):
            with self.subTest(command=command):
                self.assertEqual(self.shell(command)[0], "ask")

    def test_push_forms_found_by_review_are_denied(self) -> None:
        self.repo.write_workflow(phase="build")
        for command in (
            "git -P push --force origin main",
            "git -p push -f",
            "git --git-dir .git push --force origin main",
            "git --work-tree . push --force",
            "/usr/bin/git push --force",
            '& "C:\\Program Files\\Git\\cmd\\git.exe" push --force origin main',
            "cmd /c git push --force",
            "bash -lc 'git push -f'",
            'pwsh -NoProfile -Command "git status; git push --force"',
            "sudo git push -f",
            "GIT_TRACE=1 git push --force",
            "(cd sub; git push -f)",
        ):
            with self.subTest(command=command):
                self.assertEqual(self.shell(command)[0], "deny")

    def test_force_push_mentioned_in_text_is_not_a_push(self) -> None:
        self.repo.write_workflow(phase="build")
        for command in (
            "git commit -m 'docs: explain why git push --force is blocked'",
            "Select-String -Path README.md -Pattern 'git push -d'",
            "echo git push --force",
        ):
            with self.subTest(command=command):
                self.assertEqual(self.shell(command)[0], None)

    def test_other_git_commands_have_no_decision(self) -> None:
        self.repo.write_workflow(phase="build")
        for command in ("git status", "git log --oneline -5", "git commit -m 'push it'", "git pushd"):
            with self.subTest(command=command):
                self.assertEqual(self.shell(command)[0], None)

    # az CLI ---------------------------------------------------------------------------------

    def test_az_cli_writes_are_denied(self) -> None:
        self.repo.write_workflow(phase="build")
        for command in (
            "az repos pr create --draft true --title x",
            "az --only-show-errors repos pr create --draft true",
            "az repos pr update --id 1 --auto-complete true",
            "az repos pr set-vote --id 1 --vote approve",
            "az boards work-item update --id 1234 --state Done",
            "az boards work-item relation add --id 1 --relation-type parent --target-id 2",
            "az devops invoke --area git --resource pullRequests --http-method POST",
            "az devops invoke --area git --http-method=POST",
            'az devops invoke --area wit --http-method "PATCH"',
        ):
            with self.subTest(command=command):
                self.assertEqual(self.shell(command)[0], "deny")

    def test_az_cli_reads_have_no_decision(self) -> None:
        self.repo.write_workflow(phase="build")
        for command in (
            "az repos pr list",
            "az repos pr show --id 1",
            "az repos pr policy list --id 1",
            "az -o json repos pr list",
            "az devops invoke --area git --http-method GET",
        ):
            with self.subTest(command=command):
                self.assertEqual(self.shell(command)[0], None)

    # draft PR creation ----------------------------------------------------------------------------

    def test_pr_create_when_everything_is_ready_asks(self) -> None:
        sha = self.approved_and_pushed()
        decision, reason = self.pr_create()
        self.assertEqual(decision, "ask")
        self.assertIn("DRAFT", reason)
        self.assertIn(sha[:8], reason)

    def test_pr_create_accepts_abbreviated_reviewed_sha(self) -> None:
        sha = self.approved_and_pushed()
        self.repo.write_workflow(review={"verdict": "APPROVED", "reviewed_sha": sha[:10]})
        self.assertEqual(self.pr_create()[0], "ask")

    def test_pr_create_requires_draft(self) -> None:
        self.approved_and_pushed()
        for overrides in ({"isDraft": False}, {"isDraft": None}):
            with self.subTest(overrides=overrides):
                decision, reason = self.pr_create(**overrides)
                self.assertEqual(decision, "deny")
                self.assertIn("draft", reason)

    def test_pr_create_requires_build_phase(self) -> None:
        self.approved_and_pushed(phase="design")
        decision, reason = self.pr_create()
        self.assertEqual(decision, "deny")
        self.assertIn("build phase", reason)

    def test_pr_create_requires_a_review(self) -> None:
        self.repo.commit_file("src/app.py", "x = 1\n", "feat: lot 1")
        self.repo.git("push", "-u", "origin", BRANCH)
        self.repo.write_workflow(phase="build")
        decision, reason = self.pr_create()
        self.assertEqual(decision, "deny")
        self.assertIn("review.md is missing", reason)

    def test_pr_create_rejects_stale_review(self) -> None:
        self.approved_and_pushed()
        self.repo.commit_file("src/app.py", "print('lot 2')\n", "feat(app): lot 2")
        self.repo.git("push")
        decision, reason = self.pr_create()
        self.assertEqual(decision, "deny")
        self.assertIn("but HEAD is", reason)

    def test_pr_create_rejects_changes_requested(self) -> None:
        sha = self.approved_and_pushed()
        self.repo.write_workflow(review={"verdict": "CHANGES_REQUESTED", "reviewed_sha": sha})
        decision, reason = self.pr_create()
        self.assertEqual(decision, "deny")
        self.assertIn("CHANGES_REQUESTED", reason)

    def test_pr_create_rejects_dirty_tree(self) -> None:
        self.approved_and_pushed()
        self.repo.write("src/app.py", "print('edited')\n")
        decision, reason = self.pr_create()
        self.assertEqual(decision, "deny")
        self.assertIn("uncommitted changes", reason)

    def test_pr_create_requires_pushed_head(self) -> None:
        sha = self.repo.commit_file("src/app.py", "x = 1\n", "feat: lot 1")
        self.repo.write_workflow(review={"verdict": "APPROVED", "reviewed_sha": sha})
        decision, reason = self.pr_create()
        self.assertEqual(decision, "deny")
        self.assertIn("Push first", reason)

    def test_pr_create_checks_source_target_and_description(self) -> None:
        self.approved_and_pushed()
        cases = (
            ({"sourceRefName": "refs/heads/other"}, "is not the reviewed branch"),
            ({"targetRefName": "refs/heads/develop"}, "differs from base_branch"),
            ({"description": "x" * 4001}, "at most 4000"),
            ({"autoComplete": True}, "autocomplete"),
        )
        for overrides, expected in cases:
            with self.subTest(overrides=list(overrides)):
                decision, reason = self.pr_create(**overrides)
                self.assertEqual(decision, "deny")
                self.assertIn(expected, reason)

    # PR updates and threads -----------------------------------------------------------------------

    def test_pr_update_rules(self) -> None:
        self.repo.write_workflow(phase="pr-open")
        denied = (
            {"action": "update", "pullRequestId": 7, "autoComplete": True},
            {"action": "update", "pullRequestId": 7, "bypassPolicy": True, "bypassReason": "x"},
            {"action": "update", "pullRequestId": 7, "isDraft": False},
            {"action": "update", "pullRequestId": 7, "status": "Abandoned"},
            {"action": "vote", "pullRequestId": 7, "vote": "Approved"},
            {"action": "update_reviewers", "pullRequestId": 7, "reviewerIds": ["a"], "reviewerAction": "remove"},
            {"action": "merge"},
        )
        for args in denied:
            with self.subTest(args=args):
                self.assertEqual(self.pr_write(**args)[0], "deny")
        allowed = {"action": "update", "pullRequestId": 7, "description": "Updated scope."}
        self.assertEqual(self.pr_write(**allowed)[0], None)

    def test_thread_writes_require_the_ai_marker(self) -> None:
        self.repo.write_workflow(phase="pr-open")
        tool = "mcp_ado-write_repo_pull_request_thread_write"
        base = {"repositoryId": "acme-bank", "pullRequestId": 7}
        denied = self.decide(self.local(tool, {**base, "action": "create", "content": "Missing null check."}))
        self.assertEqual(denied[0], "deny")
        self.assertIn(MARKER, denied[1])
        for args in (
            {**base, "action": "create", "content": f"{MARKER} AI review - minor: rename x."},
            {**base, "action": "reply", "threadId": 3, "content": f"  {MARKER} Fixed in abc1234."},
            {**base, "action": "update_status", "threadId": 3, "status": "Fixed"},
        ):
            with self.subTest(action=args["action"]):
                self.assertEqual(self.decide(self.local(tool, args))[0], None)

    def test_other_azure_devops_writes_are_denied(self) -> None:
        self.repo.write_workflow(phase="build")
        for tool in (
            "mcp_ado-write_wit_work_item_write",
            "mcp_ado-write_wit_work_item_link_write",
            "mcp_ado-write_wit_work_item_comment_write",
            "mcp_ado-write_wit_work_item_attachment_upload",
            "mcp_ado-write_wit_work_item_attachment_link",
            "mcp_ado-write_wiki_upsert_page",
            "mcp_ado-write_repo_create_branch",
            "mcp_ado-write_enterprise_live_migration_write",
            "repo_file_write",
            "ado-write-pipelines_write",
        ):
            with self.subTest(tool=tool):
                self.assertEqual(self.decide(self.local(tool, {"action": "update", "id": 1234}))[0], "deny")

    def test_azure_devops_read_tools_have_no_decision(self) -> None:
        self.repo.write_workflow(phase="build")
        for tool in (
            "mcp_ado-read_pipelines_run",
            "mcp_ado-read_testplan_test_run",
            "mcp_ado-read_wit_work_item_attachment",
            "mcp_ado-read_repo_pull_request_thread",
            "mcp_ado-read_search_workitem",
            "mcp_ado-read_enterprise_live_migration",
        ):
            with self.subTest(tool=tool):
                self.assertEqual(self.decide(self.local(tool, {"action": "get", "id": 1}))[0], None)

    def test_command_argument_does_not_bypass_azure_devops_rules(self) -> None:
        self.approved_and_pushed()
        thread = "mcp_ado-write_repo_pull_request_thread_write"
        for tool, args in (
            ("mcp_ado-write_repo_pull_request_write", {"action": "create", "isDraft": False, "command": "x"}),
            ("mcp_ado-write_repo_pull_request_write", {"action": "vote", "vote": "Approved", "command": "x"}),
            (thread, {"action": "create", "content": "no marker", "command": "x"}),
            ("mcp_ado-write_wit_work_item_write", {"action": "update", "command": "x"}),
        ):
            with self.subTest(tool=tool, action=args["action"]):
                self.assertEqual(self.decide(self.local(tool, args))[0], "deny")

    def test_workflow_files_in_other_encodings_keep_the_gates(self) -> None:
        directory = self.repo.write_workflow(phase="build")
        current = self.repo.path / ".ai" / "current"
        for encoding in ("utf-8-sig", "utf-16"):
            with self.subTest(encoding=encoding):
                current.write_text(directory.name + "\n", encoding=encoding)
                self.assertEqual(self.shell("git push --force")[0], "deny")

    # Copilot payload shape ------------------------------------------------------------------------

    def test_copilot_payload_shape_is_supported(self) -> None:
        self.approved_and_pushed()
        self.assertEqual(self.decide(self.copilot("powershell", {"command": "git push --force"}))[0], "deny")
        args = {
            "action": "create",
            "sourceRefName": f"refs/heads/{BRANCH}",
            "targetRefName": "refs/heads/main",
            "title": "t",
            "isDraft": True,
        }
        self.assertEqual(self.decide(self.copilot("ado-write/repo_pull_request_write", args))[0], "ask")

    def test_invalid_payload_has_no_decision(self) -> None:
        self.assertEqual(run_script(PRE_TOOL_USE, "not json", self.repo.env, cwd=self.repo.path), {})


if __name__ == "__main__":
    unittest.main()
