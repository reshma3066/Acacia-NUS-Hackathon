"""Claude boundary for the SAF Planner (owner: Syakir).

Claude is used for exactly two things:
  1. parse_request  - turn a planner's text into a structured demand Patch (tool use).
  2. explain_result - describe an already-validated Result in plain English.

All maths stays in Python: Claude only reports *which* airport and *what kind* of
change ("set to X t/year" or "change by P percent"); Python computes the new demand.
Feasibility and costs always come from the solver/validator, never from Claude.

Call budget: max 2 normal API calls per request (parse + explain) plus 1 bounded retry
in total. run_scenario() opens the budget with `request_budget()`.
"""
from __future__ import annotations

import contextlib
import contextvars
import json
import logging
import math
import os
import re
from typing import Any

from .contracts import Patch, Result, Scenario, Validation

log = logging.getLogger("saf.agent")

SCHEMA_VERSION = "1.0"
PROMPT_VERSION = "agent-prompt-v1"
AIRPORT_IDS = ("PNK", "PKN", "BPN", "TRK")
AIRPORT_NAMES = {
    "PNK": "Supadio Intl (Pontianak)",
    "PKN": "Iskandar (Pangkalan Bun)",
    "BPN": "Sultan Aji Muhammad Sulaiman Sepinggan Intl (Balikpapan)",
    "TRK": "Juwata Intl (Tarakan)",
}
API_TIMEOUT_S = 20.0
PARSE_MAX_TOKENS = 400
EXPLAIN_MAX_TOKENS = 500


class AgentUnavailable(RuntimeError):
    """Claude could not be reached (missing key, network/API error, budget exhausted)."""


# --------------------------------------------------------------------------- #
# Call budget (2 normal calls + 1 retry per request)                           #
# --------------------------------------------------------------------------- #
class _Budget:
    def __init__(self, normal: int = 2, retries: int = 1):
        self.normal_left, self.retries_left, self.calls = normal, retries, 0


_budget: contextvars.ContextVar[_Budget | None] = contextvars.ContextVar("saf_budget", default=None)


@contextlib.contextmanager
def request_budget(normal: int = 2, retries: int = 1):
    token = _budget.set(_Budget(normal, retries))
    try:
        yield _budget.get()
    finally:
        _budget.reset(token)


# --------------------------------------------------------------------------- #
# Anthropic client (lazy so the module imports without the SDK or a key)       #
# --------------------------------------------------------------------------- #
_client_cache: Any = None


def model_id() -> str:
    return os.environ.get("CLAUDE_MODEL", "").strip()


def _get_client():
    global _client_cache
    if _client_cache is None:
        try:
            from dotenv import load_dotenv  # optional
            load_dotenv()
        except ImportError:
            pass
        if not os.environ.get("ANTHROPIC_API_KEY"):
            raise AgentUnavailable("ANTHROPIC_API_KEY is not set in .env")
        if not model_id():
            raise AgentUnavailable("CLAUDE_MODEL is not set in .env")
        try:
            import anthropic
        except ImportError as e:
            raise AgentUnavailable("anthropic package not installed (pip install anthropic)") from e
        # max_retries=0: we do our own single bounded retry under the request budget
        _client_cache = anthropic.Anthropic(timeout=API_TIMEOUT_S, max_retries=0)
    return _client_cache


def _create(**kwargs):
    """One API call with at most one retry, charged against the request budget."""
    budget = _budget.get() or _Budget()  # standalone calls get their own small budget
    if budget.normal_left <= 0:
        raise AgentUnavailable("API call budget for this request is exhausted")
    budget.normal_left -= 1
    client = _get_client()
    last_err: Exception | None = None
    while True:
        budget.calls += 1
        try:
            return client.messages.create(model=model_id() or "unset", **kwargs)
        except Exception as e:  # anthropic.APIError, timeouts, connection errors
            last_err = e
            log.warning("Claude API call failed: %s", type(e).__name__)
            if budget.retries_left <= 0:
                break
            budget.retries_left -= 1
    raise AgentUnavailable(f"Claude API failed: {type(last_err).__name__}: {last_err}")


