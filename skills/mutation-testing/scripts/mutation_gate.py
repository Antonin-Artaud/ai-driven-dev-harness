#!/usr/bin/env python3
"""Mutation score of the changed lines, for the mutation-testing skill of the ai-driven-dev-harness.

Reads the report of a mutation testing run and keeps only the mutants on the lines this branch or this
lot changed: ``git diff`` between the merge base of HEAD and ``--base`` and the working tree, plus the
untracked files git does not ignore. Then it computes the mutation score of those mutants and compares
it with ``--threshold``.

Report formats, detected from the content:

* the mutation-testing-elements JSON report (StrykerJS, Stryker.NET, Stryker4s json reporter);
  schema: https://github.com/stryker-mutator/mutation-testing-elements/tree/master/packages/report-schema
* the PIT ``mutations.xml`` report (``outputFormats`` XML).

Score, as defined in https://stryker-mutator.io/docs/mutation-testing-elements/mutant-states-and-metrics/ :
detected (killed + timeout) / valid (detected + survived + no coverage). Ignored mutants (disabled in
the code with a reason), compile and runtime errors stay out of the score; pending mutants (not run)
fail the gate. PIT statuses are mapped the same way: KILLED, TIMED_OUT and MEMORY_ERROR are detected,
NON_VIABLE and RUN_ERROR are invalid, NOT_STARTED and STARTED are pending.

A mutation-testing-elements report carries the source of each file: a changed file whose source differs
from the working tree means the report is older than the code, and the gate refuses it.

Prints a JSON summary on stdout. Exit codes: 0 passed, 1 the report cannot be evaluated (unreadable,
unknown format, stale, git error), 2 below the threshold or mutants not run. Standard library only,
Python >= 3.9.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import xml.etree.ElementTree as ElementTree
from pathlib import Path, PurePosixPath
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple

EXIT_PASSED = 0
EXIT_ERROR = 1
EXIT_FAILED = 2
DEFAULT_THRESHOLD = 80.0
ELEMENTS = "mutation-testing-elements"
PITEST = "pitest-xml"

ELEMENTS_STATUS = {
    "Killed": "killed",
    "Timeout": "timeout",
    "Survived": "survived",
    "NoCoverage": "no_coverage",
    "CompileError": "invalid",
    "RuntimeError": "invalid",
    "Ignored": "ignored",
    "Pending": "pending",
}
PIT_STATUS = {
    "KILLED": ("killed", "Killed"),
    "MEMORY_ERROR": ("killed", "Killed"),
    "TIMED_OUT": ("timeout", "Timeout"),
    "SURVIVED": ("survived", "Survived"),
    "NO_COVERAGE": ("no_coverage", "NoCoverage"),
    "NON_VIABLE": ("invalid", "CompileError"),
    "RUN_ERROR": ("invalid", "RuntimeError"),
    "NOT_STARTED": ("pending", "Pending"),
    "STARTED": ("pending", "Pending"),
    "EQUIVALENT": ("ignored", "Ignored"),
}
COUNT_KEYS = ("killed", "timeout", "survived", "no_coverage", "ignored", "invalid", "pending")

# Same test file rule as the test-first commit gate (scripts/hooks/pre_tool_use.py, is_test_path).
TEST_DIRECTORIES = frozenset({"test", "tests", "__tests__", "spec", "specs", "e2e", "testing", "cypress", "playwright"})
TEST_FILE_RE = re.compile(
    r"(?:^test_|^conftest\.py$|_test\.[^.]+$|_spec\.[^.]+$|\.(?:test|spec|cy|e2e)\.[^.]+$|(?:Tests?|Spec|IT)\.[^.]+$)"
)
HUNK_RE = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")
WINDOWS_ABSOLUTE_RE = re.compile(r"^[A-Za-z]:/")


class GateError(Exception):
    """The report cannot be evaluated."""


class Mutant:
    __slots__ = ("file", "start", "end", "kind", "status", "mutator", "replacement", "reason")

    def __init__(
        self,
        file: str,
        start: int,
        end: int,
        kind: str,
        status: str,
        mutator: str,
        replacement: str = "",
        reason: str = "",
    ) -> None:
        self.file = file
        self.start = start
        self.end = end
        self.kind = kind
        self.status = status
        self.mutator = mutator
        self.replacement = replacement
        self.reason = reason


def is_test_path(path: str) -> bool:
    parts = path.replace("\\", "/").split("/")
    for part in parts[:-1]:
        lowered = part.lower()
        if lowered in TEST_DIRECTORIES or lowered.endswith((".tests", ".test", ".specs", ".integrationtests")):
            return True
    return bool(TEST_FILE_RE.search(parts[-1]))


# --- git ----------------------------------------------------------------------------------------


def git(root: Path, *args: str) -> Optional[str]:
    try:
        proc = subprocess.run(
            ["git", "-c", "core.quotepath=false", *args],
            cwd=str(root),
            stdin=subprocess.DEVNULL,
            capture_output=True,
            timeout=60,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0:
        return None
    return proc.stdout.decode("utf-8", errors="replace")


def unquote_path(text: str) -> str:
    """Undo git's C-style quoting of unusual paths (``"a/caf\\303\\251.js"``)."""
    if not (len(text) >= 2 and text[0] == text[-1] == '"'):
        return text
    raw = bytearray()
    escapes = {"n": 10, "t": 9, '"': 34, "\\": 92, "a": 7, "b": 8, "f": 12, "r": 13, "v": 11}
    inner, index = text[1:-1], 0
    while index < len(inner):
        char = inner[index]
        if char == "\\" and index + 1 < len(inner):
            following = inner[index + 1]
            if re.fullmatch(r"[0-7]{3}", inner[index + 1 : index + 4]):
                raw.append(int(inner[index + 1 : index + 4], 8))
                index += 4
                continue
            raw.append(escapes.get(following, ord(following)))
            index += 2
            continue
        raw.extend(char.encode("utf-8"))
        index += 1
    return raw.decode("utf-8", errors="replace")


