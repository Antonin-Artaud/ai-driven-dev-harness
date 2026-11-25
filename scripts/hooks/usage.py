"""Token usage per agent of the ai-driven-dev-harness, for the end-of-workflow cost table.

Neither VS Code nor GitHub Copilot sends token counts in the hook payloads: the hooks only get the
path of the session transcript (``transcript_path`` / ``transcriptPath``), whose format is not a
stable API. So the hooks read that transcript incrementally and attribute the new model requests
to the agent that was running:

* ``SubagentStart``: the new requests belong to the main agent (it ran until it called the subagent);
* ``SubagentStop``: they belong to the subagent that stops;
* ``Stop``: they belong to the main agent of the phase (``challenge`` -> challenger,
  ``design`` -> architect, later phases -> builder), unless the payload names the agent.

A request counts when a transcript line holds a recognised usage object (Anthropic, OpenAI or
camelCase field names, see ``normalize_usage``); requests are deduplicated by their id. When the
transcript has no usage object, the runs and durations are still recorded and the token columns
stay unknown: the report never invents a number. Subagents running in parallel share the
transcript, so their split is approximate.

Everything lives in the hook-owned ``.ai/<slug>/usage.json`` (``USAGE_FILE``), which a dashboard
can read: see ``docs/architecture/data.md``. Credits are estimated at report time from
``pricing.json`` (published GitHub Copilot rates, 1 AI credit = $0.01).
"""

from __future__ import annotations

import json
import os
import tempfile
import time
from pathlib import Path
from typing import Any, Callable, Dict, Iterator, List, Optional, Tuple

import workflow_gate as wg

USAGE_FILE = wg.USAGE_FILE
USAGE_VERSION = 1
PRICING_FILE = Path(__file__).resolve().parent / "pricing.json"
MAX_SEEN_IDS = 4000
MAX_READ_BYTES = 64 * 1024 * 1024
MAX_DEPTH = 8
# Requests whose prompt exceeds the smallest long-context threshold of pricing.json (100K) are also
# kept one by one, so the report can price them at the long-context rate of their model.
LONG_CONTEXT_FLOOR = 100_000
TOKEN_FIELDS = ("input", "cached_input", "cache_write", "output")
MAIN_AGENT_BY_PHASE = {"challenge": "challenger", "design": "architect"}
MAIN_AGENTS = ("challenger", "architect", "builder")
DEFAULT_MAIN_AGENT = "builder"
REPORT_ORDER = (
    "challenger",
    "architect",
    wg.SECURITY_AGENT,
    wg.PERFORMANCE_AGENT,
    "builder",
    wg.IMPLEMENTER_AGENT,
    wg.UI_DESIGNER_AGENT,
    wg.REVIEWER_AGENT,
)

_INPUT_KEYS = ("input_tokens", "inputTokens", "prompt_tokens", "promptTokens")
_OUTPUT_KEYS = ("output_tokens", "outputTokens", "completion_tokens", "completionTokens")
_CACHED_KEYS = ("cache_read_input_tokens", "cacheReadInputTokens", "cacheReadTokens", "cached_tokens", "cachedTokens")
_WRITE_KEYS = ("cache_creation_input_tokens", "cacheCreationInputTokens", "cacheWriteTokens", "cache_write_tokens")
_DETAIL_KEYS = ("prompt_tokens_details", "promptTokensDetails", "input_tokens_details", "inputTokensDetails")
_OPENAI_INPUT_KEYS = ("prompt_tokens", "promptTokens")
_MODEL_KEYS = ("model", "modelId", "model_id", "resolvedModel")
_ID_KEYS = ("requestId", "request_id", "responseId", "response_id", "message_id", "id")


# --- usage extraction ------------------------------------------------------------------------------


def _int(value: Any) -> Optional[int]:
    if isinstance(value, bool):
        return None
    if isinstance(value, int) and value >= 0:
        return value
    if isinstance(value, float) and value >= 0 and value.is_integer():
        return int(value)
    return None


def _pick(data: Dict[str, Any], keys: Tuple[str, ...]) -> Optional[int]:
    for key in keys:
        number = _int(data.get(key))
        if number is not None:
            return number
    return None


