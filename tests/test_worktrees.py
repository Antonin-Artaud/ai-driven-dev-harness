"""Parallel lots in git worktrees (plan-execution skill, ADR 0010).

A lot worktree is ``.ai/<slug>/lot-<n>/`` on the local branch ``ai/<slug>--lot-<n>``. The hooks find
the workflow from inside it, check git commands in the checkout they run in, keep the coding
subagents in their lot worktree while a wave runs, count parallel subagent runs, stop the main agent
while a lot worktree is left, and the close step removes the lot worktrees.
"""

import json
import os
import subprocess
import sys
import time
import unittest
from pathlib import Path

from support import (
    BRANCH,
    CLOSE_WORKFLOW,
    PRE_TOOL_USE,
    SLUG,
    STOP,
    SUBAGENT,
    TempGitRepo,
    load_module,
    lot_branch,
    run_script,
)

hook = load_module("pre_tool_use", PRE_TOOL_USE)
wg = hook.wg
IMPLEMENTER = {"agent_id": "a1", "agent_type": "implementer"}


class WorktreeTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.repo = TempGitRepo()
        self.repo.git("switch", "-c", BRANCH)
        self.directory = self.repo.write_workflow(phase="build")

    def tearDown(self) -> None:
        self.repo.cleanup()

    def evaluate(self, tool: str, tool_input: dict, cwd: Path = None, **extra):
        payload = {"cwd": str(cwd or self.repo.path), "tool_name": tool, "tool_input": tool_input, **extra}
        (decision, reason), _effects = hook.evaluate(wg.parse_input(payload))
        return decision, reason

    def shell(self, command: str, **extra):
        return self.evaluate("run_in_terminal", {"command": command}, **extra)

    def write(self, path: str, **extra):
        return self.evaluate("create_file", {"filePath": path, "content": "x = 1\n"}, **extra)

    def stage_in(self, worktree: Path, *paths: str) -> None:
        for relative in paths:
            target = worktree / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("x = 1\n", encoding="utf-8")
        self.repo.run_git(worktree, "add", *paths)


class DiscoveryTestCase(WorktreeTestCase):
    def test_the_workflow_is_found_from_inside_a_lot_worktree(self) -> None:
        lot = self.repo.add_lot(2)
        (lot / "src").mkdir()
        for cwd in (lot, lot / "src"):
            with self.subTest(cwd=cwd):
                workflow = wg.load_workflow(cwd)
                self.assertIsNotNone(workflow)
                self.assertTrue(wg.same_path(workflow.root, self.repo.path))
                self.assertEqual(workflow.slug, SLUG)
        self.assertEqual(wg.find_repo_root(lot), lot.resolve(), "git commands still run in the worktree")

    def test_other_linked_worktrees_keep_their_own_root(self) -> None:
        elsewhere = self.repo.base / "elsewhere"
        self.repo.git("worktree", "add", "-q", "-b", "hotfix", str(elsewhere), "main")
        self.assertIsNone(wg.load_workflow(elsewhere), "a worktree the user made elsewhere has no workflow")

    def test_lot_worktrees_are_listed_in_lot_order(self) -> None:
        self.repo.add_lot(10)
        self.repo.add_lot(2)
        (self.directory / "notes").mkdir()
        (self.directory / "lot-3").write_text("not a folder\n", encoding="utf-8")
        workflow = wg.load_workflow(self.repo.path)
        self.assertEqual([path.name for path in workflow.lot_worktrees()], ["lot-2", "lot-10"])
        self.assertEqual(workflow.lot_branch(2), lot_branch(2))

    def test_lot_paths(self) -> None:
        self.assertEqual(wg.lot_location(f"/repo/.ai/{SLUG}/lot-2/src/app.py"), ("/repo", SLUG, 2, "src/app.py"))
        self.assertEqual(wg.lot_location(f"C:\\Repo\\.AI\\{SLUG}\\LOT-2"), ("C:/Repo", SLUG, 2, ""))
        for path in (f"/repo/.ai/{SLUG}/lot-2/../state.json", f"/repo/.ai/archive/{SLUG}/lot-2/x", "/repo/lot-2"):
            with self.subTest(path=path):
                self.assertIsNone(wg.lot_location(path))


