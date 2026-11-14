"""File-write policy of the ai-driven-dev-harness hooks (ADR 0006).

Covers every file edit tool call while a workflow is active:

* ``state.json`` edits are simulated (full write, string replacement or patch) and the resulting
  state is validated: allowed phase transitions, gate preconditions, review iteration counter,
  ``done`` only through the close step.
* ``review.md`` is written by the reviewer subagent only, with the current iteration number.
* Hook-owned files (``.hooks.json``, ``log.jsonl``, subagent markers) are never written by agents.
* Role boundaries: the reviewer writes only ``review.md``; the implementer never writes under
  ``.ai/``; the main agent (challenger, architect, builder) is asked before writing outside ``.ai/``.
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

import workflow_gate as wg

Decision = Tuple[Optional[str], str]
NO_DECISION: Decision = (None, "")
_RANK = {None: 0, "allow": 1, "ask": 2, "deny": 3}

# Tools that change files (create_file, replace_string_in_file, apply_patch, edit, write ...).
FILE_WRITE_TOOL_RE = re.compile(r"create|edit|replace|insert|patch|write|delete|remove|rename|move", re.IGNORECASE)
MCP_TOOL_RE = re.compile(r"^mcp_|/")
PATH_KEYS = ("filePath", "file_path", "path", "filepath", "file", "target_file", "uri")
CONTENT_KEYS = ("content", "file_text", "fileText", "contents", "new_content")
OLD_KEYS = ("oldString", "old_string", "old_str", "oldText")
NEW_KEYS = ("newString", "new_string", "new_str", "newText")
# Windows file systems are case-insensitive: .AI\Slug\STATE.JSON is .ai/slug/state.json.
_AI_PATH_RE = re.compile(r"(?:^|/)\.ai/(.+)$", re.IGNORECASE)

# Allowed phase transitions through file edits. ``done`` is reached only through the close step.
TRANSITIONS: Dict[str, frozenset] = {
    "challenge": frozenset({"design", "escalated"}),
    "design": frozenset({"challenge", "build", "escalated"}),
    "build": frozenset({"pr-open", "escalated"}),
    "pr-open": frozenset({"triage", "escalated"}),
    "triage": frozenset({"feedback", "pr-open", "escalated"}),
    "feedback": frozenset({"pr-open", "escalated"}),
    "escalated": frozenset({"challenge", "design", "build", "pr-open", "triage", "feedback"}),
}
CYCLE_START = {("design", "build"), ("escalated", "build"), ("triage", "feedback"), ("escalated", "feedback")}
VALIDATIONS = {"brief_validated": "brief.md", "plan_validated": "plan.md"}
WRITE_ONCE = ("pull_request", "record_thread")


def deny(reason: str) -> Decision:
    return ("deny", reason)


def most_restrictive(first: Decision, second: Decision) -> Decision:
    return second if _RANK[second[0]] > _RANK[first[0]] else first


@dataclass
class PlannedWrite:
    """One file the tool call writes; ``apply`` turns the current text into the new one (None if unknown)."""

    path: str
    apply: Optional[Callable[[str], Optional[str]]] = None
    delete: bool = False


@dataclass
class Effects:
    """Hook-state updates to record once the call is allowed."""

    changes: List[Callable[[Dict[str, Any]], None]] = field(default_factory=list)

    def add(self, change: Callable[[Dict[str, Any]], None]) -> None:
        self.changes.append(change)


# --- planned writes ---------------------------------------------------------------------------


def _first_str(data: Dict[str, Any], keys: Tuple[str, ...]) -> Optional[str]:
    for key in keys:
        value = data.get(key)
        if isinstance(value, str):
            return value
    return None


def _lf(text: str) -> str:
    return text.replace("\r\n", "\n")


def _replacement(old: str, new: str, replace_all: bool = False) -> Callable[[str], Optional[str]]:
    def apply(text: str) -> Optional[str]:
        if old not in text:
            # Editors match across line endings: a file saved with CRLF (Windows) and an edit with LF.
            text, source, target = _lf(text), _lf(old), _lf(new)
            if source not in text:
                return None
            return text.replace(source, target) if replace_all else text.replace(source, target, 1)
        return text.replace(old, new) if replace_all else text.replace(old, new, 1)

    return apply


def _full(content: str) -> Callable[[str], Optional[str]]:
    return lambda _text: content


def _edit_of(data: Dict[str, Any]) -> Optional[PlannedWrite]:
    path = _first_str(data, PATH_KEYS)
    if path is None:
        return None
    content = _first_str(data, CONTENT_KEYS)
    if content is not None:
        return PlannedWrite(path, _full(content))
    old, new = _first_str(data, OLD_KEYS), _first_str(data, NEW_KEYS)
    if old is not None and new is not None:
        return PlannedWrite(path, _replacement(old, new, data.get("replace_all") is True))
    return PlannedWrite(path)


def _patch_writes(patch: str) -> List[PlannedWrite]:
    """Parse the ``*** Begin Patch`` format of apply_patch."""
    writes: List[PlannedWrite] = []
    blocks = re.split(r"^\*\*\* (Add|Update|Delete) File: (.+)$", patch, flags=re.MULTILINE)
    for index in range(1, len(blocks) - 2, 3):
        kind, path, body = blocks[index], blocks[index + 1].strip(), blocks[index + 2]
        body = re.split(r"^\*\*\* End Patch", body, flags=re.MULTILINE)[0]
        lines = body.splitlines()
        if kind == "Delete":
            writes.append(PlannedWrite(path, delete=True))
        elif kind == "Add":
            content = "\n".join(line[1:] for line in lines if line.startswith("+")) + "\n"
            writes.append(PlannedWrite(path, _full(content)))
        else:
            writes.append(PlannedWrite(path, _hunks(lines)))
    return writes


def _hunks(lines: List[str]) -> Callable[[str], Optional[str]]:
    hunks: List[Tuple[List[str], List[str]]] = []
    old: List[str] = []
    new: List[str] = []
    for line in lines:
        if line.startswith("@@") or line.startswith("*** Move to:"):
            if old or new:
                hunks.append((old, new))
            old, new = [], []
            continue
        tag, rest = (line[:1], line[1:]) if line else (" ", "")
        if tag in (" ", "-"):
            old.append(rest)
        if tag in (" ", "+"):
            new.append(rest)
    if old or new:
        hunks.append((old, new))

    def apply(text: str) -> Optional[str]:
        text = _lf(text)
        for before, after in hunks:
            source, target = "\n".join(before), "\n".join(after)
            if source not in text:
                return None
            text = text.replace(source, target, 1)
        return text

    return apply


def planned_writes(tool_input: Dict[str, Any]) -> List[PlannedWrite]:
    writes: List[PlannedWrite] = []
    edit = _edit_of(tool_input)
    if edit:
        writes.append(edit)
    for key in ("replacements", "edits", "files"):
        items = tool_input.get(key)
        if isinstance(items, list):
            for item in items:
                if isinstance(item, dict):
                    nested = _edit_of({**{k: tool_input[k] for k in PATH_KEYS if k in tool_input}, **item})
                    if nested:
                        writes.append(nested)
    for key in ("input", "patch"):
        value = tool_input.get(key)
        if isinstance(value, str) and "*** " in value:
            writes.extend(_patch_writes(value))
    return writes


def strings_in(value: Any) -> List[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [text for item in value.values() for text in strings_in(item)]
    if isinstance(value, list):
        return [text for item in value for text in strings_in(item)]
    return []


def ai_relative(path: str) -> Optional[str]:
    """``<slug>/state.json`` for any path inside a ``.ai/`` folder, else None."""
    match = _AI_PATH_RE.search(path.replace("\\", "/"))
    return match.group(1).strip("/").lower() if match else None


# --- identity ----------------------------------------------------------------------------------


def identity(hook: wg.HookInput, workflow: wg.Workflow) -> str:
    """A workflow subagent name (``reviewer``, ``implementer``, ``ui-ux-designer``, ``security-architect``,
    ``performance-architect``), ``subagent`` (unknown) or ``main``.

    The ``agent_type`` of the payload wins; otherwise a fresh SubagentStart marker of a writing
    subagent (the reviewer marker only lets review.md through, see ``evaluate_ai_write``).
    """
    named = hook.subagent
    if named:
        return named
    if hook.agent:
        return "subagent"
    running = workflow.running_subagent((*wg.CODING_AGENTS, *wg.SPECIALIST_FILES))
    if running:
        return running
    if hook.agent_id:
        return "subagent"
    return "main"


# --- state.json --------------------------------------------------------------------------------


def _user_spoke_after(hook_state: Dict[str, Any], moment: Any) -> bool:
    """True when a user prompt was recorded after ``moment`` (or when the host never reports prompts)."""
    spoke = hook_state.get("user_prompt_at")
    if not isinstance(spoke, (int, float)):
        return True  # UserPromptSubmit unsupported by the host: cannot be verified (security.md, Known gaps)
    if not isinstance(moment, (int, float)):
        return True
    return spoke > moment


def _validation_gate(
    workflow: wg.Workflow, new: Dict[str, Any], hook_state: Dict[str, Any], keys: Tuple[str, ...]
) -> Optional[str]:
    for key in keys:
        if not isinstance(new.get(key), dict):
            name = VALIDATIONS[key]
            return f"{name} is not validated: set {key} once the user has validated {name}."
        name = VALIDATIONS[key]
        if not (workflow.directory / name).is_file():
            return f"{key} is set but {wg.WORKFLOW_DIR}/{workflow.slug}/{name} does not exist."
        written = (hook_state.get("written_at") or {}).get(name)
        validated = (hook_state.get("validated_at") or {}).get(name)
        if isinstance(written, (int, float)) and isinstance(validated, (int, float)) and written > validated:
            return f"{name} changed after its validation: ask the user to validate it again, then update {key}."
    return None


def _record(section: str, name: str, moment: float) -> Callable[[Dict[str, Any]], None]:
    def change(data: Dict[str, Any]) -> None:
        data.setdefault(section, {})[name] = moment

    return change


def check_state_write(
    workflow: wg.Workflow,
    old: Optional[Dict[str, Any]],
    new_text: Optional[str],
    effects: Effects,
) -> Decision:
    if new_text is None:
        return deny(
            "state.json edits are checked by the hooks: write it with a full-file write or an exact string "
            "replacement (create_file, replace_string_in_file), not with this tool."
        )
    try:
        new = json.loads(new_text.lstrip("﻿"))
    except ValueError as exc:
        return deny(f"state.json must stay valid JSON ({exc}).")
    if not isinstance(new, dict):
        return deny("state.json must be a JSON object.")
    slug = workflow.slug
    if str(new.get("slug") or slug) != slug:
        return deny(f"state.json 'slug' must stay '{slug}'.")
    if new.get("branch") not in (None, workflow.branch):
        return deny(f"the work branch is always '{workflow.branch}'.")
    old_phase = str((old or {}).get("phase") or "").strip().lower() or None
    phase = str(new.get("phase") or "").strip().lower()
    if phase not in wg.PHASES:
        return deny(f"unknown phase '{phase}'. Phases: {', '.join(wg.PHASES)}.")
    if old is None:
        return NO_DECISION if phase == "challenge" else deny("a new workflow starts in the 'challenge' phase.")
    if phase == "done" and old_phase != "done":
        return deny(
            "only the close step sets 'done' (close_workflow.py, delivery-workflow skill): it archives the "
            "workflow once the user confirms."
        )
    hook_state = workflow.hook_state()
    for key in WRITE_ONCE:
        if old.get(key) not in (None, "") and new.get(key) != old.get(key):
            return deny(f"'{key}' is set once and never changed.")
    if (
        old.get("base_branch")
        and new.get("base_branch") != old.get("base_branch")
        and old_phase
        not in (
            "challenge",
            "design",
            "escalated",
        )
    ):
        return deny("base_branch only changes before the build starts.")

    # validations of brief.md and plan.md
    now = time.time()
    for key, name in VALIDATIONS.items():
        value = new.get(key)
        if value == old.get(key) or value in (None, False):
            continue
        if (
            not isinstance(value, dict)
            or not isinstance(value.get("at"), str)
            or not isinstance(value.get("head"), str)
        ):
            return deny(f'{key} must be {{"at": "<ISO date>", "head": "<HEAD sha>"}}.')
        if not (workflow.directory / name).is_file():
            return deny(f"cannot validate {name}: the file does not exist.")
        written = (hook_state.get("written_at") or {}).get(name)
        if not _user_spoke_after(hook_state, written):
            return deny(
                f"{name} was written after the user's last message: show it to the user and wait for their "
                f"validation before setting {key}."
            )
        effects.add(_record("validated_at", name, now))
        hook_state.setdefault("validated_at", {})[name] = now

    # review iteration counter
    old_iterations = old.get("review_iterations") or 0
    iterations = new.get("review_iterations", old_iterations) or 0
    if not isinstance(iterations, int) or not isinstance(old_iterations, int) or iterations < 0:
        return deny("review_iterations must be a non-negative integer.")
    cycle_start = (old_phase, phase) in CYCLE_START
    if cycle_start:
        if iterations != 0:
            return deny(f"entering '{phase}' starts a new review cycle: set review_iterations to 0.")
    else:
        if iterations < old_iterations:
            return deny("review_iterations never decreases within a cycle.")
        if iterations > old_iterations + 1:
            return deny("review_iterations increases by one per reviewer run.")
        if iterations > wg.MAX_REVIEW_ITERATIONS:
            return deny(
                f"the review limit ({wg.MAX_REVIEW_ITERATIONS} iterations) is reached: escalate to the user "
                '("phase": "escalated" with an "escalation" reason) instead of another review.'
            )

    # lots_done is append-only within a cycle
    lots = new.get("lots_done", [])
    old_lots = old.get("lots_done") or []
    if not isinstance(lots, list):
        return deny("lots_done must be a list.")
    if not cycle_start and isinstance(old_lots, list) and lots[: len(old_lots)] != old_lots:
        return deny("lots_done is append-only within a build cycle.")

    if phase == old_phase:
        return NO_DECISION
    if phase not in TRANSITIONS.get(old_phase or "", frozenset()):
        return deny(
            f"'{old_phase}' -> '{phase}' is not an allowed transition. From '{old_phase}': "
            f"{', '.join(sorted(TRANSITIONS.get(old_phase or '', frozenset()))) or 'none'} (delivery-workflow skill)."
        )
    if phase == "escalated":
        escalation = new.get("escalation")
        if (
            not isinstance(escalation, dict)
            or not str(escalation.get("reason") or "").strip()
            or str(escalation.get("from") or "").strip().lower() != old_phase
        ):
            return deny(
                f'escalating needs "escalation": {{"from": "{old_phase}", "reason": "<why the user must decide>"}}.'
            )
        effects.add(lambda data: data.__setitem__("escalated_at", now))
        return NO_DECISION
    if old_phase == "escalated" and not _user_spoke_after(hook_state, hook_state.get("escalated_at")):
        return deny("leaving 'escalated' needs the user's decision: ask the user and wait for their answer.")
    target = wg.Workflow(workflow.root, slug, workflow.directory, new, workflow.review)
    if phase == "design":
        blocked = _validation_gate(target, new, hook_state, ("brief_validated",))
        return deny(f"design gate: {blocked}") if blocked else NO_DECISION
    if phase == "build":
        blocked = _validation_gate(target, new, hook_state, ("brief_validated", "plan_validated"))
        if blocked:
            return deny(f"build gate: {blocked}")
        if old_phase == "design":
            baseline = wg.untracked_paths(workflow.root) or []
            effects.add(lambda data: data.__setitem__("untracked_baseline", baseline))
        return NO_DECISION
    if phase == "pr-open" and old_phase in ("build", "feedback", "escalated"):
        if not new.get("pull_request"):
            return deny("pr-open needs the draft PR id in 'pull_request'.")
        blocked = wg.review_gate(target)
        return deny(f"pr-open gate: {blocked}") if blocked else NO_DECISION
    if phase == "feedback" and old_phase == "triage":
        if not (workflow.directory / "feedback.md").is_file():
            return deny("write the triage in feedback.md first (pr-feedback skill).")
        written = (hook_state.get("written_at") or {}).get("feedback.md")
        if not _user_spoke_after(hook_state, written):
            return deny("the triage in feedback.md is not validated: show it to the user and wait for their answer.")
    return NO_DECISION


def check_review_write(workflow: wg.Workflow, new_text: Optional[str]) -> Decision:
    """The reviewer writes review.md with the iteration number the builder recorded."""
    if new_text is None:
        return NO_DECISION
    front = wg.parse_frontmatter_text(new_text)
    verdict = front.get("verdict", "").strip().upper()
    if verdict not in ("APPROVED", "CHANGES_REQUESTED"):
        return deny("review.md front matter needs verdict: APPROVED or CHANGES_REQUESTED (code-review skill).")
    iteration = wg.review_iteration(front)
    expected = workflow.state.get("review_iterations")
    if (
        iteration is None
        or not isinstance(expected, int)
        or iteration != expected
        or not (1 <= iteration <= wg.MAX_REVIEW_ITERATIONS)
    ):
        return deny(
            f"review.md iteration must be review_iterations from state.json ({expected}), between 1 and "
            f"{wg.MAX_REVIEW_ITERATIONS}. The builder increments review_iterations before each reviewer run, "
            "and escalates once the limit is reached."
        )
    return NO_DECISION


# --- entry point -------------------------------------------------------------------------------


def _current_text(path: Path) -> Optional[str]:
    try:
        return wg.read_text(path)
    except OSError:
        return None


def _new_text(write: PlannedWrite, path: Path) -> Optional[str]:
    if write.apply is None:
        return None
    current = _current_text(path)
    return write.apply(current if current is not None else "")


def evaluate_ai_write(
    hook: wg.HookInput, workflow: wg.Workflow, relative: str, write: PlannedWrite, who: str, effects: Effects
) -> Decision:
    parts = relative.split("/")
    name = parts[-1].lower()
    root = workflow.root
    if who in wg.CODING_AGENTS:
        return deny(f"the {who} never writes under .ai/ (plan-execution skill): report to the builder instead.")
    own_file = wg.SPECIALIST_FILES.get(who)
    if own_file and (len(parts) != 2 or parts[0] != workflow.slug or name != own_file):
        return deny(f"the {who} only writes .ai/{workflow.slug}/{own_file} (it does not write the plan or code).")
    if parts == ["current"]:
        if who == "reviewer":
            return deny("the reviewer only writes review.md.")
        if workflow.phase in ("build", "pr-open", "triage", "feedback"):
            return deny(
                f"workflow '{workflow.slug}' is in phase '{workflow.phase}': close it (close step) or escalate "
                "before switching .ai/current to another workflow."
            )
        text = _new_text(write, root / wg.WORKFLOW_DIR / "current")
        if text is not None and not wg.valid_slug(text.strip()):
            return deny("a slug is kebab-case, at most 40 characters (delivery-workflow skill).")
        return NO_DECISION
    if len(parts) != 2 or parts[0] == wg.ARCHIVE_DIR:
        return deny("the reviewer only writes review.md.") if who == "reviewer" else NO_DECISION
    slug = parts[0]
    target = workflow if slug == workflow.slug else wg.workflow_for(root, slug)
    if name in wg.HOOK_OWNED_FILES:
        return deny(f"{name} is written by the hooks only.")
    if name == "review.md":
        if who == "reviewer" or (who in ("main", "subagent") and not hook.agent and workflow.reviewer_running()):
            return (
                NO_DECISION if write.delete else check_review_write(target, _new_text(write, target.directory / name))
            )
        detail = f"; this call comes from '{hook.agent}'" if hook.agent else ""
        return deny(
            f"only the reviewer subagent writes review.md{detail}. Run the reviewer subagent on "
            "<merge-base>..HEAD instead of editing the review (code-review skill)."
        )
    if who == "reviewer":
        return deny("the reviewer only writes review.md (code-review skill).")
    owner = next((agent for agent, file in wg.SPECIALIST_FILES.items() if file == name), None)
    if owner and who not in (owner, "main"):
        return deny(f"{name} is written by the {owner} only.")
    if name == "state.json":
        if write.delete:
            return deny("state.json is never deleted: use the close step.")
        path = target.directory / name
        old = wg.read_json(path) if path.is_file() else None
        return check_state_write(target, old, _new_text(write, path), effects)
    if name in ("brief.md", "plan.md", "feedback.md"):
        moment = time.time()
        effects.add(_record("written_at", name, moment))
    return NO_DECISION


def evaluate_file_write(hook: wg.HookInput, workflow: Optional[wg.Workflow]) -> Tuple[Decision, Effects]:
    effects = Effects()
    if not FILE_WRITE_TOOL_RE.search(hook.tool_name) or workflow is None:
        return NO_DECISION, effects
    writes = planned_writes(hook.tool_input)
    who = identity(hook, workflow)
    decision = NO_DECISION
    seen_ai = False
    for write in writes:
        relative = ai_relative(write.path)
        if relative is None:
            if not MCP_TOOL_RE.search(hook.tool_name):  # MCP tools write remote resources, not local files
                decision = most_restrictive(decision, evaluate_outside_write(workflow, who, write.path))
            continue
        seen_ai = True
        decision = most_restrictive(decision, evaluate_ai_write(hook, workflow, relative, write, who, effects))
    if not seen_ai and any(wg.mentions_protected_path(text) for text in strings_in(hook.tool_input)):
        # A tool whose arguments we cannot map to files still mentions a protected workflow file.
        if not (
            wg.mentions_review_path(" ".join(strings_in(hook.tool_input)))
            and (who == "reviewer" or (not hook.agent and workflow.reviewer_running()))
        ):
            decision = most_restrictive(
                decision,
                deny(
                    "this call writes a workflow file the hooks protect (review.md, state.json, .ai/current or a "
                    "hook-owned file) with a tool the hooks cannot check. Use create_file or replace_string_in_file."
                ),
            )
    return decision, effects


def evaluate_outside_write(workflow: wg.Workflow, who: str, path: str) -> Decision:
    if who == "reviewer":
        return deny(f"the reviewer is read-only on the code: it only writes review.md (tried {path}).")
    if who in wg.SPECIALIST_FILES:
        return deny(f"the {who} does not write code: it only writes .ai/<slug>/{wg.SPECIALIST_FILES[who]}.")
    if who != "main" or workflow.phase == "escalated":
        return NO_DECISION
    if workflow.phase in ("challenge", "design"):
        return (
            "ask",
            f"Phase '{workflow.phase}': the challenger and the architect only write under .ai/. Allow writing {path}?",
        )
    return (
        "ask",
        f"Phase '{workflow.phase}': the builder delegates code changes to the implementer subagent. "
        f"Allow the main agent to write {path}?",
    )


def apply_effects(workflow: Optional[wg.Workflow], effects: Effects) -> None:
    if workflow is None or not effects.changes:
        return

    def change(data: Dict[str, Any]) -> None:
        for item in effects.changes:
            item(data)

    wg.update_hook_state(workflow.directory, change)
