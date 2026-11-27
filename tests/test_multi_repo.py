"""Multi-repository workspaces: .ai/ in the folder that holds the repositories (ADR 0011).

The hooks find .ai/ above the repositories, govern only the repositories state.json lists, and
check every git rule in the repository the command runs in. Single-repository behavior is covered
by the other test modules, unchanged.
"""

import json
import subprocess
import sys
import time
import unittest
from pathlib import Path

from support import (
    BRANCH,
    CLOSE_WORKFLOW,
    ONBOARD,
    PRE_TOOL_USE,
    SLUG,
    STOP,
    TempGitRepo,
    TempWorkspace,
    load_module,
    run_script,
)

hook = load_module("pre_tool_use", PRE_TOOL_USE)
wg = hook.wg
sp = hook.sp
usage_report = load_module("usage_report", wg.PLUGIN_ROOT / "scripts" / "usage_report.py")
STATE = f".ai/{SLUG}/state.json"
VALIDATED = {"at": "2026-11-27T10:00:00Z", "head": "abc1234"}
MARKER = "\U0001f916"
GUID = "3f2504e0-4f89-11d3-9a0c-0305e82c3301"


class WorkspaceTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.ws = TempWorkspace()

    def tearDown(self) -> None:
        self.ws.cleanup()

    def evaluate(self, tool: str, tool_input: dict, cwd: Path = None, **extra):
        payload = {"cwd": str(cwd or self.ws.path), "tool_name": tool, "tool_input": tool_input, **extra}
        (decision, reason), effects = hook.evaluate(wg.parse_input(payload))
        if decision != "deny":
            sp.apply_effects(wg.load_workflow(cwd or self.ws.path), effects)
        return decision, reason

    def shell(self, command: str, cwd: Path = None):
        return self.evaluate("run_in_terminal", {"command": command}, cwd)

    def write_state(self, state: dict):
        return self.evaluate("create_file", {"filePath": STATE, "content": json.dumps(state)})

    def state(self, **changes) -> dict:
        current = self.ws.state()
        current.update(changes)
        return current

    def stop(self) -> dict:
        return run_script(STOP, {"hook_event_name": "Stop", "cwd": str(self.ws.path)}, self.ws.env)

    def assert_decision(self, result, expected, text: str = "") -> None:
        self.assertEqual(result[0], expected, result[1])
        self.assertIn(text, result[1])

    def work_branch(self, *names: str) -> None:
        for name in names:
            self.ws.git(name, "switch", "-c", BRANCH)


class LocateWorkflowTestCase(WorkspaceTestCase):
    def test_workflow_root_is_the_folder_above_the_repositories(self) -> None:
        self.ws.write_workflow(phase="build")
        for cwd in (self.ws.path, self.ws.path / "api", self.ws.path / "web" / "src", self.ws.path / ".ai"):
            with self.subTest(cwd=cwd.name):
                self.assertEqual(wg.find_workflow_root(cwd), self.ws.path.resolve())
                workflow = wg.load_workflow(cwd)
                self.assertIsNotNone(workflow)
                self.assertTrue(workflow.multi_repo)
                self.assertEqual([repository.path for repository in workflow.repositories], ["api", "web"])

    def test_unlisted_repositories_keep_working_without_the_gates(self) -> None:
        self.ws.add_repository("tools")
        self.ws.write_workflow(phase="build")
        self.assertIsNone(wg.load_workflow(self.ws.path / "tools"))
        self.assertEqual(self.shell("git push --force", cwd=self.ws.path / "tools")[0], None)
        self.assertEqual(self.shell("git push --force")[0], "deny", "the workspace session is governed")
        self.ws.write_workflow(phase="challenge", repositories=None)
        self.assertIsNotNone(wg.load_workflow(self.ws.path), "the workflow is active before it lists repositories")
        self.assertIsNone(wg.load_workflow(self.ws.path / "api"), "a repository is governed once listed")

    def test_a_repository_workflow_wins_over_the_workspace_one(self) -> None:
        self.ws.write_workflow(phase="build")
        own = self.ws.path / "api" / ".ai"
        (own / "own-work").mkdir(parents=True)
        (own / "current").write_text("own-work\n", encoding="utf-8")
        (own / "own-work" / "state.json").write_text('{"phase": "design"}', encoding="utf-8")
        workflow = wg.load_workflow(self.ws.path / "api")
        self.assertEqual((workflow.root, workflow.slug), ((self.ws.path / "api").resolve(), "own-work"))
        self.assertFalse(workflow.multi_repo)

    def test_an_archive_left_in_a_repository_does_not_hide_the_workspace_workflow(self) -> None:
        self.ws.write_workflow(phase="build")
        (self.ws.path / "api" / ".ai" / "archive" / "old-work").mkdir(parents=True)
        self.assertEqual(wg.find_workflow_root(self.ws.path / "api"), self.ws.path.resolve())

    def test_only_one_level_above_the_repository(self) -> None:
        nested = self.ws.path / "services" / "billing"
        nested.mkdir(parents=True)
        self.ws.run_git(nested, "init", "-b", "main")
        self.ws.write_workflow(phase="build", repositories=["services/billing"])
        self.assertIsNotNone(wg.load_workflow(self.ws.path), "listed from the workspace")
        self.assertIsNone(wg.find_workflow_root(nested))
        self.assertIsNone(wg.load_workflow(nested))

    def test_no_workflow_folder(self) -> None:
        self.assertIsNone(wg.find_workflow_root(self.ws.path / "api"))
        self.assertIsNone(wg.load_workflow(self.ws.path))
        self.assertEqual(self.shell("git push --force")[0], None)

    def test_reviewed_sha_forms(self) -> None:
        self.assertEqual(wg.reviewed_shas("ABC1234"), {"": "abc1234"})
        expected = {"api": "abc1234", "web/app": "def5678"}
        for value in ("api=ABC1234 web/app=def5678", "api=abc1234, ./web\\app/=def5678", "api=abc1234;web/app=def5678"):
            with self.subTest(value=value):
                self.assertEqual(wg.reviewed_shas(value), expected)


