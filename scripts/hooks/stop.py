#!/usr/bin/env python3
"""Stop hook of the ai-delivery-workflow plugin: the review gate.

In the ``build`` and ``feedback`` phases, the main agent cannot finish its turn while the work
branch has uncommitted changes, or commits that are not covered by an APPROVED ``review.md``.
The stop is allowed when a previous Stop hook already blocked (``stop_hook_active``), so the
agent can never loop forever. Prints one JSON object; ``{}`` lets the agent stop.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))

import workflow_gate as wg  # noqa: E402


def evaluate(hook: wg.HookInput) -> Optional[str]:
    if hook.stop_hook_active:
        return None
    workflow = wg.load_workflow(hook.cwd)
    if workflow is None or workflow.phase not in wg.STOP_GATED_PHASES:
        return None
    head = wg.head_sha(workflow.root)
    dirty = wg.dirty_paths(workflow.root)
    if not head or dirty is None:
        return None
    base_branch = workflow.base_branch
    if not dirty and base_branch and wg.merge_base(workflow.root, base_branch) == head:
        return None  # nothing implemented on the work branch yet
    return wg.review_gate(workflow, head=head, dirty=dirty)


def main() -> int:
    hook = wg.read_input()
    try:
        reason = evaluate(hook)
    except Exception:  # noqa: BLE001 - never trap the agent because of a hook bug
        reason = None
    wg.emit(wg.stop_result(reason))
    return 0


if __name__ == "__main__":
    sys.exit(main())
