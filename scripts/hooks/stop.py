#!/usr/bin/env python3
"""Stop hook of the ai-delivery-workflow plugin: the review gate and the record gate.

In the ``build`` and ``feedback`` phases, the main agent cannot finish its turn while the work
branch has uncommitted changes, or commits that are not covered by an APPROVED ``review.md``.
In the ``pr-open`` phase, it cannot finish before the brief and the plan are archived on the draft
PR (``record_thread`` in ``state.json``).

Consecutive blocks are counted in ``.ai/<slug>/.hooks.json`` (``stop_blocks``): the hook blocks at
most ``MAX_STOP_BLOCKS`` times in a row, then lets the stop through and logs it, so the agent can
never loop forever. A user prompt or an allowed stop resets the count. The hook also removes the
subagent markers, since no subagent runs once the main agent stops. Exceptions are logged to
``log.jsonl`` and let the stop through. Prints one JSON object; ``{}`` lets the agent stop.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))

import workflow_gate as wg  # noqa: E402

Blocked = Optional[Tuple[str, str]]


def gate(workflow: wg.Workflow) -> Blocked:
    if workflow.phase == "pr-open":
        reason = record_gate(workflow)
        return ("Record gate", reason) if reason else None
    if workflow.phase not in wg.STOP_GATED_PHASES:
        return None
    head = wg.head_sha(workflow.root)
    dirty = wg.workflow_dirty_paths(workflow)
    if not head or dirty is None:
        return None
    base_branch = workflow.base_branch
    if not dirty and base_branch and wg.merge_base(workflow.root, base_branch) == head:
        return None  # nothing implemented on the work branch yet
    reason = wg.review_gate(workflow, head=head, dirty=dirty)
    return ("Review gate", reason) if reason else None


def evaluate(hook: wg.HookInput) -> Blocked:
    workflow = wg.load_workflow(hook.cwd)
    if workflow is None:
        return None
    for marker in (workflow.reviewer_marker, workflow.implementer_marker):
        marker.unlink(missing_ok=True)
    wg.touch_heartbeat(workflow, "Stop")
    blocked = gate(workflow)
    count = workflow.hook_state().get("stop_blocks")
    count = count if isinstance(count, int) else 0
    if blocked and count >= wg.MAX_STOP_BLOCKS:
        wg.log_event(workflow, "Stop", "", "released", f"{blocked[0]} released after {count} blocks: {blocked[1]}")
        blocked = None
    new_count = count + 1 if blocked else 0

    def change(data: Dict[str, Any]) -> None:
        data["stop_blocks"] = new_count

    if new_count != count:
        wg.update_hook_state(workflow.directory, change)
    if blocked:
        wg.log_event(workflow, "Stop", "", "block", f"{blocked[0]}: {blocked[1]}")
    return blocked


def record_gate(workflow: wg.Workflow) -> Optional[str]:
    """Once the draft PR exists, the brief and the plan must be archived on it."""
    pull_request = workflow.state.get("pull_request")
    if not pull_request or workflow.state.get("record_thread"):
        return None
    return (
        f"draft PR {pull_request} has no workflow record yet. Post brief.md and plan.md as the "
        f'"{wg.AI_MARKER} Workflow record" thread (azure-devops skill), then set "record_thread" in state.json.'
    )


def main() -> int:
    hook = wg.read_input()
    try:
        blocked = evaluate(hook)
    except Exception as exc:  # noqa: BLE001 - never trap the agent because of a hook bug
        blocked = None
        try:
            wg.log_event(wg.load_workflow(hook.cwd), "Stop", "", "error", f"hook error: {exc!r}")
        except Exception:  # noqa: BLE001
            pass
        sys.stderr.write(f"{wg.LOG_PREFIX} Stop hook error: {exc!r}\n")
    wg.emit(wg.stop_result(*blocked) if blocked else {})
    return 0


if __name__ == "__main__":
    sys.exit(main())
