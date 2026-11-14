import json
import os
import time
import unittest

from support import BRANCH, PRE_TOOL_USE, TempGitRepo, run_script

MARKER = "\U0001f916"


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

    def test_git_aliases_are_resolved(self) -> None:
        self.repo.write_workflow(phase="build")
        self.repo.git("config", "alias.p", "push")
        self.repo.git("config", "alias.yolo", "!git push --force")
        self.repo.git("config", "alias.pp", "p")
        denied = (
            "git -c alias.p=push p --force origin main",
            "git -c alias.x=push -c alias.y=x y -f",
            "git p --force",
            "git p -d origin ai/x",
            "git yolo",
            "git -c 'alias.z=!f() { git push -f; }; f' z",
            "git pp --force",
        )
        for command in denied:
            with self.subTest(command=command):
                self.assertEqual(self.shell(command)[0], "deny")
        for command in ("git p", f"git -c alias.up=push up -u origin {BRANCH}"):
            with self.subTest(command=command):
                self.assertEqual(self.shell(command)[0], "ask")

    def test_aliases_of_builtins_and_unknown_names_are_ignored(self) -> None:
        self.repo.write_workflow(phase="build")
        self.repo.git("config", "alias.lg", "log --oneline")
        for command in ("git -c alias.status=push status", "git lg", "git nothing-here"):
            with self.subTest(command=command):
                self.assertEqual(self.shell(command)[0], None)

    def test_alias_loops_ask(self) -> None:
        self.repo.write_workflow(phase="build")
        self.repo.git("config", "alias.a", "b")
        self.repo.git("config", "alias.b", "a")
        self.assertEqual(self.shell("git a")[0], "ask")

    # review.md is written by the reviewer only -------------------------------------------------

    def review_edit(self, tool: str = "create_file", path: str = "", **extra):
        path = path or str(self.repo.path / ".ai" / "1234-demo" / "review.md")
        content = "---\nverdict: APPROVED\nreviewed_sha: abc1234\niteration: 1\n---\n"
        payload = self.local(tool, {"filePath": path, "content": content})
        payload.update(extra)
        return self.decide(payload)

    def test_main_agent_cannot_write_review(self) -> None:
        self.repo.write_workflow(phase="build")
        for tool in ("create_file", "replace_string_in_file", "insert_edit_into_file"):
            with self.subTest(tool=tool):
                decision, reason = self.review_edit(tool)
                self.assertEqual(decision, "deny")
                self.assertIn("reviewer subagent", reason)
        other_slug = self.review_edit(path=".ai\\another-slug\\review.md")
        self.assertEqual(other_slug[0], "deny")
        patch = "*** Begin Patch\n*** Update File: .ai/1234-demo/review.md\n@@\n-verdict: X\n+verdict: APPROVED\n"
        self.assertEqual(self.decide(self.local("apply_patch", {"input": patch}))[0], "deny")
        marker = self.review_edit(path=".ai/1234-demo/.reviewer-active")
        self.assertEqual(marker[0], "deny")

    def test_other_subagents_cannot_write_review(self) -> None:
        self.repo.write_workflow(phase="build")
        (self.repo.path / ".ai" / "1234-demo" / ".reviewer-active").write_text("1\n", encoding="utf-8")
        decision, reason = self.review_edit(agent_id="a1", agent_type="implementer")
        self.assertEqual(decision, "deny")
        self.assertIn("implementer", reason)

    def test_reviewer_can_write_review(self) -> None:
        self.repo.write_workflow(phase="build", review_iterations=1)
        self.assertEqual(self.review_edit(agent_id="a1", agent_type="reviewer")[0], None)
        self.assertEqual(self.review_edit(agentId="a1", agentType="ai-driven-dev-harness:reviewer")[0], None)
        (self.repo.path / ".ai" / "1234-demo" / ".reviewer-active").write_text("1\n", encoding="utf-8")
        self.assertEqual(self.review_edit()[0], None, "marker fallback when the harness sends no agent type")
        self.assertEqual(self.review_edit(agent_id="a1")[0], None)

    def test_stale_reviewer_marker_is_ignored(self) -> None:
        self.repo.write_workflow(phase="build")
        marker = self.repo.path / ".ai" / "1234-demo" / ".reviewer-active"
        marker.write_text("1\n", encoding="utf-8")
        old = time.time() - 2 * 3600
        os.utime(marker, (old, old))
        self.assertEqual(self.review_edit()[0], "deny")

    def test_reading_review_is_allowed(self) -> None:
        self.repo.write_workflow(phase="build")
        path = ".ai/1234-demo/review.md"
        self.assertEqual(self.decide(self.local("read_file", {"filePath": path}))[0], None)
        for command in (f"cat {path}", f"Get-Content {path}", "git diff main..HEAD -- src/review.md"):
            with self.subTest(command=command):
                self.assertEqual(self.shell(command)[0], None)

    def test_shell_cannot_write_review(self) -> None:
        self.repo.write_workflow(phase="build")
        for command in (
            "echo 'verdict: APPROVED' > .ai/1234-demo/review.md",
            "Set-Content -Path .ai\\1234-demo\\review.md -Value x",
            "cp /tmp/forged.md .ai/1234-demo/review.md",
            "sed -i 's/CHANGES_REQUESTED/APPROVED/' .ai/1234-demo/review.md",
            "python -c \"open('.ai/1234-demo/review.md','w').write('x')\"",
            "touch .ai/1234-demo/.reviewer-active",
        ):
            with self.subTest(command=command):
                self.assertEqual(self.shell(command)[0], "deny")

    def test_review_rules_need_an_active_workflow(self) -> None:
        self.assertEqual(self.review_edit()[0], None)

    # az CLI ---------------------------------------------------------------------------------

    # git commit: test-first gate ---------------------------------------------------------------

    def stage(self, *paths: str) -> None:
        for path in paths:
            self.repo.write(path, "x = 1\n")
        self.repo.git("add", *paths)

    def test_commit_of_code_without_tests_asks_the_user(self) -> None:
        self.repo.write_workflow(phase="build")
        self.stage("src/scoring.py", "docs/architecture/components.md")
        for command in (
            "git commit -m 'feat(scoring): x'",
            "git -C . commit -q -m 'feat: x'",
            'bash -c "git commit -m x"',
        ):
            with self.subTest(command=command):
                decision, reason = self.shell(command)
                self.assertEqual(decision, "ask")
                self.assertIn("src/scoring.py", reason)
                self.assertIn("red-green-refactor", reason)
                self.assertNotIn("components.md", reason)

    def test_commit_with_tests_has_no_decision(self) -> None:
        self.repo.write_workflow(phase="build")
        for test_path in (
            "tests/test_scoring.py",
            "src/scoring_test.go",
            "web/app/scoring.spec.ts",
            "web/app/__tests__/scoring.js",
            "src/Bank.Tests/ScoringTests.cs",
            "e2e/login.cy.js",
        ):
            with self.subTest(test=test_path):
                self.stage("src/scoring.py", test_path)
                self.assertEqual(self.shell("git commit -m 'feat: x'")[0], None)
                self.repo.git("reset", "-q")

    def test_commit_without_code_has_no_decision(self) -> None:
        self.repo.write_workflow(phase="build")
        self.stage("README.md", "docs/architecture/data.md", "config/app.json")
        self.assertEqual(self.shell("git commit -m 'docs: x'")[0], None)

    def test_commit_gate_sees_files_staged_by_the_same_command(self) -> None:
        self.repo.write_workflow(phase="feedback")
        self.repo.write("src/scoring.py", "x = 2\n")
        for command in ("git add -A && git commit -m 'fix: x'", "git add src/scoring.py; git commit -m x"):
            with self.subTest(command=command):
                self.assertEqual(self.shell(command)[0], "ask")
        self.repo.commit_file("src/scoring.py", "x = 3\n", "feat: base")
        self.repo.write("src/scoring.py", "x = 4\n")
        self.assertEqual(self.shell("git commit -am 'fix: x'")[0], "ask")

    def test_amend_includes_the_files_of_the_amended_commit(self) -> None:
        self.repo.write_workflow(phase="build")
        self.stage("tests/test_scoring.py")
        self.repo.commit_file("src/scoring.py", "x = 1\n", "feat: lot 1")
        self.stage("src/scoring.py")
        self.assertEqual(self.shell("git commit --amend --no-edit")[0], None)
        self.repo.commit_file("src/other.py", "x = 1\n", "feat: lot 2")
        self.assertEqual(self.shell("git commit --amend --no-edit")[0], "ask")

    def test_commit_gate_only_applies_in_build_and_feedback(self) -> None:
        self.stage("src/scoring.py")
        self.assertEqual(self.shell("git commit -m x")[0], None)
        for phase in ("plan", "pr-open", "escalated"):
            with self.subTest(phase=phase):
                self.repo.write_workflow(phase=phase)
                self.assertEqual(self.shell("git commit -m x")[0], None)

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
        self.repo.write_workflow(phase="pr-open", pull_request=7)
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
        self.repo.write_workflow(phase="pr-open", pull_request=7)
        tool = "mcp_ado-write_repo_pull_request_thread_write"
        base = {"repositoryId": "acme-bank", "pullRequestId": 7}
        denied = self.decide(self.local(tool, {**base, "action": "create", "content": "Missing null check."}))
        self.assertEqual(denied[0], "deny")
        self.assertIn(MARKER, denied[1])
        for args in (
            {**base, "action": "create", "content": f"{MARKER} AI review - minor: rename x."},
            {**base, "action": "reply", "threadId": 3, "content": f"  {MARKER} Fixed in abc1234."},
        ):
            with self.subTest(action=args["action"]):
                self.assertEqual(self.decide(self.local(tool, args))[0], None)
        status = {**base, "action": "update_status", "threadId": 3, "status": "Fixed"}
        decision, reason = self.decide(self.local(tool, status))
        self.assertEqual(decision, "ask", "thread ownership cannot be checked: the user confirms")
        self.assertIn("thread 3", reason)

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
