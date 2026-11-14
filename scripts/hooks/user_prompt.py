#!/usr/bin/env python3
"""UserPromptSubmit hook of the ai-driven-dev-harness plugin.

Records the time of the user's last prompt in ``.ai/<slug>/.hooks.json`` (``user_prompt_at``) and
refreshes the heartbeat. The PreToolUse hook compares it with the time ``brief.md``, ``plan.md`` or
``feedback.md`` was last written, and with the escalation time: a validation, or a way out of
``escalated``, needs a user message after the artifact changed. A prompt also resets the Stop
hook's block count. Prints ``{}``: this hook never blocks.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path
from typing import Any, Dict

sys.path.insert(0, str(Path(__file__).resolve().parent))

import workflow_gate as wg  # noqa: E402


def evaluate(hook: wg.HookInput) -> None:
    workflow = wg.load_workflow(hook.cwd)
    if workflow is None:
        return
    now = time.time()

    def change(data: Dict[str, Any]) -> None:
        data["user_prompt_at"] = now
        data["stop_blocks"] = 0
        data["heartbeat"] = {
            "at": wg.now_iso(now),
            "epoch": now,
            "version": wg.plugin_version(),
            "hook": "UserPromptSubmit",
        }

    wg.update_hook_state(workflow.directory, change)


def main() -> int:
    hook = wg.read_input()
    try:
        evaluate(hook)
    except Exception as exc:  # noqa: BLE001 - never block the user's prompt
        sys.stderr.write(f"{wg.LOG_PREFIX} UserPromptSubmit hook error: {exc!r}\n")
    wg.emit({})
    return 0


if __name__ == "__main__":
    sys.exit(main())
