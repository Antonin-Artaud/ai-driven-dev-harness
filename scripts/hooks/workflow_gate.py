"""Shared helpers for the ai-driven-dev-harness hooks.

Standard library only, Python >= 3.9. The hooks accept both payload shapes:

* VS Code Local harness, and PascalCase event aliases in the Copilot runtime:
  ``tool_name``, ``tool_input`` and ``stop_hook_active``.
* GitHub Copilot runtime camelCase events: ``toolName`` and ``toolArgs``
  (an object or a JSON string).

Each hook writes exactly one JSON object to stdout. Decisions are written in both the
Local (``hookSpecificOutput``) and the Copilot (top-level) formats, so the same script
serves both harnesses.

The hooks own four kinds of files under ``.ai/<slug>/`` that no agent may write: ``.hooks.json``
(heartbeat, time of the last user prompt, validation and escalation times), ``log.jsonl``
(append-only decision log), ``usage.json`` (token usage per agent, ``usage.py``) and the subagent
markers (``.reviewer-active``, ``.implementer-active``...).

``.ai/`` sits in the *workflow root*: the root of the git repository, or, in a multi-repository
workspace, the folder that holds the repositories (ADR 0011). A workflow changes the repositories
listed in ``state.json`` (``repositories``), or the workflow root itself when none is listed.
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
# state.json field listing the repositories of a multi-repository workflow (ADR 0011).
REPOSITORIES_FIELD = "repositories"
INACTIVE_PHASES = frozenset({"done"})
STOP_GATED_PHASES = frozenset({"build", "feedback"})
PR_CREATION_PHASES = frozenset({"build"})
PHASES = ("challenge", "design", "build", "pr-open", "triage", "feedback", "escalated", "done")
MAX_REVIEW_ITERATIONS = 2
MAX_STOP_BLOCKS = 3
PR_DESCRIPTION_LIMIT = 4000
LOG_PREFIX = "[ai-driven-dev-harness]"
REVIEWER_AGENT = "reviewer"
IMPLEMENTER_AGENT = "implementer"
UI_DESIGNER_AGENT = "ui-ux-designer"
SECURITY_AGENT = "security-architect"
PERFORMANCE_AGENT = "performance-architect"
# Subagents of the workflow; each has a marker ``.<name>-active`` while it runs.
SUBAGENTS = (REVIEWER_AGENT, IMPLEMENTER_AGENT, UI_DESIGNER_AGENT, SECURITY_AGENT, PERFORMANCE_AGENT)
# Subagents with the implementer's rights (code, never .ai/).
CODING_AGENTS = (IMPLEMENTER_AGENT, UI_DESIGNER_AGENT)
# Design specialists: each writes only its own file under .ai/<slug>/.
SPECIALIST_FILES = {SECURITY_AGENT: "security.md", PERFORMANCE_AGENT: "performance.md"}
# Written by the SubagentStart hook while a subagent runs, removed by SubagentStop and Stop.
REVIEWER_MARKER = ".reviewer-active"
IMPLEMENTER_MARKER = ".implementer-active"
MARKER_MAX_AGE = 3600.0
# File times can be slightly ahead of time.time() (coarse system clock on Windows, network drives).
CLOCK_SKEW = 5.0
REVIEWER_MARKER_MAX_AGE = MARKER_MAX_AGE
HOOK_STATE = ".hooks.json"
LOG_FILE = "log.jsonl"
USAGE_FILE = "usage.json"
HEARTBEAT_INTERVAL = 60.0
GIT_TIMEOUT = 4.0

# Slug rule (delivery-workflow skill): kebab-case, at most 40 characters.
SLUG_RE = re.compile(r"^(?=.{1,40}$)[a-z0-9]+(?:-[a-z0-9]+)*$")
_SLUG_RE = SLUG_RE
RESERVED_SLUGS = frozenset({ARCHIVE_DIR})
_NAME_RE = {name: re.compile(r"(?:^|[^a-z0-9])" + re.escape(name) + r"$") for name in SUBAGENTS}
# Files under .ai/<any>/ that only the hooks write.
HOOK_OWNED_FILES = frozenset({*(f".{name}-active" for name in SUBAGENTS), HOOK_STATE, LOG_FILE, USAGE_FILE})
# review.md, state.json and the hook-owned files of any slug: never written from the shell.
PROTECTED_PATH_RE = re.compile(
    r"(?:^|[^a-z0-9._-])\.ai/(?:current(?![a-z0-9._-])|[a-z0-9][a-z0-9._-]*/(?:review\.md|state\.json|security\.md|performance\.md|"
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
    transcript: str = ""

    @property
    def in_subagent(self) -> bool:
        return bool(self.agent or self.agent_id)

    @property
    def is_reviewer(self) -> bool:
        return is_reviewer_name(self.agent)

    @property
    def is_implementer(self) -> bool:
        return is_agent_name(self.agent, IMPLEMENTER_AGENT)

    @property
    def subagent(self) -> Optional[str]:
        """The workflow subagent named by the payload (``agent_type``), if any."""
        return subagent_name(self.agent)


def _identifier(value: Any) -> Optional[str]:
    """A PR or thread ID as text, or None when unset."""
    return str(value).strip() if value not in (None, "", False) else None


def _branch_name(value: Any) -> Optional[str]:
    return value.strip() if isinstance(value, str) and value.strip() else None


def normalize_repository_path(value: Any) -> Optional[str]:
    """A repository folder relative to the workflow root, as a POSIX path (``.`` for the root itself).

    None when the value is not a relative folder inside the workflow root (absolute, drive letter,
    ``..``, or the ``.ai`` folder).
    """
    if not isinstance(value, str):
        return None
    text = value.strip().replace("\\", "/")
    if not text or text.startswith("/") or re.match(r"^[A-Za-z]:", text):
        return None
    parts = [part for part in text.split("/") if part not in ("", ".")]
    if ".." in parts or (parts and parts[0].lower() == WORKFLOW_DIR):
        return None
    return "/".join(parts) or "."


def path_key(path: Path) -> str:
    """Comparable form of a folder path (resolved, case-folded where the file system ignores case)."""
    try:
        resolved = path.resolve()
    except (OSError, RuntimeError):
        resolved = path
    return os.path.normcase(str(resolved))


@dataclass(frozen=True)
class Repository:
    """A git repository the workflow changes: its folder, base branch, draft PR and record thread."""

    path: str
    root: Path
    base_branch: Optional[str]
    pull_request: Optional[str] = None
    record_thread: Optional[str] = None
    listed: bool = True

    @property
    def prefix(self) -> str:
        """Prefix of its paths relative to the workflow root (``api/``; empty for the root itself)."""
        return "" if self.path == "." else f"{self.path}/"


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
        return _branch_name(self.state.get("base_branch"))

    @property
    def branch(self) -> str:
        """The work branch is always ``ai/<slug>``, in every repository: state.json cannot redirect it."""
        return f"ai/{self.slug}"

    @property
    def pull_request(self) -> Optional[str]:
        return _identifier(self.state.get("pull_request"))

    @property
    def listed_repositories(self) -> List[Repository]:
        """The valid entries of ``state.repositories`` (strings or objects with a ``path``), in order."""
        entries = self.state.get(REPOSITORIES_FIELD)
        found: List[Repository] = []
        seen = set()
        for entry in entries if isinstance(entries, list) else []:
            data = entry if isinstance(entry, dict) else {"path": entry}
            path = normalize_repository_path(data.get("path"))
            if path is None or path.casefold() in seen:
                continue
            seen.add(path.casefold())
            found.append(
                Repository(
                    path=path,
                    root=self.root if path == "." else self.root / path,
                    base_branch=_branch_name(data.get("base_branch")) or self.base_branch,
                    pull_request=_identifier(data.get("pull_request")),
                    record_thread=_identifier(data.get("record_thread")),
                )
            )
        return found

    @property
    def multi_repo(self) -> bool:
        """True when ``state.repositories`` lists the repositories: PRs are then recorded per repository."""
        return bool(self.listed_repositories)

    @property
    def repositories(self) -> List[Repository]:
        """The repositories the workflow changes; the workflow root itself when none is listed."""
        listed = self.listed_repositories
        if listed:
            return listed
        return [
            Repository(
                ".", self.root, self.base_branch, self.pull_request, _identifier(self.state.get("record_thread"))
            )
        ]

    @property
    def default_repository(self) -> Optional[Repository]:
        """The repository of a git command whose folder is unknown: the only one, else None."""
        repositories = self.repositories
        return repositories[0] if len(repositories) == 1 else None

    def repository_for(self, repo_root: Path) -> Repository:
        """The workflow repository rooted at ``repo_root``, or an unlisted one (no PR, top-level base branch)."""
        key = path_key(repo_root)
        for repository in self.repositories:
            if path_key(repository.root) == key:
                return repository
        try:
            label = repo_root.resolve().relative_to(self.root.resolve()).as_posix()
        except (OSError, RuntimeError, ValueError):
            label = str(repo_root)
        return Repository(label, repo_root, self.base_branch, listed=False)

    def pull_requests(self) -> Dict[str, Repository]:
        """Draft PR ID -> repository, for every PR the workflow recorded."""
        return {repository.pull_request: repository for repository in self.repositories if repository.pull_request}

    def repository_label(self, repository: Repository) -> str:
        """`` in api`` for messages about one repository of a multi-repository workflow, else empty."""
        return f" in {repository.path}" if self.multi_repo else ""

    @property
    def review_path(self) -> str:
        return f"{WORKFLOW_DIR}/{self.slug}/review.md"

    @property
    def reviewer_marker(self) -> Path:
        return self.directory / REVIEWER_MARKER

    @property
    def implementer_marker(self) -> Path:
        return self.directory / IMPLEMENTER_MARKER

    def marker(self, agent: str) -> Path:
        return self.directory / f".{agent}-active"

    def markers(self) -> List[Path]:
        return [self.marker(agent) for agent in SUBAGENTS]

    def running_subagent(self, candidates: Any = None) -> Optional[str]:
        """The workflow subagent whose SubagentStart marker is fresh, among ``candidates``."""
        for agent in candidates or SUBAGENTS:
            if marker_active(self.marker(agent)):
                return agent
        return None

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
    return -CLOCK_SKEW <= age <= MARKER_MAX_AGE


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
    transcript = _first(payload, "transcript_path", "transcriptPath")
    return HookInput(
        event=str(_first(payload, "hook_event_name", "hookEventName") or ""),
        tool_name=str(_first(payload, "tool_name", "toolName") or ""),
        tool_input=tool_input,
        cwd=cwd if isinstance(cwd, str) and cwd else os.getcwd(),
        stop_hook_active=bool(_first(payload, "stop_hook_active", "stopHookActive")),
        agent=str(agent).strip() if agent is not None else "",
        agent_id=str(agent_id).strip() if agent_id is not None else "",
        transcript=transcript.strip() if isinstance(transcript, str) else "",
    )


def is_agent_name(name: str, agent: str) -> bool:
    """``agent``, possibly namespaced by the client (``ai-driven-dev-harness:reviewer``)."""
    return bool(_NAME_RE[agent].search(name.strip().lower()))


def subagent_name(name: str) -> Optional[str]:
    return next((agent for agent in SUBAGENTS if is_agent_name(name, agent)), None)


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


def _resolved(cwd: Any) -> Optional[Path]:
    try:
        return Path(str(cwd)).resolve()
    except (OSError, RuntimeError):
        return None


def find_repo_root(cwd: Any) -> Optional[Path]:
    """The closest folder holding ``.git`` (a folder, or a file for worktrees), without running git."""
    start = _resolved(cwd)
    if start is None:
        return None
    for folder in (start, *start.parents):
        if (folder / ".git").exists():
            return folder
    return None


def _workflow_root_candidates(start: Path, repo: Optional[Path]) -> List[Path]:
    """``start`` and its parents up to one level above its git repository (all of them outside a repository)."""
    if repo is None:
        return [start, *start.parents]
    candidates: List[Path] = []
    for folder in (start, *start.parents):
        candidates.append(folder)
        if folder == repo:
            break
    if repo.parent != repo:
        candidates.append(repo.parent)
    return candidates


def find_workflow_root(cwd: Any) -> Optional[Path]:
    """The folder holding the workflow's ``.ai/``, without running git (ADR 0011).

    The closest folder with ``.ai/current``, from ``cwd`` up to the folder that holds its git
    repository (every parent when ``cwd`` is outside a repository): the repository root of a
    single-repository project, or the folder above several repositories. Without any
    ``.ai/current``, the closest ``.ai/`` folder (archived workflows), else None.
    """
    start = _resolved(cwd)
    if start is None:
        return None
    fallback: Optional[Path] = None
    for folder in _workflow_root_candidates(start, find_repo_root(start)):
        workflow_dir = folder / WORKFLOW_DIR
        if (workflow_dir / "current").is_file():
            return folder
        if fallback is None and workflow_dir.is_dir():
            fallback = folder
    return fallback


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
    """Return the active workflow that governs ``cwd``, if any.

    When ``.ai/`` sits above the git repository holding ``cwd`` (multi-repository workspace), the
    workflow governs that repository only if ``state.json`` lists it: another repository of the
    same folder keeps working without the gates.
    """
    root = find_workflow_root(cwd)
    if root is None:
        return None
    slug = read_current_slug(root)
    if slug is None:
        return None
    workflow = workflow_for(root, slug)
    if workflow.phase in INACTIVE_PHASES and not include_inactive:
        return None
    repo = find_repo_root(cwd)
    if repo is not None and root in repo.parents and not workflow.repository_for(repo).listed:
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
        if isinstance(last, (int, float)) and -CLOCK_SKEW <= now - last < HEARTBEAT_INTERVAL:
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
        "head": head if head is not None else workflow_heads(workflow),
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


def baseline_of(hook_state: Dict[str, Any], repository: Repository) -> List[str]:
    """Untracked files of ``repository`` recorded when the build started (paths relative to it).

    ``untracked_baseline`` holds paths relative to the workflow root (``api/notes.txt``); for a
    single repository at the root, they are the repository paths themselves.
    """
    entries = hook_state.get("untracked_baseline")
    prefix = repository.prefix
    return [
        entry[len(prefix) :]
        for entry in (entries if isinstance(entries, list) else [])
        if isinstance(entry, str) and entry.startswith(prefix)
    ]


def repository_dirty_paths(workflow: Workflow, repository: Repository) -> Optional[List[str]]:
    """Uncommitted paths of one repository, relative to it, outside its build-start baseline."""
    return dirty_paths(repository.root, baseline_of(workflow.hook_state(), repository))


@dataclass
class RepoStatus:
    """HEAD, uncommitted paths (relative to the repository) and merge base of one workflow repository."""

    repository: Repository
    head: Optional[str]
    dirty: Optional[List[str]]
    merge_base: Optional[str] = None

    @property
    def changed(self) -> bool:
        """Something to review: uncommitted paths, commits on top of the merge base, or an unknown merge base."""
        return bool(self.dirty) or self.merge_base is None or self.head != self.merge_base


def workflow_status(workflow: Workflow, with_merge_base: bool = False) -> List[RepoStatus]:
    """The status of every repository of the workflow, in the order of ``state.repositories``."""
    hook_state = workflow.hook_state()
    statuses: List[RepoStatus] = []
    for repository in workflow.repositories:
        head = head_sha(repository.root)
        dirty = dirty_paths(repository.root, baseline_of(hook_state, repository))
        base = repository.base_branch
        found = merge_base(repository.root, base) if with_merge_base and head and base else None
        statuses.append(RepoStatus(repository, head, dirty, found))
    return statuses


def workflow_heads(workflow: Workflow) -> Any:
    """HEAD of the workflow's repository, or ``{path: HEAD}`` for a multi-repository workflow (decision log)."""
    if not workflow.multi_repo:
        return head_sha(workflow.root)
    return {repository.path: head_sha(repository.root) for repository in workflow.repositories}


