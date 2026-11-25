#!/usr/bin/env python3
"""Close step of the ai-driven-dev-harness: archive the active workflow.

Removes the lot worktrees a parallel wave left (``.ai/<slug>/lot-<n>/``) and the lot branches
already contained in the work branch, sets ``phase: done`` (with ``closed_at`` and the reason) in
``.ai/<slug>/state.json``, moves ``.ai/<slug>/`` to ``.ai/archive/<slug>/`` (suffixed with a
timestamp if that folder exists) and removes ``.ai/current``. A lot worktree with uncommitted changes
stops the close before anything changes: only the user discards work. A lot branch with commits the
work branch does not contain is kept and reported. The PreToolUse hook asks the user before an
agent runs it. Prints a JSON summary whose ``usage_table`` is the Markdown table of the tokens and
estimated credits of each agent (``usage_report.py``), to show the user; exit code 0 on success, 1
when there is nothing to close, a lot worktree holds uncommitted work or the files cannot be moved.

Usage: python close_workflow.py [--repo <path>] [--reason <text>]
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

sys.path.insert(0, str(Path(__file__).resolve().parent / "hooks"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import usage_report  # noqa: E402
import workflow_gate as wg  # noqa: E402

# Removing a worktree deletes its files (dependencies and build outputs included): longer than a hook's git call.
WORKTREE_TIMEOUT = 120.0


def remove_lot_worktrees(workflow: wg.Workflow) -> Dict[str, List[str]]:
    """Remove the lot worktrees of the workflow, then delete the lot branches the work branch contains.

    Returns ``blocked`` (nothing was removed: a lot worktree has uncommitted changes or is not a git
    worktree), or ``removed``, ``deleted_branches`` and ``kept_branches`` (commits not in the work branch).
    """
    root = workflow.root
    lots = workflow.lot_worktrees()
    blocked: List[str] = []
    for path in lots:
        name = path.relative_to(root).as_posix()
        top = wg.git(path, "rev-parse", "--show-toplevel")
        if top is None or not wg.same_path(top, path):
            blocked.append(f"{name} (not a git worktree)")
            continue
        status = wg.git(path, "status", "--porcelain", strip=False)
        if status is None or status.strip():
            blocked.append(f"{name} (uncommitted changes)")
    if blocked:
        return {"blocked": blocked}
    removed: List[str] = []
    for path in lots:
        name = path.relative_to(root).as_posix()
        if wg.git(root, "worktree", "remove", str(path), timeout=WORKTREE_TIMEOUT) is None:
            return {"blocked": [f"{name} (git worktree remove failed)"], "removed": removed}
        removed.append(name)
    wg.git(root, "worktree", "prune")
    deleted: List[str] = []
    kept: List[str] = []
    refs = wg.git(root, "for-each-ref", "--format=%(refname:short)", f"refs/heads/{workflow.branch}--lot-*")
    for branch in (refs or "").splitlines():
        contained = wg.git(root, "merge-base", "--is-ancestor", branch, workflow.branch) is not None
        if contained and wg.git(root, "branch", "-D", branch) is not None:
            deleted.append(branch)
        else:
            kept.append(branch)
    return {"removed": removed, "deleted_branches": deleted, "kept_branches": kept}


def close(repo: Path, reason: str) -> Dict[str, Any]:
    root = wg.find_workflow_root(repo)
    if root is None:
        return {"ok": False, "error": f"'{repo}' is not inside a git repository."}
    slug = wg.read_current_slug(root)
    if slug is None:
        return {"ok": False, "error": "no active workflow: .ai/current is missing or invalid."}
    workflow = wg.workflow_for(root, slug)
    previous = workflow.phase
    lots = remove_lot_worktrees(workflow)
    if lots.get("blocked"):
        return {
            "ok": False,
            "error": "lot worktrees cannot be removed: "
            + "; ".join(lots["blocked"])
            + ". Commit and integrate them (plan-execution skill), or discard them yourself "
            "(git worktree remove --force <path>; a folder that is not a worktree: delete it), then close again.",
            "slug": slug,
            "removed_lot_worktrees": lots.get("removed", []),
        }
    state = dict(workflow.state)
    state.update(phase="done", closed_at=wg.now_iso(), close_reason=reason, closed_from=previous)
    workflow.directory.mkdir(parents=True, exist_ok=True)
    (workflow.directory / "state.json").write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
    wg.log_event(workflow, "close", "close_workflow.py", "done", reason)
    for marker in workflow.markers():
        marker.unlink(missing_ok=True)
    archive = root / wg.WORKFLOW_DIR / wg.ARCHIVE_DIR
    destination = archive / slug
    if destination.exists():
        destination = archive / f"{slug}-{time.strftime('%Y%m%d%H%M%S')}"
    archive.mkdir(parents=True, exist_ok=True)
    try:
        shutil.move(str(workflow.directory), str(destination))
        (root / wg.WORKFLOW_DIR / "current").unlink(missing_ok=True)
    except OSError as exc:
        return {"ok": False, "error": f"cannot archive the workflow: {exc}", "slug": slug}
    try:
        usage_table = usage_report.report(destination)["markdown"]
    except Exception as exc:  # noqa: BLE001 - the cost table never prevents the close
        usage_table = f"(usage report unavailable: {exc!r})"
    return {
        "ok": True,
        "slug": slug,
        "closed_from": previous,
        "archived_to": destination.relative_to(root).as_posix(),
        "pull_request": state.get("pull_request"),
        "removed_lot_worktrees": lots.get("removed", []),
        "deleted_lot_branches": lots.get("deleted_branches", []),
        "kept_lot_branches": lots.get("kept_branches", []),
        "usage_table": usage_table,
    }


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Close and archive the active delivery workflow.")
    parser.add_argument("--repo", default=".", help="Path inside the git repository (default: current directory).")
    parser.add_argument("--reason", default="closed by the user", help="Why the workflow is closed.")
    args = parser.parse_args(argv)
    result = close(Path(args.repo), args.reason)
    wg.write_stdout(json.dumps(result, indent=2, ensure_ascii=False) + "\n")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
