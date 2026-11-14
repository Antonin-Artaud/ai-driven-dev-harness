#!/usr/bin/env python3
"""Cost of each agent of a delivery workflow: tokens and estimated GitHub AI credits.

Reads ``.ai/<slug>/usage.json`` (written by the hooks, see ``scripts/hooks/usage.py``) of the
active workflow, or of ``--slug`` (active or archived), and prints a Markdown table, one row per
agent, with the total. ``--json`` prints the same summary as JSON (for a dashboard). ``--probe``
prints the key structure of a transcript, never its values, to adapt the reader when a VS Code
release changes the transcript format.

Usage: python usage_report.py [--repo <path>] [--slug <slug>] [--lang fr|en] [--json]
       python usage_report.py --probe <transcript>
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, Optional, Sequence

sys.path.insert(0, str(Path(__file__).resolve().parent / "hooks"))

import usage  # noqa: E402
import workflow_gate as wg  # noqa: E402


def workflow_directory(repo: Path, slug: Optional[str]) -> Optional[Path]:
    root = wg.find_repo_root(repo)
    if root is None:
        return None
    base = root / wg.WORKFLOW_DIR
    slug = slug or wg.read_current_slug(root)
    if not slug or not wg.valid_slug(slug):
        return None
    for directory in (base / slug, base / wg.ARCHIVE_DIR / slug):
        if directory.is_dir():
            return directory
    return None


def report(directory: Path, language: Optional[str] = None) -> Dict[str, Any]:
    """Summary and Markdown table of the workflow in ``directory`` (active or archived)."""
    state = wg.read_json(directory / "state.json")
    language = language or ("fr" if str(state.get("language", "fr")).lower().startswith("fr") else "en")
    summary = usage.summarize(usage.read_usage(directory), usage.load_pricing())
    return {"slug": directory.name, "summary": summary, "markdown": usage.render_markdown(summary, language)}


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Token usage and estimated credits per agent of a delivery workflow.")
    parser.add_argument("--repo", default=".", help="Path inside the git repository (default: current directory).")
    parser.add_argument("--slug", help="Workflow slug, active or archived (default: the active workflow).")
    parser.add_argument("--lang", choices=("fr", "en"), help="Language of the table (default: state.json).")
    parser.add_argument("--json", action="store_true", help="Print the summary as JSON.")
    parser.add_argument("--probe", metavar="TRANSCRIPT", help="Print the key structure of a transcript and exit.")
    args = parser.parse_args(argv)
    if args.probe:
        wg.write_stdout("".join(line + "\n" for line in usage.transcript_shape(Path(args.probe))))
        return 0
    directory = workflow_directory(Path(args.repo), args.slug)
    if directory is None:
        sys.stderr.write("No workflow found: give --slug, or run it inside a repository with an active workflow.\n")
        return 1
    result = report(directory, args.lang)
    if args.json:
        wg.write_stdout(json.dumps({"slug": result["slug"], **result["summary"]}, indent=2, ensure_ascii=False) + "\n")
    else:
        wg.write_stdout(result["markdown"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