def normalize_usage(data: Dict[str, Any]) -> Optional[Dict[str, int]]:
    """Token counts of one model request, or None when ``data`` is not a usage object.

    ``input`` excludes the cached and cache-write tokens: OpenAI's ``prompt_tokens`` includes its
    ``cached_tokens``, Anthropic's ``input_tokens`` does not.
    """
    raw_input = _pick(data, _INPUT_KEYS)
    output = _pick(data, _OUTPUT_KEYS)
    if raw_input is None or output is None:
        return None
    cached = _pick(data, _CACHED_KEYS)
    for key in _DETAIL_KEYS:
        details = data.get(key)
        if cached is None and isinstance(details, dict):
            cached = _pick(details, _CACHED_KEYS)
    cached = cached or 0
    write = _pick(data, _WRITE_KEYS) or 0
    openai_style = any(key in data for key in _OPENAI_INPUT_KEYS)
    fresh = max(raw_input - cached, 0) if openai_style else raw_input
    return {"input": fresh, "cached_input": cached, "cache_write": write, "output": output}


def _string(data: Dict[str, Any], keys: Tuple[str, ...]) -> Optional[str]:
    for key in keys:
        value = data.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def extract_requests(entry: Any) -> List[Dict[str, Any]]:
    """Model requests found in one transcript line: ``{"id", "model", "tokens"}``."""
    found: List[Dict[str, Any]] = []

    def walk(node: Any, model: Optional[str], ident: Optional[str], depth: int) -> None:
        if depth > MAX_DEPTH:
            return
        if isinstance(node, list):
            for item in node:
                walk(item, model, ident, depth + 1)
            return
        if not isinstance(node, dict):
            return
        model = _string(node, _MODEL_KEYS) or model
        ident = _string(node, _ID_KEYS) or ident
        tokens = normalize_usage(node)
        if tokens is not None:
            found.append({"id": ident, "model": model, "tokens": tokens})
            return
        for value in node.values():
            if isinstance(value, (dict, list)):
                walk(value, model, ident, depth + 1)

    walk(entry, None, None, 0)
    return found


def _new_lines(path: Path, offset: int) -> Tuple[List[bytes], int]:
    """Complete lines appended to ``path`` since ``offset``, and the new offset."""
    try:
        size = path.stat().st_size
    except OSError:
        return [], offset
    if size < offset:
        offset = 0  # the transcript was rewritten
    if size - offset > MAX_READ_BYTES:
        offset = size - MAX_READ_BYTES
    with path.open("rb") as stream:
        stream.seek(offset)
        data = stream.read()
    end = data.rfind(b"\n")
    if end < 0:
        return [], offset
    return data[: end + 1].splitlines(), offset + end + 1


def read_new_requests(path: Path, cursor: Dict[str, Any]) -> List[Dict[str, Any]]:
    """New, deduplicated requests of the transcript; ``cursor`` (offset, seen ids) is updated."""
    offset = cursor.get("offset")
    lines, cursor["offset"] = _new_lines(path, offset if isinstance(offset, int) and offset >= 0 else 0)
    seen_list = cursor.get("seen")
    seen: List[str] = [item for item in seen_list if isinstance(item, str)] if isinstance(seen_list, list) else []
    known = set(seen)
    requests: List[Dict[str, Any]] = []
    for line in lines:
        text = line.decode("utf-8", errors="replace").strip().lstrip("﻿")
        if not text:
            continue
        try:
            entry = json.loads(text)
        except ValueError:
            continue
        for request in extract_requests(entry):
            ident = request["id"]
            if ident:
                if ident in known:
                    continue
                known.add(ident)
                seen.append(ident)
            requests.append(request)
    cursor["seen"] = seen[-MAX_SEEN_IDS:]
    return requests


# --- usage.json ----------------------------------------------------------------------------------


def read_usage(directory: Path) -> Dict[str, Any]:
    data = wg.read_json(directory / USAGE_FILE)
    return data if data.get("version") == USAGE_VERSION else {}


def update_usage(directory: Path, change: Callable[[Dict[str, Any]], None]) -> None:
    """Read-modify-write ``usage.json`` atomically, like ``.hooks.json``, under the hook lock (parallel subagents)."""
    if not directory.is_dir():
        return
    with wg.locked(directory):
        data = read_usage(directory)
        data.setdefault("version", USAGE_VERSION)
        data.setdefault("agents", {})
        data.setdefault("transcripts", {})
        change(data)
        data["updated_at"] = wg.now_iso()
        handle, temporary = tempfile.mkstemp(prefix=".usage-", dir=str(directory))
        try:
            with os.fdopen(handle, "w", encoding="utf-8") as stream:
                json.dump(data, stream, indent=2, sort_keys=True)
            os.replace(temporary, directory / USAGE_FILE)
        except OSError:
            try:
                os.unlink(temporary)
            except OSError:
                pass


