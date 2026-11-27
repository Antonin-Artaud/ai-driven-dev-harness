#!/usr/bin/env python3
"""Close step of the ai-driven-dev-harness: archive the active workflow.

Sets ``phase: done`` (with ``closed_at`` and the reason) in ``.ai/<slug>/state.json``, moves
``.ai/<slug>/`` to ``.ai/archive/<slug>/`` (suffixed with a timestamp if that folder exists) and
removes ``.ai/current``. ``.ai/`` is found like the hooks find it: at the repository root, or in
the folder that holds the repositories of a multi-repository workspace. The PreToolUse hook asks
the user before an agent runs it. Prints a JSON summary whose ``usage_table`` is the Markdown
table of the tokens and estimated credits of each agent (``usage_report.py``), to show the user;
exit code 0 on success, 1 when there is nothing to close or the files cannot be moved.

Usage: python close_workflow.py [--repo <path>] [--reason <text>]
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
from pathlib import Path
from typing import Any, Dict, Optional, Sequence

sys.path.insert(0, str(Path(__file__).resolve().parent / "hooks"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import usage_report  # noqa: E402
import workflow_gate as wg  # noqa: E402


def close(repo: Path, reason: str) -> Dict[str, Any]:
    root = wg.find_workflow_root(repo)
    if root is None:
        return {
            "ok": False,
            "error": f"no {wg.WORKFLOW_DIR}/ folder found from '{repo}' (repository root, or the folder above it).",
        }
    slug = wg.read_current_slug(root)
    if slug is None:
        return {"ok": False, "error": "no active workflow: .ai/current is missing or invalid."}
    workflow = wg.workflow_for(root, slug)
    previous = workflow.phase
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
        "usage_table": usage_table,
    }


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Close and archive the active delivery workflow.")
    parser.add_argument(
        "--repo",
        default=".",
        help="Path inside the git repository or the multi-repository workspace (default: current directory).",
    )
    parser.add_argument("--reason", default="closed by the user", help="Why the workflow is closed.")
    args = parser.parse_args(argv)
    result = close(Path(args.repo), args.reason)
    wg.write_stdout(json.dumps(result, indent=2, ensure_ascii=False) + "\n")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