def parse_diff(diff: str) -> Dict[str, Set[int]]:
    """New line numbers added or changed per file, from ``git diff --unified=0`` output."""
    changed: Dict[str, Set[int]] = {}
    current: Optional[str] = None
    for line in diff.splitlines():
        if line.startswith("diff --git "):
            current = None
        elif line.startswith("+++ "):
            target = unquote_path(line[4:].rstrip("\t"))
            current = None if target == "/dev/null" else (target[2:] if target.startswith("b/") else target)
        elif current is not None:
            match = HUNK_RE.match(line)
            if match:
                start = int(match.group(1))
                count = 1 if match.group(2) is None else int(match.group(2))
                if count:
                    changed.setdefault(current, set()).update(range(start, start + count))
    return changed


def line_count(path: Path) -> int:
    try:
        data = path.read_bytes()
    except OSError:
        return 0
    if not data:
        return 0
    return data.count(b"\n") + (0 if data.endswith(b"\n") else 1)


def changed_lines(root: Path, base: str) -> Dict[str, Set[int]]:
    diff = git(
        root,
        "diff",
        "--unified=0",
        "--no-color",
        "--no-ext-diff",
        "--no-textconv",
        "-M",
        "--src-prefix=a/",
        "--dst-prefix=b/",
        base,
        "--",
    )
    if diff is None:
        raise GateError(f"git diff against {base} failed.")
    changed = parse_diff(diff)
    untracked = git(root, "ls-files", "--others", "--exclude-standard", "-z")
    for path in (untracked or "").split("\0"):
        if path:
            count = line_count(root / path)
            if count:
                changed[path] = set(range(1, count + 1))
    return changed


# --- report paths -------------------------------------------------------------------------------


def _clean(path: str) -> str:
    return path.replace("\\", "/")


def _relative_to_root(path: str, root: Path) -> Optional[str]:
    """A report path as a repository-relative POSIX path, or None when it is outside the repository."""
    text = _clean(path)
    if text.startswith("/") or WINDOWS_ABSOLUTE_RE.match(text):
        absolute = os.path.realpath(text) if os.path.exists(text) else text
        root_text = _clean(os.path.realpath(str(root))).rstrip("/")
        absolute = _clean(absolute)
        if absolute.casefold().startswith(root_text.casefold() + "/"):
            return absolute[len(root_text) + 1 :]
        return None
    parts: List[str] = []
    for part in PurePosixPath(text).parts:
        if part == "..":
            if not parts:
                return None
            parts.pop()
        elif part not in ("", "."):
            parts.append(part)
    return "/".join(parts) or None


