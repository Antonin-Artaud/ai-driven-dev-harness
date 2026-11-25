"""Test helpers: isolated git repositories, hook runners and a small front matter parser."""

from __future__ import annotations

import importlib.util
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
from pathlib import Path
from types import ModuleType
from typing import Any, Dict, List, Optional

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
HOOKS_DIR = PLUGIN_ROOT / "scripts" / "hooks"
PRE_TOOL_USE = HOOKS_DIR / "pre_tool_use.py"
STOP = HOOKS_DIR / "stop.py"
SUBAGENT = HOOKS_DIR / "subagent.py"
USER_PROMPT = HOOKS_DIR / "user_prompt.py"
CLOSE_WORKFLOW = PLUGIN_ROOT / "scripts" / "close_workflow.py"
ONBOARD = PLUGIN_ROOT / "skills" / "project-onboarding" / "scripts" / "onboard.py"
SLUG = "1234-demo"
BRANCH = f"ai/{SLUG}"


def lot_branch(lot: int) -> str:
    return f"{BRANCH}--lot-{lot}"


def load_module(name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _make_writable(func: Any, path: str, _exc: Any) -> None:
    os.chmod(path, stat.S_IWRITE)
    func(path)


def remove_tree(path: Path) -> None:
    if sys.version_info >= (3, 12):
        shutil.rmtree(path, onexc=_make_writable)
    else:
        shutil.rmtree(path, onerror=_make_writable)


def isolated_env(home: Path) -> Dict[str, str]:
    config = home / "gitconfig"
    config.write_text("", encoding="utf-8")
    env = dict(os.environ)
    env.update(
        {
            "GIT_CONFIG_GLOBAL": str(config),
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_AUTHOR_NAME": "Test",
            "GIT_AUTHOR_EMAIL": "test@example.com",
            "GIT_COMMITTER_NAME": "Test",
            "GIT_COMMITTER_EMAIL": "test@example.com",
            "GIT_TERMINAL_PROMPT": "0",
        }
    )
    return env


class TempGitRepo:
    """A work repository on ``main`` with one commit, pushed to a local bare ``origin``."""

    def __init__(self, with_origin: bool = True) -> None:
        self.base = Path(tempfile.mkdtemp(prefix="aidw-"))
        self.env = isolated_env(self.base)
        self.path = self.base / "work"
        self.path.mkdir()
        self.git("init", "-b", "main")
        self.commit_file("README.md", "# test\n", "chore: init")
        if with_origin:
            origin = self.base / "origin.git"
            self.run_git(self.base, "init", "--bare", "-b", "main", str(origin))
            self.git("remote", "add", "origin", str(origin))
            self.git("push", "-u", "origin", "main")

    def run_git(self, cwd: Path, *args: str) -> str:
        proc = subprocess.run(
            ["git", *args], cwd=str(cwd), env=self.env, capture_output=True, text=True, encoding="utf-8"
        )
        if proc.returncode != 0:
            raise RuntimeError(f"git {' '.join(args)} failed: {proc.stderr}")
        return proc.stdout.strip()

    def git(self, *args: str) -> str:
        return self.run_git(self.path, *args)

    def write(self, relative: str, content: str) -> Path:
        target = self.path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return target

    def commit_file(self, relative: str, content: str, message: str) -> str:
        self.write(relative, content)
        self.git("add", relative)
        self.git("commit", "-m", message)
        return self.head()

    def head(self) -> str:
        return self.git("rev-parse", "HEAD")

    def exclude(self, entry: str) -> None:
        exclude = self.path / ".git" / "info" / "exclude"
        exclude.parent.mkdir(parents=True, exist_ok=True)
        with exclude.open("a", encoding="utf-8") as handle:
            handle.write(f"\n{entry}\n")

    def write_workflow(
        self,
        phase: str = "build",
        review: Optional[Dict[str, str]] = None,
        base_branch: Optional[str] = "main",
        exclude: bool = True,
        **state_overrides: Any,
    ) -> Path:
        directory = self.path / ".ai" / SLUG
        directory.mkdir(parents=True, exist_ok=True)
        (self.path / ".ai" / "current").write_text(SLUG + "\n", encoding="utf-8")
        state: Dict[str, Any] = {
            "slug": SLUG,
            "phase": phase,
            "path": "standard",
            "branch": BRANCH,
            "work_item": 1234,
            "pull_request": None,
            "review_iterations": 0,
            "language": "fr",
        }
        if base_branch:
            state["base_branch"] = base_branch
        state.update(state_overrides)
        (directory / "state.json").write_text(json.dumps(state, indent=2), encoding="utf-8")
        review_file = directory / "review.md"
        if review is None:
            if review_file.exists():
                review_file.unlink()
        else:
            lines = ["---", *(f"{key}: {value}" for key, value in review.items()), "---", "# Review", ""]
            review_file.write_text("\n".join(lines), encoding="utf-8")
        exclude_file = self.path / ".git" / "info" / "exclude"
        if exclude and (not exclude_file.exists() or ".ai/" not in exclude_file.read_text(encoding="utf-8")):
            self.exclude(".ai/")
        return directory

    def add_lot(self, lot: int, start: str = BRANCH) -> Path:
        """A lot worktree as the builder creates it: .ai/<slug>/lot-<n> on branch ai/<slug>--lot-<n>."""
        path = self.path / ".ai" / SLUG / f"lot-{lot}"
        self.git("worktree", "add", "-q", "-b", lot_branch(lot), str(path), start)
        return path

    def hook_state(self) -> Dict[str, Any]:
        path = self.path / ".ai" / SLUG / ".hooks.json"
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}

    def set_hook_state(self, **values: Any) -> None:
        path = self.path / ".ai" / SLUG / ".hooks.json"
        data = self.hook_state()
        data.update(values)
        path.write_text(json.dumps(data), encoding="utf-8")

    def state(self) -> Dict[str, Any]:
        return json.loads((self.path / ".ai" / SLUG / "state.json").read_text(encoding="utf-8"))

    def log_entries(self) -> List[Dict[str, Any]]:
        path = self.path / ".ai" / SLUG / "log.jsonl"
        if not path.exists():
            return []
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]

    def cleanup(self) -> None:
        remove_tree(self.base)


