#!/usr/bin/env python3
"""PreToolUse policy of the ai-driven-dev-harness plugin.

Acts only where a workflow is active (``.ai/current`` present and phase not ``done``), in its
git repository or, for a multi-repository workflow, in the folder above its repositories. The
rules are listed once, in skills/delivery-workflow/references/gates.md. In short:

* file edits: state.json transitions, review.md ownership and role boundaries (``state_policy``);
* shell commands: ``git push`` asks and only targets ``ai/<slug>``; force pushes, deletions, az
  writes and HTTP calls to Azure DevOps are denied; commands the hook cannot resolve ask; in the
  build and feedback phases, a commit that changes code without any test file asks the user
  (red-green-refactor skill). Each git command is checked in the repository it runs in, followed
  through ``cd``, ``pushd``, ``Set-Location`` and ``git -C``;
* Azure DevOps MCP tools: known read tools pass, PR and comment writes are checked and scoped to
  the workflow's PRs (one per repository in a multi-repository workflow), every other tool is denied.

Prints one JSON object; ``{}`` means no decision (the normal permission flow applies).
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Dict, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))

import state_policy as sp  # noqa: E402
import workflow_gate as wg  # noqa: E402

Decision = Tuple[Optional[str], str]
NO_DECISION: Decision = (None, "")
most_restrictive = sp.most_restrictive
deny = sp.deny

PR_WRITE_TOOL = "repo_pull_request_write"
PR_THREAD_WRITE_TOOL = "repo_pull_request_thread_write"

# Tool names of the Azure DevOps MCP servers, possibly prefixed by the client (mcp_ado-write_..., ado-write/...).
ADO_TOOL_RE = re.compile(
    r"(?:^|[^a-z0-9])((?:core|repo|wit|wiki|pipelines|testplan|work|advsec|enterprise_live_migration|search)"
    r"(?:_[a-z0-9_]+)?)$",
    re.IGNORECASE,
)
# Read tools of the remote server (learn.microsoft.com/azure/devops/mcp-server/remote-mcp-server) and of the
# local @azure-devops/mcp server (github.com/microsoft/azure-devops-mcp, docs/TOOLSET.md), checked 2026-11-13.
# Any other tool from an Azure DevOps server is treated as a write.
ADO_READ_TOOLS = frozenset(
    {
        "core_list_orgs",
        "core_list_projects",
        "core_list_project_teams",
        "core_list_group_members",
        "core_get_identity_ids",
        "work",
        "wit_work_item",
        "wit_query",
        "wit_query_by_wiql",
        "wit_backlog",
        "wit_work_item_attachment",
        "repo_repository",
        "repo_pull_request",
        "repo_pull_request_org",
        "repo_pull_request_thread",
        "repo_branch",
        "repo_file",
        "repo_search_commits",
        "pipelines_build",
        "pipelines_build_log",
        "pipelines_definition",
        "pipelines_run",
        "pipelines_artifact",
        "wiki",
        "testplan",
        "testplan_show_test_results_from_build_id",
        "testplan_test_run",
        "search_code",
        "search_wiki",
        "search_workitem",
        "advsec_alerts",
        "advsec_get_alerts",
        "advsec_get_alert_details",
        "enterprise_live_migration",
    }
)
# Read dispatchers that also carry a write action.
ADO_WRITE_ACTIONS_OF_READ_TOOLS = {"wit_backlog": frozenset({"reorder"})}
ADO_SERVER_HINT_RE = re.compile(r"ado|azure|devops|vsts", re.IGNORECASE)
PR_UPDATE_FIELDS = frozenset(
    {
        "action",
        "repositoryId",
        "repository",
        "project",
        "organization",
        "pullRequestId",
        "title",
        "description",
        "isDraft",
    }
)
WEB_TOOL_RE = re.compile(r"fetch|web|browse|http", re.IGNORECASE)
GUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.IGNORECASE)

SEPARATOR_CHARS = frozenset(";|&\n\r(){}`")
QUOTE_CHARS = "\"'"
MAX_NESTING = 2
# Wrappers that run the command that follows: their options taking a value, and their positional arguments.
WRAPPERS: Dict[str, Tuple[frozenset, int]] = {
    "sudo": (
        frozenset(
            {
                "-u",
                "-g",
                "-h",
                "-p",
                "-C",
                "-U",
                "-r",
                "-t",
                "-D",
                "-R",
                "-T",
                "--user",
                "--group",
                "--host",
                "--prompt",
                "--chdir",
                "--role",
                "--type",
                "--other-user",
                "--close-from",
            }
        ),
        0,
    ),
    "doas": (frozenset({"-u", "-C"}), 0),
    "env": (frozenset({"-u", "--unset", "-C", "--chdir"}), 0),
    "command": (frozenset(), 0),
    "exec": (frozenset({"-a"}), 0),
    "nohup": (frozenset(), 0),
    "time": (frozenset({"-f", "-o", "--format", "--output"}), 0),
    "timeout": (frozenset({"-s", "-k", "--signal", "--kill-after"}), 1),
    "nice": (frozenset({"-n", "--adjustment"}), 0),
    "ionice": (frozenset({"-c", "-n", "-p", "--class", "--classdata"}), 0),
    "stdbuf": (frozenset({"-i", "-o", "-e"}), 0),
    "xargs": (
        frozenset(
            {
                "-n",
                "-I",
                "-L",
                "-P",
                "-d",
                "-E",
                "-s",
                "-a",
                "--max-args",
                "--replace",
                "--max-lines",
                "--max-procs",
                "--delimiter",
                "--eof",
                "--max-chars",
                "--arg-file",
            }
        ),
        0,
    ),
    "watch": (frozenset({"-n", "--interval"}), 0),
    "call": (frozenset(), 0),
    "@": (frozenset(), 0),
    ".": (frozenset(), 0),
}
CURRENT_SHELL_LAUNCHERS = frozenset({"eval", "iex", "invoke-expression"})
SHELL_LAUNCHERS = frozenset(
    {
        "cmd",
        "bash",
        "sh",
        "zsh",
        "dash",
        "ksh",
        "fish",
        "pwsh",
        "powershell",
        "wsl",
        "start",
        "invoke-expression",
        "iex",
        "eval",
    }
)
INTERPRETER_CODE_FLAGS: Dict[str, frozenset] = {
    "python": frozenset({"-c"}),
    "py": frozenset({"-c"}),
    "node": frozenset({"-e", "-p", "--eval", "--print"}),
    "nodejs": frozenset({"-e", "-p", "--eval", "--print"}),
    "perl": frozenset({"-e", "-E"}),
    "ruby": frozenset({"-e"}),
    "php": frozenset({"-r"}),
    "deno": frozenset({"eval"}),
    "bun": frozenset({"-e", "--eval"}),
}
FIND_EXEC = frozenset({"-exec", "-execdir", "-ok", "-okdir"})
HTTP_CLIENTS = frozenset(
    {"curl", "wget", "invoke-restmethod", "invoke-webrequest", "irm", "iwr", "http", "https", "xh"}
)
ADO_HOST_RE = re.compile(r"dev\.azure\.com|\.visualstudio\.com", re.IGNORECASE)
EXECUTABLE_SUFFIXES = (".exe", ".cmd", ".bat", ".com")
ENV_ASSIGNMENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
PS_VARIABLE_RE = re.compile(r"^\$\{?([A-Za-z_][A-Za-z0-9_]*)\}?$")
GIT_OPTIONS_WITH_VALUE = frozenset(
    {"-c", "-C", "--git-dir", "--work-tree", "--namespace", "--config-env", "--super-prefix"}
)
PUSH_OPTIONS_WITH_VALUE = frozenset({"-o", "--push-option", "--repo", "--receive-pack", "--exec"})
FORBIDDEN_PUSH_OPTIONS = frozenset(
    {"--force", "--force-with-lease", "--force-if-includes", "--mirror", "--delete", "--prune", "--all", "--branches"}
)
FORCE_TEXT_RE = re.compile(
    r"--force|--mirror|--delete|--prune|(?<![\w-])-[a-z]*[fd][a-z]*(?![\w-])|(?<![\w-])\+[\w/]|['\"\s]:[\w/]"
)
AZ_GLOBAL_OPTIONS_WITH_VALUE = frozenset({"-o", "--output", "--query", "--subscription"})
AZ_DEVOPS_GROUPS = frozenset({"devops", "repos", "boards", "pipelines", "artifacts"})
AZ_READ_VERBS = frozenset({"list", "show", "query", "get", "checkout", "list-defaults", "show-defaults"})
AZ_WRITE_VERBS = frozenset(
    {
        "create",
        "update",
        "delete",
        "add",
        "remove",
        "run",
        "set",
        "set-vote",
        "import",
        "lock",
        "unlock",
        "queue",
        "cancel",
        "enable",
        "disable",
        "approve",
        "reject",
        "publish",
        "upload",
        "link",
        "unlink",
        "rename",
        "reactivate",
        "complete",
        "abandon",
        "invoke",
        "install",
        "uninstall",
    }
)
CLOSE_SCRIPT = "close_workflow.py"
# Commands that change the folder of the next commands of the same line (POSIX, cmd, PowerShell).
CHANGE_DIRECTORY = frozenset({"cd", "chdir", "pushd", "popd", "set-location", "sl", "push-location", "pop-location"})
CHANGE_DIRECTORY_OPTIONS = frozenset({"-path", "-literalpath", "/d", "-l", "-p"})
# Subshells, pipes, blocks and substitutions: a cd there may not apply to the commands after it.
SCOPED_CD_RE = re.compile(r"[(){}`]|(?<!\|)\|(?!\|)")
# git commit: test-first gate (red-green-refactor skill).
COMMIT_GATED_PHASES = wg.STOP_GATED_PHASES
COMMIT_OPTIONS_WITH_VALUE = frozenset(
    {
        "-m",
        "-F",
        "-c",
        "-C",
        "-t",
        "--message",
        "--file",
        "--reuse-message",
        "--reedit-message",
        "--template",
        "--author",
        "--date",
        "--cleanup",
        "--fixup",
        "--squash",
        "--trailer",
        "--pathspec-from-file",
    }
)
COMMIT_SHORT_FLAGS_WITH_VALUE = "mFcCt"
GIT_STAGE_RE = re.compile(r"\bgit\b.*?\b(?:add|rm|mv|stage)\b", re.IGNORECASE | re.DOTALL)
CODE_EXTENSIONS = frozenset(
    {
        ".py",
        ".js",
        ".jsx",
        ".mjs",
        ".cjs",
        ".ts",
        ".tsx",
        ".vue",
        ".svelte",
        ".java",
        ".kt",
        ".kts",
        ".scala",
        ".groovy",
        ".cs",
        ".fs",
        ".vb",
        ".go",
        ".rs",
        ".rb",
        ".php",
        ".swift",
        ".m",
        ".mm",
        ".c",
        ".cc",
        ".cpp",
        ".cxx",
        ".h",
        ".hpp",
        ".dart",
        ".ex",
        ".exs",
        ".erl",
        ".clj",
        ".lua",
        ".r",
        ".sql",
        ".sh",
        ".ps1",
        ".psm1",
    }
)
TEST_DIRECTORIES = frozenset({"test", "tests", "__tests__", "spec", "specs", "e2e", "testing", "cypress", "playwright"})
TEST_FILE_RE = re.compile(
    r"(?:^test_|^conftest\.py$|_test\.[^.]+$|_spec\.[^.]+$|\.(?:test|spec|cy|e2e)\.[^.]+$|(?:Tests?|Spec|IT)\.[^.]+$)"
)

# Git ignores aliases that shadow built-in commands: only other names are looked up in the git config.
GIT_BUILTINS = frozenset(
    {
        "add",
        "am",
        "apply",
        "bisect",
        "blame",
        "branch",
        "bundle",
        "cat-file",
        "checkout",
        "cherry-pick",
        "clean",
        "clone",
        "commit",
        "config",
        "describe",
        "diff",
        "fetch",
        "for-each-ref",
        "format-patch",
        "gc",
        "grep",
        "help",
        "init",
        "log",
        "ls-files",
        "ls-remote",
        "ls-tree",
        "merge",
        "merge-base",
        "mv",
        "notes",
        "pull",
        "push",
        "range-diff",
        "rebase",
        "reflog",
        "remote",
        "reset",
        "restore",
        "rev-list",
        "rev-parse",
        "revert",
        "rm",
        "shortlog",
        "show",
        "show-ref",
        "stash",
        "status",
        "submodule",
        "switch",
        "symbolic-ref",
        "tag",
        "worktree",
        "version",
        "var",
        "cherry",
        "fsck",
        "whatchanged",
    }
)
MAX_ALIAS_DEPTH = 3

# Shell forms that write a file named on the command line.
SHELL_WRITE_RE = re.compile(
    r">|\b(?:set-content|add-content|out-file|new-item|copy-item|move-item|remove-item|rename-item|sc|ac|"
    r"tee|cp|mv|rm|del|erase|copy|move|ren|rename|touch|truncate|dd|install|ln|sed|perl|awk|python3?|py|"
    r"node|ruby|pwsh|powershell|bash|sh)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class Token:
    text: str
    quoted: bool


def is_true(value: Any) -> bool:
    return value is True or (isinstance(value, str) and value.strip().lower() in {"true", "1", "yes"})


def is_false(value: Any) -> bool:
    return value is False or (isinstance(value, str) and value.strip().lower() in {"false", "0", "no"})


def normalize_ref(ref: str) -> str:
    ref = ref.strip()
    return ref[len("refs/heads/") :] if ref.startswith("refs/heads/") else ref


def utf16_length(text: str) -> int:
    """Length in UTF-16 code units, as counted by Azure DevOps (a non-BMP emoji counts 2)."""
    return len(text.encode("utf-16-le")) // 2


# --- shell commands -------------------------------------------------------------------------


def lex(command: str) -> List[List[Token]]:
    """Split a command line into segments of tokens.

    Quotes group words (and are removed); separators outside quotes (``; | & ( ) { }``, backtick,
    newline) end a segment. Backslashes are kept verbatim so Windows paths survive, except ``\\"``
    inside double quotes, which is an escaped quote.
    """
    segments: List[List[Token]] = []
    tokens: List[Token] = []
    chars: List[str] = []
    quote: Optional[str] = None
    quoted = False
    started = False

    def end_token() -> None:
        nonlocal chars, quoted, started
        if started:
            tokens.append(Token("".join(chars), quoted))
        chars, quoted, started = [], False, False

    def end_segment() -> None:
        nonlocal tokens
        end_token()
        if tokens:
            segments.append(tokens)
        tokens = []

    escaped = False
    for char in command:
        if quote:
            if escaped:
                chars.append(char if char == '"' else "\\" + char)
                escaped = False
            elif quote == '"' and char == "\\":
                escaped = True
            elif char == quote:
                quote = None
            else:
                chars.append(char)
        elif char in QUOTE_CHARS:
            quote, quoted, started = char, True, True
        elif char in SEPARATOR_CHARS:
            end_segment()
        elif char.isspace():
            end_token()
        else:
            chars.append(char)
            started = True
    end_segment()
    return segments


def command_name(token: str) -> str:
    name = re.split(r"[\\/]", token)[-1].lower()
    for suffix in EXECUTABLE_SUFFIXES:
        if name.endswith(suffix):
            name = name[: -len(suffix)]
            break
    if re.fullmatch(r"python[0-9.]*w?", name):
        return "python"
    return name


def is_unresolved(text: str) -> bool:
    """A word whose value is only known at run time (variable, substitution, ANSI-C quoting)."""
    return "$" in text or "`" in text


class ShellContext:
    """State shared by the segments of one command line: variables assigned before use, current folder."""

    def __init__(self, workflow: wg.Workflow, stages: bool = False, cwd: Optional[Path] = None) -> None:
        self.workflow = workflow
        self.variables: Dict[str, str] = {}
        self.git_aliases: Dict[str, str] = {}
        # The command line also stages files, so a commit is checked against the working tree.
        self.stages = stages
        # Folder the next command runs in: the hook's cwd, followed through cd; None once unknown.
        self.cwd = cwd
        # Subshells, pipes and blocks: the hook cannot tell which commands a cd applies to.
        self.scoped_cd = False

    def repository(self, directories: Optional[List[str]] = None) -> Optional[wg.Repository]:
        """The repository a git command runs in (``git -C <dir>`` relative to the current folder).

        When the folder is unknown or holds no repository, the workflow's only repository (a
        single-repository workflow behaves as before), else None.
        """
        folder = self.cwd
        for directory in directories or []:
            if folder is None or is_unresolved(directory):
                folder = None
                break
            path = Path(directory)
            folder = path if path.is_absolute() else folder / path
        root = wg.find_repo_root(folder) if folder is not None else None
        if root is not None:
            return self.workflow.repository_for(root)
        return self.workflow.default_repository

    def change_directory(self, name: str, args: List[str]) -> None:
        """Follow ``cd <dir>``; a folder the hook cannot know (variable, ``-``, ``~``, ``popd``) makes it unknown."""
        targets = [arg for arg in args if arg.lower() not in CHANGE_DIRECTORY_OPTIONS]
        target = targets[0] if targets else None
        if name in ("popd", "pop-location") or target is None or target == "-" or target.startswith("~"):
            self.cwd = None
            return
        path = Path(target)
        if self.scoped_cd or is_unresolved(target):
            self.cwd = None
        elif path.is_absolute():
            self.cwd = path
        elif self.cwd is not None:
            self.cwd = self.cwd / path


def evaluate_opaque(text: str, what: str) -> Decision:
    """Code the hook cannot parse (eval, interpreter one-liner, deep nesting): judge it by what it mentions."""
    lowered = text.lower()
    mentions_git = re.search(r"(?<![\w-])git(?![\w-])", lowered) is not None
    if mentions_git and re.search(r"(?<![\w-])push(?![\w-])", lowered) and FORCE_TEXT_RE.search(lowered):
        return deny(f"{what} runs a git push with a force, delete or mirror option: not allowed.")
    if ADO_HOST_RE.search(lowered):
        return ("ask", f"{what} calls Azure DevOps directly; the workflow only writes through the MCP gates. Allow it?")
    if mentions_git or re.search(r"(?<![\w-])az(?![\w-])", lowered):
        return ("ask", f"{what} runs git or az commands the hooks cannot check. Allow it?")
    return NO_DECISION


def skip_wrappers(tokens: List[Token], context: ShellContext, depth: int) -> Tuple[int, Decision]:
    """Index of the real command after env assignments and wrappers (sudo -u x, timeout 5, nice -n 5 ...)."""
    texts = [token.text for token in tokens]
    index = 0
    extra = NO_DECISION
    while index < len(texts):
        word = texts[index]
        if ENV_ASSIGNMENT_RE.match(word):
            index += 1
            continue
        name = command_name(word)
        if name not in WRAPPERS:
            break
        value_options, positionals = WRAPPERS[name]
        index += 1
        while index < len(texts) and texts[index].startswith("-") and len(texts[index]) > 1:
            option = texts[index]
            if option == "--":
                index += 1
                break
            if name == "env" and (option in ("-S", "--split-string") or option.startswith("--split-string=")):
                value = (
                    option.split("=", 1)[1] if "=" in option else (texts[index + 1] if index + 1 < len(texts) else "")
                )
                extra = most_restrictive(extra, evaluate_nested(value, context, depth + 1, "env -S"))
                index += 1 if "=" in option else 2
                continue
            index += 2 if option in value_options else 1
        while index < len(texts) and ENV_ASSIGNMENT_RE.match(texts[index]):
            index += 1
        index += positionals
    return index, extra


def git_subcommand(args: List[str]) -> Tuple[Optional[str], List[str], Dict[str, str]]:
    """Return the subcommand, its arguments and the aliases defined inline with ``-c alias.<name>=``."""
    aliases: Dict[str, str] = {}
    index = 0
    while index < len(args):
        arg = args[index]
        if arg in GIT_OPTIONS_WITH_VALUE:
            if arg == "-c" and index + 1 < len(args):
                key, _, value = args[index + 1].partition("=")
                if key.lower().startswith("alias."):
                    aliases[key[len("alias.") :].lower()] = value
            index += 2
        elif arg.startswith("-"):
            index += 1
        else:
            return arg.lower(), args[index + 1 :], aliases
    return None, [], aliases


def git_directories(args: List[str]) -> List[str]:
    """The ``-C <dir>`` options before the git subcommand, in order (git applies each relative to the previous)."""
    directories: List[str] = []
    index = 0
    while index < len(args):
        arg = args[index]
        if arg in GIT_OPTIONS_WITH_VALUE:
            if arg == "-C" and index + 1 < len(args):
                directories.append(args[index + 1])
            index += 2
        elif arg.startswith("-"):
            index += 1
        else:
            break
    return directories


def git_alias(name: str, inline: Dict[str, str], folder: Path) -> Optional[str]:
    if name in GIT_BUILTINS:
        return None
    if name in inline:
        return inline[name]
    return wg.git(folder, "config", "--get", f"alias.{name}")


def push_violation(args: List[str]) -> Optional[str]:
    for arg in args:
        lowered = arg.lower()
        if lowered in FORBIDDEN_PUSH_OPTIONS or lowered.startswith(("--force-with-lease=", "--force-if-includes=")):
            return arg
        if re.fullmatch(r"-[A-Za-z]+", arg) and re.search(r"[fd]", arg[1:]):
            return arg
        if len(arg) > 1 and arg[0] in "+:":
            return arg
        if is_unresolved(arg) and (
            FORCE_TEXT_RE.search(" " + arg.replace("$", "")) or arg.replace("$", "")[:1] in "+:"
        ):
            return arg
    return None


def push_positionals(args: List[str]) -> List[str]:
    positionals: List[str] = []
    index = 0
    while index < len(args):
        arg = args[index]
        if arg == "--":
            positionals.extend(args[index + 1 :])
            break
        if arg in PUSH_OPTIONS_WITH_VALUE:
            index += 2
            continue
        if not arg.startswith("-"):
            positionals.append(arg)
        index += 1
    return positionals


def push_destination_problem(
    args: List[str], workflow: wg.Workflow, repository: Optional[wg.Repository]
) -> Tuple[Optional[str], bool]:
    """(denial reason, unresolved) for the destinations of a push without forbidden options."""
    branch = workflow.branch
    positionals = push_positionals(args)
    unresolved = any(is_unresolved(arg) for arg in args)
    refspecs = positionals[1:]
    where = workflow.repository_label(repository) if repository else ""
    if not refspecs:
        current = wg.current_branch(repository.root) if repository else None
        if repository is None or current is None:
            return None, True
        if current != branch:
            return f"the current branch{where} is '{current}'; the workflow only pushes '{branch}'.", False
        merge = wg.git(repository.root, "config", "--get", f"branch.{current}.merge")
        if merge and normalize_ref(merge) != branch:
            return f"'{current}'{where} tracks '{merge}'; the workflow only pushes to '{branch}'.", False
        return None, unresolved
    for refspec in refspecs:
        if is_unresolved(refspec):
            unresolved = True
            continue
        source, colon, destination = refspec.partition(":")
        if colon and not destination:
            return f"refspec '{refspec}' has no destination.", False
        target = destination if colon else source
        if not colon and source == "HEAD":
            if repository is None:
                unresolved = True
                continue
            target = wg.current_branch(repository.root) or "HEAD"
        if target.startswith("refs/") and not target.startswith("refs/heads/"):
            return f"'{refspec}' pushes '{target}'; the workflow only pushes the branch '{branch}'.", False
        if normalize_ref(target) != branch:
            return f"'{refspec}' pushes to '{normalize_ref(target)}'; the workflow only pushes to '{branch}'.", False
    return None, unresolved


def evaluate_push(
    args: List[str], workflow: wg.Workflow, resolved: bool = True, repository: Optional[wg.Repository] = None
) -> Decision:
    """``repository``: where the push runs; None when the hooks cannot tell (several repositories)."""
    violation = push_violation(args)
    if violation:
        return deny(
            f"'{violation}' is not allowed: no force push, branch deletion or mirror push in the "
            "delivery workflow. Ask the user to do it manually if it is really needed."
        )
    problem, unresolved = push_destination_problem(args, workflow, repository)
    if problem:
        return deny(f"push destination: {problem}")
    shown = " ".join(["git push", *args])
    if repository is None and unresolved:
        return (
            "ask",
            f"`{shown}` runs in a folder the hooks cannot match to one of the workflow's repositories "
            "(use `git -C <repository> push` or `cd <repository>` first). Allow it?",
        )
    if unresolved or not resolved:
        return ("ask", f"`{shown}` cannot be fully resolved by the hooks (variables or substitutions). Allow it?")
    where = workflow.repository_label(repository) if repository else ""
    return (
        "ask",
        f"Confirm `{shown}` to {workflow.branch}{where} (workflow '{workflow.slug}', phase '{workflow.phase}').",
    )


def is_test_path(path: str) -> bool:
    parts = path.replace("\\", "/").split("/")
    for part in parts[:-1]:
        lowered = part.lower()
        if lowered in TEST_DIRECTORIES or lowered.endswith((".tests", ".test", ".specs", ".integrationtests")):
            return True
    return bool(TEST_FILE_RE.search(parts[-1]))


def is_code_path(path: str) -> bool:
    return Path(path).suffix.lower() in CODE_EXTENSIONS and not is_test_path(path)


def parse_commit_args(args: List[str]) -> Tuple[bool, bool, List[str]]:
    """Return (all tracked changes, amend, pathspecs) of a ``git commit`` command."""
    commit_all = amend = False
    pathspecs: List[str] = []
    index = 0
    while index < len(args):
        arg = args[index]
        if arg == "--":
            pathspecs.extend(args[index + 1 :])
            break
        if arg in ("-a", "--all"):
            commit_all = True
        elif arg == "--amend":
            amend = True
        elif arg in COMMIT_OPTIONS_WITH_VALUE:
            index += 1
        elif re.fullmatch(r"-[A-Za-z]+", arg):
            for position, flag in enumerate(arg[1:]):
                if flag == "a":
                    commit_all = True
                if flag in COMMIT_SHORT_FLAGS_WITH_VALUE:
                    if position == len(arg) - 2:
                        index += 1
                    break
        elif not arg.startswith("-"):
            pathspecs.append(arg)
        index += 1
    return commit_all, amend, pathspecs


def commit_paths(
    args: List[str], workflow: wg.Workflow, stages: bool, repository: wg.Repository
) -> Optional[List[str]]:
    """Paths the commit will contain (a superset when files are staged by the same command), or None."""
    root = repository.root
    commit_all, amend, pathspecs = parse_commit_args(args)
    if stages or commit_all or pathspecs:
        found = wg.repository_dirty_paths(workflow, repository)
    else:
        staged = wg.git(root, "diff", "--cached", "--name-only")
        found = None if staged is None else staged.splitlines()
    if found is None:
        return None
    paths = set(found)
    if amend:
        previous = wg.git(root, "diff-tree", "--no-commit-id", "--name-only", "-r", "HEAD")
        paths.update((previous or "").splitlines())
    return sorted(path for path in paths if path)


def evaluate_commit(
    args: List[str], workflow: wg.Workflow, stages: bool, repository: Optional[wg.Repository] = None
) -> Decision:
    """Test-first gate: a build or feedback commit that changes code without any test file asks the user.

    ``repository``: where the commit runs; None when the hooks cannot tell (folder unknown in a
    multi-repository workflow), which asks too, since the commit cannot be checked.
    """
    if workflow.phase not in COMMIT_GATED_PHASES:
        return NO_DECISION
    if repository is None:
        shown = " ".join(["git commit", *args])
        return (
            "ask",
            f"`{shown}` runs in a folder the hooks cannot match to one of the workflow's repositories, so they "
            "cannot check that it contains a test file (red-green-refactor skill). Use `git -C <repository> "
            "commit` or `cd <repository>` first. Allow it?",
        )
    paths = commit_paths(args, workflow, stages, repository)
    if not paths or any(is_test_path(path) for path in paths):
        return NO_DECISION
    code = [path for path in paths if is_code_path(path)]
    if not code:
        return NO_DECISION
    shown = ", ".join(code[:5]) + (f" and {len(code) - 5} more" if len(code) > 5 else "")
    where = workflow.repository_label(repository)
    return (
        "ask",
        f"This commit{where} changes code ({shown}) without any test file, against the red-green-refactor skill. "
        "Allow it only if you accept this lot without tests (for example a legacy project with no test "
        "harness); otherwise deny it and the implementer writes the failing test first.",
    )


def evaluate_git(
    args: List[str],
    context: ShellContext,
    depth: int = 0,
    inherited: Optional[Dict[str, str]] = None,
    directories: Optional[List[str]] = None,
) -> Decision:
    """``directories``: the ``git -C`` options of the command an alias expands from."""
    workflow = context.workflow
    subcommand, sub_args, inline_aliases = git_subcommand(args)
    inline_aliases = {**context.git_aliases, **(inherited or {}), **inline_aliases}
    directories = [*(directories or []), *git_directories(args)]
    if subcommand is None:
        return NO_DECISION
    repository = context.repository(directories)
    if is_unresolved(subcommand):
        return evaluate_unresolved([subcommand, *sub_args], context, repository)
    if subcommand == "config":
        record_git_alias(sub_args, context)
        return NO_DECISION
    if subcommand == "commit":
        return evaluate_commit(sub_args, workflow, context.stages, repository)
    if subcommand != "push":
        alias = git_alias(subcommand, inline_aliases, repository.root if repository else workflow.root)
        if not alias:
            return NO_DECISION
        if depth >= MAX_ALIAS_DEPTH:
            return ("ask", f"Confirm `git {subcommand}`: the alias is nested too deeply to be checked.")
        rest = " ".join(sub_args)
        if alias.startswith("!"):
            # git runs shell aliases from the top of the repository.
            saved = context.cwd
            context.cwd = repository.root if repository else None
            try:
                return evaluate_command(f"{alias[1:]} {rest}", context, depth + 1)
            finally:
                context.cwd = saved
        expanded = [token.text for segment in lex(alias) for token in segment]
        return evaluate_git(expanded + sub_args, context, depth + 1, inline_aliases, directories)
    return evaluate_push(sub_args, workflow, repository=repository)


def record_git_alias(args: List[str], context: ShellContext) -> None:
    """``git config [--global] alias.pf 'push --force'`` defines an alias used later in the same command line."""
    positionals = [arg for arg in args if not arg.startswith("-")]
    if len(positionals) >= 2 and positionals[0].lower().startswith("alias."):
        context.git_aliases[positionals[0][len("alias.") :].lower()] = " ".join(positionals[1:])


def evaluate_unresolved(
    words: List[str], context: ShellContext, repository: Optional[wg.Repository] = None
) -> Decision:
    """A command whose name is only known at run time: a ``push`` among its words is treated as a git push."""
    lowered = [word.lower() for word in words]
    if "push" in lowered:
        return evaluate_push(
            words[lowered.index("push") + 1 :],
            context.workflow,
            resolved=False,
            repository=repository or context.repository(),
        )
    if lowered and lowered[0] in AZ_DEVOPS_GROUPS | {"rest"}:
        return ("ask", f"`{' '.join(words)}` looks like an az command the hooks cannot resolve. Allow it?")
    return NO_DECISION


def evaluate_az(args: List[str]) -> Decision:
    words: List[str] = []
    index = 0
    lowered = [arg.lower() for arg in args]
    while index < len(lowered):
        arg = lowered[index]
        if arg.startswith("-"):
            if not words and arg in AZ_GLOBAL_OPTIONS_WITH_VALUE:
                index += 2
                continue
            if words:
                break
            index += 1
            continue
        words.append(arg)
        index += 1
    rest = " ".join(lowered[index:])
    if not words:
        return NO_DECISION
    if words[0] == "rest":
        return deny("`az rest` can call any Azure DevOps API: not allowed by the delivery workflow.")
    if words[0] not in AZ_DEVOPS_GROUPS:
        return NO_DECISION
    if words[:2] == ["repos", "pr"]:
        nested = tuple(words[2:4])
        if (len(words) > 2 and words[2] in ("list", "show", "checkout")) or nested in {
            ("policy", "list"),
            ("reviewer", "list"),
            ("work-item", "list"),
        }:
            return NO_DECISION
        return deny(
            "pull requests are managed through the ado-write MCP tools only (azure-devops skill); "
            "`az repos pr` writes are not allowed."
        )
    if words[:2] == ["repos", "policy"]:
        return deny("branch policies are the user's decision: `az repos policy` is not allowed.")
    if words[:2] == ["boards", "work-item"] and words[-1] in AZ_WRITE_VERBS:
        return deny("the delivery workflow never modifies Azure DevOps work items.")
    if words[:2] == ["devops", "invoke"]:
        if re.search(r"--http-method[=\s]+(?:post|put|patch|delete)\b", rest):
            return deny("write calls through `az devops invoke` are not allowed by the delivery workflow.")
        return NO_DECISION
    verb = words[-1]
    if verb in AZ_READ_VERBS or verb.startswith(("list-", "show-")):
        return NO_DECISION
    if verb in AZ_WRITE_VERBS:
        return deny(
            f"`az {' '.join(words)}` writes to Azure DevOps: not allowed (the workflow uses the MCP tools only)."
        )
    return (
        "ask",
        f"`az {' '.join(words)}` is not a known read command and the builder never uses the az CLI. Allow it?",
    )


def evaluate_nested(text: str, context: ShellContext, depth: int, what: str) -> Decision:
    if depth > MAX_NESTING:
        decision = evaluate_opaque(text, f"{what} (nested too deeply to be parsed)")
        return decision
    return evaluate_command(text, context, depth)


def evaluate_launcher(launcher: str, tokens: List[Token], context: ShellContext, depth: int) -> Decision:
    """Evaluate the command run by a shell launcher (cmd /c, bash -c, pwsh -Command, iex, eval ...)."""
    flag_prefixes = ("/",) if launcher == "cmd" else ("-",)
    index = 0
    while index < len(tokens) and not tokens[index].quoted and tokens[index].text.startswith(flag_prefixes):
        index += 1
    rest = tokens[index:]
    if not rest:
        return NO_DECISION
    text = rest[0].text if len(rest) == 1 and rest[0].quoted else " ".join(token.text for token in rest)
    if depth > MAX_NESTING:
        return evaluate_opaque(text, f"`{launcher}` (nested too deeply to be parsed)")
    # A child shell's cd does not move the commands after it; eval and iex run in the current shell.
    saved = context.cwd
    try:
        if launcher == "eval" or (len(rest) == 1 and rest[0].quoted):
            return evaluate_command(text, context, depth)
        return evaluate_segment(rest, context, depth)
    finally:
        if launcher not in CURRENT_SHELL_LAUNCHERS:
            context.cwd = saved


def evaluate_interpreter(name: str, texts: List[str]) -> Decision:
    flags = INTERPRETER_CODE_FLAGS[name]
    for index, text in enumerate(texts):
        if text in flags and index + 1 < len(texts):
            return evaluate_opaque(" ".join(texts[index + 1 :]), f"`{name} {text}`")
        attached = next(
            (
                flag
                for flag in flags
                if flag.startswith("-") and len(flag) == 2 and text.startswith(flag) and len(text) > 2
            ),
            None,
        )
        if attached:
            return evaluate_opaque(text[2:], f"`{name} {attached}`")
    return NO_DECISION


def evaluate_find(tokens: List[Token], context: ShellContext, depth: int) -> Decision:
    decision = NO_DECISION
    texts = [token.text for token in tokens]
    for index, text in enumerate(texts):
        if text in FIND_EXEC:
            end = index + 1
            while end < len(texts) and texts[end] not in (";", "\\;", "+", "\\"):
                end += 1
            decision = most_restrictive(decision, evaluate_segment(tokens[index + 1 : end], context, depth + 1))
    return decision


def record_assignment(texts: List[str], context: ShellContext) -> bool:
    """``g=git`` (POSIX) or ``$g = 'git'`` (PowerShell) alone in a segment."""
    if texts and all(ENV_ASSIGNMENT_RE.match(text) for text in texts):
        for text in texts:
            name, _, value = text.partition("=")
            context.variables[name] = value
        return True
    if len(texts) == 3 and texts[1] == "=":
        match = PS_VARIABLE_RE.match(texts[0])
        if match:
            context.variables[match.group(1)] = texts[2]
            return True
    return False


def resolve_variable(word: str, context: ShellContext) -> Optional[str]:
    match = PS_VARIABLE_RE.match(word)
    return context.variables.get(match.group(1)) if match else None


def evaluate_segment(tokens: List[Token], context: ShellContext, depth: int) -> Decision:
    texts = [token.text for token in tokens]
    if record_assignment(texts, context):
        return NO_DECISION
    start, decision = skip_wrappers(tokens, context, depth)
    if start >= len(texts):
        return decision
    word = texts[start]
    if is_unresolved(word):
        value = resolve_variable(word, context)
        if value is None:
            return most_restrictive(decision, evaluate_unresolved(texts[start + 1 :], context))
        replaced = [Token(part, False) for part in value.split()] + list(tokens[start + 1 :])
        return most_restrictive(decision, evaluate_segment(replaced, context, depth + 1))
    name = command_name(word)
    args = texts[start + 1 :]
    if name in CHANGE_DIRECTORY:
        context.change_directory(name, args)
        return decision
    if any(text.lower().endswith(CLOSE_SCRIPT) for text in texts[start : start + 3]):
        workflow = context.workflow
        return most_restrictive(
            decision,
            (
                "ask",
                f"Close workflow '{workflow.slug}' (phase '{workflow.phase}'): archive .ai/{workflow.slug}, "
                "clear .ai/current and set phase done?",
            ),
        )
    if name == "git":
        result = evaluate_git(args, context, depth)
    elif name == "push":  # the rest of `$(echo git) push ...`
        result = evaluate_push(args, context.workflow, resolved=False, repository=context.repository())
    elif name == "az":
        result = evaluate_az(args)
    elif name in HTTP_CLIENTS and any(ADO_HOST_RE.search(arg) for arg in args):
        result = deny(
            f"`{name}` calls to Azure DevOps are not allowed: the workflow writes through the MCP gates only."
        )
    elif name in SHELL_LAUNCHERS:
        result = evaluate_launcher(name, tokens[start + 1 :], context, depth + 1)
    elif name in INTERPRETER_CODE_FLAGS:
        result = evaluate_interpreter(name, args)
    elif name == "find":
        result = evaluate_find(tokens[start + 1 :], context, depth)
    else:
        result = NO_DECISION
    return most_restrictive(decision, result)


def evaluate_command(command: str, context: Any, depth: int = 0) -> Decision:
    if isinstance(context, wg.Workflow):
        context = ShellContext(context)
    decision = NO_DECISION
    for segment in lex(command):
        decision = most_restrictive(decision, evaluate_segment(segment, context, depth))
    for token_text in re.findall(r"\$'[^']*'", command):
        if FORCE_TEXT_RE.search(" " + token_text[2:-1]) and re.search(r"\bpush\b", command):
            decision = most_restrictive(decision, deny(f"ANSI-C quoted argument {token_text} in a push: not allowed."))
    return decision


def evaluate_shell(command: str, hook: wg.HookInput, workflow: wg.Workflow) -> Decision:
    context = ShellContext(workflow, stages=bool(GIT_STAGE_RE.search(command)), cwd=Path(hook.cwd))
    context.scoped_cd = bool(SCOPED_CD_RE.search(command))
    decision = evaluate_command(command, context)
    if wg.mentions_protected_path(command) and SHELL_WRITE_RE.search(command):
        decision = most_restrictive(
            decision,
            deny(
                "review.md, state.json, .ai/current and the hook-owned files are never written from the shell: "
                "use the file edit tools, which the hooks check (delivery-workflow skill)."
            ),
        )
    return decision


# --- Azure DevOps MCP tools -----------------------------------------------------------------


def _matches(value: Any, expected: str) -> bool:
    return str(value or "").strip().lower() == expected.strip().lower()


def repository_names(repository: wg.Repository) -> List[str]:
    """Names a PR call may use for ``repository``: its Azure Repos name, else its folder and origin names."""
    coordinates = wg.ado_coordinates(repository.root)
    if coordinates:
        return [coordinates["repository"]]
    names = [repository.path, PurePosixPath(repository.path).name]
    origin = wg.git(repository.root, "config", "--get", "remote.origin.url")
    if origin:
        names.append(re.sub(r"\.git$", "", origin.strip().rstrip("/").replace("\\", "/").rsplit("/", 1)[-1]))
    return [name for name in names if name and name != "."]


def pr_repository(name: str, workflow: wg.Workflow) -> Tuple[Optional[wg.Repository], Optional[str]]:
    """The workflow repository a draft PR call targets (``repositoryId``), or why it cannot be told."""
    repositories = workflow.repositories
    if len(repositories) == 1:
        return repositories[0], None
    shown = ", ".join(f"{repository.path} ({'/'.join(repository_names(repository))})" for repository in repositories)
    if not name:
        return None, f"name the repository of the PR in repositoryId, one of the workflow's repositories: {shown}."
    if GUID_RE.match(name):
        return None, (
            "a multi-repository workflow tells its repositories apart by name: give the repository name of the "
            f"project contract in repositoryId, not its ID ({shown})."
        )
    found = [
        repository
        for repository in repositories
        if any(_matches(name, candidate) for candidate in repository_names(repository))
    ]
    if len(found) == 1:
        return found[0], None
    if not found:
        return None, f"repository '{name}' is not one of the workflow's repositories: {shown}."
    return None, f"repository '{name}' matches several repositories of the workflow: {shown}."


def evaluate_pr_create(args: Dict[str, Any], workflow: wg.Workflow) -> Decision:
    if workflow.phase not in wg.PR_CREATION_PHASES:
        return deny(f"draft PRs are created at the end of the build phase; the current phase is '{workflow.phase}'.")
    repository = str(args.get("repositoryId") or args.get("repository") or "").strip()
    target_repository, problem = pr_repository(repository, workflow)
    if target_repository is None:
        return deny(f"draft PR blocked: {problem}")
    multi = workflow.multi_repo
    if target_repository.pull_request:
        if not multi:
            return deny(f"the workflow already has draft PR {target_repository.pull_request}: update it instead.")
        return deny(
            f"repository '{target_repository.path}' already has draft PR {target_repository.pull_request}: "
            "update it instead."
        )
    if not is_true(args.get("isDraft")):
        return deny("only draft PRs are allowed: set isDraft to true. The user publishes the PR after reviewing it.")
    if is_true(args.get("autoComplete")) or is_true(args.get("bypassPolicy")):
        return deny("autocomplete and branch policy bypass are not allowed.")
    description = args.get("description")
    if isinstance(description, str) and utf16_length(description) > wg.PR_DESCRIPTION_LIMIT:
        return deny(
            f"the description has {utf16_length(description)} UTF-16 characters; Azure DevOps accepts at most "
            f"{wg.PR_DESCRIPTION_LIMIT}. Shorten pr-description.md."
        )
    root = target_repository.root
    project = str(args.get("project") or "").strip()
    coordinates = wg.ado_coordinates(root)
    if coordinates:
        if project and not _matches(project, coordinates["project"]) and not GUID_RE.match(project):
            return deny(
                f"draft PR blocked: project '{project}' is not the workflow's project '{coordinates['project']}'."
            )
        if repository and not GUID_RE.match(repository) and not _matches(repository, coordinates["repository"]):
            return deny(
                f"draft PR blocked: repository '{repository}' is not the workflow's repository "
                f"'{coordinates['repository']}' (origin)."
            )
    statuses = wg.workflow_status(workflow, with_merge_base=len(workflow.repositories) > 1)
    blocked = wg.review_gate(workflow, statuses)
    if blocked:
        return deny(f"draft PR blocked: {blocked}")
    status = next(item for item in statuses if item.repository.path == target_repository.path)
    head = status.head
    where = workflow.repository_label(target_repository)
    if len(statuses) > 1 and not status.changed:
        return deny(
            f"draft PR blocked: {target_repository.path} has no commit on top of "
            f"{target_repository.base_branch or 'its base branch'}: nothing to merge there."
        )
    branch = wg.current_branch(root)
    if not branch:
        return deny(f"draft PR blocked: HEAD{where} is detached; check out the work branch.")
    if branch != workflow.branch:
        return deny(
            f"draft PR blocked: the current branch{where} is '{branch}', not the work branch '{workflow.branch}'."
        )
    base_branch = target_repository.base_branch
    source = str(args.get("sourceRefName") or "")
    if source.strip() and normalize_ref(source) != branch:
        return deny(f"draft PR blocked: sourceRefName '{source}' is not the reviewed branch '{branch}'.")
    target = normalize_ref(str(args.get("targetRefName") or ""))
    if base_branch and target and target != base_branch:
        return deny(
            f"draft PR blocked: targetRefName '{target}' differs from base_branch '{base_branch}'{where} in "
            "state.json. Fix the call, or update state.json if the user chose another target."
        )
    if wg.remote_branch_sha(root, branch) != head:
        push = f"git -C {target_repository.path} push -u origin {branch}" if multi else f"git push -u origin {branch}"
        return deny(
            f"draft PR blocked: origin/{branch}{where} is not at the reviewed commit {head[:8] if head else '?'}. "
            f"Push first ({push})."
        )
    title = str(args.get("title") or "").strip()
    shown = f"{project or '?'}/{repository or '?'}"
    if not coordinates:
        shown += " (not verified: origin is not an Azure Repos URL)"
    return (
        "ask",
        f"Create the DRAFT pull request '{title}' in {shown}{where} from {branch} into "
        f"{target or base_branch or '?'} (review APPROVED at {head[:8] if head else '?'})?",
    )


def check_pr_scope(args: Dict[str, Any], workflow: wg.Workflow, what: str) -> Optional[str]:
    pull_requests = workflow.pull_requests()
    if not pull_requests:
        where = f"the pull_request of its repositories in {wg.REPOSITORIES_FIELD}" if workflow.multi_repo else ""
        return f"{what}: the workflow has no draft PR yet (state.json {where or 'pull_request'})."
    given = str(args.get("pullRequestId") or "").strip()
    if given not in pull_requests:
        if not workflow.multi_repo:
            return f"{what}: pullRequestId '{given or 'missing'}' is not the workflow's PR {workflow.pull_request}."
        shown = ", ".join(f"{number} ({repository.path})" for number, repository in pull_requests.items())
        return f"{what}: pullRequestId '{given or 'missing'}' is not one of the workflow's PRs: {shown}."
    return None


def evaluate_pr_write(args: Dict[str, Any], workflow: wg.Workflow) -> Decision:
    action = str(args.get("action") or "").strip().lower()
    if action == "create":
        return evaluate_pr_create(args, workflow)
    if action == "update":
        if is_true(args.get("autoComplete")):
            return deny("autocomplete would complete the PR without the user's review: not allowed.")
        if is_true(args.get("bypassPolicy")):
            return deny("bypassing branch policies is not allowed.")
        if "isDraft" in args and not is_true(args.get("isDraft")):
            return deny("publishing the draft is the user's decision: they publish it in Azure DevOps.")
        extra = sorted(key for key, value in args.items() if key not in PR_UPDATE_FIELDS and value is not None)
        if extra:
            return deny(
                f"PR updates are limited to title and description; {', '.join(extra)} "
                "is the user's decision in Azure DevOps."
            )
        blocked = check_pr_scope(args, workflow, "PR update blocked")
        if blocked:
            return deny(blocked)
        description = args.get("description")
        if isinstance(description, str) and utf16_length(description) > wg.PR_DESCRIPTION_LIMIT:
            return deny(f"the description exceeds {wg.PR_DESCRIPTION_LIMIT} UTF-16 characters.")
        return NO_DECISION
    if action in {"update_reviewers", "vote"}:
        return deny(f"'{action}' is the user's decision in Azure DevOps.")
    return deny(f"unknown or missing action '{action}' for {PR_WRITE_TOOL}.")


def evaluate_thread_write(args: Dict[str, Any], workflow: wg.Workflow) -> Decision:
    action = str(args.get("action") or "").strip().lower()
    if action not in {"create", "reply", "update", "update_status"}:
        return deny(f"unknown or missing action '{action}' for {PR_THREAD_WRITE_TOOL}.")
    blocked = check_pr_scope(args, workflow, "PR comment blocked")
    if blocked:
        return deny(blocked)
    if action == "update_status":
        thread = args.get("threadId")
        given = str(args.get("pullRequestId") or "").strip()
        repository = workflow.pull_requests()[given]
        if str(thread or "") == str(repository.record_thread or "-"):
            return deny("the workflow record thread keeps its status (azure-devops skill).")
        return (
            "ask",
            f"Set thread {thread} of PR {given}{workflow.repository_label(repository)} to '{args.get('status')}'? "
            "Only AI threads the workflow opened may change status; human threads are resolved by their authors.",
        )
    content = args.get("content")
    if not isinstance(content, str) or not content.lstrip().startswith(wg.AI_MARKER):
        return deny(
            "comments posted by the workflow appear under the user's identity: start the content "
            f"with '{wg.AI_MARKER}' (azure-devops skill)."
        )
    return NO_DECISION


def ado_tool(tool_name: str) -> Optional[str]:
    """The Azure DevOps tool name, when the tool comes from an Azure DevOps MCP server."""
    match = ADO_TOOL_RE.search(tool_name)
    if not match:
        return None
    prefix = tool_name[: match.start(1)]
    if prefix and not ADO_SERVER_HINT_RE.search(prefix):
        return None  # another server's tool (mcp_github_repo_file_write ...)
    return match.group(1).lower()


def evaluate_ado(tool: str, args: Dict[str, Any], workflow: wg.Workflow) -> Decision:
    action = str(args.get("action") or "").strip().lower()
    if tool in ADO_READ_TOOLS and action not in ADO_WRITE_ACTIONS_OF_READ_TOOLS.get(tool, frozenset()):
        return NO_DECISION
    if tool == PR_WRITE_TOOL:
        return evaluate_pr_write(args, workflow)
    if tool == PR_THREAD_WRITE_TOOL:
        return evaluate_thread_write(args, workflow)
    return deny(
        f"'{tool}' writes to Azure DevOps (or is not a known read tool). The delivery workflow only creates "
        "draft PRs and AI-marked PR comments, and never modifies work items."
    )


# --- entry point ----------------------------------------------------------------------------


def evaluate(hook: wg.HookInput, workflow: Optional[wg.Workflow] = None) -> Tuple[Decision, sp.Effects]:
    effects = sp.Effects()
    if workflow is None:
        workflow = wg.load_workflow(hook.cwd)
    if workflow is None:
        return NO_DECISION, effects
    decision = NO_DECISION
    tool = ado_tool(hook.tool_name)
    if tool:
        decision = evaluate_ado(tool, hook.tool_input, workflow)
    command = hook.tool_input.get("command")
    if isinstance(command, str) and command.strip():
        decision = most_restrictive(decision, evaluate_shell(command, hook, workflow))
    elif not tool:
        file_decision, effects = sp.evaluate_file_write(hook, workflow)
        decision = most_restrictive(decision, file_decision)
    return decision, effects


def is_sensitive(hook: wg.HookInput) -> bool:
    tool = ado_tool(hook.tool_name)
    if tool and tool not in ADO_READ_TOOLS:
        return True
    return any(wg.mentions_protected_path(text) for text in sp.strings_in(hook.tool_input))


def main() -> int:
    hook = wg.read_input()
    workflow: Optional[wg.Workflow] = None
    try:
        workflow = wg.load_workflow(hook.cwd)
        if workflow is not None:
            wg.touch_heartbeat(workflow, "PreToolUse")
        (decision, reason), effects = evaluate(hook, workflow)
        if decision != "deny":
            sp.apply_effects(workflow, effects)
        if decision is not None:
            wg.log_event(workflow, "PreToolUse", hook.tool_name, decision, reason)
        elif workflow is not None and WEB_TOOL_RE.search(hook.tool_name) and not ado_tool(hook.tool_name):
            target = " ".join(sp.strings_in(hook.tool_input))[:200]
            wg.log_event(workflow, "PreToolUse", hook.tool_name, "observed", f"web access: {target}")
    except Exception as exc:  # noqa: BLE001 - a hook bug must not break unrelated tools
        if is_sensitive(hook):
            decision, reason = "deny", f"hook error while checking a pull request or workflow file write: {exc}"
        else:
            decision, reason = None, ""
        wg.log_event(workflow, "PreToolUse", hook.tool_name, decision or "error", f"hook error: {exc!r}")
    wg.emit(wg.pre_tool_use_result(decision, reason))
    return 0


if __name__ == "__main__":
    sys.exit(main())
