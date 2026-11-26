"""mutation_gate.py: mutation score of the changed lines, from a mutation-testing-elements JSON or PIT XML report."""

import json
import subprocess
import sys
import unittest
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from support import MUTATION_GATE, PRE_TOOL_USE, TempGitRepo, load_module

gate = load_module("mutation_gate", MUTATION_GATE)

PRICING_V1 = "function discount(total, member) {\n  return total;\n}\nmodule.exports = { discount };\n"
PRICING_V2 = (
    "function discount(total, member) {\n"
    "  if (total >= 100 && member) {\n"
    "    return total * 0.9;\n"
    "  }\n"
    "  return total;\n"
    "}\n"
    "module.exports = { discount };\n"
)


def mutant(
    mutant_id: str,
    status: str,
    line: int,
    end_line: Optional[int] = None,
    mutator: str = "EqualityOperator",
    replacement: str = "total > 100",
    end_column: int = 20,
    reason: Optional[str] = None,
) -> Dict[str, Any]:
    data: Dict[str, Any] = {
        "id": mutant_id,
        "mutatorName": mutator,
        "replacement": replacement,
        "status": status,
        "location": {"start": {"line": line, "column": 3}, "end": {"line": end_line or line, "column": end_column}},
    }
    if reason:
        data["statusReason"] = reason
    return data


def elements_report(files: Dict[str, Tuple[str, List[Dict[str, Any]]]], project_root: Optional[str] = None) -> str:
    report: Dict[str, Any] = {
        "schemaVersion": "1.0",
        "thresholds": {"high": 80, "low": 60},
        "files": {
            key: {"language": "javascript", "source": source, "mutants": mutants}
            for key, (source, mutants) in files.items()
        },
    }
    if project_root is not None:
        report["projectRoot"] = project_root
    return json.dumps(report, indent=2)


def pit_mutation(status: str, line: int, source: str = "Pricing.java", cls: str = "com.example.Pricing") -> str:
    detected = "true" if status in ("KILLED", "TIMED_OUT", "MEMORY_ERROR") else "false"
    return (
        f"<mutation detected='{detected}' status='{status}' numberOfTestsRun='1'><sourceFile>{source}</sourceFile>"
        f"<mutatedClass>{cls}</mutatedClass><mutatedMethod>discount</mutatedMethod>"
        f"<methodDescription>(DZ)D</methodDescription><lineNumber>{line}</lineNumber>"
        "<mutator>org.pitest.mutationtest.engine.gregor.mutators.ConditionalsBoundaryMutator</mutator>"
        "<indexes><index>6</index></indexes><blocks><block>0</block></blocks><killingTest/>"
        "<description>changed conditional boundary</description></mutation>"
    )


class GateTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.repo = TempGitRepo(with_origin=False)
        self.repo.exclude("reports/")
        self.base = self.repo.commit_file("src/pricing.js", PRICING_V1, "feat: pricing")

    def tearDown(self) -> None:
        self.repo.cleanup()

    def report(self, content: str, name: str = "reports/mutation/mutation.json") -> str:
        self.repo.write(name, content)
        return name

    def run_gate(self, report: str, *args: str, base: Optional[str] = None) -> Tuple[int, Dict[str, Any]]:
        proc = subprocess.run(
            [
                sys.executable,
                str(MUTATION_GATE),
                "--repo",
                str(self.repo.path),
                "--report",
                str(self.repo.path / report),
                "--base",
                base or self.base,
                *args,
            ],
            capture_output=True,
            env=self.repo.env,
            timeout=60,
        )
        out = proc.stdout.decode("utf-8").strip()
        self.assertTrue(out, proc.stderr.decode("utf-8", "replace"))
        return proc.returncode, json.loads(out)

    def change_pricing(self) -> None:
        self.repo.write("src/pricing.js", PRICING_V2)

    def test_scores_only_the_mutants_on_changed_lines(self) -> None:
        self.change_pricing()
        report = self.report(
            elements_report(
                {
                    "src/pricing.js": (
                        PRICING_V2,
                        [
                            mutant("1", "Killed", 2),
                            mutant("2", "Killed", 3, mutator="ArithmeticOperator", replacement="total / 0.9"),
                            mutant("3", "Killed", 2, mutator="LogicalOperator"),
                            mutant("4", "Survived", 2, replacement="total > 100"),
                            mutant("5", "Survived", 7, mutator="ObjectLiteral", replacement="{}"),
                        ],
                    )
                }
            )
        )
        code, result = self.run_gate(report, "--threshold", "70")
        self.assertEqual(code, 0, result)
        self.assertTrue(result["ok"])
        self.assertTrue(result["passed"])
        self.assertEqual(result["format"], "mutation-testing-elements")
        self.assertEqual(result["score"], 75.0)
        self.assertEqual(result["counts"]["valid"], 4)
        self.assertEqual(result["counts"]["detected"], 3)
        self.assertEqual(
            result["survivors"],
            [
                {
                    "file": "src/pricing.js",
                    "line": 2,
                    "status": "Survived",
                    "mutator": "EqualityOperator",
                    "replacement": "total > 100",
                }
            ],
        )
        self.assertEqual(result["outside_changes"], {"mutants": 1, "detected": 0, "score": 0.0})
        self.assertEqual(result["changed"]["files"], ["src/pricing.js"])
        self.assertIn("75.0%", result["summary"])
        self.assertIn("src/pricing.js:2 EqualityOperator", result["summary"])

    def test_below_the_threshold_fails_with_exit_code_2(self) -> None:
        self.change_pricing()
        report = self.report(
            elements_report({"src/pricing.js": (PRICING_V2, [mutant("1", "Killed", 2), mutant("2", "Survived", 3)])})
        )
        code, result = self.run_gate(report)
        self.assertEqual(code, 2, result)
        self.assertTrue(result["ok"])
        self.assertFalse(result["passed"])
        self.assertEqual(result["threshold"], 80.0)
        self.assertEqual(result["score"], 50.0)
        self.assertIn("below the threshold", result["summary"])

    def test_status_rules(self) -> None:
        """Timeout counts as detected, no coverage as undetected; ignored and invalid mutants leave the score."""
        self.change_pricing()
        mutants = [
            mutant("1", "Timeout", 2),
            mutant("2", "NoCoverage", 3),
            mutant("3", "CompileError", 2),
            mutant("4", "RuntimeError", 2),
            mutant("5", "Ignored", 4, reason="equivalent: the branch returns the same value"),
            mutant("6", "Killed", 3),
        ]
        report = self.report(elements_report({"src/pricing.js": (PRICING_V2, mutants)}))
        code, result = self.run_gate(report, "--threshold", "60")
        self.assertEqual(code, 0, result)
        counts = result["counts"]
        self.assertEqual((counts["detected"], counts["timeout"], counts["no_coverage"]), (2, 1, 1))
        self.assertEqual((counts["invalid"], counts["ignored"], counts["valid"]), (2, 1, 3))
        self.assertAlmostEqual(result["score"], 66.7)
        self.assertEqual([item["status"] for item in result["survivors"]], ["NoCoverage"])
        self.assertEqual(
            result["ignored"],
            [
                {
                    "file": "src/pricing.js",
                    "line": 4,
                    "mutator": "EqualityOperator",
                    "reason": "equivalent: the branch returns the same value",
                }
            ],
        )

    def test_pending_mutants_on_changed_lines_fail_the_gate(self) -> None:
        self.change_pricing()
        report = self.report(
            elements_report({"src/pricing.js": (PRICING_V2, [mutant("1", "Killed", 2), mutant("2", "Pending", 3)])})
        )
        code, result = self.run_gate(report)
        self.assertEqual(code, 2, result)
        self.assertFalse(result["passed"])
        self.assertEqual(result["counts"]["pending"], 1)
        self.assertTrue(any("not run" in warning for warning in result["warnings"]))

    def test_multi_line_mutants_and_exclusive_end(self) -> None:
        self.repo.write("src/pricing.js", PRICING_V1.replace("  return total;", "  return total + 0;"))
        mutants = [
            mutant("1", "Survived", 1, end_line=3, mutator="BlockStatement", end_column=2),
            mutant("2", "Survived", 1, end_line=2, mutator="StringLiteral", end_column=1),
        ]
        report = self.report(elements_report({"src/pricing.js": (self.read("src/pricing.js"), mutants)}))
        _code, result = self.run_gate(report)
        self.assertEqual([item["mutator"] for item in result["survivors"]], ["BlockStatement"])
        self.assertEqual(result["outside_changes"]["mutants"], 1, "ends before column 1 of line 2: line 1 only")

    def read(self, relative: str) -> str:
        return (self.repo.path / relative).read_text(encoding="utf-8")

    def test_untracked_files_are_entirely_changed(self) -> None:
        source = "export const rate = (member) => (member ? 0.9 : 1);\n"
        self.repo.write("src/rate.js", source)
        report = self.report(elements_report({"src/rate.js": (source, [mutant("1", "Survived", 1)])}))
        code, result = self.run_gate(report)
        self.assertEqual(code, 2, result)
        self.assertEqual(result["changed"]["files"], ["src/rate.js"])
        self.assertEqual(result["survivors"][0]["file"], "src/rate.js")

    def test_committed_branch_against_its_merge_base(self) -> None:
        self.repo.git("switch", "-c", "ai/demo")
        self.change_pricing()
        self.repo.git("commit", "-am", "feat: member discount")
        report = self.report(elements_report({"src/pricing.js": (PRICING_V2, [mutant("1", "Killed", 2)])}))
        code, result = self.run_gate(report, base="main")
        self.assertEqual(code, 0, result)
        self.assertEqual(result["base"], self.base)
        self.assertEqual(result["score"], 100.0)

    def test_absolute_and_windows_style_report_paths(self) -> None:
        self.change_pricing()
        absolute = str((self.repo.path / "src" / "pricing.js").resolve())
        for key, root in (
            (absolute, None),
            ("pricing.js", str((self.repo.path / "src").resolve())),
            ("src\\pricing.js", str(self.repo.path.resolve())),
            ("SRC/Pricing.js", None),
        ):
            with self.subTest(key=key):
                report = self.report(
                    elements_report({key: (PRICING_V2, [mutant("1", "Survived", 2)])}, project_root=root)
                )
                _code, result = self.run_gate(report)
                self.assertEqual(result["survivors"][0]["file"], "src/pricing.js", result)

    def test_stale_report_is_rejected(self) -> None:
        self.change_pricing()
        report = self.report(elements_report({"src/pricing.js": (PRICING_V1, [mutant("1", "Killed", 2)])}))
        code, result = self.run_gate(report)
        self.assertEqual(code, 1, result)
        self.assertFalse(result["ok"])
        self.assertEqual(result["stale"], ["src/pricing.js"])
        self.assertIn("rerun", result["error"])

    def test_line_endings_do_not_make_a_report_stale(self) -> None:
        self.change_pricing()
        crlf = PRICING_V2.replace("\n", "\r\n")
        report = self.report(elements_report({"src/pricing.js": (crlf, [mutant("1", "Killed", 2)])}))
        code, result = self.run_gate(report)
        self.assertEqual(code, 0, result)
        self.assertEqual(result["stale"], [])

    def test_changed_code_files_missing_from_the_report(self) -> None:
        self.change_pricing()
        self.repo.write("src/rate.js", "export const rate = 1;\n")
        self.repo.write("test/pricing.test.js", "test('x', () => {});\n")
        self.repo.write("README.md", "# test\nmore\n")
        report = self.report(elements_report({"src/pricing.js": (PRICING_V2, [mutant("1", "Killed", 2)])}))
        code, result = self.run_gate(report)
        self.assertEqual(code, 0, result)
        self.assertEqual(result["not_in_report"], ["src/rate.js"])
        self.assertIn("src/rate.js", result["summary"])

    def test_no_mutant_on_changed_lines(self) -> None:
        self.repo.write("src/pricing.js", PRICING_V1 + "// comment\n")
        report = self.report(
            elements_report({"src/pricing.js": (self.read("src/pricing.js"), [mutant("1", "Killed", 2)])})
        )
        code, result = self.run_gate(report)
        self.assertEqual(code, 0, result)
        self.assertTrue(result["passed"])
        self.assertIsNone(result["score"])
        self.assertIn("No mutant on the changed lines", result["summary"])

    def test_deleted_and_renamed_files(self) -> None:
        self.repo.commit_file("src/old.js", "module.exports = 1;\n", "chore: old")
        base = self.repo.head()
        self.repo.git("rm", "-q", "src/old.js")
        self.repo.git("mv", "src/pricing.js", "src/price.js")
        report = self.report(elements_report({"src/price.js": (PRICING_V1, [mutant("1", "Survived", 2)])}))
        code, result = self.run_gate(report, base=base)
        self.assertEqual(code, 0, result)
        self.assertEqual(result["changed"]["files"], [], "a pure rename changes no line")
        self.assertIsNone(result["score"])

    def test_pit_xml_report(self) -> None:
        self.repo.commit_file("src/main/java/com/example/Pricing.java", "class Pricing {\n}\n", "feat: pricing class")
        base = self.repo.head()
        self.repo.write(
            "src/main/java/com/example/Pricing.java",
            "class Pricing {\n"
            "  double discount(double t, boolean m) {\n"
            "    return t >= 100 && m ? t * 0.9 : t;\n"
            "  }\n"
            "}\n",
        )
        xml = (
            '<?xml version="1.0" encoding="UTF-8"?>\n<mutations partial="true">\n'
            + "\n".join(
                [
                    pit_mutation("KILLED", 3),
                    pit_mutation("TIMED_OUT", 3),
                    pit_mutation("MEMORY_ERROR", 3),
                    pit_mutation("SURVIVED", 3),
                    pit_mutation("NO_COVERAGE", 2),
                    pit_mutation("NON_VIABLE", 3),
                    pit_mutation("RUN_ERROR", 3),
                    pit_mutation("SURVIVED", 1),
                    pit_mutation("SURVIVED", 3, source="Other.java", cls="com.example.Other"),
                    pit_mutation("KILLED", 3, cls="com.example.Pricing$Inner"),
                ]
            )
            + "\n</mutations>\n"
        )
        report = self.report(xml, "reports/pit/mutations.xml")
        code, result = self.run_gate(report, "--threshold", "60", base=base)
        self.assertEqual(code, 0, result)
        self.assertEqual(result["format"], "pitest-xml")
        self.assertEqual(result["counts"]["detected"], 4)
        self.assertEqual(result["counts"]["valid"], 6)
        self.assertEqual(result["counts"]["invalid"], 2)
        self.assertAlmostEqual(result["score"], 66.7)
        self.assertEqual(
            [(item["file"], item["line"], item["status"]) for item in result["survivors"]],
            [
                ("src/main/java/com/example/Pricing.java", 2, "NoCoverage"),
                ("src/main/java/com/example/Pricing.java", 3, "Survived"),
            ],
        )
        self.assertEqual(result["survivors"][1]["mutator"], "ConditionalsBoundaryMutator")
        self.assertEqual(result["survivors"][1]["replacement"], "changed conditional boundary")
        self.assertEqual(result["outside_changes"]["mutants"], 2)
        self.assertEqual(result["stale"], [], "PIT reports carry no source to compare")

    def test_unusable_reports(self) -> None:
        self.change_pricing()
        for name, content, message in (
            ("reports/a.json", "{not json", "cannot read"),
            ("reports/b.json", json.dumps({"files": "x"}), "not a mutation-testing-elements"),
            ("reports/c.xml", "<coverage/>", "not a PIT"),
            ("reports/d.txt", "hello", "unknown report format"),
        ):
            with self.subTest(name=name):
                self.report(content, name)
                code, result = self.run_gate(name)
                self.assertEqual(code, 1, result)
                self.assertFalse(result["ok"])
                self.assertIn(message, result["error"])
        code, result = self.run_gate("reports/missing.json")
        self.assertEqual((code, result["ok"]), (1, False))
        report = self.report(elements_report({}))
        code, result = self.run_gate(report, base="no-such-ref")
        self.assertEqual(code, 1, result)
        self.assertIn("no-such-ref", result["error"])

    def test_threshold_must_be_a_percentage(self) -> None:
        report = self.report(elements_report({}))
        code, result = self.run_gate(report, "--threshold", "120")
        self.assertEqual(code, 1, result)
        self.assertIn("threshold", result["error"])

    def test_not_a_git_repository(self) -> None:
        folder = self.repo.base / "plain"
        folder.mkdir()
        proc = subprocess.run(
            [sys.executable, str(MUTATION_GATE), "--repo", str(folder), "--report", "x.json", "--base", "HEAD"],
            capture_output=True,
            env=self.repo.env,
            timeout=60,
        )
        self.assertEqual(proc.returncode, 1)
        self.assertIn("git repository", json.loads(proc.stdout.decode("utf-8"))["error"])


