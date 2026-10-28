"""Shared helpers for the ai-delivery-workflow hooks.

Standard library only, Python >= 3.9. The hooks accept both payload shapes:

* VS Code Local harness, and PascalCase event aliases in the Copilot runtime:
  ``tool_name``, ``tool_input`` and ``stop_hook_active``.
* GitHub Copilot runtime camelCase events: ``toolName`` and ``toolArgs``
  (an object or a JSON string).

Each hook writes exactly one JSON object to stdout. Decisions are written in both the
Local (``hookSpecificOutput``) and the Copilot (top-level) formats, so the same script
serves both harnesses.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

AI_MARKER = "\U0001F916"
WORKFLOW_DIR = ".ai"
INACTIVE_PHASES = frozenset({"done"})
STOP_GATED_PHASES = frozenset({"build", "feedback"})
PR_CREATION_PHASES = frozenset({"build"})
PR_DESCRIPTION_LIMIT = 4000
LOG_PREFIX = "[ai-delivery-workflow]"

_SLUG_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,99}$")
_SHA_RE = re.compile(r"^[0-9a-f]{7,64}$")
_FRONTMATTER_LINE_RE = re.compile(r"^([A-Za-z0-9_-]+)\s*:\s*(.*?)\s*$")


@dataclass
class HookInput:
    event: str
    tool_name: str
    tool_input: Dict[str, Any]
    cwd: str
    stop_hook_active: bool


@dataclass
class Workflow:
    root: Path
    slug: str
    directory: Path
    state: Dict[str, Any]
    review: Optional[Dict[str, str]]

    @property
    def phase(self) -> str:
        return str(self.state.get("phase") or "unknown").strip().lower()

    @property
    def base_branch(self) -> Optional[str]:
        value = self.state.get("base_branch")
        return value.strip() if isinstance(value, str) and value.strip() else None

    @property
    def review_path(self) -> str:
        return f"{WORKFLOW_DIR}/{self.slug}/review.md"


def read_input() -> HookInput:
    stream = getattr(sys.stdin, "buffer", None)
    raw = stream.read() if stream is not None else sys.stdin.read().encode("utf-8")
    text = raw.decode("utf-8", errors="replace").lstrip("\ufeff")
    try:
        payload = json.loads(text) if text.strip() else {}
    except ValueError:
        payload = {}
    return parse_input(payload if isinstance(payload, dict) else {})


def parse_input(payload: Dict[str, Any]) -> HookInput:
    tool_input = _first(payload, "tool_input", "toolArgs", "toolInput", "tool_args")
    if isinstance(tool_input, str):
        try:
            tool_input = json.loads(tool_input)
        except ValueError:
            tool_input = {}
    if not isinstance(tool_input, dict):
        tool_input = {}
    cwd = _first(payload, "cwd", "workingDirectory")
    return HookInput(
        event=str(_first(payload, "hook_event_name", "hookEventName") or ""),
        tool_name=str(_first(payload, "tool_name", "toolName") or ""),
        tool_input=tool_input,
        cwd=cwd if isinstance(cwd, str) and cwd else os.getcwd(),
        stop_hook_active=bool(_first(payload, "stop_hook_active", "stopHookActive")),
    )


def _first(payload: Dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if payload.get(key) is not None:
            return payload[key]
    return None


def git(cwd: Any, *args: str, strip: bool = True, timeout: float = 10.0) -> Optional[str]:
    env = dict(os.environ, GIT_OPTIONAL_LOCKS="0", GIT_TERMINAL_PROMPT="0")
    try:
        proc = subprocess.run(
            ["git", *args],
            cwd=str(cwd),
            env=env,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            timeout=timeout,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0:
        return None
    out = proc.stdout.decode("utf-8", errors="replace")
    return out.strip() if strip else out


def find_repo_root(cwd: Any) -> Optional[Path]:
    out = git(cwd, "rev-parse", "--show-toplevel")
    return Path(out) if out else None


def load_workflow(cwd: Any) -> Optional[Workflow]:
    """Return the active workflow of the repository containing ``cwd``, if any."""
    root = find_repo_root(cwd)
    if root is None:
        return None
    try:
        slug = read_text(root / WORKFLOW_DIR / "current").strip().lstrip("\ufeff")
    except OSError:
        return None
    if not _SLUG_RE.match(slug):
        return None
    directory = root / WORKFLOW_DIR / slug
    workflow = Workflow(
        root=root,
        slug=slug,
        directory=directory,
        state=_read_json(directory / "state.json"),
        review=read_frontmatter(directory / "review.md"),
    )
    if workflow.phase in INACTIVE_PHASES:
        return None
    return workflow


def read_text(path: Path) -> str:
    """Read a file written by any editor or shell: UTF-8 with or without BOM, UTF-16 with BOM, or ANSI."""
    data = path.read_bytes()
    if data.startswith((b"\xff\xfe", b"\xfe\xff")):
        return data.decode("utf-16", errors="replace")
    if data.startswith(b"\xef\xbb\xbf"):
        data = data[3:]
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return data.decode("cp1252", errors="replace")


def _read_json(path: Path) -> Dict[str, Any]:
    try:
        data = json.loads(read_text(path))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def read_frontmatter(path: Path) -> Optional[Dict[str, str]]:
    """Parse the flat ``key: value`` front matter of a Markdown file (None if the file is missing)."""
    try:
        text = read_text(path)
    except OSError:
        return None
    lines = text.splitlines()
    result: Dict[str, str] = {}
    if not lines or lines[0].strip() != "---":
        return result
    for line in lines[1:]:
        if line.strip() == "---":
            break
        match = _FRONTMATTER_LINE_RE.match(line)
        if not match:
            continue
        value = re.sub(r"\s+#.*$", "", match.group(2))
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
            value = value[1:-1]
        result[match.group(1).lower()] = value.strip()
    return result


def head_sha(root: Path) -> Optional[str]:
    return git(root, "rev-parse", "--verify", "--quiet", "HEAD")


def current_branch(root: Path) -> Optional[str]:
    return git(root, "symbolic-ref", "--quiet", "--short", "HEAD") or None


def remote_branch_sha(root: Path, branch: str, remote: str = "origin") -> Optional[str]:
    return git(root, "rev-parse", "--verify", "--quiet", f"refs/remotes/{remote}/{branch}")


def merge_base(root: Path, base_branch: str) -> Optional[str]:
    for ref in (f"origin/{base_branch}", base_branch):
        out = git(root, "merge-base", "HEAD", ref)
        if out:
            return out
    return None


def dirty_paths(root: Path) -> Optional[List[str]]:
    """Uncommitted paths outside ``.ai/`` (None when git status fails)."""
    out = git(root, "status", "--porcelain=v1", "--untracked-files=all", strip=False)
    if out is None:
        return None
    paths: List[str] = []
    for line in out.splitlines():
        if len(line) < 4:
            continue
        path = line[3:]
        if " -> " in path:
            path = path.split(" -> ", 1)[1]
        path = path.strip().strip('"')
        if path == WORKFLOW_DIR or path.startswith(WORKFLOW_DIR + "/"):
            continue
        paths.append(path)
    return paths


def review_gate(
    workflow: Workflow,
    head: Optional[str] = None,
    dirty: Optional[List[str]] = None,
) -> Optional[str]:
    """Return why HEAD is not covered by an approved review, or None when it is."""
    head = head or head_sha(workflow.root)
    if not head:
        return "cannot resolve HEAD."
    if dirty is None:
        dirty = dirty_paths(workflow.root)
        if dirty is None:
            return "cannot read the working tree status (git status failed)."
    if dirty:
        listed = ", ".join(dirty[:5]) + (" ..." if len(dirty) > 5 else "")
        return (
            f"uncommitted changes ({listed}). Commit the current lot first "
            "(plan-execution skill), then run the reviewer subagent."
        )
    review = workflow.review
    if review is None:
        return (
            f"{workflow.review_path} is missing for HEAD {head[:8]}. "
            "Run the reviewer subagent on <merge-base>..HEAD (code-review skill)."
        )
    reviewed = review.get("reviewed_sha", "").strip().lower()
    if not _SHA_RE.match(reviewed) or not head.lower().startswith(reviewed):
        return (
            f"{workflow.review_path} reviewed {reviewed[:8] or 'nothing'} but HEAD is {head[:8]}. "
            "Run the reviewer subagent on the new commits."
        )
    verdict = review.get("verdict", "").strip().upper()
    if verdict != "APPROVED":
        return (
            f"the review verdict for HEAD {head[:8]} is {verdict or 'missing'}. Fix the blocker and "
            "major findings with the implementer subagent and review again (at most 2 iterations), "
            'or set "phase": "escalated" in state.json and ask the user.'
        )
    return None


def emit(payload: Dict[str, Any]) -> None:
    sys.stdout.write(json.dumps(payload, ensure_ascii=True))
    sys.stdout.flush()


def pre_tool_use_result(decision: Optional[str], reason: str = "") -> Dict[str, Any]:
    if decision is None:
        return {}
    message = f"{LOG_PREFIX} {reason}".strip()
    return {
        "permissionDecision": decision,
        "permissionDecisionReason": message,
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": decision,
            "permissionDecisionReason": message,
        },
    }


def stop_result(reason: Optional[str]) -> Dict[str, Any]:
    if not reason:
        return {}
    message = f"{LOG_PREFIX} Review gate: {reason}"
    return {
        "decision": "block",
        "reason": message,
        "hookSpecificOutput": {"hookEventName": "Stop", "decision": "block", "reason": message},
    }
