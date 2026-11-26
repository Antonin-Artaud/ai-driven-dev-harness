import json
import subprocess
import sys
import unittest
from pathlib import Path

from support import ONBOARD, TempGitRepo, load_module

onboard = load_module("onboard", ONBOARD)

ADO_REMOTE = "https://contoso@dev.azure.com/contoso/Credit%20Scoring/_git/acme-bank"


class RemoteParsingTestCase(unittest.TestCase):
    def test_supported_remote_formats(self) -> None:
        expected = {"organization": "contoso", "project": "Credit Scoring", "repository": "acme-bank"}
        for url in (
            "https://dev.azure.com/contoso/Credit%20Scoring/_git/acme-bank",
            "https://contoso@dev.azure.com/contoso/Credit%20Scoring/_git/acme-bank",
            "https://user:s3cret@dev.azure.com/contoso/Credit%20Scoring/_git/acme-bank/",
            "git@ssh.dev.azure.com:v3/contoso/Credit%20Scoring/acme-bank",
            "ssh://git@ssh.dev.azure.com:22/v3/contoso/Credit%20Scoring/acme-bank",
            "https://contoso.visualstudio.com/Credit%20Scoring/_git/acme-bank",
            "https://contoso.visualstudio.com/DefaultCollection/Credit%20Scoring/_git/acme-bank",
            "contoso@vs-ssh.visualstudio.com:v3/contoso/Credit%20Scoring/acme-bank",
        ):
            with self.subTest(url=url):
                self.assertEqual(onboard.parse_ado_remote(url), expected)

    def test_project_defaults_to_repository_name(self) -> None:
        self.assertEqual(
            onboard.parse_ado_remote("https://dev.azure.com/contoso/_git/acme-bank"),
            {"organization": "contoso", "project": "acme-bank", "repository": "acme-bank"},
        )

    def test_azure_devops_server_urls(self) -> None:
        expected = {
            "server": "tfs.contoso.local",
            "collection": "DefaultCollection",
            "project": "Credit",
            "repository": "acme-bank",
        }
        for url in (
            "https://tfs.contoso.local/tfs/DefaultCollection/Credit/_git/acme-bank",
            "https://tfs.contoso.local/DefaultCollection/Credit/_git/acme-bank",
            "ssh://tfs.contoso.local:22/tfs/DefaultCollection/Credit/_git/acme-bank",
        ):
            with self.subTest(url=url):
                self.assertEqual(onboard.parse_ado_server_remote(url), expected)
        self.assertIsNone(onboard.parse_ado_server_remote("https://dev.azure.com/contoso/Credit/_git/acme-bank"))
        self.assertIsNone(onboard.parse_ado_server_remote("https://github.com/contoso/acme-bank.git"))

    def test_non_azure_remotes_are_ignored(self) -> None:
        for url in ("https://github.com/contoso/acme-bank.git", "git@github.com:contoso/acme-bank.git", ""):
            with self.subTest(url=url):
                self.assertIsNone(onboard.parse_ado_remote(url))

    def test_credentials_are_redacted(self) -> None:
        self.assertEqual(
            onboard.redact_remote("https://user:s3cret@dev.azure.com/contoso/p/_git/r"),
            "https://dev.azure.com/contoso/p/_git/r",
        )
        self.assertEqual(onboard.redact_remote("git@ssh.dev.azure.com:v3/o/p/r"), "git@ssh.dev.azure.com:v3/o/p/r")

    def test_strip_jsonc(self) -> None:
        text = '{\n  // comment\n  "a": "http://x//y", /* block */\n  "b": [1, 2,],\n}\n'
        cleaned, had_comments = onboard.strip_jsonc(text)
        self.assertTrue(had_comments)
        self.assertEqual(json.loads(cleaned), {"a": "http://x//y", "b": [1, 2]})


class OnboardScriptTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.repo = TempGitRepo(with_origin=False)
        self.repo.git("remote", "add", "origin", ADO_REMOTE)
        self.mcp = self.repo.path / ".vscode" / "mcp.json"

    def tearDown(self) -> None:
        self.repo.cleanup()

    def run_onboard(self, *args: str, cwd: Path = None):
        proc = subprocess.run(
            [sys.executable, str(ONBOARD), "--repo", str(cwd or self.repo.path), *args],
            capture_output=True,
            env=self.repo.env,
            timeout=60,
        )
        return proc.returncode, json.loads(proc.stdout.decode("utf-8"))

    def exclude_lines(self):
        return (self.repo.path / ".git" / "info" / "exclude").read_text(encoding="utf-8").splitlines()

    def test_first_run_creates_config_and_excludes(self) -> None:
        code, summary = self.run_onboard()
        self.assertEqual(code, 0)
        self.assertEqual(summary["azure_devops"]["project"], "Credit Scoring")
        self.assertEqual(summary["remote"], "https://dev.azure.com/contoso/Credit%20Scoring/_git/acme-bank")
        self.assertEqual(summary["base_branch"], {"name": "main", "source": "local main"})
        self.assertEqual(summary["mcp_json"]["action"], "created")
        config = json.loads(self.mcp.read_text(encoding="utf-8"))
        read, write = config["servers"]["ado-read"], config["servers"]["ado-write"]
        self.assertEqual(read["url"], "https://mcp.dev.azure.com/contoso")
        self.assertEqual(read["headers"], {"X-MCP-Readonly": "true", "X-MCP-Toolsets": "repos,wit,wiki"})
        self.assertEqual(write["headers"], {"X-MCP-Tools": "repo_pull_request_write, repo_pull_request_thread_write"})
        self.assertEqual(summary["git_exclude"]["added"], [".ai/", ".vscode/mcp.json"])
        self.assertIn(".ai/", self.exclude_lines())

        code, again = self.run_onboard()
        self.assertEqual(again["mcp_json"]["action"], "unchanged")
        self.assertEqual(again["git_exclude"]["added"], [])
        self.assertEqual(self.exclude_lines().count(".ai/"), 1)

    def test_dry_run_writes_nothing(self) -> None:
        code, summary = self.run_onboard("--dry-run", "--base-branch", "develop")
        self.assertEqual(code, 0)
        self.assertTrue(summary["dry_run"])
        self.assertEqual(summary["base_branch"], {"name": "develop", "source": "argument"})
        self.assertFalse(self.mcp.exists())
        self.assertNotIn(".ai/", self.exclude_lines())

    def test_merge_keeps_other_servers(self) -> None:
        self.repo.write(".vscode/mcp.json", json.dumps({"servers": {"other": {"type": "stdio", "command": "x"}}}))
        code, summary = self.run_onboard()
        self.assertEqual(summary["mcp_json"]["action"], "merged")
        servers = json.loads(self.mcp.read_text(encoding="utf-8"))["servers"]
        self.assertEqual(sorted(servers), ["ado-read", "ado-write", "other"])
        self.assertEqual(summary["git_exclude"]["added"], [".ai/"])

    def test_commented_config_is_left_untouched(self) -> None:
        original = '{\n  // team servers\n  "servers": {}\n}\n'
        self.repo.write(".vscode/mcp.json", original)
        code, summary = self.run_onboard()
        self.assertEqual(summary["mcp_json"]["action"], "manual")
        self.assertIn("ado-read", summary["mcp_json"]["snippet"]["servers"])
        self.assertEqual(self.mcp.read_text(encoding="utf-8"), original)

    def test_conflicts_require_force(self) -> None:
        servers = {"servers": {"ado-read": {"type": "http", "url": "https://mcp.dev.azure.com/other"}}}
        self.repo.write(".vscode/mcp.json", json.dumps(servers))
        code, summary = self.run_onboard()
        self.assertEqual((code, summary["ok"]), (onboard.EXIT_CONFLICT, False))
        self.assertEqual(summary["mcp_json"]["action"], "merged")
        self.assertEqual(summary["mcp_json"]["conflicts"], ["ado-read"])
        self.assertEqual(summary["mcp_json"]["added"], ["ado-write"])
        code, summary = self.run_onboard()
        self.assertEqual((code, summary["ok"]), (onboard.EXIT_CONFLICT, False))
        self.assertEqual(summary["mcp_json"]["action"], "conflict")
        code, summary = self.run_onboard("--force")
        self.assertEqual((code, summary["ok"]), (0, True))
        self.assertEqual(summary["mcp_json"]["action"], "merged")
        self.assertEqual(summary["mcp_json"]["replaced"], ["ado-read"])
        url = json.loads(self.mcp.read_text(encoding="utf-8"))["servers"]["ado-read"]["url"]
        self.assertEqual(url, "https://mcp.dev.azure.com/contoso")

    def test_non_azure_remote_only_excludes_workflow_folder(self) -> None:
        self.repo.git("remote", "set-url", "origin", "https://github.com/contoso/acme-bank.git")
        code, summary = self.run_onboard()
        self.assertEqual(code, 0)
        self.assertIsNone(summary["mcp_json"])
        self.assertTrue(summary["warnings"])
        self.assertFalse(self.mcp.exists())
        self.assertEqual(summary["git_exclude"]["added"], [".ai/"])

    def test_docs_skeleton_is_created_once(self) -> None:
        docs = self.repo.path / "docs" / "architecture"
        code, summary = self.run_onboard("--docs")
        self.assertEqual(code, 0)
        self.assertEqual(summary["architecture_docs"]["action"], "created")
        self.assertEqual(
            summary["architecture_docs"]["created"],
            ["docs/architecture/README.md", "docs/architecture/decisions/README.md"],
        )
        readme = (docs / "README.md").read_text(encoding="utf-8")
        self.assertIn("# Architecture map", readme)
        self.assertNotIn("<YYYY-MM-DD>", readme)
        self.assertTrue((docs / "decisions" / "README.md").is_file())
        self.assertTrue(any("architecture-mapping" in step for step in summary["next_steps"]))

        code, again = self.run_onboard("--docs")
        self.assertEqual(again["architecture_docs"]["action"], "unchanged")
        self.assertEqual(len(again["architecture_docs"]["existing"]), 2)

    def test_docs_existing_files_are_kept(self) -> None:
        self.repo.write("docs/architecture/README.md", "# Team map\n")
        code, summary = self.run_onboard("--docs")
        self.assertEqual(summary["architecture_docs"]["existing"], ["docs/architecture/README.md"])
        self.assertEqual(summary["architecture_docs"]["created"], ["docs/architecture/decisions/README.md"])
        text = (self.repo.path / "docs" / "architecture" / "README.md").read_text(encoding="utf-8")
        self.assertEqual(text, "# Team map\n")

    def test_docs_custom_path_and_dry_run(self) -> None:
        code, summary = self.run_onboard("--dry-run", "--docs-path", "./documentation\\archi/")
        self.assertEqual(code, 0)
        self.assertEqual(summary["architecture_docs"]["path"], "documentation/archi")
        self.assertEqual(summary["architecture_docs"]["action"], "created")
        self.assertFalse((self.repo.path / "documentation").exists())

    def test_docs_path_must_stay_in_the_repository(self) -> None:
        for path in ("../outside", "/tmp/docs", "C:/docs", "docs/../../x"):
            with self.subTest(path=path):
                code, summary = self.run_onboard("--docs-path", path)
                self.assertEqual(code, 1)
                self.assertFalse(summary["ok"])

    def test_docs_are_not_created_by_default(self) -> None:
        code, summary = self.run_onboard()
        self.assertIsNone(summary["architecture_docs"])
        self.assertFalse((self.repo.path / "docs").exists())

    def test_exclude_file_in_another_encoding(self) -> None:
        exclude = self.repo.path / ".git" / "info" / "exclude"
        exclude.write_bytes(b"# caf\xe9 notes\r\n*.log\r\n")
        code, summary = self.run_onboard()
        self.assertEqual(code, 0)
        self.assertEqual(summary["git_exclude"]["added"], [".ai/", ".vscode/mcp.json"])
        data = exclude.read_bytes()
        self.assertIn(b"\n.ai/\n", data)
        self.assertIn(b"*.log", data)

    def test_written_files_use_lf(self) -> None:
        self.run_onboard("--docs")
        for path in (self.mcp, self.repo.path / "docs" / "architecture" / "README.md"):
            with self.subTest(path=path.name):
                self.assertNotIn(b"\r\n", path.read_bytes())

    def test_missing_repo_folder(self) -> None:
        code, summary = self.run_onboard(cwd=self.repo.base / "nope")
        self.assertEqual(code, 1)
        self.assertIn("does not exist", summary["error"])

    def test_azure_devops_server_is_reported(self) -> None:
        self.repo.git(
            "remote", "set-url", "origin", "https://tfs.contoso.local/tfs/DefaultCollection/Credit/_git/acme-bank"
        )
        code, summary = self.run_onboard()
        self.assertEqual(code, 0)
        self.assertIsNone(summary["mcp_json"])
        self.assertEqual(summary["azure_devops_server"]["collection"], "DefaultCollection")
        self.assertTrue(any("Azure DevOps Server" in warning for warning in summary["warnings"]))

    def test_dotnet_project_gets_the_docs_server(self) -> None:
        self.repo.write("src/App/App.csproj", "<Project />\n")
        code, summary = self.run_onboard()
        self.assertEqual(code, 0)
        self.assertTrue(summary["dotnet"]["detected"])
        servers = json.loads(self.mcp.read_text(encoding="utf-8"))["servers"]
        self.assertEqual(servers["ms-learn"], {"type": "http", "url": "https://learn.microsoft.com/api/mcp"})
        self.assertEqual(sorted(servers), ["ado-read", "ado-write", "ms-learn"])
        code, again = self.run_onboard()
        self.assertEqual(again["mcp_json"]["action"], "unchanged")

    def test_dotnet_detection_markers(self) -> None:
        for marker in ("App.sln", "App.slnx", "global.json", "lib/Lib.fsproj"):
            with self.subTest(marker=marker):
                repo = TempGitRepo(with_origin=False)
                try:
                    repo.write(marker, "{}\n")
                    self.assertTrue(onboard.detect_dotnet(repo.path, False)["detected"])
                finally:
                    repo.cleanup()
        self.assertFalse(onboard.detect_dotnet(self.repo.path, False)["detected"])
        self.assertTrue(onboard.detect_dotnet(self.repo.path, True)["detected"], "--dotnet forces it")

    def test_non_dotnet_project_has_no_docs_server(self) -> None:
        self.run_onboard()
        self.assertNotIn("ms-learn", json.loads(self.mcp.read_text(encoding="utf-8"))["servers"])

    def test_docs_server_without_azure_devops(self) -> None:
        self.repo.git("remote", "set-url", "origin", "https://github.com/contoso/acme-bank.git")
        code, summary = self.run_onboard("--dotnet")
        self.assertEqual(code, 0)
        self.assertEqual(sorted(json.loads(self.mcp.read_text(encoding="utf-8"))["servers"]), ["ms-learn"])

    def test_mutation_tools_are_detected_and_their_output_excluded(self) -> None:
        self.repo.write("src/App/App.csproj", "<Project />\n")
        self.repo.commit_file("web/package.json", "{}\n", "chore: web")
        code, summary = self.run_onboard()
        self.assertEqual(code, 0)
        tools = summary["mutation_testing"]["tools"]
        self.assertEqual([tool["tool"] for tool in tools], ["stryker-net", "stryker-js"])
        self.assertEqual(tools[0]["source"], "src/App/App.csproj")
        self.assertEqual(tools[1]["source"], "web/package.json")
        for entry in ("StrykerOutput/", ".stryker-tmp/", "reports/mutation/", "reports/stryker-incremental.json"):
            self.assertIn(entry, self.exclude_lines())
        self.assertIn("StrykerOutput/", summary["git_exclude"]["added"])
        self.assertTrue(any("Mutation testing" in step for step in summary["next_steps"]))
        code, again = self.run_onboard()
        self.assertEqual(again["git_exclude"]["added"], [])

    def test_mutation_tool_override_dry_run_and_none(self) -> None:
        self.repo.write("pyproject.toml", "[project]\nname = 'demo'\n")
        code, summary = self.run_onboard("--dry-run")
        self.assertEqual([tool["tool"] for tool in summary["mutation_testing"]["tools"]], ["mutmut"])
        self.assertIn("mutants/", summary["git_exclude"]["added"])
        self.assertNotIn("mutants/", self.exclude_lines())
        code, summary = self.run_onboard("--mutation-tool", "none")
        self.assertEqual(summary["mutation_testing"], {"tools": [], "exclude": []})
        self.assertNotIn("mutants/", self.exclude_lines())
        self.assertTrue(any("off" in step for step in summary["next_steps"] if "Mutation testing" in step))
        code, summary = self.run_onboard("--mutation-tool", "pitest", "--mutation-tool", "cargo-mutants")
        self.assertEqual(code, 0)
        self.assertEqual(
            summary["mutation_testing"]["tools"],
            [
                {"tool": "pitest", "stack": "JVM (Java)", "source": "--mutation-tool"},
                {"tool": "cargo-mutants", "stack": "Rust", "source": "--mutation-tool"},
            ],
        )
        for entry in ("target/pit-reports/", "build/reports/pitest/", "mutants.out/", "mutants.out.old/"):
            self.assertIn(entry, self.exclude_lines())

    def test_mutation_tools_follow_the_mutation_testing_skill(self) -> None:
        tools = (ONBOARD.parents[2] / "mutation-testing" / "references" / "tools.md").read_text(encoding="utf-8")
        for name, spec in onboard.MUTATION_TOOLS.items():
            with self.subTest(tool=name):
                self.assertIn(f"`{name}`", tools)
                for entry in spec["exclude"]:
                    self.assertIn(f"`{entry}`", tools)

    def test_not_a_git_repository(self) -> None:
        folder = self.repo.base / "plain"
        folder.mkdir()
        code, summary = self.run_onboard(cwd=folder)
        self.assertEqual(code, 1)
        self.assertFalse(summary["ok"])


if __name__ == "__main__":
    unittest.main()