class ShellInLotWorktreeTestCase(WorktreeTestCase):
    def test_a_commit_is_checked_in_the_lot_worktree_it_runs_in(self) -> None:
        lot = self.repo.add_lot(2)
        self.stage_in(lot, "src/scoring.py")
        relative = f".ai/{SLUG}/lot-2"
        self.assertEqual(self.shell("git commit -m x")[0], None, "nothing is staged in the main checkout")
        for command in (
            f"cd {relative} && git commit -m 'feat: x'",
            f"cd {relative}; git add -A; git commit -m x",
            f"git -C {relative} commit -m x",
            f"git -C '{lot}' commit -m x",
            f"pushd {relative} && git commit -m x",
            f"Set-Location -Path {relative}; git commit -m x",
            f"git -C .ai -C {SLUG}/lot-2 commit -m x",
        ):
            with self.subTest(command=command):
                decision, reason = self.shell(command)
                self.assertEqual(decision, "ask", reason)
                self.assertIn("src/scoring.py", reason)
        self.stage_in(lot, "tests/test_scoring.py")
        self.assertEqual(self.shell(f"git -C {relative} commit -m x")[0], None)

    def test_a_commit_in_an_unknown_folder_asks_in_gated_phases(self) -> None:
        for command in ("cd $WORKTREE && git commit -m x", "cd - && git commit -m x", "git --git-dir=x commit -m x"):
            with self.subTest(command=command):
                decision, reason = self.shell(command)
                self.assertEqual(decision, "ask")
                self.assertIn("cannot resolve", reason)
        self.repo.write_workflow(phase="pr-open", pull_request=7)
        self.assertEqual(self.shell("cd $WORKTREE && git commit -m x")[0], None)

    def test_coding_subagents_commit_in_their_lot_worktree_only(self) -> None:
        self.stage_in(self.repo.path, "src/app.py", "tests/test_app.py")
        self.assertEqual(self.shell("git commit -m x", **IMPLEMENTER)[0], None, "no wave: the main checkout")
        lot = self.repo.add_lot(2)
        for command in ("git commit -m x", f"cd {self.repo.path} && git commit -m x"):
            with self.subTest(command=command):
                decision, reason = self.shell(command, **IMPLEMENTER)
                self.assertEqual(decision, "deny")
                self.assertIn("git -C", reason)
        self.assertEqual(self.shell("git commit -m x", agent_id="a2", agent_type="ui-ux-designer")[0], "deny")
        self.assertEqual(self.shell("git commit -m x")[0], None, "the rule is for the coding subagents")
        self.stage_in(lot, "src/app.py", "tests/test_app.py")
        self.assertEqual(self.shell(f"git -C {lot} commit -m x", **IMPLEMENTER)[0], None)

    def test_a_push_from_a_lot_worktree_is_denied(self) -> None:
        lot = self.repo.add_lot(2)
        relative = f".ai/{SLUG}/lot-2"
        for command in (
            f"cd {relative} && git push",
            f"git -C {relative} push origin HEAD",
            f"git -C '{lot}' push -u origin HEAD",
            f"git push origin {lot_branch(2)}",
        ):
            with self.subTest(command=command):
                decision, reason = self.shell(command)
                self.assertEqual(decision, "deny")
                self.assertIn(BRANCH, reason)
        self.assertEqual(self.shell(f"cd {relative} && cd ../../.. && git push origin HEAD")[0], "ask")
        self.assertEqual(self.shell("git push origin HEAD")[0], "ask", "the main checkout is unchanged")
        self.assertEqual(self.shell("cd $X && git push")[0], "ask", "unknown folder: unresolved")

    def test_coding_subagents_never_push(self) -> None:
        for agent in ("implementer", "ai-driven-dev-harness:ui-ux-designer"):
            with self.subTest(agent=agent):
                decision, reason = self.shell(f"git push origin {BRANCH}", agent_id="a1", agent_type=agent)
                self.assertEqual(decision, "deny")
                self.assertIn("never pushes", reason)
        marker = self.directory / ".implementer-active"
        marker.write_text(f"{time.time():.0f} a1\n", encoding="utf-8")
        self.assertEqual(self.shell("git push")[0], "deny", "identity from the marker")
        marker.unlink()
        self.assertEqual(self.shell(f"git push origin {BRANCH}")[0], "ask")

    def test_aliases_keep_the_folder_of_the_command(self) -> None:
        self.repo.add_lot(2)
        self.repo.git("config", "alias.p", "push")
        self.assertEqual(self.shell(f"git -C .ai/{SLUG}/lot-2 p origin HEAD")[0], "deny")
        self.assertEqual(self.shell("git p origin HEAD")[0], "ask")

    def test_worktree_add_follows_the_lot_convention(self) -> None:
        lot = f".ai/{SLUG}/lot-2"
        allowed = (
            f"git worktree add -b {lot_branch(2)} {lot} {BRANCH}",
            f"git worktree add -b {lot_branch(2)} {self.repo.path / lot}",
            f"git worktree add {lot} {lot_branch(2)}",
            f"git -C .ai worktree add -b {lot_branch(2)} {SLUG}/lot-2 {BRANCH}",
            "git worktree list --porcelain",
            f"git worktree remove {lot}",
            "git worktree prune",
        )
        for command in allowed:
            with self.subTest(command=command):
                self.assertEqual(self.shell(command)[0], None)
        asked = (
            "git worktree add ../elsewhere",
            f"git worktree add -b feature {lot}",
            f"git worktree add -B {lot_branch(2)} {lot} {BRANCH}",
            f"git worktree add --detach {lot} {lot_branch(2)}",
            f"git worktree add -b {lot_branch(3)} {lot} {BRANCH}",
            f"git worktree add -b {lot_branch(2)} .ai/other-work/lot-2",
            f"git worktree add -b {lot_branch(2)} $WT",
        )
        for command in asked:
            with self.subTest(command=command):
                decision, reason = self.shell(command)
                self.assertEqual(decision, "ask")
                self.assertIn("lot convention", reason)

    def test_close_step_mentions_the_lot_worktrees(self) -> None:
        self.repo.add_lot(2)
        decision, reason = self.shell("python /plugin/scripts/close_workflow.py --repo .")
        self.assertEqual(decision, "ask")
        self.assertIn("1 lot worktree", reason)


