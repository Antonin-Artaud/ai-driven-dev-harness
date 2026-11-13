"""Shared helpers for the ai-delivery-workflow hooks.

Standard library only, Python >= 3.9. The hooks accept both payload shapes:

* VS Code Local harness, and PascalCase event aliases in the Copilot runtime:
  ``tool_name``, ``tool_input`` and ``stop_hook_active``.
* GitHub Copilot runtime camelCase events: ``toolName`` and ``toolArgs``
  (an object or a JSON string).

Each hook writes exactly one JSON object to stdout. Decisions are written in both the
Local (``hookSpecificOutput``) and the Copilot (top-level) formats, so the same script
serves both harnesses.

The hooks own three files under ``.ai/<slug>/`` that no agent may write: ``.hooks.json``
(heartbeat, time of the last user prompt, validation and escalation times), ``log.jsonl``
(append-only decision log) and the subagent markers (``.reviewer-active``, ``.implementer-active``).
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

PLUGIN_ROOT = Path(__file__).resolve().parents[2]
AI_MARKER = "\U0001f916"
WORKFLOW_DIR = ".ai"
ARCHIVE_DIR = "archive"
INACTIVE_PHASES = frozenset({"done"})
STOP_GATED_PHASES = frozenset({"build", "feedback"})
PR_CREATION_PHASES = frozenset({"build"})
PHASES = ("challenge", "design", "build", "pr-open", "triage", "feedback", "escalated", "done")
MAX_REVIEW_ITERATIONS = 2
MAX_STOP_BLOCKS = 3
PR_DESCRIPTION_LIMIT = 4000
LOG_PREFIX = "[ai-delivery-workflow]"
REVIEWER_AGENT = "reviewer"
IMPLEMENTER_AGENT = "implementer"
# Written by the SubagentStart hook while a subagent runs, removed by SubagentStop and Stop.
REVIEWER_MARKER = ".reviewer-active"
IMPLEMENTER_MARKER = ".implementer-active"
MARKER_MAX_AGE = 3600.0
REVIEWER_MARKER_MAX_AGE = MARKER_MAX_AGE
HOOK_STATE = ".hooks.json"
LOG_FILE = "log.jsonl"
HEARTBEAT_INTERVAL = 60.0
GIT_TIMEOUT = 4.0

# Slug rule (delivery-workflow skill): kebab-case, at most 40 characters.
SLUG_RE = re.compile(r"^(?=.{1,40}$)[a-z0-9]+(?:-[a-z0-9]+)*$")
_SLUG_RE = SLUG_RE
RESERVED_SLUGS = frozenset({ARCHIVE_DIR})
_NAME_RE = {name: re.compile(r"(?:^|[^a-z0-9])" + name + r"$") for name in (REVIEWER_AGENT, IMPLEMENTER_AGENT)}
# Files under .ai/<any>/ that only the hooks write.
HOOK_OWNED_FILES = frozenset({REVIEWER_MARKER, IMPLEMENTER_MARKER, HOOK_STATE, LOG_FILE})
# review.md, state.json and the hook-owned files of any slug: never written from the shell.
PROTECTED_PATH_RE = re.compile(
    r"(?:^|[^a-z0-9._-])\.ai/(?:current(?![a-z0-9._-])|[a-z0-9][a-z0-9._-]*/(?:review\.md|state\.json|"
    + "|".join(re.escape(name) for name in sorted(HOOK_OWNED_FILES))
    + r")(?![a-z0-9._-]))"
)
REVIEW_PATH_RE = re.compile(
    r"(?:^|[^a-z0-9._-])\.ai/[a-z0-9][a-z0-9._-]*/(?:review\.md|" + re.escape(REVIEWER_MARKER) + r")(?![a-z0-9._-])"
)
_SHA_RE = re.compile(r"^[0-9a-f]{7,64}$")
_FRONTMATTER_LINE_RE = re.compile(r"^([A-Za-z0-9_-]+)\s*:\s*(.*?)\s*$")


def plugin_version() -> str:
    try:
        return str(json.loads((PLUGIN_ROOT / "plugin.json").read_text(encoding="utf-8")).get("version") or "?")
    except (OSError, ValueError):
        return "?"


@dataclass
class HookInput:
    event: str
    tool_name: str
    tool_input: Dict[str, Any]
    cwd: str
    stop_hook_active: bool
    agent: str = ""
    agent_id: str = ""

    @property
    def in_subagent(self) -> bool:
        return bool(self.agent or self.agent_id)

    @property
    def is_reviewer(self) -> bool:
        return is_reviewer_name(self.agent)

    @property
    def is_implementer(self) -> bool:
        return is_agent_name(self.agent, IMPLEMENTER_AGENT)


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
    def branch(self) -> str:
        """The work branch is always ``ai/<slug>``: state.json cannot redirect it."""
        return f"ai/{self.slug}"

    @property
    def pull_request(self) -> Optional[str]:
        value = self.state.get("pull_request")
        return str(value).strip() if value not in (None, "", False) else None

    @property
    def review_path(self) -> str:
        return f"{WORKFLOW_DIR}/{self.slug}/review.md"

    @property
    def reviewer_marker(self) -> Path:
        return self.directory / REVIEWER_MARKER

    @property
    def implementer_marker(self) -> Path:
        return self.directory / IMPLEMENTER_MARKER

    def reviewer_running(self) -> bool:
        """True while the SubagentStart hook has recorded a running reviewer subagent."""
        return marker_active(self.reviewer_marker)

    def implementer_running(self) -> bool:
        return marker_active(self.implementer_marker)

    def hook_state(self) -> Dict[str, Any]:
        return read_hook_state(self.directory)


def marker_active(path: Path) -> bool:
    try:
        age = time.time() - path.stat().st_mtime
    except OSError:
        return False
    return 0 <= age <= MARKER_MAX_AGE


def read_input() -> HookInput:
    stream = getattr(sys.stdin, "buffer", None)
    raw = stream.read() if stream is not None else sys.stdin.read().encode("utf-8")
    text = raw.decode("utf-8", errors="replace").lstrip("﻿")
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
    # Hooks fired inside a subagent carry agent_id and, when known, agent_type; Subagent* events carry agentName.
    agent = _first(payload, "agent_type", "agentType", "agent_name", "agentName")
    agent_id = _first(payload, "agent_id", "agentId")
    return HookInput(
        event=str(_first(payload, "hook_event_name", "hookEventName") or ""),
        tool_name=str(_first(payload, "tool_name", "toolName") or ""),
        tool_input=tool_input,
        cwd=cwd if isinstance(cwd, str) and cwd else os.getcwd(),
        stop_hook_active=bool(_first(payload, "stop_hook_active", "stopHookActive")),
        agent=str(agent).strip() if agent is not None else "",
        agent_id=str(agent_id).strip() if agent_id is not None else "",
    )


def is_agent_name(name: str, agent: str) -> bool:
    """``agent``, possibly namespaced by the client (``ai-delivery-workflow:reviewer``)."""
    return bool(_NAME_RE[agent].search(name.strip().lower()))


def is_reviewer_name(name: str) -> bool:
    return is_agent_name(name, REVIEWER_AGENT)


def mentions_protected_path(text: str) -> bool:
    return bool(PROTECTED_PATH_RE.search(text.replace("\\", "/").lower()))


def mentions_review_path(text: str) -> bool:
    return bool(REVIEW_PATH_RE.search(text.replace("\\", "/").lower()))


def _first(payload: Dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if payload.get(key) is not None:
            return payload[key]
    return None


def git(cwd: Any, *args: str, strip: bool = True, timeout: float = GIT_TIMEOUT) -> Optional[str]:
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
    """The closest folder holding ``.git`` (a folder, or a file for worktrees), without running git."""
    try:
        start = Path(str(cwd)).resolve()
    except (OSError, RuntimeError):
        return None
    for folder in (start, *start.parents):
        if (folder / ".git").exists():
            return folder
    return None


def read_current_slug(root: Path) -> Optional[str]:
    try:
        slug = read_text(root / WORKFLOW_DIR / "current").strip().lstrip("﻿")
    except OSError:
        return None
    return slug if valid_slug(slug) else None


def valid_slug(slug: str) -> bool:
    return bool(SLUG_RE.match(slug)) and slug not in RESERVED_SLUGS


def workflow_for(root: Path, slug: str) -> Workflow:
    directory = root / WORKFLOW_DIR / slug
    return Workflow(
        root=root,
        slug=slug,
        directory=directory,
        state=read_json(directory / "state.json"),
        review=read_frontmatter(directory / "review.md"),
    )


def load_workflow(cwd: Any, include_inactive: bool = False) -> Optional[Workflow]:
    """Return the active workflow of the repository containing ``cwd``, if any."""
    root = find_repo_root(cwd)
    if root is None:
        return None
    slug = read_current_slug(root)
    if slug is None:
        return None
    workflow = workflow_for(root, slug)
    if workflow.phase in INACTIVE_PHASES and not include_inactive:
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


def read_json(path: Path) -> Dict[str, Any]:
    try:
        data = json.loads(read_text(path))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


_read_json = read_json


def parse_frontmatter_text(text: str) -> Dict[str, str]:
    lines = text.lstrip("﻿").splitlines()
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


def read_frontmatter(path: Path) -> Optional[Dict[str, str]]:
    """Parse the flat ``key: value`` front matter of a Markdown file (None if the file is missing)."""
    try:
        text = read_text(path)
    except OSError:
        return None
    return parse_frontmatter_text(text)


# --- hook-owned state, heartbeat and log -----------------------------------------------------


def read_hook_state(directory: Path) -> Dict[str, Any]:
    return read_json(directory / HOOK_STATE)


def update_hook_state(directory: Path, change: Callable[[Dict[str, Any]], None]) -> None:
    """Read-modify-write ``.hooks.json`` atomically (temporary file, then replace)."""
    if not directory.is_dir():
        return
    data = read_hook_state(directory)
    change(data)
    handle, temporary = tempfile.mkstemp(prefix=".hooks-", dir=str(directory))
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            json.dump(data, stream, indent=2, sort_keys=True)
        os.replace(temporary, directory / HOOK_STATE)
    except OSError:
        try:
            os.unlink(temporary)
        except OSError:
            pass


def now_iso(epoch: Optional[float] = None) -> str:
    moment = datetime.fromtimestamp(epoch if epoch is not None else time.time(), tz=timezone.utc)
    return moment.isoformat(timespec="seconds")


def touch_heartbeat(workflow: Workflow, hook_name: str, force: bool = False) -> None:
    """Record that the hooks run (builder precondition), at most once a minute."""
    now = time.time()
    previous = workflow.hook_state().get("heartbeat")
    if not force and isinstance(previous, dict):
        last = previous.get("epoch")
        if isinstance(last, (int, float)) and 0 <= now - last < HEARTBEAT_INTERVAL:
            return

    def change(data: Dict[str, Any]) -> None:
        data["heartbeat"] = {"at": now_iso(now), "epoch": now, "version": plugin_version(), "hook": hook_name}

    update_hook_state(workflow.directory, change)


_REDACTIONS = (
    (re.compile(r"(?i)\b([a-z][a-z0-9+.-]*://)[^/\s@]+@"), r"\1***@"),
    (re.compile(r"(?i)(authorization\s*[:=]\s*)(?:(?:basic|bearer)\s+)?\S+"), r"\1***"),
    (re.compile(r"(?i)\bbearer\s+\S+"), "Bearer ***"),
    (
        re.compile(r"(?i)(--?(?:token|password|passwd|pat|secret|api-key|apikey|client-secret|key)(?:\s+|=))(\S+)"),
        r"\1***",
    ),
    (re.compile(r"(?i)\b((?:[a-z_]*(?:token|password|secret|pat|key))=)\S+"), r"\1***"),
    (re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{20,}|[A-Za-z0-9]{52})\b"), "***"),
)


def redact(text: str) -> str:
    """Remove credentials from a text before it is logged."""
    for pattern, replacement in _REDACTIONS:
        text = pattern.sub(replacement, text)
    return text


def log_event(
    workflow: Optional[Workflow],
    hook_name: str,
    tool: str = "",
    decision: Optional[str] = None,
    reason: str = "",
    head: Optional[str] = None,
    **extra: Any,
) -> None:
    """Append one line to ``.ai/<slug>/log.jsonl``; never raises."""
    if workflow is None or not workflow.directory.is_dir():
        return
    entry: Dict[str, Any] = {
        "at": now_iso(),
        "hook": hook_name,
        "tool": tool,
        "decision": decision,
        "reason": redact(reason)[:500],
        "head": head if head is not None else head_sha(workflow.root),
        "phase": workflow.phase,
    }
    entry.update({key: redact(value) if isinstance(value, str) else value for key, value in extra.items()})
    try:
        with (workflow.directory / LOG_FILE).open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(entry, ensure_ascii=True) + "\n")
    except OSError:
        pass


# --- git state -----------------------------------------------------------------------------------


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


def status_entries(root: Path) -> Optional[List[str]]:
    """``git status --porcelain`` lines (None when git status fails)."""
    out = git(root, "status", "--porcelain=v1", "--untracked-files=all", strip=False)
    return None if out is None else [line for line in out.splitlines() if len(line) >= 4]


def _entry_path(line: str) -> str:
    path = line[3:]
    if " -> " in path:
        path = path.split(" -> ", 1)[1]
    return path.strip().strip('"')


def untracked_paths(root: Path) -> Optional[List[str]]:
    entries = status_entries(root)
    if entries is None:
        return None
    return [_entry_path(line) for line in entries if line.startswith("??") and not _in_workflow_dir(_entry_path(line))]


def _in_workflow_dir(path: str) -> bool:
    return path == WORKFLOW_DIR or path.startswith(WORKFLOW_DIR + "/")


def dirty_paths(root: Path, baseline: Optional[List[str]] = None) -> Optional[List[str]]:
    """Uncommitted paths outside ``.ai/`` (None when git status fails).

    Untracked files listed in ``baseline`` (recorded when the build started) are ignored: they
    belong to the user, not to the workflow.
    """
    entries = status_entries(root)
    if entries is None:
        return None
    ignored = set(baseline or [])
    paths: List[str] = []
    for line in entries:
        path = _entry_path(line)
        if _in_workflow_dir(path):
            continue
        if line.startswith("??") and path in ignored:
            continue
        paths.append(path)
    return paths


def workflow_dirty_paths(workflow: Workflow) -> Optional[List[str]]:
    baseline = workflow.hook_state().get("untracked_baseline")
    return dirty_paths(workflow.root, baseline if isinstance(baseline, list) else None)


def review_iteration(review: Optional[Dict[str, str]]) -> Optional[int]:
    if not review:
        return None
    try:
        return int(str(review.get("iteration", "")).strip())
    except ValueError:
        return None


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
        dirty = workflow_dirty_paths(workflow)
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
        iterations = workflow.state.get("review_iterations")
        if isinstance(iterations, int) and iterations >= MAX_REVIEW_ITERATIONS:
            return (
                f"the review verdict for HEAD {head[:8]} is {verdict or 'missing'} after {iterations} review "
                'iterations, the limit. Escalate: set "phase": "escalated" with "escalation": '
                '{"from": <phase>, "reason": ...} in state.json and ask the user.'
            )
        return (
            f"the review verdict for HEAD {head[:8]} is {verdict or 'missing'}. Fix the blocker and "
            f"major findings with the implementer subagent and review again (at most {MAX_REVIEW_ITERATIONS} "
            'iterations), or escalate ("phase": "escalated" with an "escalation" reason) and ask the user.'
        )
    return None


# --- Azure DevOps coordinates of the repository ----------------------------------------------------

_REPO = r"(?P<repo>[^/?#\s]+?)(?:\.git)?/?$"
_REMOTE_PATTERNS = (
    re.compile(r"^https?://(?:[^@/]+@)?dev\.azure\.com/(?P<org>[^/]+)/(?P<project>[^/]+)/_git/" + _REPO, re.I),
    re.compile(r"^https?://(?:[^@/]+@)?dev\.azure\.com/(?P<org>[^/]+)/_git/" + _REPO, re.I),
    re.compile(
        r"^(?:ssh://)?[^@/\s]+@ssh\.dev\.azure\.com(?::22)?[:/]v3/(?P<org>[^/]+)/(?P<project>[^/]+)/" + _REPO, re.I
    ),
    re.compile(
        r"^https?://(?:[^@/]+@)?(?P<org>[^./]+)\.visualstudio\.com/(?:DefaultCollection/)?(?P<project>[^/]+)/_git/"
        + _REPO,
        re.I,
    ),
    re.compile(r"^https?://(?:[^@/]+@)?(?P<org>[^./]+)\.visualstudio\.com/(?:DefaultCollection/)?_git/" + _REPO, re.I),
    re.compile(
        r"^(?:ssh://)?[^@/\s]+@vs-ssh\.visualstudio\.com(?::22)?[:/]v3/(?P<org>[^/]+)/(?P<project>[^/]+)/" + _REPO,
        re.I,
    ),
)


def parse_ado_remote(url: str) -> Optional[Dict[str, str]]:
    """Return the organization, project and repository of an Azure Repos remote URL."""
    from urllib.parse import unquote

    url = url.strip()
    for pattern in _REMOTE_PATTERNS:
        match = pattern.match(url)
        if match:
            groups = match.groupdict()
            repository = unquote(groups["repo"])
            return {
                "organization": unquote(groups["org"]),
                "project": unquote(groups.get("project") or repository),
                "repository": repository,
            }
    return None


def ado_coordinates(root: Path) -> Optional[Dict[str, str]]:
    url = git(root, "config", "--get", "remote.origin.url")
    return parse_ado_remote(url) if url else None


# --- outputs -------------------------------------------------------------------------------------


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


def stop_result(gate: str, reason: Optional[str]) -> Dict[str, Any]:
    if not reason:
        return {}
    message = f"{LOG_PREFIX} {gate}: {reason}"
    return {
        "decision": "block",
        "reason": message,
        "hookSpecificOutput": {"hookEventName": "Stop", "decision": "block", "reason": message},
    }
