#!/usr/bin/env python3
"""Deterministic part of the ai-delivery-workflow project onboarding.

* Detects the Azure DevOps organization, project and repository from the ``origin`` remote.
* Detects the base branch.
* Creates or merges ``.vscode/mcp.json`` with the ``ado-read`` and ``ado-write`` servers.
* Adds ``.ai/`` (and a newly created, untracked ``.vscode/mcp.json``) to ``.git/info/exclude``.
* With ``--docs``: creates the architecture map skeleton (``docs/architecture/`` by default) without
  overwriting existing files; the architecture-mapping skill fills it.

Prints a JSON summary on stdout and never prints credentials. Exit codes: 0 done, 1 error,
3 ``ado-read``/``ado-write`` definitions conflict (rerun with ``--force``). Files are written in
UTF-8 with LF line endings. Standard library only, Python >= 3.9.

The server URL and the ``X-MCP-*`` headers follow the documentation of the remote Azure DevOps MCP
server: https://learn.microsoft.com/en-us/azure/devops/mcp-server/remote-mcp-server (checked 2026-11-13).
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import date
from pathlib import Path, PurePosixPath
from typing import Any, Dict, List, Optional, Sequence, Tuple
from urllib.parse import unquote, urlsplit, urlunsplit

MCP_ENDPOINT = "https://mcp.dev.azure.com/{organization}"
EXIT_ERROR = 1
EXIT_CONFLICT = 3
READ_SERVER = "ado-read"
WRITE_SERVER = "ado-write"
READ_TOOLSETS = "repos,wit,wiki"
WRITE_TOOLS = "repo_pull_request_write, repo_pull_request_thread_write"
MCP_CONFIG = ".vscode/mcp.json"
WORKFLOW_EXCLUDE = ".ai/"
DOCS_DEFAULT = "docs/architecture"
DOCS_TEMPLATES = Path(__file__).resolve().parents[2] / "architecture-mapping" / "assets"
DECISIONS_README = (
    "# Architecture decisions\n\n"
    "One record per significant decision, numbered `0001`, `0002`..., written from the ADR template of the "
    "architecture-mapping skill.\n"
)

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


# Azure DevOps Server (on-premises): https://<server>[/tfs]/<collection>/<project>/_git/<repo>
_SERVER_PATTERN = re.compile(
    r"^(?:https?|ssh)://(?:[^@/]+@)?(?P<server>[^/:]+)(?::\d+)?/(?:tfs/)?(?P<collection>[^/]+)/(?P<project>[^/]+)/_git/"
    + _REPO,
    re.I,
)


def git(cwd: Any, *args: str) -> Optional[str]:
    try:
        proc = subprocess.run(["git", *args], cwd=str(cwd), stdin=subprocess.DEVNULL, capture_output=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0:
        return None
    return proc.stdout.decode("utf-8", errors="replace").strip()


def parse_ado_remote(url: str) -> Optional[Dict[str, str]]:
    """Return the organization, project and repository of an Azure Repos remote URL."""
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


def parse_ado_server_remote(url: str) -> Optional[Dict[str, str]]:
    """Return the server, collection, project and repository of an Azure DevOps Server remote URL."""
    url = url.strip()
    if parse_ado_remote(url):
        return None
    match = _SERVER_PATTERN.match(url)
    if not match or match.group("server").lower().endswith(("dev.azure.com", "visualstudio.com")):
        return None
    return {
        "server": match.group("server"),
        "collection": unquote(match.group("collection")),
        "project": unquote(match.group("project")),
        "repository": unquote(match.group("repo")),
    }


def redact_remote(url: str) -> str:
    """Drop user info (user names, PATs) from an HTTP(S) remote URL."""
    try:
        parts = urlsplit(url)
    except ValueError:
        return "<unparsable remote>"
    if parts.scheme in ("http", "https") and "@" in parts.netloc:
        return urlunsplit((parts.scheme, parts.netloc.rsplit("@", 1)[1], parts.path, parts.query, parts.fragment))
    return url


def detect_base_branch(root: Path, override: Optional[str]) -> Dict[str, str]:
    if override:
        return {"name": override, "source": "argument"}
    origin_head = git(root, "symbolic-ref", "--quiet", "--short", "refs/remotes/origin/HEAD")
    if origin_head and "/" in origin_head:
        return {"name": origin_head.split("/", 1)[1], "source": "origin/HEAD"}
    for prefix, label in (("refs/remotes/origin/", "origin/"), ("refs/heads/", "local ")):
        for candidate in ("main", "master", "develop"):
            if git(root, "rev-parse", "--verify", "--quiet", prefix + candidate):
                return {"name": candidate, "source": label + candidate}
    current = git(root, "symbolic-ref", "--quiet", "--short", "HEAD")
    return {"name": current or "main", "source": "current branch" if current else "default"}


def _scan(text: str, drop_comments: bool, drop_trailing_commas: bool) -> Tuple[str, bool]:
    out: List[str] = []
    in_string = False
    found_comment = False
    i, length = 0, len(text)
    while i < length:
        char = text[i]
        if in_string:
            out.append(char)
            if char == "\\" and i + 1 < length:
                out.append(text[i + 1])
                i += 2
                continue
            if char == '"':
                in_string = False
            i += 1
            continue
        if char == '"':
            in_string = True
        elif drop_comments and text.startswith("//", i):
            found_comment = True
            end = text.find("\n", i)
            i = length if end == -1 else end
            continue
        elif drop_comments and text.startswith("/*", i):
            found_comment = True
            end = text.find("*/", i + 2)
            i = length if end == -1 else end + 2
            continue
        elif drop_trailing_commas and char == ",":
            j = i + 1
            while j < length and text[j] in " \t\r\n":
                j += 1
            if j < length and text[j] in "}]":
                i += 1
                continue
        out.append(char)
        i += 1
    return "".join(out), found_comment


def strip_jsonc(text: str) -> Tuple[str, bool]:
    """Remove comments and trailing commas outside strings. Returns (json_text, had_comments)."""
    without_comments, had_comments = _scan(text, drop_comments=True, drop_trailing_commas=False)
    cleaned, _ = _scan(without_comments, drop_comments=False, drop_trailing_commas=True)
    return cleaned, had_comments


def desired_servers(organization: str) -> Dict[str, Dict[str, Any]]:
    url = MCP_ENDPOINT.format(organization=organization)
    return {
        READ_SERVER: {
            "type": "http",
            "url": url,
            "headers": {"X-MCP-Readonly": "true", "X-MCP-Toolsets": READ_TOOLSETS},
        },
        WRITE_SERVER: {"type": "http", "url": url, "headers": {"X-MCP-Tools": WRITE_TOOLS}},
    }


def write_lf(path: Path, content: str) -> None:
    """Write UTF-8 with LF line endings on every platform (Path.write_text uses the platform newline)."""
    path.write_bytes(content.replace("\r\n", "\n").encode("utf-8"))


def write_json(path: Path, data: Any) -> None:
    write_lf(path, json.dumps(data, indent=2, ensure_ascii=False) + "\n")


def merge_mcp_config(root: Path, organization: str, dry_run: bool, force: bool) -> Dict[str, Any]:
    path = root / MCP_CONFIG
    desired = desired_servers(organization)
    result: Dict[str, Any] = {"path": MCP_CONFIG, "servers": sorted(desired)}
    if not path.exists():
        result["action"] = "created"
        if not dry_run:
            path.parent.mkdir(parents=True, exist_ok=True)
            write_json(path, {"servers": desired, "inputs": []})
        return result

    def manual(reason: str, servers: Dict[str, Any]) -> Dict[str, Any]:
        result.update(action="manual", reason=reason, snippet={"servers": servers})
        return result

    try:
        cleaned, had_comments = strip_jsonc(path.read_text(encoding="utf-8-sig"))
        data = json.loads(cleaned) if cleaned.strip() else {}
    except (OSError, ValueError) as exc:
        return manual(f"cannot parse the existing file: {exc}", desired)
    if not isinstance(data, dict):
        return manual("the existing file is not a JSON object", desired)
    servers = data.get("servers", {})
    if not isinstance(servers, dict):
        return manual('"servers" is not an object', desired)

    added: List[str] = []
    replaced: List[str] = []
    conflicts: List[str] = []
    for name, definition in desired.items():
        current = servers.get(name)
        if current is None:
            added.append(name)
        elif current != definition:
            (replaced if force else conflicts).append(name)
    if conflicts:
        result["conflicts"] = conflicts
    changes = added + replaced
    if not changes:
        result["action"] = "conflict" if conflicts else "unchanged"
        if conflicts:
            result["reason"] = "existing definitions differ; rerun with --force to replace them"
        return result
    if had_comments:
        return manual(
            "the existing file contains comments; merge this snippet by hand to keep them",
            {name: desired[name] for name in changes},
        )
    data["servers"] = {**servers, **{name: desired[name] for name in changes}}
    result.update(action="merged", added=added, replaced=replaced)
    if not dry_run:
        write_json(path, data)
    return result


def ensure_excluded(root: Path, entries: Sequence[str], dry_run: bool) -> Dict[str, Any]:
    location = git(root, "rev-parse", "--git-path", "info/exclude")
    path = Path(location) if location else Path(".git/info/exclude")
    if not path.is_absolute():
        path = root / path
    try:
        existing = path.read_bytes().decode("utf-8", errors="replace").splitlines()
    except OSError:
        existing = []
    present = {line.strip().lstrip("/").rstrip("/") for line in existing}
    missing = [entry for entry in entries if entry.lstrip("/").rstrip("/") not in present]
    if missing and not dry_run:
        path.parent.mkdir(parents=True, exist_ok=True)
        content = "# ai-delivery-workflow\n" + "\n".join(missing) + "\n"
        try:
            original = path.read_bytes()
        except OSError:
            original = b""
        # Keep the existing lines byte for byte (another encoding stays untouched), then append.
        prefix = original if original.endswith(b"\n") or not original else original + b"\n"
        path.write_bytes(prefix + content.encode("utf-8"))
    try:
        shown = path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        shown = str(path)
    return {"path": shown, "added": missing}


def normalize_docs_path(value: str) -> Optional[str]:
    """Return the docs folder as a clean relative POSIX path, or None when it leaves the repository."""
    text = value.strip().replace("\\", "/")
    if not text or text.startswith("/") or re.match(r"^[A-Za-z]:", text):
        return None
    parts = [part for part in PurePosixPath(text).parts if part not in ("", ".")]
    if not parts or ".." in parts:
        return None
    return "/".join(parts)


def scaffold_docs(root: Path, relative: str, dry_run: bool) -> Dict[str, Any]:
    """Create the architecture map skeleton; existing files are never overwritten."""
    readme = (DOCS_TEMPLATES / "readme-template.md").read_text(encoding="utf-8")
    files = {
        "README.md": readme.replace("<YYYY-MM-DD>", date.today().isoformat()),
        "decisions/README.md": DECISIONS_README,
    }
    created: List[str] = []
    existing: List[str] = []
    for name, content in files.items():
        path = root / relative / name
        shown = f"{relative}/{name}"
        if path.exists():
            existing.append(shown)
            continue
        created.append(shown)
        if not dry_run:
            path.parent.mkdir(parents=True, exist_ok=True)
            write_lf(path, content)
    return {"path": relative, "action": "created" if created else "unchanged", "created": created, "existing": existing}


def print_json(data: Any) -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    sys.stdout.write(json.dumps(data, indent=2, ensure_ascii=False) + "\n")


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Onboard a repository to the ai-delivery-workflow.")
    parser.add_argument("--repo", default=".", help="Path inside the git repository (default: current directory).")
    parser.add_argument("--base-branch", help="Override the detected base branch.")
    parser.add_argument("--dry-run", action="store_true", help="Show what would change without writing anything.")
    parser.add_argument("--force", action="store_true", help="Replace conflicting ado-read/ado-write definitions.")
    parser.add_argument("--docs", action="store_true", help="Create the architecture map skeleton.")
    parser.add_argument(
        "--docs-path", help=f"Folder of the architecture map, relative to the repository (default: {DOCS_DEFAULT})."
    )
    args = parser.parse_args(argv)
    docs_path = None
    if args.docs or args.docs_path:
        docs_path = normalize_docs_path(args.docs_path or DOCS_DEFAULT)
        if docs_path is None:
            print_json(
                {"ok": False, "error": f"--docs-path '{args.docs_path}' must be a folder inside the repository."}
            )
            return EXIT_ERROR

    if not Path(args.repo).is_dir():
        print_json({"ok": False, "error": f"--repo '{args.repo}' does not exist or is not a folder."})
        return EXIT_ERROR
    root_text = git(Path(args.repo), "rev-parse", "--show-toplevel")
    if not root_text:
        print_json(
            {
                "ok": False,
                "error": f"'{args.repo}' is not inside a git repository. Initialize it and add the Azure Repos "
                "remote as 'origin' first.",
            }
        )
        return 1
    root = Path(root_text)
    summary: Dict[str, Any] = {"ok": True, "dry_run": args.dry_run, "repo_root": str(root), "warnings": []}

    remote = git(root, "remote", "get-url", "origin")
    summary["remote"] = redact_remote(remote) if remote else None
    ado = parse_ado_remote(remote) if remote else None
    summary["azure_devops"] = ado
    summary["base_branch"] = detect_base_branch(root, args.base_branch)

    exclude = [WORKFLOW_EXCLUDE]
    next_steps = []
    summary["azure_devops_server"] = None
    if ado:
        mcp = merge_mcp_config(root, ado["organization"], args.dry_run, args.force)
        mcp["tracked"] = git(root, "ls-files", "--error-unmatch", MCP_CONFIG) is not None
        if mcp["action"] == "created" and not mcp["tracked"]:
            exclude.append(MCP_CONFIG)
        summary["mcp_json"] = mcp
        next_steps.append(
            f"Start '{READ_SERVER}' and '{WRITE_SERVER}' from the MCP view (Microsoft Entra sign-in), "
            "then list the project's repositories with an ado-read tool."
        )
    else:
        summary["mcp_json"] = None
        server = parse_ado_server_remote(remote) if remote else None
        summary["azure_devops_server"] = server
        if server:
            summary["warnings"].append(
                f"origin is an Azure DevOps Server (on-premises) remote ({server['server']}, collection "
                f"'{server['collection']}'): the remote Azure DevOps MCP server is documented for Azure DevOps "
                "Services (https://mcp.dev.azure.com/<organization>), so no MCP configuration was generated. "
                "Work item intake and draft PR creation are manual; the hooks and the rest of the workflow still apply."
            )
    if not ado and not (remote and parse_ado_server_remote(remote)):
        summary["warnings"].append(
            "origin is not an Azure Repos remote: no MCP configuration was generated, so work item intake "
            "and draft PR creation are unavailable."
            if remote
            else "no 'origin' remote: add the Azure Repos remote, then rerun this script."
        )
    summary["git_exclude"] = ensure_excluded(root, exclude, args.dry_run)
    summary["architecture_docs"] = scaffold_docs(root, docs_path, args.dry_run) if docs_path else None
    if docs_path:
        next_steps.append(
            f"Map the application into {docs_path}/ with the architecture-mapping skill, then add "
            f"'Architecture docs: {docs_path}' to the project contract."
        )
    next_steps += [
        "Write or update the 'AI delivery workflow' section of AGENTS.md (project-onboarding skill).",
        "Enable chat.useHooks and trust this workspace so the workflow gates run.",
    ]
    summary["next_steps"] = next_steps
    conflicts = (summary.get("mcp_json") or {}).get("conflicts")
    if conflicts:
        summary["ok"] = False
        summary["error"] = (
            f"{', '.join(conflicts)} already defined differently in {MCP_CONFIG}: review them, then rerun with --force "
            "to replace them."
        )
        print_json(summary)
        return EXIT_CONFLICT
    print_json(summary)
    return 0


if __name__ == "__main__":
    sys.exit(main())