class FileWritesTestCase(WorktreeTestCase):
    def test_lot_worktree_writes_follow_the_code_rules(self) -> None:
        lot = self.repo.add_lot(2)
        inside = (str(lot / "src" / "app.py"), f".ai/{SLUG}/lot-2/src/app.py", f".AI\\{SLUG}\\LOT-2\\src\\app.py")
        for path in inside:
            with self.subTest(path=path):
                self.assertEqual(self.write(path, **IMPLEMENTER)[0], None)
                self.assertEqual(self.write(path, agent_id="a2", agent_type="ui-ux-designer")[0], None)
                self.assertEqual(self.write(path, agent_id="a3", agent_type="reviewer")[0], "deny")
                self.assertEqual(self.write(path, agent_id="a4", agent_type="security-architect")[0], "deny")
                self.assertEqual(self.write(path)[0], "ask", "the builder does not code")
        self.repo.write_workflow(phase="escalated", escalation={"from": "build", "reason": "x"})
        self.assertEqual(self.write(inside[0])[0], None)

    def test_the_git_link_and_ai_folder_of_a_lot_worktree_are_not_edited(self) -> None:
        lot = self.repo.add_lot(2)
        for path in (lot / ".git", lot / ".ai" / SLUG / "state.json", lot):
            with self.subTest(path=path):
                decision, reason = self.write(str(path), **IMPLEMENTER)
                self.assertEqual(decision, "deny")
                self.assertIn("git worktree", reason)

    def test_coding_subagents_stay_out_of_the_main_checkout_during_a_wave(self) -> None:
        main_file = str(self.repo.path / "src" / "app.py")
        self.assertEqual(self.write(main_file, **IMPLEMENTER)[0], None, "no wave yet")
        lot = self.repo.add_lot(2)
        for path in (main_file, "src/app.py", str(lot / ".." / ".." / ".." / "src" / "app.py")):
            with self.subTest(path=path):
                decision, reason = self.write(path, **IMPLEMENTER)
                self.assertEqual(decision, "deny")
                self.assertIn("lot-2", reason)
        marker = self.directory / ".implementer-active"
        marker.write_text(f"{time.time():.0f} a1\n", encoding="utf-8")
        self.assertEqual(self.write(main_file)[0], "deny", "identity from the marker")
        marker.unlink()
        outside = str(self.repo.base / "scratch.txt")
        self.assertEqual(self.write(outside, **IMPLEMENTER)[0], None, "outside the repository: not the checkout")
        self.assertEqual(self.write(f".ai/{SLUG}/plan.md", **IMPLEMENTER)[0], "deny")
        self.repo.git("worktree", "remove", str(lot))
        self.assertEqual(self.write(main_file, **IMPLEMENTER)[0], None, "wave over")

    def test_dot_segments_do_not_hide_a_workflow_file(self) -> None:
        self.repo.add_lot(2)
        state = json.dumps({**self.repo.state(), "phase": "pr-open"})
        for path in (
            f".ai/{SLUG}/lot-2/../state.json",
            f".ai/{SLUG}/../{SLUG}/state.json",
            f".ai/{SLUG}/x/../state.json",
            f".ai\\{SLUG}\\.\\state.json",
        ):
            with self.subTest(path=path):
                decision, reason = self.evaluate("create_file", {"filePath": path, "content": state})
                self.assertEqual(decision, "deny")
                self.assertIn("pull_request", reason)
        for command in (
            f"echo '{{}}' > .ai/{SLUG}/lot-2/../state.json",
            f"cp /tmp/forged.md .ai/{SLUG}/x/y/../../review.md",
            f"touch .ai/{SLUG}/./.reviewer-active",
        ):
            with self.subTest(command=command):
                self.assertEqual(self.shell(command)[0], "deny")
        self.assertEqual(self.shell(f"cat .ai/{SLUG}/lot-2/../state.json")[0], None, "reading is fine")

    def test_the_lock_is_hook_owned(self) -> None:
        self.assertEqual(self.write(f".ai/{SLUG}/.lock")[0], "deny")
        self.assertEqual(self.shell(f"touch .ai/{SLUG}/.lock")[0], "deny")


