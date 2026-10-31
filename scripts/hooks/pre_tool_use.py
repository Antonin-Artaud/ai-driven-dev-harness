#!/usr/bin/env python3
"""PreToolUse policy of the ai-delivery-workflow plugin.

Acts only in a git repository with an active workflow (``.ai/current`` present and phase not
``done``). It gates draft PR creation, asks before ``git push`` and before a build or feedback
commit that changes code without any test file (red-green-refactor skill), and denies force
pushes, Azure DevOps writes other than draft PRs and AI-marked PR comments, and az CLI writes.
Prints one JSON object; ``{}`` means no decision (the normal permission flow applies).
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))

import workflow_gate as wg  # noqa: E402

Decision = Tuple[Optional[str], str]
NO_DECISION: Decision = (None, "")
_RANK = {None: 0, "allow": 1, "ask": 2, "deny": 3}

PR_WRITE_TOOL = "repo_pull_request_write"
PR_THREAD_WRITE_TOOL = "repo_pull_request_thread_write"

# Tool names of the Azure DevOps MCP servers, possibly prefixed by the client (mcp_ado-write_..., ado-write/...).
ADO_TOOL_RE = re.compile(
    r"(?:^|[^a-z0-9])((?:repo|wit|wiki|pipelines|testplan|work|advsec|enterprise_live_migration|search)_[a-z0-9_]+)$",
    re.IGNORECASE,
)
# Write tools are the *_write dispatchers plus these (Azure DevOps remote MCP server reference).
ADO_EXTRA_WRITE_TOOLS = frozenset(
    {"repo_create_branch", "wiki_upsert_page", "wit_work_item_attachment_upload", "wit_work_item_attachment_link"}
)

SEPARATOR_CHARS = frozenset(";|&\n\r(){}`")
QUOTE_CHARS = "\"'"
MAX_NESTING = 2
TRANSPARENT_PREFIXES = frozenset({"sudo", "env", "command", "exec", "nohup", "time", "call", "@", "."})
SHELL_LAUNCHERS = frozenset(
    {"cmd", "bash", "sh", "zsh", "dash", "pwsh", "powershell", "wsl", "start", "invoke-expression", "iex"}
)
EXECUTABLE_SUFFIXES = (".exe", ".cmd", ".bat", ".com")
ENV_ASSIGNMENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
GIT_OPTIONS_WITH_VALUE = frozenset({"-c", "-C", "--git-dir", "--work-tree", "--namespace", "--config-env", "--super-prefix"})
FORBIDDEN_PUSH_OPTIONS = frozenset(
    {"--force", "--force-with-lease", "--force-if-includes", "--mirror", "--delete", "--prune"}
)
_AZ_GLOBAL_OPTIONS = r"(?:\s+--?[a-z][a-z-]*(?:[=\s](?!-)\S+)?)*"
AZ_REPOS_PR_RE = re.compile(r"^az" + _AZ_GLOBAL_OPTIONS + r"\s+repos\s+pr\s+(?P<sub>[a-z-]+)(?:\s+(?P<sub2>[a-z-]+))?")
AZ_WORK_ITEM_WRITE_RE = re.compile(
    r"^az" + _AZ_GLOBAL_OPTIONS + r"\s+boards\s+work-item\s+(?:create|update|delete|relation\s+(?:add|remove))\b"
)
AZ_INVOKE_WRITE_RE = re.compile(
    r"^az" + _AZ_GLOBAL_OPTIONS + r"\s+devops\s+invoke\b.*--http-method[=\s]+(?:post|put|patch|delete)\b", re.DOTALL
)
# git commit: test-first gate (red-green-refactor skill).
COMMIT_GATED_PHASES = wg.STOP_GATED_PHASES
COMMIT_OPTIONS_WITH_VALUE = frozenset(
    {"-m", "-F", "-c", "-C", "-t", "--message", "--file", "--reuse-message", "--reedit-message",
     "--template", "--author", "--date", "--cleanup", "--fixup", "--squash", "--trailer", "--pathspec-from-file"}
)
COMMIT_SHORT_FLAGS_WITH_VALUE = "mFcCt"
GIT_STAGE_RE = re.compile(r"\bgit\b.*?\b(?:add|rm|mv|stage)\b", re.IGNORECASE | re.DOTALL)
CODE_EXTENSIONS = frozenset(
    {".py", ".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx", ".vue", ".svelte", ".java", ".kt", ".kts", ".scala",
     ".groovy", ".cs", ".fs", ".vb", ".go", ".rs", ".rb", ".php", ".swift", ".m", ".mm", ".c", ".cc", ".cpp",
     ".cxx", ".h", ".hpp", ".dart", ".ex", ".exs", ".erl", ".clj", ".lua", ".r", ".sql", ".sh", ".ps1", ".psm1"}
)
TEST_DIRECTORIES = frozenset({"test", "tests", "__tests__", "spec", "specs", "e2e", "testing", "cypress", "playwright"})
TEST_FILE_RE = re.compile(
    r"(?:^test_|^conftest\.py$|_test\.[^.]+$|_spec\.[^.]+$|\.(?:test|spec|cy|e2e)\.[^.]+$|(?:Tests?|Spec|IT)\.[^.]+$)"
)
AZ_PR_READ_SUBCOMMANDS = frozenset({"list", "show", "checkout"})
AZ_PR_READ_NESTED = frozenset({("policy", "list"), ("reviewer", "list"), ("work-item", "list")})


@dataclass(frozen=True)
class Token:
    text: str
    quoted: bool


def deny(reason: str) -> Decision:
    return ("deny", reason)


def most_restrictive(first: Decision, second: Decision) -> Decision:
    return second if _RANK[second[0]] > _RANK[first[0]] else first


def is_true(value: Any) -> bool:
    return value is True or (isinstance(value, str) and value.strip().lower() in {"true", "1", "yes"})


def is_false(value: Any) -> bool:
    return value is False or (isinstance(value, str) and value.strip().lower() in {"false", "0", "no"})


def normalize_ref(ref: str) -> str:
    ref = ref.strip()
    return ref[len("refs/heads/"):] if ref.startswith("refs/heads/") else ref


# --- shell commands -------------------------------------------------------------------------


def lex(command: str) -> List[List[Token]]:
    """Split a command line into segments of tokens.

    Quotes group words (and are removed); separators outside quotes (``; | & ( ) { }``, backtick,
    newline) end a segment. Backslashes are kept verbatim so Windows paths survive.
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

    for char in command:
        if quote:
            if char == quote:
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
            return name[: -len(suffix)]
    return name