def run_script(
    script: Path, payload: Any, env: Dict[str, str], cwd: Optional[Path] = None, args: Optional[List[str]] = None
) -> Dict[str, Any]:
    data = payload if isinstance(payload, (bytes, str)) else json.dumps(payload)
    proc = subprocess.run(
        [sys.executable, str(script), *(args or [])],
        input=data.encode("utf-8") if isinstance(data, str) else data,
        capture_output=True,
        env=env,
        cwd=str(cwd) if cwd else None,
        timeout=60,
    )
    if proc.returncode != 0:
        raise AssertionError(f"{script.name} exited {proc.returncode}: {proc.stderr.decode('utf-8', 'replace')}")
    out = proc.stdout.decode("utf-8").strip()
    return json.loads(out) if out else {}


# --- minimal YAML front matter parser (subset used by the plugin files) ----------------------


def _split_inline(inner: str) -> List[str]:
    parts, buffer, quote = [], [], None
    for char in inner:
        if quote:
            buffer.append(char)
            if char == quote:
                quote = None
        elif char in "'\"":
            quote = char
            buffer.append(char)
        elif char == ",":
            parts.append("".join(buffer))
            buffer = []
        else:
            buffer.append(char)
    if buffer:
        parts.append("".join(buffer))
    return [part.strip() for part in parts if part.strip()]


def scalar(value: str) -> Any:
    value = value.strip()
    if value.startswith("[") and value.endswith("]"):
        return [scalar(part) for part in _split_inline(value[1:-1])]
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
        inner = value[1:-1]
        return inner.replace("''", "'") if value[0] == "'" else inner.replace('\\"', '"')
    if value in ("true", "false"):
        return value == "true"
    return value


def _parse_block(block: List[str]) -> Any:
    items: List[Any] = []
    mapping: Dict[str, Any] = {}
    current: Optional[Dict[str, Any]] = None
    for raw in block:
        stripped = raw.strip()
        if not stripped:
            continue
        if stripped.startswith("- "):
            content = stripped[2:]
            if ":" in content and content[0] not in "'\"":
                key, _, value = content.partition(":")
                current = {key.strip(): scalar(value)}
                items.append(current)
            else:
                current = None
                items.append(scalar(content))
        else:
            key, _, value = stripped.partition(":")
            (current if current is not None else mapping)[key.strip()] = scalar(value)
    return items if items else mapping


def parse_frontmatter(text: str) -> Dict[str, Any]:
    lines = text.lstrip("\ufeff").splitlines()
    if not lines or lines[0].strip() != "---":
        raise ValueError("missing front matter")
    end = next(index for index in range(1, len(lines)) if lines[index].strip() == "---")
    block = lines[1:end]
    result: Dict[str, Any] = {}
    index = 0
    while index < len(block):
        line = block[index]
        if not line.strip() or line.lstrip().startswith("#"):
            index += 1
            continue
        if line[0] in " \t":
            raise ValueError(f"unexpected indentation: {line!r}")
        key, _, rest = line.partition(":")
        index += 1
        if rest.strip():
            result[key.strip()] = scalar(rest)
            continue
        nested = []
        while index < len(block) and (not block[index].strip() or block[index][0] in " \t"):
            nested.append(block[index])
            index += 1
        result[key.strip()] = _parse_block(nested)
    return result