class PathResolver:
    """Maps the file names of a report onto the changed files of the repository."""

    def __init__(self, root: Path, changed: Iterable[str]) -> None:
        self.root = root
        self.changed = sorted(changed)
        self.folded = {path.casefold(): path for path in self.changed}

    def _match(self, candidate: Optional[str]) -> Optional[str]:
        if not candidate:
            return None
        if candidate in self.changed:
            return candidate
        return self.folded.get(candidate.casefold())

    def resolve(self, name: str, project_root: Optional[str] = None) -> Optional[str]:
        text = _clean(name)
        candidates = [text]
        if project_root and not (text.startswith("/") or WINDOWS_ABSOLUTE_RE.match(text)):
            candidates.insert(0, _clean(project_root).rstrip("/") + "/" + text)
        for candidate in candidates:
            found = self._match(_relative_to_root(candidate, self.root))
            if found:
                return found
        while text.startswith("./"):
            text = text[2:]
        for fold in (False, True):
            name = text.casefold() if fold else text
            paths = [(path.casefold() if fold else path, path) for path in self.changed]
            # A longer report path that ends with a changed path (an absolute path under another spelling of the
            # repository folder, such as a Windows short name): the most specific changed path wins.
            longer = [path for key, path in paths if name == key or name.endswith("/" + key)]
            if longer:
                best = max(len(path) for path in longer)
                most_specific = [path for path in longer if len(path) == best]
                if len(most_specific) == 1:
                    return most_specific[0]
            # A shorter report path, relative to a sub-folder: it must match exactly one changed path.
            shorter = [path for key, path in paths if key.endswith("/" + name)]
            if len(shorter) == 1:
                return shorter[0]
        return None


# --- reports ------------------------------------------------------------------------------------


def read_report(path: Path) -> Tuple[str, Any]:
    try:
        text = path.read_bytes().decode("utf-8-sig", errors="replace")
    except OSError as exc:
        raise GateError(f"cannot read the report {path}: {exc}") from exc
    stripped = text.lstrip()
    if stripped.startswith("{"):
        try:
            return ELEMENTS, json.loads(text)
        except ValueError as exc:
            raise GateError(f"cannot read the report {path} as JSON: {exc}") from exc
    if stripped.startswith("<"):
        try:
            return PITEST, ElementTree.fromstring(text)
        except ElementTree.ParseError as exc:
            raise GateError(f"cannot read the report {path} as XML: {exc}") from exc
    raise GateError(
        f"unknown report format for {path}: expected a mutation-testing-elements JSON report or a PIT mutations.xml."
    )


def _position(location: Any, key: str) -> Tuple[int, int]:
    point = location.get(key) if isinstance(location, dict) else None
    if not isinstance(point, dict):
        return 0, 0
    try:
        return int(point.get("line", 0)), int(point.get("column", 0))
    except (TypeError, ValueError):
        return 0, 0


def elements_mutants(
    report: Any, resolver: PathResolver, warnings: List[str]
) -> Tuple[List[Mutant], Dict[str, str], Set[str]]:
    """Mutants of a mutation-testing-elements report, the source of each changed file and all report files."""
    files = report.get("files") if isinstance(report, dict) else None
    if not isinstance(files, dict):
        raise GateError("not a mutation-testing-elements report: 'files' must be an object.")
    project_root = report.get("projectRoot") if isinstance(report.get("projectRoot"), str) else None
    mutants: List[Mutant] = []
    sources: Dict[str, str] = {}
    names: Set[str] = set()
    unknown: Set[str] = set()
    for name, entry in files.items():
        names.add(_clean(name))
        if not isinstance(entry, dict):
            continue
        resolved = resolver.resolve(name, project_root)
        label = resolved or _clean(name)
        if resolved and isinstance(entry.get("source"), str):
            sources[resolved] = entry["source"]
        for item in entry.get("mutants") or []:
            if not isinstance(item, dict):
                continue
            status = str(item.get("status", ""))
            kind = ELEMENTS_STATUS.get(status)
            if kind is None:
                unknown.add(status)
                kind = "invalid"
            start, _ = _position(item.get("location"), "start")
            end, end_column = _position(item.get("location"), "end")
            if end > start and end_column <= 1:
                end -= 1  # the end position is exclusive
            mutants.append(
                Mutant(
                    file=label if resolved else "",
                    start=start,
                    end=max(start, end),
                    kind=kind,
                    status=status,
                    mutator=str(item.get("mutatorName", "")),
                    replacement=str(item.get("replacement", "") or ""),
                    reason=str(item.get("statusReason", "") or "") if kind == "ignored" else "",
                )
            )
    if unknown:
        warnings.append(f"unknown mutant statuses counted as invalid: {', '.join(sorted(unknown))}.")
    return mutants, sources, names


def _child_text(element: Any, tag: str) -> str:
    child = element.find(tag)
    return (child.text or "").strip() if child is not None else ""