def review_iteration(review: Optional[Dict[str, str]]) -> Optional[int]:
    if not review:
        return None
    try:
        return int(str(review.get("iteration", "")).strip())
    except ValueError:
        return None


def reviewed_shas(value: str) -> Dict[str, str]:
    """The ``reviewed_sha`` of review.md: ``<sha>``, or ``<path>=<sha>`` pairs in a multi-repository workflow.

    Pairs are separated by spaces, commas or semicolons. Keys are case-folded repository paths;
    a bare SHA is stored under ``""``.
    """
    found: Dict[str, str] = {}
    for token in re.split(r"[\s,;]+", value.strip()):
        if not token:
            continue
        path, separator, sha = token.rpartition("=")
        if separator:
            key = normalize_repository_path(path) or path
            found[key.casefold()] = sha.strip().lower()
        else:
            found[""] = token.lower()
    return found


def _reviewed_sha_of(reviewed: Dict[str, str], repository: Repository, single: bool) -> str:
    sha = reviewed.get(repository.path.casefold())
    if sha is None and single:
        sha = reviewed.get("")
    return sha or ""


def _short_heads(statuses: List[RepoStatus], multi: bool) -> str:
    if not multi:
        return (statuses[0].head or "")[:8]
    return ", ".join(f"{status.repository.path}@{(status.head or '')[:8]}" for status in statuses)


