#!/usr/bin/env python3
"""SubagentStart / SubagentStop hooks of the ai-delivery-workflow plugin.

While a workflow subagent (reviewer, implementer, ui-ux-designer, security-architect,
performance-architect) runs, ``.ai/<slug>/.<name>-active`` exists. The PreToolUse hook uses these
markers when the harness does not send the agent type with each tool call: the reviewer marker
lets ``review.md`` through, the other markers identify who writes files. The event comes from the first
argument (``start`` or ``stop``) because the Copilot camelCase payloads do not name it.
Prints ``{}``: these hooks never block.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))

import workflow_gate as wg  # noqa: E402


def marker_for(workflow: wg.Workflow, agent: str) -> Optional[Path]:
    name = wg.subagent_name(agent)
    return workflow.marker(name) if name else None


def evaluate(event: str, hook: wg.HookInput) -> None:
    workflow = wg.load_workflow(hook.cwd)
    if workflow is None:
        return
    marker = marker_for(workflow, hook.agent)
    if marker is None:
        return
    if event == "start":
        marker.write_text(f"{time.time():.0f}\n", encoding="utf-8")
    elif event == "stop":
        marker.unlink(missing_ok=True)
    wg.log_event(workflow, f"Subagent{event.capitalize()}", hook.agent, "observed", "")


def main() -> int:
    event = sys.argv[1].strip().lower() if len(sys.argv) > 1 else ""
    hook = wg.read_input()
    try:
        evaluate(event, hook)
    except Exception as exc:  # noqa: BLE001 - a missing marker only makes the write gates stricter
        sys.stderr.write(f"{wg.LOG_PREFIX} subagent hook error: {exc!r}\n")
    wg.emit({})
    return 0


if __name__ == "__main__":
    sys.exit(main())
