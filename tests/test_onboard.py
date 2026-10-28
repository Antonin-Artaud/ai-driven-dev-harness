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
        self.assertEqual(summary["mcp_json"]["action"], "merged")
        self.assertEqual(summary["mcp_json"]["conflicts"], ["ado-read"])
        self.assertEqual(summary["mcp_json"]["added"], ["ado-write"])
        code, summary = self.run_onboard()
        self.assertEqual(summary["mcp_json"]["action"], "conflict")
        code, summary = self.run_onboard("--force")
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

    def test_not_a_git_repository(self) -> None:
        folder = self.repo.base / "plain"
        folder.mkdir()
        code, summary = self.run_onboard(cwd=folder)
        self.assertEqual(code, 1)
        self.assertFalse(summary["ok"])


if __name__ == "__main__":
    unittest.main()