class StopAndHostTestCase(WorktreeTestCase):
    def stop(self, cwd: Path = None) -> dict:
        payload = {"hook_event_name": "Stop", "cwd": str(cwd or self.repo.path), "stop_hook_active": False}
        return run_script(STOP, payload, self.repo.env)

    def test_stop_waits_for_the_lot_worktrees_to_be_integrated(self) -> None:
        sha = self.repo.commit_file("src/app.py", "x = 1\n", "feat: lot 1")
        self.repo.write_workflow(phase="build", review={"verdict": "APPROVED", "reviewed_sha": sha})
        self.assertEqual(self.stop(), {})
        lot = self.repo.add_lot(2)
        result = self.stop()
        self.assertEqual(result.get("decision"), "block")
        self.assertIn("Lot gate", result["reason"])
        self.assertIn(f".ai/{SLUG}/lot-2", result["reason"])
        self.assertIn("merge --ff-only", result["reason"])
        self.repo.git("worktree", "remove", str(lot))
        self.assertEqual(self.stop(), {})
        self.repo.add_lot(3)
        self.repo.write_workflow(phase="escalated", escalation={"from": "build", "reason": "plan deviation"})
        self.assertEqual(self.stop(), {}, "escalated: the user decides")

    def test_hooks_apply_when_the_host_runs_in_a_lot_worktree(self) -> None:
        lot = self.repo.add_lot(2)
        payload = {"cwd": str(lot), "tool_name": "run_in_terminal", "tool_input": {"command": "git push"}}
        result = run_script(PRE_TOOL_USE, payload, self.repo.env)
        self.assertEqual(result["permissionDecision"], "deny")
        self.assertIn(lot_branch(2), result["permissionDecisionReason"])
        self.assertEqual(self.repo.log_entries()[-1]["decision"], "deny", "logged in the main checkout's .ai/")
        self.assertEqual(self.stop(cwd=lot).get("decision"), "block")