def _agent_entry(data: Dict[str, Any], agent: str) -> Dict[str, Any]:
    agents = data.setdefault("agents", {})
    entry = agents.get(agent)
    if not isinstance(entry, dict):
        entry = agents[agent] = {"runs": 0, "turns": 0, "duration_s": 0, "requests": 0, "models": {}}
    return entry


def add_requests(entry: Dict[str, Any], requests: List[Dict[str, Any]]) -> None:
    models = entry.setdefault("models", {})
    for request in requests:
        tokens = request["tokens"]
        empty = {"requests": 0, **{field: 0 for field in TOKEN_FIELDS}}
        bucket = models.setdefault(request["model"] or "unknown", empty)
        bucket["requests"] = bucket.get("requests", 0) + 1
        for field in TOKEN_FIELDS:
            bucket[field] = bucket.get(field, 0) + tokens[field]
        if tokens["input"] + tokens["cached_input"] + tokens["cache_write"] > LONG_CONTEXT_FLOOR:
            bucket.setdefault("long_context_requests", []).append(dict(tokens))
    entry["requests"] = entry.get("requests", 0) + len(requests)


def main_agent(workflow: wg.Workflow, payload_agent: str) -> str:
    name = payload_agent.strip().lower()
    for agent in MAIN_AGENTS:
        if name == agent or name.endswith(":" + agent):
            return agent
    return MAIN_AGENT_BY_PHASE.get(workflow.phase, DEFAULT_MAIN_AGENT)


def subagent_label(payload_agent: str) -> str:
    name = payload_agent.strip()
    known = wg.subagent_name(name)
    if known:
        return known
    return name.split(":")[-1].lower() if name else "subagent"


def record(
    workflow: wg.Workflow,
    event: str,
    transcript: str,
    payload_agent: str = "",
    started_at: Optional[float] = None,
) -> int:
    """Attribute the new requests of ``transcript`` for ``event``: ``start``, ``stop`` (subagent) or ``main-stop``.

    Returns the number of requests attributed. A missing or unreadable transcript only leaves the
    token columns unknown.
    """
    if event == "stop":
        agent = subagent_label(payload_agent)
    else:
        agent = main_agent(workflow, payload_agent if event == "main-stop" else "")
    now = time.time()
    counted = 0

    def change(data: Dict[str, Any]) -> None:
        nonlocal counted
        requests: List[Dict[str, Any]] = []
        if transcript:
            cursors = data.setdefault("transcripts", {})
            cursor = cursors.get(transcript)
            if not isinstance(cursor, dict):
                cursor = cursors[transcript] = {}
            try:
                requests = read_new_requests(Path(transcript), cursor)
            except OSError:
                requests = []
            cursor["read_at"] = wg.now_iso(now)
        else:
            data["missing_transcript"] = data.get("missing_transcript", 0) + 1
        entry = _agent_entry(data, agent)
        if requests:
            add_requests(entry, requests)
        if event == "stop":
            entry["runs"] = entry.get("runs", 0) + 1
            if started_at is not None and -wg.CLOCK_SKEW <= now - started_at <= 24 * 3600:
                entry["duration_s"] = entry.get("duration_s", 0) + max(int(round(now - started_at)), 0)
        elif event == "main-stop":
            entry["turns"] = entry.get("turns", 0) + 1
        counted = len(requests)

    update_usage(workflow.directory, change)
    return counted


# --- pricing and report --------------------------------------------------------------------------


def load_pricing(path: Path = PRICING_FILE) -> Dict[str, Any]:
    data = wg.read_json(path)
    return data if isinstance(data.get("models"), list) else {"models": []}


def model_key(name: str) -> str:
    """``Claude Opus 5.5 (copilot)``, ``claude-opus-5.5`` and ``claude-opus-5-5`` give the same key."""
    text = name.lower().replace("(copilot)", "")
    for char in " ._/":
        text = text.replace(char, "-")
    return "-".join(part for part in text.split("-") if part)


def _dated(key: str, alias_key: str) -> bool:
    suffix = key[len(alias_key) + 1 :].replace("-", "") if key.startswith(alias_key + "-") else ""
    return suffix.isdigit() and len(suffix) >= 6