def review_gate(workflow: Workflow, statuses: Optional[List[RepoStatus]] = None) -> Optional[str]:
    """Return why the work is not covered by an approved review, or None when it is.

    Every repository must be clean; ``review.md`` must name the HEAD of each repository with
    changes (of every repository when none has changes) and approve it.
    """
    multi = workflow.multi_repo
    if statuses is None:
        statuses = workflow_status(workflow, with_merge_base=len(workflow.repositories) > 1)
    for status in statuses:
        of = f" of {status.repository.path}" if multi else ""
        if not status.head:
            return f"cannot resolve HEAD{of}."
        if status.dirty is None:
            return f"cannot read the working tree status{of} (git status failed)."
    dirty = [status.repository.prefix + path for status in statuses for path in status.dirty or []]
    if dirty:
        listed = ", ".join(dirty[:5]) + (" ..." if len(dirty) > 5 else "")
        return (
            f"uncommitted changes ({listed}). Commit the current lot first "
            "(plan-execution skill), then run the reviewer subagent."
        )
    scope = [status for status in statuses if status.changed] or statuses
    heads = _short_heads(scope, multi)
    review = workflow.review
    if review is None:
        return (
            f"{workflow.review_path} is missing for HEAD {heads}. "
            "Run the reviewer subagent on <merge-base>..HEAD (code-review skill)."
        )
    reviewed = reviewed_shas(review.get("reviewed_sha", ""))
    for status in scope:
        head = status.head or ""
        sha = _reviewed_sha_of(reviewed, status.repository, len(statuses) == 1)
        if not _SHA_RE.match(sha) or not head.lower().startswith(sha):
            if not multi:
                return (
                    f"{workflow.review_path} reviewed {sha[:8] or 'nothing'} but HEAD is {head[:8]}. "
                    "Run the reviewer subagent on the new commits."
                )
            path = status.repository.path
            return (
                f"{workflow.review_path} reviewed {sha[:8] or 'nothing'} for {path} but HEAD of {path} is "
                f"{head[:8]}. Run the reviewer subagent on the new commits; its reviewed_sha lists "
                "<path>=<HEAD sha> for every repository with changes (code-review skill)."
            )
    verdict = review.get("verdict", "").strip().upper()
    if verdict != "APPROVED":
        iterations = workflow.state.get("review_iterations")
        if isinstance(iterations, int) and iterations >= MAX_REVIEW_ITERATIONS:
            return (
                f"the review verdict for HEAD {heads} is {verdict or 'missing'} after {iterations} review "
                'iterations, the limit. Escalate: set "phase": "escalated" with "escalation": '
                '{"from": <phase>, "reason": ...} in state.json and ask the user.'
            )
        return (
            f"the review verdict for HEAD {heads} is {verdict or 'missing'}. Fix the blocker and "
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


def write_stdout(text: str) -> None:
    """Write ``text`` to stdout as UTF-8 whatever the console code page (cp1252 on Windows)."""
    stream = getattr(sys.stdout, "buffer", None)
    if stream is None:
        sys.stdout.write(text)
    else:
        sys.stdout.flush()
        stream.write(text.encode("utf-8"))
    sys.stdout.flush()


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