class ParallelSubagentsTestCase(WorktreeTestCase):
    def event(self, event: str, payload: dict) -> dict:
        return run_script(SUBAGENT, {"cwd": str(self.repo.path), **payload}, self.repo.env, args=[event])

    def test_the_marker_lasts_until_the_last_parallel_run_stops(self) -> None:
        marker = self.directory / ".implementer-active"
        self.event("start", {"agentName": "implementer", "agentId": "a1"})
        self.event("start", {"agentName": "implementer", "agentId": "a2"})
        self.assertEqual([run for _, run in wg.marker_runs(marker)], ["a1", "a2"])
        self.event("stop", {"agent_type": "implementer", "agent_id": "a1"})
        self.assertEqual([run for _, run in wg.marker_runs(marker)], ["a2"])
        self.assertTrue(wg.marker_active(marker), "lot 3 still runs: its writes keep the implementer's rights")
        self.event("stop", {"agent_type": "implementer", "agent_id": "a2"})
        self.assertFalse(marker.exists())
        usage = json.loads((self.directory / "usage.json").read_text(encoding="utf-8"))
        self.assertEqual(usage["agents"]["implementer"]["runs"], 2)

    def test_runs_without_id_stop_oldest_first(self) -> None:
        marker = self.directory / ".implementer-active"
        marker.write_text("1\n", encoding="utf-8")  # written by an earlier plugin version
        self.event("start", {"agentName": "implementer"})
        self.assertEqual(len(wg.marker_runs(marker)), 2)
        self.assertEqual(wg.remove_marker_run(marker, ""), 1.0)
        self.assertEqual(len(wg.marker_runs(marker)), 1)
        self.assertIsNotNone(wg.remove_marker_run(marker, "unknown"))
        self.assertFalse(marker.exists())
        self.assertIsNone(wg.remove_marker_run(marker, ""))

    def test_concurrent_starts_keep_every_run(self) -> None:
        env = dict(self.repo.env, PYTHONPATH=str(Path(__file__).resolve().parent))
        processes = []
        for index in range(4):
            payload = json.dumps({"cwd": str(self.repo.path), "agentName": "implementer", "agentId": f"r{index}"})
            process = subprocess.Popen(
                [sys.executable, str(SUBAGENT), "start"],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=env,
            )
            processes.append((process, payload))
        for process, payload in processes:
            process.communicate(payload.encode("utf-8"), timeout=60)
            self.assertEqual(process.returncode, 0)
        runs = sorted(run for _, run in wg.marker_runs(self.directory / ".implementer-active"))
        self.assertEqual(runs, ["r0", "r1", "r2", "r3"])
        self.assertFalse((self.directory / ".lock").exists())

    def test_the_lock_waits_then_gives_up_and_breaks_stale_locks(self) -> None:
        lock = self.directory / ".lock"
        saved = wg.LOCK_TIMEOUT
        wg.LOCK_TIMEOUT = 0.05
        try:
            lock.write_text("", encoding="utf-8")
            started = time.time()
            with wg.locked(self.directory) as acquired:
                self.assertFalse(acquired, "held by another hook: go on without it")
            self.assertLess(time.time() - started, 2)
            self.assertTrue(lock.exists(), "another hook's lock is left alone")
            old = time.time() - wg.LOCK_STALE - 5
            os.utime(lock, (old, old))
            with wg.locked(self.directory) as acquired:
                self.assertTrue(acquired, "a killed hook's lock is broken")
            self.assertFalse(lock.exists())
            with wg.locked(self.directory / "missing") as acquired:
                self.assertFalse(acquired)
        finally:
            wg.LOCK_TIMEOUT = saved