# --------------------------------------------------------------------------- #
# 1. parse_request                                                             #
# --------------------------------------------------------------------------- #
PATCH_TOOL = {
    "name": "submit_demand_patch",
    "description": (
        "Report how the planner wants to change SAF demand at airports. "
        "Use status 'ready' only for clear airport demand changes. Use 'clarify' if the "
        "airport, amount or direction is ambiguous. Use 'unsupported' for any other kind "
        "of change (costs, yields, facilities, routes, new airports...)."
    ),
    "input_schema": {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "status": {"type": "string", "enum": ["ready", "clarify", "unsupported"]},
            "changes": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "airport_id": {"type": "string", "enum": list(AIRPORT_IDS)},
                        "mode": {"type": "string", "enum": ["set", "percent_change"],
                                 "description": "'set' = new absolute demand in t/year; "
                                                "'percent_change' = relative change, e.g. 20 for +20%, -10 for -10%"},
                        "value": {"type": "number"},
                    },
                    "required": ["airport_id", "mode", "value"],
                },
            },
            "question": {"type": "string",
                         "description": "For clarify/unsupported: a short question or note for the planner."},
        },
        "required": ["status", "changes"],
    },
}

PARSE_SYSTEM = (
    "You translate a SAF supply-chain planner's request into a structured demand change. "
    "Only SAF demand (tonnes/year) at these four airports can be changed: "
    + "; ".join(f"{k} = {v}" for k, v in AIRPORT_NAMES.items())
    + ". Do NOT calculate new values yourself: report percentages as mode 'percent_change' and "
    "absolute targets as mode 'set'. Never guess an airport or amount; ask instead. "
    "Always answer by calling submit_demand_patch exactly once."
)


def _patch(status: str, changes: list | None = None, question: str | None = None) -> Patch:
    return {"schema_version": SCHEMA_VERSION, "status": status,
            "changes": changes or [], "question": None if status == "ready" else question}


def _clarify(msg: str) -> Patch:
    return _patch("clarify", question=msg)


def _tool_input(resp) -> dict | None:
    for block in getattr(resp, "content", []) or []:
        if getattr(block, "type", None) == "tool_use" and getattr(block, "name", None) == PATCH_TOOL["name"]:
            return block.input if isinstance(block.input, dict) else None
    return None


def _finite_nonneg(x) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x) and x >= 0


def tool_input_to_patch(data: dict | None, scenario: Scenario) -> Patch:
    """Strictly validate Claude's tool input and compute new demand in Python."""
    if not isinstance(data, dict):
        return _clarify("I couldn't interpret that request. Which airport's SAF demand should change, and by how much?")
    allowed_top = {"status", "changes", "question"}
    if set(data) - allowed_top:
        return _clarify("I couldn't interpret that request safely. Please restate the airport and the demand change.")
    status = data.get("status")
    question = data.get("question") or None
    if status in ("clarify", "unsupported"):
        default = ("Only airport SAF demand changes (PNK, PKN, BPN, TRK) are supported right now."
                   if status == "unsupported" else
                   "Which airport (PNK, PKN, BPN or TRK) and what demand change do you mean?")
        return _patch(status, question=question or default)
    if status != "ready":
        return _clarify("I couldn't interpret that request. Which airport and what change?")

    changes = data.get("changes")
    if not isinstance(changes, list) or not changes:
        return _clarify("Which airport's demand should change, and by how much?")
    demand = scenario.get("demand_t_per_year", {})
    out, seen = [], set()
    for ch in changes:
        if not isinstance(ch, dict) or set(ch) - {"airport_id", "mode", "value"}:
            return _clarify("I couldn't interpret one of the changes. Please restate it.")
        aid, mode, value = ch.get("airport_id"), ch.get("mode"), ch.get("value")
        if aid not in AIRPORT_IDS or aid not in demand:
            return _clarify(f"'{aid}' isn't one of the four airports (PNK, PKN, BPN, TRK). Which did you mean?")
        if aid in seen:
            return _clarify(f"{aid} was changed twice. What single new demand should it have?")
        seen.add(aid)
        if not (isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)):
            return _clarify(f"What amount should {aid} change by?")
        if mode == "set":
            new = float(value)
        elif mode == "percent_change":
            new = float(demand[aid]) * (1.0 + float(value) / 100.0)
        else:
            return _clarify(f"Should {aid} be set to a value or changed by a percentage?")
        new = round(new, 6)
        if not _finite_nonneg(new):
            return _clarify(f"That would make {aid} demand negative ({new:g} t/year). Demand must be zero or more.")
        out.append({"airport_id": aid, "new_demand_t_per_year": new})
    return _patch("ready", out)