class ShellCommandsTestCase(WorkspaceTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.work_branch("api")
        self.ws.write_workflow(phase="build")

    def test_push_is_checked_in_the_repository_it_runs_in(self) -> None:
        cases = (
            (f"cd api && git push -u origin {BRANCH}", "ask", "in api"),
            ("git -C api push", "ask", "in api"),
            ("git -C web push", "deny", "current branch in web is 'main'"),
            ("cd web; git push", "deny", "in web"),
            ("pushd web && git push", "deny", "in web"),
            ("Set-Location -Path web; git push", "deny", "in web"),
            ("cd web && cd ../api && git push", "ask", "in api"),
            (f"cd {self.ws.path / 'web'} && git push origin HEAD", "deny", "pushes to 'main'"),
            ("git push", "ask", "cannot match"),
            ("cd $REPO && git push", "ask", "cannot match"),
            ("(cd api; git status) && git push", "ask", "cannot match"),
            ("git -C web push origin ai/x:main", "deny", "pushes to 'main'"),
            ("cd api && git push --force", "deny", "force push"),
            ("git -C web push -f", "deny", "force push"),
        )
        for command, expected, text in cases:
            with self.subTest(command=command):
                self.assert_decision(self.shell(command), expected, text)

    def test_a_child_shell_does_not_move_the_next_commands(self) -> None:
        api = self.ws.path / "api"
        self.assert_decision(self.shell("bash -c 'cd ../web' && git push", cwd=api), "ask", "in api")
        self.assert_decision(self.shell('cmd /c "cd ..\\web" && git push', cwd=api), "ask", "in api")
        self.assert_decision(self.shell("eval 'cd ../web' && git push", cwd=api), "deny", "in web")

    def test_git_aliases_of_a_repository_are_resolved_there(self) -> None:
        self.ws.git("web", "config", "alias.pf", "push --force")
        self.assert_decision(self.shell("git -C web pf"), "deny", "force push")
        self.ws.git("api", "config", "alias.up", "push")
        self.assert_decision(self.shell("cd api && git up"), "ask", "in api")
        self.assertEqual(self.shell("git -C web up")[0], None, "the alias is defined in api only")

    def test_commit_gate_runs_in_the_repository_of_the_commit(self) -> None:
        self.ws.write("api", "src/app.py", "x = 1\n")
        self.ws.git("api", "add", "src/app.py")
        for command in ("cd api && git commit -m 'feat: x'", "git -C api commit -m x"):
            with self.subTest(command=command):
                self.assert_decision(self.shell(command), "ask", "This commit in api changes code (src/app.py)")
        self.ws.write("web", "src/app.ts", "export {}\n")
        self.ws.write("web", "src/app.spec.ts", "export {}\n")
        self.ws.git("web", "add", "src")
        self.assertEqual(self.shell("git -C web commit -m 'feat: y'")[0], None)
        for command in ("git commit -m x", "(cd api && git commit -m x)", "cd $REPO && git commit -m x"):
            with self.subTest(command=command):
                self.assert_decision(self.shell(command), "ask", "cannot match")
        self.ws.write_workflow(phase="pr-open")
        self.assertEqual(self.shell("(cd api && git commit -m x)")[0], None, "the gate covers build and feedback")

    def test_decisions_log_the_head_of_every_repository(self) -> None:
        run_script(
            PRE_TOOL_USE,
            {"cwd": str(self.ws.path), "tool_name": "run_in_terminal", "tool_input": {"command": "git push -f"}},
            self.ws.env,
        )
        entry = self.ws.log_entries()[-1]
        self.assertEqual(entry["decision"], "deny")
        self.assertEqual(entry["head"], {"api": self.ws.head("api"), "web": self.ws.head("web")})


class StopGateTestCase(WorkspaceTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.work_branch("api", "web")

    def test_nothing_implemented_yet_allows_stop(self) -> None:
        self.ws.write_workflow(phase="build")
        self.assertEqual(self.stop(), {})

    def test_review_covers_every_repository_with_changes(self) -> None:
        api = self.ws.commit_file("api", "src/app.py", "x = 1\n", "feat: lot 1")
        self.ws.write_workflow(phase="build")
        self.assertIn(f"review.md is missing for HEAD api@{api[:8]}", self.stop()["reason"])
        self.ws.write_workflow(phase="build", review={"verdict": "APPROVED", "reviewed_sha": f"api={api}"})
        self.assertEqual(self.stop(), {}, "web has no change: nothing to review there")
        self.ws.write_workflow(phase="build", review={"verdict": "APPROVED", "reviewed_sha": api})
        self.assertIn("reviewed nothing for api but HEAD of api", self.stop()["reason"], "two repositories: by path")
        web = self.ws.commit_file("web", "src/app.ts", "export {}\n", "feat: lot 2")
        self.ws.write_workflow(phase="feedback", review={"verdict": "APPROVED", "reviewed_sha": f"api={api}"})
        self.assertIn(f"but HEAD of web is {web[:8]}", self.stop()["reason"])
        both = f"api={api[:10]} web={web}"
        self.ws.write_workflow(phase="feedback", review={"verdict": "APPROVED", "reviewed_sha": both})
        self.assertEqual(self.stop(), {})
        self.ws.write_workflow(phase="feedback", review={"verdict": "CHANGES_REQUESTED", "reviewed_sha": both})
        self.assertIn("CHANGES_REQUESTED", self.stop()["reason"])

    def test_uncommitted_changes_of_any_repository_block(self) -> None:
        api = self.ws.commit_file("api", "src/app.py", "x = 1\n", "feat: lot 1")
        self.ws.write_workflow(phase="build", review={"verdict": "APPROVED", "reviewed_sha": f"api={api}"})
        self.ws.write("web", "notes.txt", "user notes\n")
        self.assertIn("uncommitted changes (web/notes.txt)", self.stop()["reason"])
        self.ws.set_hook_state(untracked_baseline=["web/notes.txt"], stop_blocks=0)
        self.assertEqual(self.stop(), {})

    def test_record_gate_covers_every_pull_request(self) -> None:
        repositories = [
            {"path": "api", "pull_request": 7, "record_thread": 3},
            {"path": "web", "pull_request": 9, "record_thread": None},
        ]
        self.ws.write_workflow(phase="pr-open", repositories=repositories)
        reason = self.stop()["reason"]
        self.assertIn("Record gate", reason)
        self.assertIn("9 (web)", reason)
        self.assertNotIn("7 (api)", reason)
        repositories[1]["record_thread"] = 4
        self.ws.write_workflow(phase="pr-open", repositories=repositories)
        self.assertEqual(self.stop(), {})


class StateTransitionsTestCase(WorkspaceTestCase):
    def design_ready(self, **overrides) -> None:
        now = time.time()
        self.ws.write_workflow(phase="design", brief_validated=VALIDATED, plan_validated=VALIDATED, **overrides)
        for name in ("brief.md", "plan.md"):
            (self.ws.path / ".ai" / SLUG / name).write_text("# x\n", encoding="utf-8")
        self.ws.set_hook_state(
            written_at={"brief.md": now - 100, "plan.md": now - 90},
            validated_at={"brief.md": now - 80, "plan.md": now - 70},
        )

    def test_build_needs_the_repositories(self) -> None:
        self.design_ready(repositories=None)
        self.assert_decision(self.write_state(self.state(phase="build")), "deny", "is not a git repository")
        (self.ws.path / "docs").mkdir()
        self.design_ready(repositories=["api", "docs"])
        self.assert_decision(
            self.write_state(self.state(phase="build")), "deny", "repository 'docs' is not the root of a git repository"
        )
        self.ws.write("web", "notes.txt", "user notes\n")
        self.design_ready()
        self.assert_decision(self.write_state(self.state(phase="build")), None)
        self.assertEqual(self.ws.hook_state()["untracked_baseline"], ["web/notes.txt"])

    def test_repositories_are_well_formed(self) -> None:
        new = {"slug": "new-work", "phase": "challenge", "repositories": ["../x"]}
        created = self.evaluate("create_file", {"filePath": ".ai/new-work/state.json", "content": json.dumps(new)})
        self.ws.write_workflow(phase="design")
        self.assertEqual(created[0], None, "no active workflow yet: no rule")
        self.assert_decision(
            self.evaluate("create_file", {"filePath": ".ai/new-work/state.json", "content": json.dumps(new)}),
            "deny",
            "inside the workflow root",
        )
        for value, text in (
            ("api", "must be a list"),
            (["../elsewhere"], "inside the workflow root"),
            (["/abs/api"], "inside the workflow root"),
            ([".ai/x"], "inside the workflow root"),
            (["api", "./API/"], "listed twice"),
            (["services/billing"], "must sit directly in the workflow root"),
            ([{"path": "api", "base_branch": ""}], "base_branch of repository 'api'"),
        ):
            with self.subTest(value=value):
                self.assert_decision(self.write_state(self.state(repositories=value)), "deny", text)
        changed = [{"path": "web", "base_branch": "develop"}, "api"]
        self.assert_decision(self.write_state(self.state(repositories=changed)), None)

    def test_repositories_are_fixed_once_the_build_starts(self) -> None:
        self.ws.write_workflow(phase="build")
        self.assert_decision(
            self.write_state(self.state(repositories=["api"])), "deny", "only changes before the build starts"
        )
        moved = [{"path": "api", "base_branch": "develop"}, {"path": "web"}]
        self.assert_decision(self.write_state(self.state(repositories=moved)), "deny", "only changes before")
        recorded = [{"path": "api", "pull_request": 7}, {"path": "web"}]
        self.assert_decision(self.write_state(self.state(repositories=recorded)), None)
        self.ws.write_workflow(phase="build", repositories=recorded)
        changed = [{"path": "api", "pull_request": 8}, {"path": "web"}]
        self.assert_decision(self.write_state(self.state(repositories=changed)), "deny", "'pull_request' of repository")
        self.assert_decision(self.write_state(self.state(pull_request=7)), "deny", "not at the top level")

    def test_pr_open_needs_a_pull_request_per_changed_repository(self) -> None:
        self.work_branch("api", "web")
        api = self.ws.commit_file("api", "src/app.py", "x = 1\n", "feat: lot 1")
        web = self.ws.commit_file("web", "src/app.ts", "export {}\n", "feat: lot 2")
        review = {"verdict": "APPROVED", "reviewed_sha": f"api={api} web={web}", "iteration": "1"}
        self.ws.write_workflow(phase="build", review_iterations=1, review=review)
        self.assert_decision(self.write_state(self.state(phase="pr-open")), "deny", "'pull_request' of its repository")
        one = [{"path": "api", "pull_request": 7}, {"path": "web"}]
        self.assert_decision(self.write_state(self.state(phase="pr-open", repositories=one)), "deny", "web has no")
        self.ws.write_workflow(phase="build", review_iterations=1, review=review, repositories=one)
        both = [{"path": "api", "pull_request": 7}, {"path": "web", "pull_request": 9}]
        self.assert_decision(self.write_state(self.state(phase="pr-open", repositories=both)), None)


class PullRequestTestCase(WorkspaceTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.work_branch("api", "web")
        self.api = self.ws.commit_file("api", "src/app.py", "x = 1\n", "feat: lot 1")
        self.web = self.ws.commit_file("web", "src/app.ts", "export {}\n", "feat: lot 2")
        for name in ("api", "web"):
            self.ws.git(name, "push", "-u", "origin", BRANCH)
        self.review = {"verdict": "APPROVED", "reviewed_sha": f"api={self.api} web={self.web}"}

    def pr_create(self, **overrides):
        args = {
            "action": "create",
            "repositoryId": "web",
            "project": "Credit",
            "sourceRefName": f"refs/heads/{BRANCH}",
            "targetRefName": "refs/heads/main",
            "title": "feat(web): show the score",
            "description": "Why: users need the score.",
            "isDraft": True,
        }
        args.update(overrides)
        return self.evaluate("mcp_ado-write_repo_pull_request_write", args)

    def test_pr_create_targets_the_named_repository(self) -> None:
        self.ws.write_workflow(phase="build", review=self.review)
        self.assert_decision(self.pr_create(), "ask", f"in web from {BRANCH} into main")
        self.assert_decision(self.pr_create(repositoryId="api"), "ask", f"in api from {BRANCH}")
        self.assert_decision(self.pr_create(repositoryId="web-origin"), "ask", "in web")

    def test_pr_create_needs_a_repository_name(self) -> None:
        self.ws.write_workflow(phase="build", review=self.review)
        self.assert_decision(self.pr_create(repositoryId=None), "deny", "name the repository")
        self.assert_decision(self.pr_create(repositoryId=GUID), "deny", "by name")
        self.assert_decision(self.pr_create(repositoryId="billing"), "deny", "not one of the workflow's repositories")

    def test_pr_create_checks_the_target_repository(self) -> None:
        self.ws.write_workflow(phase="build", review=self.review)
        self.ws.commit_file("web", "src/other.ts", "export {}\n", "feat: unpushed")
        self.assert_decision(self.pr_create(), "deny", "but HEAD of web")
        review = {"verdict": "APPROVED", "reviewed_sha": f"api={self.api} web={self.ws.head('web')}"}
        self.ws.write_workflow(phase="build", review=review)
        self.assert_decision(self.pr_create(), "deny", "git -C web push -u origin")
        self.assert_decision(self.pr_create(repositoryId="api"), "ask", "in api")

    def test_one_pull_request_per_repository(self) -> None:
        recorded = [{"path": "api"}, {"path": "web", "pull_request": 9}]
        self.ws.write_workflow(phase="build", review=self.review, repositories=recorded)
        self.assert_decision(self.pr_create(), "deny", "repository 'web' already has draft PR 9")
        self.assert_decision(self.pr_create(repositoryId="api"), "ask", "in api")

    def test_each_repository_has_its_base_branch(self) -> None:
        repositories = [{"path": "api"}, {"path": "web", "base_branch": "develop"}]
        self.ws.write_workflow(phase="build", review=self.review, repositories=repositories)
        self.assert_decision(self.pr_create(), "deny", "differs from base_branch 'develop' in web")
        self.assert_decision(self.pr_create(targetRefName="refs/heads/develop"), "ask", "into develop")

    def test_a_repository_without_commits_has_nothing_to_merge(self) -> None:
        self.ws.add_repository("docs")
        self.ws.git("docs", "switch", "-c", BRANCH)
        review = {"verdict": "APPROVED", "reviewed_sha": f"api={self.api} web={self.web}"}
        self.ws.write_workflow(phase="build", review=review, repositories=["api", "web", "docs"])
        self.assert_decision(self.pr_create(repositoryId="docs"), "deny", "nothing to merge")

    def test_pr_writes_are_scoped_to_the_workflow_pull_requests(self) -> None:
        repositories = [
            {"path": "api", "pull_request": 7, "record_thread": 3},
            {"path": "web", "pull_request": 9, "record_thread": 4},
        ]
        self.ws.write_workflow(phase="pr-open", repositories=repositories)
        thread = "mcp_ado-write_repo_pull_request_thread_write"
        reply = {"action": "reply", "threadId": 5, "content": f"{MARKER} Fixed in abc1234."}
        self.assert_decision(self.evaluate(thread, {**reply, "pullRequestId": 9}), None)
        self.assert_decision(self.evaluate(thread, {**reply, "pullRequestId": 8}), "deny", "7 (api), 9 (web)")
        status = {"action": "update_status", "status": "Fixed"}
        self.assert_decision(
            self.evaluate(thread, {**status, "pullRequestId": 9, "threadId": 4}), "deny", "record thread"
        )
        self.assert_decision(
            self.evaluate(thread, {**status, "pullRequestId": 9, "threadId": 3}), "ask", "thread 3 of PR 9 in web"
        )
        update = {"action": "update", "pullRequestId": 7, "description": "Updated scope."}
        self.assert_decision(self.evaluate("mcp_ado-write_repo_pull_request_write", update), None)


class ScriptsTestCase(WorkspaceTestCase):
    def test_close_archives_the_workspace_workflow(self) -> None:
        self.ws.write_workflow(phase="pr-open", repositories=[{"path": "api", "pull_request": 7}])
        proc = subprocess.run(
            [sys.executable, str(CLOSE_WORKFLOW), "--repo", str(self.ws.path / "api"), "--reason", "PR completed"],
            capture_output=True,
            env=self.ws.env,
            timeout=60,
        )
        result = json.loads(proc.stdout.decode("utf-8"))
        self.assertEqual(proc.returncode, 0, result)
        self.assertEqual(result["archived_to"], f".ai/archive/{SLUG}")
        self.assertFalse((self.ws.path / ".ai" / "current").exists())
        self.assertTrue((self.ws.path / ".ai" / "archive" / SLUG / "state.json").is_file())
        self.assertEqual(
            usage_report.workflow_directory(self.ws.path / "web", SLUG),
            (self.ws.path / ".ai" / "archive" / SLUG).resolve(),
        )


class OnboardWorkspaceTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.ws = TempWorkspace(names=("api",))
        self.ws.git("api", "remote", "set-url", "origin", "https://dev.azure.com/contoso/Credit/_git/acme-api")

    def tearDown(self) -> None:
        self.ws.cleanup()

    def run_onboard(self, *args: str):
        proc = subprocess.run(
            [sys.executable, str(ONBOARD), "--repo", str(self.ws.path / "api"), *args],
            capture_output=True,
            env=self.ws.env,
            timeout=60,
        )
        return proc.returncode, json.loads(proc.stdout.decode("utf-8"))

    def test_mcp_config_goes_to_the_workspace(self) -> None:
        code, summary = self.run_onboard("--workspace", str(self.ws.path))
        self.assertEqual(code, 0, summary)
        self.assertEqual(summary["workspace"]["repository_path"], "api")
        self.assertTrue((self.ws.path / ".vscode" / "mcp.json").is_file())
        self.assertFalse((self.ws.path / "api" / ".vscode").exists())
        self.assertEqual(summary["git_exclude"]["added"], [".ai/"])
        self.assertIsNone(summary["workspace_git_exclude"])
        self.assertTrue(any("--workspace" in step for step in summary["next_steps"]))

    def test_workspace_inside_another_repository_is_excluded_there(self) -> None:
        self.ws.run_git(self.ws.path, "init", "-b", "main")
        code, summary = self.run_onboard("--workspace", str(self.ws.path))
        self.assertEqual(code, 0, summary)
        self.assertEqual(summary["workspace_git_exclude"]["added"], [".ai/", ".vscode/mcp.json"])
        exclude = (self.ws.path / ".git" / "info" / "exclude").read_text(encoding="utf-8").splitlines()
        self.assertIn(".ai/", exclude)

    def test_workspace_must_hold_the_repository(self) -> None:
        other = TempGitRepo(with_origin=False)
        try:
            code, summary = self.run_onboard("--workspace", str(other.path))
            self.assertEqual((code, summary["ok"]), (1, False))
            self.assertIn("must be an existing folder that holds the repository", summary["error"])
        finally:
            other.cleanup()

    def test_workspace_equal_to_the_repository_is_the_single_repository_layout(self) -> None:
        code, summary = self.run_onboard("--workspace", str(self.ws.path / "api"))
        self.assertEqual(code, 0, summary)
        self.assertIsNone(summary["workspace"])
        self.assertTrue((self.ws.path / "api" / ".vscode" / "mcp.json").is_file())


if __name__ == "__main__":
    unittest.main()
