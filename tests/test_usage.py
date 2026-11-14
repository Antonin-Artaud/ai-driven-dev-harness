"""Token usage per agent: transcript reading, attribution by the hooks, pricing and the report."""

import json
import subprocess
import sys
import unittest

from support import (
    BRANCH,
    CLOSE_WORKFLOW,
    HOOKS_DIR,
    PLUGIN_ROOT,
    SLUG,
    STOP,
    SUBAGENT,
    TempGitRepo,
    load_module,
    run_script,
)

sys.path.insert(0, str(HOOKS_DIR))  # usage.py imports workflow_gate
usage = load_module("usage", HOOKS_DIR / "usage.py")
USAGE_REPORT = PLUGIN_ROOT / "scripts" / "usage_report.py"


def anthropic_line(ident: str, model: str, fresh: int, read: int, write: int, out: int) -> dict:
    return {
        "type": "assistant",
        "message": {
            "id": ident,
            "model": model,
            "usage": {
                "input_tokens": fresh,
                "cache_read_input_tokens": read,
                "cache_creation_input_tokens": write,
                "output_tokens": out,
            },
        },
    }


def openai_line(ident: str, model: str, prompt: int, cached: int, out: int) -> dict:
    return {
        "response": {
            "id": ident,
            "model": model,
            "usage": {
                "prompt_tokens": prompt,
                "completion_tokens": out,
                "prompt_tokens_details": {"cached_tokens": cached},
            },
        }
    }


class ExtractionTestCase(unittest.TestCase):
    def test_anthropic_usage(self) -> None:
        [request] = usage.extract_requests(anthropic_line("m1", "claude-opus-5-5", 10, 200, 30, 40))
        self.assertEqual(request["id"], "m1")
        self.assertEqual(request["model"], "claude-opus-5-5")
        self.assertEqual(request["tokens"], {"input": 10, "cached_input": 200, "cache_write": 30, "output": 40})

    def test_openai_prompt_tokens_include_the_cached_ones(self) -> None:
        [request] = usage.extract_requests(openai_line("r1", "gpt-6.1-sol", 1000, 600, 50))
        self.assertEqual(request["tokens"], {"input": 400, "cached_input": 600, "cache_write": 0, "output": 50})

    def test_camel_case_usage(self) -> None:
        usage_object = {"promptTokens": 5, "outputTokens": 7}
        entry = {"requestId": "q", "result": {"modelId": "Claude Sonnet 5.5", "usage": usage_object}}
        [request] = usage.extract_requests(entry)
        self.assertEqual((request["id"], request["model"], request["tokens"]["output"]), ("q", "Claude Sonnet 5.5", 7))

    def test_lines_without_usage(self) -> None:
        self.assertEqual(usage.extract_requests({"type": "user", "message": {"content": "input_tokens"}}), [])
        self.assertEqual(usage.extract_requests({"usage": {"input_tokens": True, "output_tokens": 1}}), [])


class TranscriptReadingTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.repo = TempGitRepo(with_origin=False)
        self.transcript = self.repo.base / "transcript.jsonl"

    def tearDown(self) -> None:
        self.repo.cleanup()

    def append(self, *entries: object, partial: str = "") -> None:
        with self.transcript.open("a", encoding="utf-8") as stream:
            for entry in entries:
                stream.write(json.dumps(entry) + "\n")
            stream.write(partial)

    def test_incremental_and_deduplicated(self) -> None:
        cursor: dict = {}
        line = anthropic_line("m1", "claude-sonnet-5-5", 1, 2, 3, 4)
        self.append(line, line, partial='{"half": ')
        self.assertEqual(len(usage.read_new_requests(self.transcript, cursor)), 1, "same message id counted once")
        self.assertEqual(usage.read_new_requests(self.transcript, cursor), [], "nothing new, partial line kept")
        with self.transcript.open("a", encoding="utf-8") as stream:
            stream.write("1}\n" + json.dumps(anthropic_line("m2", "claude-sonnet-5-5", 1, 1, 1, 1)) + "\n")
        self.assertEqual([request["id"] for request in usage.read_new_requests(self.transcript, cursor)], ["m2"])

    def test_missing_transcript(self) -> None:
        self.assertEqual(usage.read_new_requests(self.repo.base / "nope.jsonl", {}), [])


class HookAttributionTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.repo = TempGitRepo()
        self.repo.git("switch", "-c", BRANCH)
        self.directory = self.repo.write_workflow(phase="build")
        self.transcript = self.repo.base / "session.jsonl"
        self.transcript.write_text("", encoding="utf-8")

    def tearDown(self) -> None:
        self.repo.cleanup()

    def append(self, *entries: dict) -> None:
        with self.transcript.open("a", encoding="utf-8") as stream:
            for entry in entries:
                stream.write(json.dumps(entry) + "\n")

    def subagent(self, event: str, name: str) -> None:
        payload = {"cwd": str(self.repo.path), "agentName": name, "transcriptPath": str(self.transcript)}
        self.assertEqual(run_script(SUBAGENT, payload, self.repo.env, args=[event]), {})

    def stop(self) -> None:
        payload = {"cwd": str(self.repo.path), "hook_event_name": "Stop", "transcript_path": str(self.transcript)}
        run_script(STOP, payload, self.repo.env)

    def usage_file(self) -> dict:
        return json.loads((self.directory / "usage.json").read_text(encoding="utf-8"))

    def test_requests_go_to_the_agent_that_ran(self) -> None:
        self.append(anthropic_line("b1", "claude-sonnet-5-5", 100, 0, 1000, 50))
        self.subagent("start", "ai-driven-dev-harness:implementer")
        self.append(anthropic_line("i1", "claude-sonnet-5-5", 10, 1000, 0, 500))
        self.append(anthropic_line("i2", "claude-sonnet-5-5", 10, 1500, 0, 700))
        self.subagent("stop", "implementer")
        self.subagent("start", "reviewer")
        self.append(openai_line("r1", "gpt-6.1-sol", 3000, 1000, 400))
        self.subagent("stop", "reviewer")
        self.append(anthropic_line("b2", "claude-sonnet-5-5", 5, 2000, 0, 80))
        self.stop()
        agents = self.usage_file()["agents"]
        self.assertEqual(agents["builder"]["requests"], 2)
        self.assertEqual(agents["builder"]["turns"], 1)
        self.assertEqual(agents["implementer"]["runs"], 1)
        self.assertEqual(agents["implementer"]["models"]["claude-sonnet-5-5"]["output"], 1200)
        self.assertEqual(agents["reviewer"]["models"]["gpt-6.1-sol"]["input"], 2000)
        self.stop()
        self.assertEqual(self.usage_file()["agents"]["builder"]["requests"], 2, "a transcript line is counted once")

    def test_agents_cannot_write_the_usage_file(self) -> None:
        self.assertIn("usage.json", usage.wg.HOOK_OWNED_FILES)
        self.assertTrue(usage.wg.mentions_protected_path(f"echo {{}} > .ai/{SLUG}/usage.json"))

    def test_close_prints_the_table(self) -> None:
        self.append(anthropic_line("b1", "Claude Opus 5.5", 1_000_000, 0, 0, 100_000))
        self.stop()
        # Windows consoles default to cp1252, which has neither U+202F nor "≥": output must stay UTF-8.
        proc = subprocess.run(
            [sys.executable, str(CLOSE_WORKFLOW), "--repo", str(self.repo.path)],
            capture_output=True,
            env={**self.repo.env, "PYTHONIOENCODING": "cp1252"},
            timeout=60,
        )
        result = json.loads(proc.stdout.decode("utf-8"))
        self.assertTrue(result["ok"], result)
        table = result["usage_table"]
        self.assertIn("| builder | Claude Opus 5.5 | 1 |", table)
        self.assertIn("**600,0**", table, "1M input at $4 + 100K output at $20 = $6 = 600 credits")
        report = subprocess.run(
            [sys.executable, str(USAGE_REPORT), "--repo", str(self.repo.path), "--slug", SLUG, "--json"],
            capture_output=True,
            env={**self.repo.env, "PYTHONIOENCODING": "cp1252"},
            timeout=60,
        )
        summary = json.loads(report.stdout.decode("utf-8"))
        self.assertAlmostEqual(summary["total"]["credits"], 600.0)


class PricingTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.pricing = usage.load_pricing()

    def test_model_names(self) -> None:
        for name, expected in (
            ("Claude Opus 5.5 (copilot)", "Claude Opus 5.5"),
            ("claude-opus-5-5", "Claude Opus 5.5"),
            ("claude-opus-5", "Claude Opus 5"),
            ("claude-opus-5-20261001", "Claude Opus 5"),
            ("copilot/gpt-6.1-sol", "GPT-6.1 Sol"),
            ("gpt-6-sol", "GPT-6 Sol"),
        ):
            with self.subTest(model=name):
                self.assertEqual(usage.find_rates(self.pricing, name)["name"], expected)
        self.assertIsNone(usage.find_rates(self.pricing, "claude-sonnet-4-5"), "never priced as another model")
        self.assertIsNone(usage.find_rates(self.pricing, "gemini-3.1-pro"))

    def test_long_context_requests(self) -> None:
        row = usage.find_rates(self.pricing, "GPT-6.1 Sol")
        for prompt, expected in ((300_000, 1.2), (200_000, 0.4)):
            with self.subTest(prompt=prompt):
                entry: dict = {}
                tokens = {"input": prompt, "cached_input": 0, "cache_write": 0, "output": 0}
                usage.add_requests(entry, [{"id": "a", "model": "gpt-6.1-sol", "tokens": tokens}])
                self.assertAlmostEqual(usage.model_cost_usd(entry["models"]["gpt-6.1-sol"], row), expected)

    def test_unknown_tokens_are_never_invented(self) -> None:
        summary = usage.summarize({"agents": {"reviewer": {"runs": 2, "duration_s": 90, "models": {}}}}, self.pricing)
        self.assertIsNone(summary["rows"][0]["credits"])
        self.assertFalse(summary["tokens_found"])
        table = usage.render_markdown(summary, "fr")
        self.assertIn("| reviewer | – | 2 | 1 min 30 s | n/d | n/d | n/d | n/d | n/d |", table)
        self.assertIn("aucun compteur de tokens", table)

    def test_unpriced_model_makes_the_total_a_minimum(self) -> None:
        tokens = {"requests": 1, "input": 1_000_000, "cached_input": 0, "cache_write": 0, "output": 0}
        agents = {
            "builder": {"models": {"claude-sonnet-5-5": tokens}},
            "reviewer": {"models": {"gemini-3.1-pro": tokens}},
        }
        summary = usage.summarize({"agents": agents}, self.pricing)
        self.assertEqual([row["agent"] for row in summary["rows"]], ["builder", "reviewer"])
        self.assertAlmostEqual(summary["total"]["credits"], 200.0)
        self.assertFalse(summary["total"]["complete"])
        self.assertIn("**≥ 200.0**", usage.render_markdown(summary, "en"))


if __name__ == "__main__":
    unittest.main()