class IntegrationAndCloseTestCase(WorktreeTestCase):
    def commit_in(self, worktree: Path, relative: str, message: str) -> str:
        (worktree / relative).parent.mkdir(parents=True, exist_ok=True)
        (worktree / relative).write_text(f"# {message}\n", encoding="utf-8")
        self.repo.run_git(worktree, "add", relative)
        self.repo.run_git(worktree, "commit", "-q", "-m", message)
        return self.repo.run_git(worktree, "rev-parse", "HEAD")

    def close(self):
        proc = subprocess.run(
            [sys.executable, str(CLOSE_WORKFLOW), "--repo", str(self.repo.path), "--reason", "PR completed"],
            capture_output=True,
            env=self.repo.env,
            timeout=60,
        )
        return proc.returncode, json.loads(proc.stdout.decode("utf-8"))

    def integrate(self, lot: int, worktree: Path) -> None:
        """The builder's integration step (plan-execution skill)."""
        self.repo.run_git(worktree, "rebase", "-q", BRANCH)
        self.repo.git("merge", "-q", "--ff-only", lot_branch(lot))
        self.repo.git("worktree", "remove", str(worktree))
        self.repo.git("branch", "-d", lot_branch(lot))

    def test_documented_integration_keeps_one_commit_per_lot_on_a_linear_branch(self) -> None:
        base = self.repo.head()
        lot2, lot3 = self.repo.add_lot(2), self.repo.add_lot(3)
        self.commit_in(lot2, "src/a.py", "feat: lot 2")
        self.commit_in(lot3, "src/b.py", "feat: lot 3")
        self.integrate(2, lot2)
        self.integrate(3, lot3)
        log = self.repo.git("log", "--format=%s", f"{base}..HEAD").splitlines()
        self.assertEqual(log, ["feat: lot 3", "feat: lot 2"])
        self.assertEqual(self.repo.git("rev-list", "--merges", f"{base}..HEAD"), "", "no merge commit")
        self.assertEqual(wg.load_workflow(self.repo.path).lot_worktrees(), [])

    def test_close_removes_the_lot_worktrees_and_the_integrated_branches(self) -> None:
        lot2, lot3 = self.repo.add_lot(2), self.repo.add_lot(3)
        self.commit_in(lot2, "src/a.py", "feat: lot 2")
        self.repo.run_git(lot2, "rebase", "-q", BRANCH)
        self.repo.git("merge", "-q", "--ff-only", lot_branch(2))
        self.commit_in(lot3, "src/b.py", "feat: lot 3 (never integrated)")
        (lot3 / "build").mkdir()
        self.repo.exclude("build/")
        (lot3 / "build" / "out.bin").write_text("ignored output\n", encoding="utf-8")
        code, result = self.close()
        self.assertEqual(code, 0, result)
        self.assertEqual(result["removed_lot_worktrees"], [f".ai/{SLUG}/lot-2", f".ai/{SLUG}/lot-3"])
        self.assertEqual(result["deleted_lot_branches"], [lot_branch(2)])
        self.assertEqual(result["kept_lot_branches"], [lot_branch(3)], "its commit is not in the work branch")
        self.assertTrue((self.repo.path / ".ai" / "archive" / SLUG / "state.json").exists())
        self.assertNotIn("lot-", self.repo.git("worktree", "list"))

    def test_close_stops_before_anything_changes_when_a_lot_holds_uncommitted_work(self) -> None:
        lot = self.repo.add_lot(2)
        (lot / "wip.py").write_text("x = 1\n", encoding="utf-8")
        (self.directory / "lot-3").mkdir()
        code, result = self.close()
        self.assertEqual(code, 1)
        self.assertIn("lot-2 (uncommitted changes)", result["error"])
        self.assertIn("lot-3 (not a git worktree)", result["error"])
        self.assertEqual(self.repo.state()["phase"], "build")
        self.assertTrue(lot.exists())
        self.assertTrue((self.repo.path / ".ai" / "current").exists())


if __name__ == "__main__":
    unittest.main()