def command_start(texts: List[str]) -> int:
    index = 0
    while index < len(texts) and (texts[index].lower() in TRANSPARENT_PREFIXES or ENV_ASSIGNMENT_RE.match(texts[index])):
        index += 1
    return index


def git_subcommand(args: List[str]) -> Tuple[Optional[str], List[str]]:
    index = 0
    while index < len(args):
        arg = args[index]
        if arg in GIT_OPTIONS_WITH_VALUE:
            index += 2
        elif arg.startswith("-"):
            index += 1
        else:
            return arg.lower(), args[index + 1:]
    return None, []


def push_violation(args: List[str]) -> Optional[str]:
    for arg in args:
        lowered = arg.lower()
        if lowered in FORBIDDEN_PUSH_OPTIONS or lowered.startswith("--force-with-lease="):
            return arg
        if re.fullmatch(r"-[A-Za-z]+", arg) and re.search(r"[fd]", arg[1:]):
            return arg
        if len(arg) > 1 and arg[0] in "+:":
            return arg
    return None


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
            pathspecs.extend(args[index + 1:])
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


def commit_paths(args: List[str], workflow: wg.Workflow, stages: bool) -> Optional[List[str]]:
    """Paths the commit will contain (a superset when files are staged by the same command), or None."""
    root = workflow.root
    commit_all, amend, pathspecs = parse_commit_args(args)
    if stages or commit_all or pathspecs:
        found = wg.dirty_paths(root)
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


def evaluate_commit(args: List[str], workflow: wg.Workflow, stages: bool) -> Decision:
    if workflow.phase not in COMMIT_GATED_PHASES:
        return NO_DECISION
    paths = commit_paths(args, workflow, stages)
    if not paths or any(is_test_path(path) for path in paths):
        return NO_DECISION
    code = [path for path in paths if is_code_path(path)]
    if not code:
        return NO_DECISION
    shown = ", ".join(code[:5]) + (f" and {len(code) - 5} more" if len(code) > 5 else "")
    return (
        "ask",
        f"This commit changes code ({shown}) without any test file, against the red-green-refactor skill. "
        "Allow it only if you accept this lot without tests (for example a legacy project with no test "
        "harness); otherwise deny it and the implementer writes the failing test first.",
    )


def evaluate_git(args: List[str], workflow: wg.Workflow, stages: bool = False) -> Decision:
    subcommand, push_args = git_subcommand(args)
    if subcommand == "commit":
        return evaluate_commit(push_args, workflow, stages)
    if subcommand != "push":
        return NO_DECISION
    violation = push_violation(push_args)
    if violation:
        return deny(
            f"'{violation}' is not allowed: no force push, branch deletion or mirror push in the "
            "delivery workflow. Ask the user to do it manually if it is really needed."
        )
    shown = " ".join(["git push", *push_args])
    return ("ask", f"Confirm `{shown}` (workflow '{workflow.slug}', phase '{workflow.phase}').")