class ParsingTestCase(unittest.TestCase):
    def test_diff_hunks(self) -> None:
        diff = (
            "diff --git a/src/a.js b/src/a.js\n"
            "--- a/src/a.js\n"
            "+++ b/src/a.js\n"
            "@@ -1,0 +2,3 @@\n"
            "+x\n+y\n+z\n"
            "@@ -10 +12 @@\n"
            "-old\n+new\n"
            "@@ -20,2 +23,0 @@\n"
            "-gone\n-gone\n"
            "diff --git a/src/gone.js b/src/gone.js\n"
            "--- a/src/gone.js\n"
            "+++ /dev/null\n"
            "@@ -1 +0,0 @@\n"
            "-x\n"
            'diff --git "a/src/caf\\303\\251.js" "b/src/caf\\303\\251.js"\n'
            '--- "a/src/caf\\303\\251.js"\n'
            '+++ "b/src/caf\\303\\251.js"\n'
            "@@ -1 +1 @@\n"
            "-a\n+b\n"
        )
        self.assertEqual(gate.parse_diff(diff), {"src/a.js": {2, 3, 4, 12}, "src/café.js": {1}})

    def test_report_paths_are_matched_to_changed_files(self) -> None:
        resolver = gate.PathResolver(
            Path("/work/repo"), ["src/pricing.js", "lib/pricing.js", "pricing.js", ".github/x.js"]
        )
        cases = {
            "C:/Users/RUNNER~1/repo/src/pricing.js": "src/pricing.js",
            "/elsewhere/repo/pricing.js": "pricing.js",
            "./.github/x.js": ".github/x.js",
            "SRC\\PRICING.JS": "src/pricing.js",
            "x.js": ".github/x.js",
            "other/pricing.ts": None,
            "../outside.js": None,
        }
        for name, expected in cases.items():
            with self.subTest(name=name):
                self.assertEqual(resolver.resolve(name), expected)
        ambiguous = gate.PathResolver(Path("/work/repo"), ["src/pricing.js", "lib/pricing.js"])
        self.assertIsNone(ambiguous.resolve("pricing.js"), "two changed files end with the report name")

    def test_test_paths_match_the_commit_gate(self) -> None:
        hook = load_module("pre_tool_use_for_gate", PRE_TOOL_USE)
        for path in (
            "src/pricing.js",
            "src/pricing.test.ts",
            "tests/test_pricing.py",
            "src/Shop.Tests/PricingTests.cs",
            "src/main/java/com/example/PricingTest.java",
            "spec/pricing_spec.rb",
            "pkg/pricing_test.go",
            "src/__tests__/pricing.js",
            "src/testing_utils.py",
            "conftest.py",
        ):
            with self.subTest(path=path):
                self.assertEqual(gate.is_test_path(path), hook.is_test_path(path))


if __name__ == "__main__":
    unittest.main()