def find_rates(pricing: Dict[str, Any], model: str) -> Optional[Dict[str, Any]]:
    """Rate row of ``model``: same name, or with a provider prefix (``copilot/…``) or a date suffix."""
    key = model_key(model)
    best: Optional[Dict[str, Any]] = None
    best_length = 0
    for row in pricing.get("models", []):
        if not isinstance(row, dict):
            continue
        for alias in [row.get("name", ""), *row.get("aliases", [])]:
            alias_key = model_key(str(alias))
            if alias_key and (key == alias_key or key.endswith("-" + alias_key) or _dated(key, alias_key)):
                if len(alias_key) > best_length:
                    best, best_length = row, len(alias_key)
    return best


def _cost(tokens: Dict[str, Any], rates: Dict[str, Any]) -> float:
    total = 0.0
    for field in TOKEN_FIELDS:
        rate = rates.get(field)
        if isinstance(rate, (int, float)):
            total += tokens.get(field, 0) * rate / 1_000_000
    return total


def model_cost_usd(bucket: Dict[str, Any], row: Dict[str, Any]) -> float:
    """Cost of a model bucket; requests above the row's long-context threshold use its long rates."""
    rates = row.get("rates", {})
    long_context = row.get("long_context")
    if not isinstance(long_context, dict):
        return _cost(bucket, rates)
    threshold = long_context.get("threshold", 0)
    long_requests = [
        request
        for request in bucket.get("long_context_requests", [])
        if request.get("input", 0) + request.get("cached_input", 0) + request.get("cache_write", 0) > threshold
    ]
    long_total = {field: sum(request.get(field, 0) for request in long_requests) for field in TOKEN_FIELDS}
    short_total = {field: bucket.get(field, 0) - long_total[field] for field in TOKEN_FIELDS}
    return _cost(short_total, rates) + _cost(long_total, long_context.get("rates", {}))


def summarize(usage: Dict[str, Any], pricing: Dict[str, Any]) -> Dict[str, Any]:
    """Rows per agent with tokens and estimated credits (``None`` when unknown); readable by a dashboard."""
    credit_usd = pricing.get("credit_usd", 0.01)
    rows: List[Dict[str, Any]] = []
    agents = usage.get("agents")
    if not isinstance(agents, dict):
        agents = {}
    for name, entry in agents.items():
        if not isinstance(entry, dict):
            continue
        models = entry.get("models")
        if not isinstance(models, dict):
            models = {}
        usd: Optional[float] = 0.0
        unpriced: List[str] = []
        for model, bucket in models.items():
            row = find_rates(pricing, model)
            if row is None:
                unpriced.append(model)
            else:
                usd = (usd or 0.0) + model_cost_usd(bucket, row)
        if unpriced or not models:
            usd = None
        rows.append(
            {
                "agent": name,
                "runs": entry.get("runs", 0),
                "turns": entry.get("turns", 0),
                "duration_s": entry.get("duration_s", 0),
                "requests": entry.get("requests", 0),
                "models": sorted(models),
                "tokens": token_totals(models) if models else None,
                "usd": usd,
                "credits": None if usd is None else usd / credit_usd,
                "unpriced_models": unpriced,
            }
        )
    order = list(REPORT_ORDER)
    rows.sort(key=lambda row: (order.index(row["agent"]) if row["agent"] in order else len(order), row["agent"]))
    known = [row for row in rows if row["tokens"] is not None]
    total_usd = sum(row["usd"] for row in rows if row["usd"] is not None)
    return {
        "rows": rows,
        "total": {
            "tokens": {field: sum(row["tokens"][field] for row in known) for field in TOKEN_FIELDS} if known else None,
            "usd": total_usd if known else None,
            "credits": total_usd / credit_usd if known else None,
            "complete": bool(rows) and all(row["usd"] is not None for row in rows),
        },
        "credit_usd": credit_usd,
        "pricing_source": pricing.get("source"),
        "pricing_checked_on": pricing.get("checked_on"),
        "tokens_found": bool(known),
    }


def token_totals(models: Dict[str, Any]) -> Dict[str, int]:
    return {field: sum(int(bucket.get(field, 0)) for bucket in models.values()) for field in TOKEN_FIELDS}


_HEADERS = {
    "fr": ("Agent", "Modèle", "Exécutions", "Durée", "Entrée", "Cache lu", "Cache écrit", "Sortie", "Crédits (estim.)"),
    "en": ("Agent", "Model", "Runs", "Duration", "Input", "Cache read", "Cache write", "Output", "Credits (est.)"),
}


def _number(value: Optional[float], language: str, decimals: int = 0) -> str:
    if value is None:
        return "n/d" if language == "fr" else "n/a"
    text = f"{value:,.{decimals}f}"
    return text.replace(",", " ").replace(".", ",") if language == "fr" else text


