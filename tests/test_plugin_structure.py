import json
import re
import unittest

from support import PLUGIN_ROOT, parse_frontmatter

SKILLS_DIR = PLUGIN_ROOT / "skills"
AGENTS_DIR = PLUGIN_ROOT / "com.github.copilot" / "agents"
HOOKS_FILE = PLUGIN_ROOT / "com.github.copilot" / "hooks" / "hooks.json"
KNOWN_HOOK_EVENTS = {
    "SessionStart",
    "SessionEnd",
    "UserPromptSubmit",
    "PreToolUse",
    "PostToolUse",
    "PreCompact",
    "SubagentStart",
    "SubagentStop",
    "Stop",
}
TOOL_ALIASES = {"read", "edit", "search", "execute", "agent", "web", "todo"}
LINK_RE = re.compile(r"\]\((\./[^)\s]+)\)")


def family(model: str) -> str:
    """Model family: the first word of the display name (Claude, GPT, Gemini ...)."""
    return model.split()[0].split("-")[0].lower()


def agents():
    result = {}
    for path in sorted(AGENTS_DIR.glob("*.agent.md")):
        meta = parse_frontmatter(path.read_text(encoding="utf-8"))
        result[meta.get("name") or path.name[: -len(".agent.md")]] = (path, meta)
    return result