def parse_request(text: str, scenario: Scenario) -> Patch:
    """Text -> Patch. Raises AgentUnavailable if Claude cannot be reached."""
    if not isinstance(text, str) or not text.strip():
        return _clarify("Please type a request, e.g. 'Increase BPN demand by 20%'.")
    current = {k: scenario.get("demand_t_per_year", {}).get(k) for k in AIRPORT_IDS}
    resp = _create(
        max_tokens=PARSE_MAX_TOKENS,
        system=PARSE_SYSTEM,
        tools=[PATCH_TOOL],
        tool_choice={"type": "tool", "name": PATCH_TOOL["name"]},
        messages=[{"role": "user", "content":
                   f"Current SAF demand (t/year): {json.dumps(current)}\n\nPlanner request: {text.strip()[:1000]}"}],
    )
    patch = tool_input_to_patch(_tool_input(resp), scenario)
    log.info("parse_request -> status=%s changes=%s", patch["status"], patch["changes"])
    return patch


# --------------------------------------------------------------------------- #
# 2. explain_result                                                            #
# --------------------------------------------------------------------------- #
VALID_STATUSES = ("optimal", "feasible")


def result_facts(scenario: Scenario, result: Result, validation: Validation) -> dict:
    """Compact, JSON-safe facts. This is ALL Claude sees - never flows or raw data."""
    fac = result.get("facilities") or []
    count = {}
    for f in fac:
        key = f"{f.get('kind')}_{f.get('size')}"
        count[key] = count.get(key, 0) + 1
    return {
        "scenario_id": scenario.get("scenario_id"),
        "assumptions_status": scenario.get("assumptions_status"),
        "demand_t_per_year": scenario.get("demand_t_per_year"),
        "status": result.get("status"),
        "provenance": result.get("provenance"),
        "mip_gap": result.get("mip_gap"),
        "facility_counts": count,
        "deliveries_t_per_year": result.get("deliveries_t_per_year"),
        "costs": result.get("costs"),
        "validation_valid": validation.get("valid") if validation else None,
        "checks_passed": [c.get("name") for c in (validation or {}).get("checks", []) if c.get("passed")],
        "validation_errors": (validation or {}).get("errors", []),
    }


def _money(x) -> str:
    return "n/a" if x is None else f"${x:,.0f}"


def template_explanation(scenario: Scenario, result: Result | None, validation: Validation | None,
                         note: str | None = None) -> str:
    """Deterministic explanation - used when Claude is unavailable or the plan is not valid."""
    if result is None:
        return note or "No result was produced."
    status = result.get("status")
    if status not in VALID_STATUSES or not (validation or {}).get("valid"):
        reasons = (validation or {}).get("errors") or [result.get("message") or "no reason given"]
        text = (f"Scenario {scenario.get('scenario_id')}: NO VALID PLAN (solver status: {status}). "
                f"Reason: {'; '.join(map(str, reasons))}. "
                "The previous plan has not been reused. Adjust demand or assumptions and solve again.")
    else:
        c = result.get("costs") or {}
        f = result_facts(scenario, result, validation)
        text = (f"Scenario {scenario.get('scenario_id')} ({status}, provenance: {result.get('provenance')}). "
                f"Total annual cost {_money(c.get('total_usd_per_year'))}: annualised CapEx "
                f"{_money(c.get('annualised_capex_usd_per_year'))}, transport {_money(c.get('transport_usd_per_year'))}, "
                f"OpEx {_money(c.get('opex_usd_per_year'))}. Facilities: {f['facility_counts']}. "
                f"Deliveries (t/year): {result.get('deliveries_t_per_year')}. "
                f"Validation passed: {', '.join(f['checks_passed']) or 'yes'}.")
    if scenario.get("assumptions_status", "").startswith("DEMO"):
        text += " Assumptions are demo values, not organiser-confirmed."
    return (note + " " + text) if note else text