def pit_mutants(root_element: Any, resolver: PathResolver, warnings: List[str]) -> Tuple[List[Mutant], Set[str]]:
    if root_element.tag != "mutations":
        raise GateError(f"not a PIT mutations.xml report: the root element is <{root_element.tag}>.")
    mutants: List[Mutant] = []
    names: Set[str] = set()
    unknown: Set[str] = set()
    for element in root_element.iter("mutation"):
        mutated_class = _child_text(element, "mutatedClass").split("$", 1)[0]
        source_file = _child_text(element, "sourceFile")
        package = mutated_class.rsplit(".", 1)[0].replace(".", "/") if "." in mutated_class else ""
        name = f"{package}/{source_file}" if package else source_file
        names.add(name)
        status_text = (element.get("status") or "").upper()
        mapped = PIT_STATUS.get(status_text)
        if mapped is None:
            unknown.add(status_text)
            detected = (element.get("detected") or "").lower() == "true"
            mapped = ("killed", "Killed") if detected else ("survived", "Survived")
        try:
            line = int(_child_text(element, "lineNumber"))
        except ValueError:
            line = 0
        resolved = resolver.resolve(name)
        mutants.append(
            Mutant(
                file=resolved or "",
                start=line,
                end=line,
                kind=mapped[0],
                status=mapped[1],
                mutator=_child_text(element, "mutator").rsplit(".", 1)[-1],
                replacement=_child_text(element, "description"),
            )
        )
    if unknown:
        warnings.append(f"unknown PIT statuses mapped from the 'detected' attribute: {', '.join(sorted(unknown))}.")
    return mutants, names


# --- evaluation ---------------------------------------------------------------------------------


def normalize_source(text: str) -> str:
    return text.lstrip("﻿").replace("\r\n", "\n").replace("\r", "\n")


def stale_files(root: Path, sources: Dict[str, str]) -> List[str]:
    stale = []
    for path, source in sorted(sources.items()):
        try:
            current = (root / path).read_bytes().decode("utf-8-sig", errors="replace")
        except OSError:
            continue
        if normalize_source(current) != normalize_source(source):
            stale.append(path)
    return stale


def score(detected: int, valid: int) -> Optional[float]:
    return round(100.0 * detected / valid, 1) if valid else None


def _extension(path: str) -> str:
    return PurePosixPath(path).suffix.lower()


def evaluate(root: Path, report_path: Path, base: str, threshold: float) -> Tuple[int, Dict[str, Any]]:
    head = git(root, "rev-parse", "--verify", "--quiet", "HEAD^{commit}")
    resolved_base = git(root, "rev-parse", "--verify", "--quiet", f"{base}^{{commit}}")
    if not head or not resolved_base:
        raise GateError(f"'{base}' is not a commit of this repository.")
    merge_base = (git(root, "merge-base", "HEAD", resolved_base.strip()) or resolved_base).strip()
    changed = changed_lines(root, merge_base)
    resolver = PathResolver(root, changed)
    warnings: List[str] = []
    report_format, data = read_report(report_path)
    sources: Dict[str, str] = {}
    if report_format == ELEMENTS:
        mutants, sources, names = elements_mutants(data, resolver, warnings)
    else:
        mutants, names = pit_mutants(data, resolver, warnings)

    counts = {key: 0 for key in COUNT_KEYS}
    outside = {"mutants": 0, "detected": 0}
    survivors: List[Dict[str, Any]] = []
    ignored: List[Dict[str, Any]] = []
    mutated_files: Set[str] = set()
    for item in mutants:
        if item.file:
            mutated_files.add(item.file)
        lines = changed.get(item.file, set()) if item.file else set()
        on_changed = any(line in lines for line in range(item.start, item.end + 1))
        if not on_changed:
            if item.kind in ("killed", "timeout", "survived", "no_coverage"):
                outside["mutants"] += 1
                outside["detected"] += item.kind in ("killed", "timeout")
            continue
        counts[item.kind] += 1
        if item.kind in ("survived", "no_coverage"):
            survivors.append(
                {
                    "file": item.file,
                    "line": item.start,
                    "status": item.status,
                    "mutator": item.mutator,
                    "replacement": item.replacement,
                }
            )
        elif item.kind == "ignored":
            ignored.append({"file": item.file, "line": item.start, "mutator": item.mutator, "reason": item.reason})
    survivors.sort(key=lambda entry: (entry["file"], entry["line"], entry["mutator"]))
    ignored.sort(key=lambda entry: (entry["file"], entry["line"], entry["mutator"]))
    detected = counts["killed"] + counts["timeout"]
    valid = detected + counts["survived"] + counts["no_coverage"]
    counts.update(detected=detected, valid=valid)

    languages = {_extension(name) for name in names} - {""}
    not_in_report = [
        path
        for path in sorted(changed)
        if _extension(path) in languages and not is_test_path(path) and path not in mutated_files
    ]
    stale = stale_files(root, sources)
    value = score(detected, valid)
    passed = (value is None or detected * 100 >= threshold * valid) and not counts["pending"]
    if counts["pending"]:
        warnings.append(f"{counts['pending']} mutants on the changed lines were not run (Pending): rerun the tool.")

    result: Dict[str, Any] = {
        "ok": True,
        "passed": passed,
        "format": report_format,
        "report": str(report_path),
        "base": merge_base,
        "threshold": threshold,
        "score": value,
        "changed": {
            "files": sorted(path for path, lines in changed.items() if lines),
            "lines": sum(map(len, changed.values())),
        },
        "counts": counts,
        "survivors": survivors,
        "ignored": ignored,
        "outside_changes": {**outside, "score": score(outside["detected"], outside["mutants"])},
        "not_in_report": not_in_report,
        "stale": stale,
        "warnings": warnings,
    }
    if stale:
        result.update(
            ok=False,
            passed=False,
            error=f"the report is older than the code of {', '.join(stale)}: rerun the mutation testing tool.",
        )
        result["summary"] = result["error"]
        return EXIT_ERROR, result
    result["summary"] = summarize(result)
    return (EXIT_PASSED if passed else EXIT_FAILED), result