def evaluate_az(args: List[str]) -> Decision:
    line = " ".join(["az", *(arg.lower() for arg in args)])
    pull_request = AZ_REPOS_PR_RE.match(line)
    if pull_request:
        sub = pull_request.group("sub")
        sub2 = pull_request.group("sub2") or ""
        if sub in AZ_PR_READ_SUBCOMMANDS or (sub, sub2) in AZ_PR_READ_NESTED:
            return NO_DECISION
        return deny(
            "pull requests are managed through the ado-write MCP tools only (azure-devops skill); "
            "`az repos pr` writes are not allowed."
        )
    if AZ_WORK_ITEM_WRITE_RE.match(line):
        return deny("the delivery workflow never modifies Azure DevOps work items.")
    if AZ_INVOKE_WRITE_RE.match(line):
        return deny("write calls through `az devops invoke` are not allowed by the delivery workflow.")
    return NO_DECISION


def evaluate_launcher(
    launcher: str, tokens: List[Token], workflow: wg.Workflow, depth: int, stages: bool = False
) -> Decision:
    """Evaluate the command run by a shell launcher (cmd /c, bash -c, pwsh -Command, iex ...)."""
    flag_prefixes = ("/",) if launcher == "cmd" else ("-",)
    index = 0
    while index < len(tokens) and not tokens[index].quoted and tokens[index].text.startswith(flag_prefixes):
        index += 1
    rest = tokens[index:]
    if not rest:
        return NO_DECISION
    if len(rest) == 1 and rest[0].quoted:
        return evaluate_command(rest[0].text, workflow, depth, stages)
    return evaluate_segment(rest, workflow, depth, stages)


def evaluate_segment(tokens: List[Token], workflow: wg.Workflow, depth: int, stages: bool = False) -> Decision:
    texts = [token.text for token in tokens]
    start = command_start(texts)
    if start >= len(texts):
        return NO_DECISION
    name = command_name(texts[start])
    if name == "git":
        return evaluate_git(texts[start + 1:], workflow, stages)
    if name == "az":
        return evaluate_az(texts[start + 1:])
    if name in SHELL_LAUNCHERS and depth < MAX_NESTING:
        return evaluate_launcher(name, tokens[start + 1:], workflow, depth + 1, stages)
    return NO_DECISION


def evaluate_command(command: str, workflow: wg.Workflow, depth: int = 0, stages: bool = False) -> Decision:
    """``stages``: the command line also stages files, so a commit is checked against the working tree."""
    decision = NO_DECISION
    for segment in lex(command):
        decision = most_restrictive(decision, evaluate_segment(segment, workflow, depth, stages))
    return decision


def evaluate_shell(command: str, hook: wg.HookInput) -> Decision:
    lowered = command.lower()
    if "git" not in lowered and "az" not in lowered:
        return NO_DECISION
    workflow = wg.load_workflow(hook.cwd)
    if workflow is None:
        return NO_DECISION
    return evaluate_command(command, workflow, stages=bool(GIT_STAGE_RE.search(command)))


# --- Azure DevOps MCP tools -----------------------------------------------------------------


def evaluate_pr_create(args: Dict[str, Any], workflow: wg.Workflow) -> Decision:
    if workflow.phase not in wg.PR_CREATION_PHASES:
        return deny(f"draft PRs are created at the end of the build phase; the current phase is '{workflow.phase}'.")
    if not is_true(args.get("isDraft")):
        return deny("only draft PRs are allowed: set isDraft to true. The user publishes the PR after reviewing it.")
    if is_true(args.get("autoComplete")) or is_true(args.get("bypassPolicy")):
        return deny("autocomplete and branch policy bypass are not allowed.")
    description = args.get("description")
    if isinstance(description, str) and len(description) > wg.PR_DESCRIPTION_LIMIT:
        return deny(
            f"the description has {len(description)} characters; Azure DevOps accepts at most "
            f"{wg.PR_DESCRIPTION_LIMIT}. Shorten pr-description.md."
        )
    root = workflow.root
    head = wg.head_sha(root)
    blocked = wg.review_gate(workflow, head=head)
    if blocked:
        return deny(f"draft PR blocked: {blocked}")
    branch = wg.current_branch(root)
    if not branch:
        return deny("draft PR blocked: HEAD is detached; check out the work branch.")
    base_branch = workflow.base_branch
    if base_branch and branch == base_branch:
        return deny(f"draft PR blocked: you are on the base branch '{base_branch}'; the work happens on ai/<slug>.")
    source = str(args.get("sourceRefName") or "")
    if source.strip() and normalize_ref(source) != branch:
        return deny(f"draft PR blocked: sourceRefName '{source}' is not the reviewed branch '{branch}'.")
    target = normalize_ref(str(args.get("targetRefName") or ""))
    if base_branch and target and target != base_branch:
        return deny(
            f"draft PR blocked: targetRefName '{target}' differs from base_branch '{base_branch}' in state.json. "
            "Fix the call, or update state.json if the user chose another target."
        )
    if wg.remote_branch_sha(root, branch) != head:
        return deny(
            f"draft PR blocked: origin/{branch} is not at the reviewed commit {head[:8]}. "
            f"Push first (git push -u origin {branch})."
        )
    title = str(args.get("title") or "").strip()
    return (
        "ask",
        f"Create the DRAFT pull request '{title}' from {branch} into {target or base_branch or '?'} "
        f"(review APPROVED at {head[:8]})?",
    )