class ManifestTestCase(unittest.TestCase):
    def test_plugin_manifest(self) -> None:
        manifest = json.loads((PLUGIN_ROOT / "plugin.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["$schema"], "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json")
        self.assertRegex(manifest["name"], r"^[a-z0-9]+(-[a-z0-9]+)*$")
        self.assertRegex(manifest["version"], r"^\d+\.\d+\.\d+$")

    def test_hooks_reference_existing_scripts(self) -> None:
        config = json.loads(HOOKS_FILE.read_text(encoding="utf-8"))
        self.assertTrue(set(config["hooks"]) <= KNOWN_HOOK_EVENTS)
        for event, entries in config["hooks"].items():
            for entry in entries:
                self.assertEqual(entry["type"], "command")
                self.assertNotIn("timeout", entry, "use timeoutSec only (portable across harnesses)")
                self.assertFalse({"command", "windows", "linux", "osx"} & set(entry), "use bash/powershell keys")
                for key in ("bash", "powershell"):
                    match = re.search(r"\$\{PLUGIN_ROOT\}/([^\"]+)", entry[key])
                    self.assertIsNotNone(match, f"{event}.{key} must use ${{PLUGIN_ROOT}}")
                    self.assertTrue((PLUGIN_ROOT / match.group(1)).is_file(), match.group(1))
                self.assertTrue(entry["bash"].startswith("python3 "))
                self.assertTrue(entry["powershell"].startswith("python "))


class SkillsTestCase(unittest.TestCase):
    def test_skills_are_valid(self) -> None:
        folders = [path for path in SKILLS_DIR.iterdir() if path.is_dir()]
        self.assertGreaterEqual(len(folders), 9)
        for folder in folders:
            with self.subTest(skill=folder.name):
                skill_file = folder / "SKILL.md"
                text = skill_file.read_text(encoding="utf-8")
                meta = parse_frontmatter(text)
                self.assertEqual(meta["name"], folder.name)
                self.assertRegex(meta["name"], r"^[a-z0-9]+(-[a-z0-9]+)*$")
                self.assertLessEqual(len(meta["name"]), 64)
                self.assertTrue(10 < len(meta["description"]) <= 1024)
                self.assertIn("Use ", meta["description"])
                self.assertLess(len(text.splitlines()), 500)
                for link in LINK_RE.findall(text):
                    self.assertTrue((folder / link).resolve().is_file(), f"broken link {link}")

    def test_stage_skills_trigger_only_in_the_workflow(self) -> None:
        for name in ("business-challenge", "solution-design", "plan-execution", "code-review", "pr-feedback"):
            with self.subTest(skill=name):
                meta = parse_frontmatter((SKILLS_DIR / name / "SKILL.md").read_text(encoding="utf-8"))
                self.assertIs(meta.get("user-invocable"), False)
                self.assertIn("ai-driven-dev-harness", meta["description"])
        meta = parse_frontmatter((SKILLS_DIR / "architecture-mapping" / "SKILL.md").read_text(encoding="utf-8"))
        self.assertIn("docs/architecture", meta["description"])
        self.assertNotIn("Use when mapping or documenting an architecture", meta["description"])

    def test_specialist_skills(self) -> None:
        for name in ("ui-ux-design", "security-design", "performance-design"):
            with self.subTest(skill=name):
                text = (SKILLS_DIR / name / "SKILL.md").read_text(encoding="utf-8")
                self.assertIn("ai-driven-dev-harness", parse_frontmatter(text)["description"])
        for name in ("security.md", "performance.md"):
            self.assertFalse((SKILLS_DIR / "solution-design" / "references" / name).exists(), f"{name} moved")
        for agent, skill in (
            ("ui-ux-designer", "ui-ux-design"),
            ("security-architect", "security-design"),
            ("performance-architect", "performance-design"),
        ):
            text = (AGENTS_DIR / f"{agent}.agent.md").read_text(encoding="utf-8")
            self.assertIn(f"`{skill}` skill", text)
        plan = (SKILLS_DIR / "solution-design" / "assets" / "plan-template.md").read_text(encoding="utf-8")
        self.assertIn("**Kind:**", plan)
        self.assertIn("Specialists consulted", plan)
        checklist = (SKILLS_DIR / "code-review" / "references" / "baseline-checklist.md").read_text(encoding="utf-8")
        self.assertIn("## UI (UI lots only)", checklist)

    def test_dotnet_performance_rules_are_sourced(self) -> None:
        folder = SKILLS_DIR / "dotnet-performance"
        text = (folder / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("Tier A", text)
        self.assertIn("Tier B", text)
        references = sorted((folder / "references").glob("*.md"))
        self.assertGreaterEqual(len(references), 6)
        for path in references:
            rows = [
                line
                for line in path.read_text(encoding="utf-8").splitlines()
                if line.startswith("| ") and not line.startswith("| Tier") and not line.startswith("|---")
            ]
            self.assertTrue(rows, path.name)
            for row in rows:
                with self.subTest(file=path.name, row=row[:60]):
                    self.assertRegex(row, r"\| [AB] \|", "every rule has a tier")
                    self.assertIn("https://", row, "every rule has its source")
        for name in ("plan-execution", "code-review", "performance-design", "solution-design"):
            with self.subTest(skill=name):
                self.assertIn(
                    "`dotnet-performance` skill", (SKILLS_DIR / name / "SKILL.md").read_text(encoding="utf-8")
                )

    def test_untrusted_content_is_data(self) -> None:
        for name in (
            "pr-feedback",
            "business-challenge",
            "azure-devops",
            "solution-design",
            "security-design",
            "performance-design",
            "dotnet-performance",
        ):
            with self.subTest(skill=name):
                text = (SKILLS_DIR / name / "SKILL.md").read_text(encoding="utf-8")
                self.assertIn("never instructions", text)
        architect = (AGENTS_DIR / "architect.agent.md").read_text(encoding="utf-8")
        self.assertIn("cite", architect)
        self.assertIn("never instructions", architect)

    def test_referenced_skills_exist(self) -> None:
        names = {path.name for path in SKILLS_DIR.iterdir() if path.is_dir()}
        for path in list(SKILLS_DIR.rglob("*.md")) + list(AGENTS_DIR.glob("*.agent.md")):
            for name in re.findall(r"`([a-z]+(?:-[a-z]+)+)` skill", path.read_text(encoding="utf-8")):
                with self.subTest(file=path.name, skill=name):
                    self.assertIn(name, names)


class AgentsTestCase(unittest.TestCase):
    def test_agents_are_consistent(self) -> None:
        found = agents()
        self.assertEqual(
            set(found),
            {
                "challenger",
                "architect",
                "builder",
                "implementer",
                "reviewer",
                "ui-ux-designer",
                "security-architect",
                "performance-architect",
            },
        )
        for name, (path, meta) in found.items():
            with self.subTest(agent=name):
                self.assertTrue(path.name.startswith(name))
                self.assertTrue(len(meta["description"]) > 20)
                tools = meta["tools"]
                for tool in tools:
                    self.assertTrue(tool in TOOL_ALIASES or tool.endswith("/*"), tool)
                self.assertTrue(meta["model"])
                for handoff in meta.get("handoffs", []):
                    self.assertIn(handoff["agent"], found)
                    self.assertIs(handoff["send"], False)
                    self.assertTrue(handoff["label"] and handoff["prompt"])
                for subagent in meta.get("agents", []):
                    self.assertIn(subagent, found)
                    self.assertIn("agent", tools)

    def test_subagents_are_hidden_and_read_only_agents_cannot_execute(self) -> None:
        found = agents()
        for name in ("implementer", "reviewer", "ui-ux-designer"):
            self.assertIs(found[name][1].get("user-invocable"), False)
        for name in ("challenger", "architect", "security-architect", "performance-architect"):
            self.assertNotIn("execute", found[name][1]["tools"])
            self.assertNotIn("ado-write/*", found[name][1]["tools"])
        self.assertEqual(found["builder"][1]["agents"], ["implementer", "ui-ux-designer", "reviewer"])
        self.assertEqual(found["architect"][1]["agents"], ["security-architect", "performance-architect"])
        architect_text = found["architect"][0].read_text(encoding="utf-8")
        self.assertIn("`architecture-mapping` skill", architect_text)
        reviewer_models = found["reviewer"][1]["model"]
        implementer_models = found["implementer"][1]["model"]
        self.assertNotEqual(family(reviewer_models[0]), family(implementer_models[0]), "cross-family review")
        designer_models = found["ui-ux-designer"][1]["model"]
        self.assertNotEqual(family(reviewer_models[0]), family(designer_models[0]), "cross-family review of UI lots")
        self.assertEqual(designer_models, implementer_models, "the designer is a builder subagent of the same tier")
        for name in ("security-architect", "performance-architect"):
            self.assertEqual(found[name][1]["model"], found["architect"][1]["model"], f"{name}: architect tier")
            self.assertEqual(
                [tool for tool in found[name][1]["tools"] if tool not in ("web", "ms-learn/*")],
                ["read", "search", "edit", "todo", "ado-read/*"],
            )
        self.assertGreaterEqual(len({family(model) for model in reviewer_models}), 2, "a fallback from another family")

    def test_docs_mcp_tools(self) -> None:
        found = agents()
        for name in ("architect", "performance-architect", "implementer", "ui-ux-designer", "reviewer"):
            with self.subTest(agent=name):
                self.assertIn("ms-learn/*", found[name][1]["tools"])
        for name in ("performance-architect", "implementer", "ui-ux-designer", "reviewer"):
            with self.subTest(agent=name):
                self.assertIn("`dotnet-performance` skill", found[name][0].read_text(encoding="utf-8"))

    def test_handoffs_name_a_model(self) -> None:
        for name, (_path, meta) in agents().items():
            for handoff in meta.get("handoffs", []):
                with self.subTest(agent=name, handoff=handoff["label"]):
                    self.assertTrue(handoff.get("model"))


if __name__ == "__main__":
    unittest.main()