def _duration(seconds: Any) -> str:
    if not isinstance(seconds, (int, float)) or seconds <= 0:
        return "–"
    minutes, second = divmod(int(seconds), 60)
    return f"{minutes} min {second:02d} s" if minutes else f"{second} s"


def render_markdown(summary: Dict[str, Any], language: str = "fr") -> str:
    """Markdown table (one row per agent, then the total) followed by the notes on the estimate."""
    language = "fr" if language == "fr" else "en"
    headers = _HEADERS[language]
    lines = ["| " + " | ".join(headers) + " |", "|---|---|" + "|".join(["---:"] * (len(headers) - 2)) + "|"]
    for row in summary["rows"]:
        tokens = row["tokens"]
        cells = [
            row["agent"],
            ", ".join(row["models"]) or "–",
            str(row["runs"] or row["turns"]),
            _duration(row["duration_s"]),
            *(_number(tokens[field] if tokens else None, language) for field in TOKEN_FIELDS),
            _number(row["credits"], language, 1),
        ]
        lines.append("| " + " | ".join(cells) + " |")
    total = summary["total"]
    credits = _number(total["credits"], language, 1)
    if total["credits"] is not None and not total["complete"]:
        credits = "≥ " + credits
    total_tokens = total["tokens"]
    lines.append(
        "| **Total** | | | | "
        + " | ".join(_number(total_tokens[field] if total_tokens else None, language) for field in TOKEN_FIELDS)
        + f" | **{credits}** |"
    )
    unpriced = any(row["unpriced_models"] for row in summary["rows"])
    source, checked = summary["pricing_source"], summary["pricing_checked_on"]
    usd = _number(summary["credit_usd"], language, 2)
    if language == "fr":
        notes = [
            "Le transcript de VS Code ne contenait aucun compteur de tokens : seules les exécutions et les durées "
            "sont connues, aucun coût n'est estimé (lance `usage_report.py --probe <transcript>` pour adapter le "
            "lecteur)."
            if not summary["tokens_found"]
            else "",
            f"Crédits estimés = tokens × tarifs publics GitHub Copilot ({source}, relevés le {checked}), "
            f"1 crédit = {usd} $. Ce n'est pas ta facture : le décompte exact est dans GitHub, "
            "Billing > Metered usage.",
            "n/d : modèle absent de `scripts/hooks/pricing.json`, ou tokens inconnus ; le total est alors un minimum."
            if unpriced
            else "",
            "Exécutions : lancements pour un subagent, tours de conversation pour un agent principal. Des subagents "
            "lancés en parallèle partagent le transcript : leur répartition est approximative.",
        ]
    else:
        notes = [
            "The VS Code transcript held no token counts: only runs and durations are known, no cost is estimated "
            "(run `usage_report.py --probe <transcript>` to adapt the reader)."
            if not summary["tokens_found"]
            else "",
            f"Estimated credits = tokens × published GitHub Copilot rates ({source}, checked on {checked}), "
            f"1 credit = ${usd}. This is not your bill: see GitHub, Billing > Metered usage.",
            "n/a: model missing from `scripts/hooks/pricing.json`, or tokens unknown; the total is then a minimum."
            if unpriced
            else "",
            "Runs: launches for a subagent, conversation turns for a main agent. Subagents run in parallel share "
            "the transcript, so their split is approximate.",
        ]
    return "\n".join(lines) + "\n\n" + "\n".join(f"- {note}" for note in notes if note) + "\n"


def transcript_shape(path: Path, limit: int = 2000) -> Iterator[str]:
    """Key paths of a transcript with their counts, never a value: used to adapt the reader (``--probe``)."""
    counts: Dict[str, int] = {}

    def walk(node: Any, prefix: str, depth: int) -> None:
        if depth > MAX_DEPTH:
            return
        if isinstance(node, dict):
            for key, value in node.items():
                path_key = f"{prefix}.{key}" if prefix else str(key)
                counts[path_key] = counts.get(path_key, 0) + 1
                walk(value, path_key, depth + 1)
        elif isinstance(node, list):
            for item in node[:20]:
                walk(item, prefix + "[]", depth + 1)

    with path.open("rb") as stream:
        for index, line in enumerate(stream):
            if index >= limit:
                break
            try:
                walk(json.loads(line.decode("utf-8", errors="replace")), "", 0)
            except ValueError:
                counts["<not json>"] = counts.get("<not json>", 0) + 1
    for key in sorted(counts):
        yield f"{counts[key]:6d}  {key}"