EXPLAIN_SYSTEM = (
    "You explain an already-solved and validated SAF supply-chain plan to a planner in 3-5 short sentences. "
    "Use ONLY numbers that appear in the JSON facts, copied exactly (you may add $ and thousands separators). "
    "Do not compute new numbers, percentages or differences. Do not claim anything about feasibility beyond "
    "the 'status' and 'validation_valid' fields. If assumptions_status starts with DEMO, say assumptions are "
    "not organiser-confirmed."
)

_NUM = re.compile(r"\d[\d,]*\.?\d*")


def _allowed_numbers(obj) -> set[str]:
    nums: set[str] = set()

    def walk(o):
        if isinstance(o, bool) or o is None:
            return
        if isinstance(o, (int, float)):
            for v in (o, round(o), round(o, 1), round(o, 2)):
                nums.add(f"{v:g}" if isinstance(v, float) else str(v))
                nums.add(str(int(v)) if float(v).is_integer() else f"{v}")
        elif isinstance(o, dict):
            for k, v in o.items():
                walk(v); nums.update(_NUM.findall(str(k)))
        elif isinstance(o, (list, tuple)):
            for v in o:
                walk(v)
        else:
            nums.update(_NUM.findall(str(o)))
    walk(obj)
    return {n.replace(",", "").rstrip(".") for n in nums}


def _grounded(text: str, facts: dict) -> bool:
    """Every number with 3+ digits in Claude's text must appear in the facts."""
    allowed = _allowed_numbers(facts)
    for raw in _NUM.findall(text):
        n = raw.replace(",", "").rstrip(".")
        if len(n.replace(".", "")) >= 3 and n not in allowed:
            try:
                if any(abs(float(n) - float(a)) < 1e-6 for a in allowed if a):
                    continue
            except ValueError:
                pass
            log.warning("explanation number %s not found in facts", n)
            return False
    return True


def explain_result(scenario: Scenario, result: Result, validation: Validation) -> str:
    """Grounded explanation. Only calls Claude for valid plans; falls back to a template."""
    if result is None or result.get("status") not in VALID_STATUSES or not (validation or {}).get("valid"):
        return template_explanation(scenario, result, validation)
    facts = result_facts(scenario, result, validation)
    try:
        resp = _create(max_tokens=EXPLAIN_MAX_TOKENS, system=EXPLAIN_SYSTEM,
                       messages=[{"role": "user", "content": json.dumps(facts)}])
    except AgentUnavailable as e:
        return template_explanation(scenario, result, validation,
                                    note=f"(AI explanation unavailable: {e}. Showing factual summary.)")
    text = " ".join(getattr(b, "text", "") for b in getattr(resp, "content", []) if getattr(b, "type", "") == "text").strip()
    if not text or not _grounded(text, facts):
        return template_explanation(scenario, result, validation,
                                    note="(AI explanation failed the number check. Showing factual summary.)")
    return text


# --------------------------------------------------------------------------- #
# Smoke test:  python -m saf.agent                                             #
# --------------------------------------------------------------------------- #
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    demo = {"scenario_id": "smoke", "demand_t_per_year": {"PNK": 25, "PKN": 25, "BPN": 25, "TRK": 25}}
    with request_budget() as b:
        p = parse_request("Increase Balikpapan demand by 20%", demo)
    print(json.dumps(p, indent=2))
    print(f"model={model_id()} prompt={PROMPT_VERSION} api_calls={b.calls}")
    assert p["status"] == "ready" and p["changes"] == [{"airport_id": "BPN", "new_demand_t_per_year": 30.0}], p
    print("SMOKE TEST PASSED")