def summarize(result: Dict[str, Any]) -> str:
    counts = result["counts"]
    threshold = f"{result['threshold']:g}%"
    if result["score"] is None:
        text = f"No mutant on the changed lines (threshold {threshold})."
    else:
        verdict = "passed" if result["passed"] else "below the threshold"
        text = (
            f"Mutation score on the changed lines: {result['score']:.1f}% ({counts['detected']} of {counts['valid']} "
            f"mutants detected), threshold {threshold}: {verdict}."
        )
    if counts["pending"]:
        text += f" {counts['pending']} mutants not run."
    if result["survivors"]:
        shown = [
            f"{item['file']}:{item['line']} {item['mutator']}"
            + (f" ({item['replacement']})" if item["replacement"] else "")
            for item in result["survivors"][:10]
        ]
        more = len(result["survivors"]) - len(shown)
        text += " Surviving: " + "; ".join(shown) + (f"; and {more} more" if more > 0 else "") + "."
    if result["ignored"]:
        text += f" {len(result['ignored'])} ignored in the code: check each reason."
    if result["not_in_report"]:
        text += " Changed files without mutants in the report: " + ", ".join(result["not_in_report"]) + "."
    return text


def print_json(data: Any) -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    sys.stdout.write(json.dumps(data, indent=2, ensure_ascii=False) + "\n")


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Mutation score of the changed lines (mutation-testing skill).")
    parser.add_argument("--repo", default=".", help="Path inside the git repository (default: current directory).")
    parser.add_argument("--report", required=True, help="mutation-testing-elements JSON report or PIT mutations.xml.")
    parser.add_argument(
        "--base",
        required=True,
        help="Changes are counted from the merge base of HEAD and this commit: HEAD for a lot before its commit, "
        "the merge base of the work branch for a review.",
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=DEFAULT_THRESHOLD,
        help=f"Minimum mutation score of the changed lines, in percent (default: {DEFAULT_THRESHOLD:g}).",
    )
    args = parser.parse_args(argv)
    if not 0 <= args.threshold <= 100:
        print_json(
            {"ok": False, "passed": False, "error": f"--threshold {args.threshold:g} must be between 0 and 100."}
        )
        return EXIT_ERROR
    root_text = git(Path(args.repo), "rev-parse", "--show-toplevel") if Path(args.repo).is_dir() else None
    if not root_text:
        print_json({"ok": False, "passed": False, "error": f"'{args.repo}' is not inside a git repository."})
        return EXIT_ERROR
    root = Path(root_text.strip())
    report = Path(args.report)
    if not report.is_absolute():
        report = Path.cwd() / report
    try:
        code, result = evaluate(root, report, args.base, args.threshold)
    except GateError as exc:
        print_json({"ok": False, "passed": False, "error": str(exc)})
        return EXIT_ERROR
    print_json(result)
    return code


if __name__ == "__main__":
    sys.exit(main())