def evaluate_pr_write(args: Dict[str, Any], workflow: wg.Workflow) -> Decision:
    action = str(args.get("action") or "").strip().lower()
    if action == "create":
        return evaluate_pr_create(args, workflow)
    if action == "update":
        if is_true(args.get("autoComplete")):
            return deny("autocomplete would complete the PR without the user's review: not allowed.")
        if is_true(args.get("bypassPolicy")):
            return deny("bypassing branch policies is not allowed.")
        if "isDraft" in args and is_false(args.get("isDraft")):
            return deny("publishing the draft is the user's decision: they publish it in Azure DevOps.")
        if str(args.get("status") or "").strip().lower() == "abandoned":
            return deny("abandoning the PR is the user's decision.")
        return NO_DECISION
    if action in {"update_reviewers", "vote"}:
        return deny(f"'{action}' is the user's decision in Azure DevOps.")
    return deny(f"unknown or missing action '{action}' for {PR_WRITE_TOOL}.")


def evaluate_thread_write(args: Dict[str, Any]) -> Decision:
    action = str(args.get("action") or "").strip().lower()
    if action in {"create", "reply", "update"}:
        content = args.get("content")
        if not isinstance(content, str) or not content.lstrip().startswith(wg.AI_MARKER):
            return deny(
                "comments posted by the workflow appear under the user's identity: start the content "
                f"with '{wg.AI_MARKER}' (azure-devops skill)."
            )
        return NO_DECISION
    if action == "update_status":
        return NO_DECISION
    return deny(f"unknown or missing action '{action}' for {PR_THREAD_WRITE_TOOL}.")


def is_ado_write_tool(tool: str) -> bool:
    return tool.endswith("_write") or tool in ADO_EXTRA_WRITE_TOOLS


def evaluate_ado(tool: str, args: Dict[str, Any], hook: wg.HookInput) -> Decision:
    tool = tool.lower()
    if not is_ado_write_tool(tool):
        return NO_DECISION
    workflow = wg.load_workflow(hook.cwd)
    if workflow is None:
        return NO_DECISION
    if tool == PR_WRITE_TOOL:
        return evaluate_pr_write(args, workflow)
    if tool == PR_THREAD_WRITE_TOOL:
        return evaluate_thread_write(args)
    return deny(
        f"'{tool}' writes to Azure DevOps. The delivery workflow only creates draft PRs and AI-marked PR "
        "comments, and never modifies work items."
    )


# --- entry point ----------------------------------------------------------------------------


def evaluate(hook: wg.HookInput) -> Decision:
    decision = NO_DECISION
    match = ADO_TOOL_RE.search(hook.tool_name)
    if match:
        decision = evaluate_ado(match.group(1), hook.tool_input, hook)
    command = hook.tool_input.get("command")
    if isinstance(command, str) and command.strip():
        decision = most_restrictive(decision, evaluate_shell(command, hook))
    return decision


def is_sensitive(hook: wg.HookInput) -> bool:
    match = ADO_TOOL_RE.search(hook.tool_name)
    return bool(match and match.group(1).lower() in {PR_WRITE_TOOL, PR_THREAD_WRITE_TOOL})


def main() -> int:
    hook = wg.read_input()
    try:
        decision, reason = evaluate(hook)
    except Exception as exc:  # noqa: BLE001 - a hook bug must not break unrelated tools
        if is_sensitive(hook):
            decision, reason = "deny", f"hook error while checking a pull request write: {exc}"
        else:
            decision, reason = None, ""
    wg.emit(wg.pre_tool_use_result(decision, reason))
    return 0


if __name__ == "__main__":
    sys.exit(main())
