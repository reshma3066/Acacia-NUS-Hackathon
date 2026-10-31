"""Orchestration for the SAF Planner (owner: Syakir).

    request -> parse -> validate patch -> solve -> validate -> explain

run_scenario() always returns exactly:
    {"scenario", "result", "validation", "explanation", "clarification"}

Rules enforced here:
  * input scenario is never mutated (apply_patch deep-copies, fresh scenario_id)
  * clarification / unsupported / API failure never call the solver
  * a non-solution or invalid result is never described as a valid plan
  * no stale output: every call builds its result from scratch
  * manual solving (request=None) never needs the Claude API
"""
from __future__ import annotations

import copy
import hashlib
import json
import logging
import math
import time
from typing import Any

from . import agent
from .contracts import Bundle, Patch, Result, Scenario, Validation

log = logging.getLogger("saf.service")

SCHEMA_VERSION = "1.0"
REQUIRED_AIRPORTS = ("PNK", "PKN", "BPN", "TRK")
RESPONSE_KEYS = ("scenario", "result", "validation", "explanation", "clarification")

# Last trace, for the UI / debugging (not part of the response schema).
LAST_TRACE: list[dict[str, Any]] = []


# --------------------------------------------------------------------------- #
# Dependencies (imported lazily so this module works before teammates finish;  #
# tests monkeypatch these two functions with fixtures)                         #
# --------------------------------------------------------------------------- #
def _solve(bundle: Bundle, scenario: Scenario) -> Result:
    from .optimizer import solve_scenario  # Reshma
    return solve_scenario(bundle, scenario)


def _validate(bundle: Bundle, scenario: Scenario, result: Result) -> Validation:
    from .validation import validate_solution  # Shaza
    return validate_solution(bundle, scenario, result)


# --------------------------------------------------------------------------- #
# apply_patch                                                                  #
# --------------------------------------------------------------------------- #
def apply_patch(scenario: Scenario, patch: Patch) -> Scenario:
    """Deep-copy config; validate airport IDs and finite nonnegative demand. Raises ValueError."""
    if not isinstance(patch, dict):
        raise ValueError("patch must be a dict")
    extra = set(patch) - {"schema_version", "status", "changes", "question"}
    if extra:
        raise ValueError(f"unknown patch fields: {sorted(extra)}")
    if patch.get("schema_version") != SCHEMA_VERSION:
        raise ValueError(f"patch schema_version must be '{SCHEMA_VERSION}'")
    if patch.get("status") != "ready":
        raise ValueError("only patches with status 'ready' can be applied")
    changes = patch.get("changes")
    if not isinstance(changes, list) or not changes:
        raise ValueError("ready patch must contain at least one change")

    demand = scenario.get("demand_t_per_year")
    if not isinstance(demand, dict):
        raise ValueError("scenario has no demand_t_per_year")
    seen = set()
    for ch in changes:
        if not isinstance(ch, dict) or set(ch) != {"airport_id", "new_demand_t_per_year"}:
            raise ValueError(f"change must have exactly airport_id and new_demand_t_per_year: {ch!r}")
        aid, val = ch["airport_id"], ch["new_demand_t_per_year"]
        if aid not in REQUIRED_AIRPORTS or aid not in demand:
            raise ValueError(f"unknown airport_id: {aid!r}")
        if aid in seen:
            raise ValueError(f"duplicate airport_id in patch: {aid}")
        seen.add(aid)
        if isinstance(val, bool) or not isinstance(val, (int, float)) or not math.isfinite(val) or val < 0:
            raise ValueError(f"demand for {aid} must be a finite number >= 0, got {val!r}")

    new = copy.deepcopy(scenario)
    for ch in changes:
        new["demand_t_per_year"][ch["airport_id"]] = float(ch["new_demand_t_per_year"])
    digest = hashlib.sha1(json.dumps(changes, sort_keys=True).encode()).hexdigest()[:8]
    new["scenario_id"] = f"{scenario.get('scenario_id', 'scenario')}+{digest}"
    return new


# --------------------------------------------------------------------------- #
# run_scenario                                                                 #
# --------------------------------------------------------------------------- #
def _response(scenario, result, validation, explanation, clarification) -> dict:
    return {"scenario": scenario, "result": result, "validation": validation,
            "explanation": explanation, "clarification": clarification}


def _error_result(scenario: Scenario, message: str) -> Result:
    return {"schema_version": SCHEMA_VERSION, "scenario_id": scenario.get("scenario_id"),
            "provenance": "solver", "status": "error", "runtime_s": 0.0, "mip_gap": None,
            "message": message, "facilities": [], "flows": [], "deliveries_t_per_year": {}, "costs": None}


def run_scenario(bundle: Bundle, scenario: Scenario, request: str | None = None) -> dict:
    """Return scenario, result, validation, explanation, clarification."""
    trace: list[dict[str, Any]] = []
    t0 = time.perf_counter()

    def step(name: str, **info):
        entry = {"step": name, "t_s": round(time.perf_counter() - t0, 3), **info}
        trace.append(entry)
        log.info("trace %s", json.dumps(entry, default=str))

    LAST_TRACE.clear()
    try:
        with agent.request_budget() as budget:
            step("request_received", scenario_id=scenario.get("scenario_id"),
                 mode="manual" if request is None else "ai", text=(request or "")[:200])
            working = scenario

            # ---- 1. parse + patch (AI mode only) ----
            if request is not None:
                try:
                    patch = agent.parse_request(request, scenario)
                except agent.AgentUnavailable as e:
                    step("parse_failed", error=str(e))
                    msg = (f"The AI assistant is unavailable ({e}). Nothing was changed. "
                           "You can still run the current scenario with Manual solve.")
                    return _response(copy.deepcopy(scenario), None, None, msg, None)
                step("patch_requested", status=patch["status"], changes=patch["changes"])
                if patch["status"] != "ready":
                    q = patch.get("question") or "Could you clarify the request?"
                    step("clarification_returned", status=patch["status"])
                    return _response(copy.deepcopy(scenario), None, None, q, q)
                try:
                    working = apply_patch(scenario, patch)
                except ValueError as e:
                    step("patch_rejected", error=str(e))
                    q = f"That change can't be applied: {e}. Please restate the demand change."
                    return _response(copy.deepcopy(scenario), None, None, q, q)
                step("patch_validated", new_scenario_id=working["scenario_id"],
                     demand=working["demand_t_per_year"])
            else:
                working = copy.deepcopy(scenario)

            # ---- 2. solve ----
            try:
                result = _solve(bundle, working)
            except ValueError as e:
                result = _error_result(working, f"Invalid input for solver: {e}")
            except Exception as e:  # never crash the UI, never reuse an old result
                log.exception("solver raised")
                result = _error_result(working, f"Solver error: {type(e).__name__}: {e}")
            step("solver_completed", status=result.get("status"), runtime_s=result.get("runtime_s"),
                 mip_gap=result.get("mip_gap"))

            # ---- 3. validate (independent checks) ----
            try:
                validation = _validate(bundle, working, result)
            except Exception as e:
                log.exception("validator raised")
                validation = {"valid": False, "checks": [], "errors": [f"Validator error: {type(e).__name__}: {e}"]}
            if result.get("status") not in agent.VALID_STATUSES and validation.get("valid"):
                # contract: non-solution results validate as valid=false
                validation = {**validation, "valid": False,
                              "errors": list(validation.get("errors", [])) + [f"No solution: status {result.get('status')}"]}
            step("checks_passed" if validation.get("valid") else "checks_failed",
                 checks=[(c.get("name"), c.get("passed")) for c in validation.get("checks", [])],
                 errors=validation.get("errors", []))

            # ---- 4. explain ----
            if request is None:
                explanation = agent.template_explanation(working, result, validation)  # no API needed
            else:
                explanation = agent.explain_result(working, result, validation)
            step("explanation_ready", api_calls=budget.calls,
                 source="template" if request is None or not validation.get("valid") else "claude_or_fallback")
            return _response(working, result, validation, explanation, None)
    finally:
        LAST_TRACE.extend(trace)


def format_trace(trace: list[dict] | None = None) -> str:
    """'request_received -> patch_requested -> ...' for logs, PRs and the demo."""
    return " -> ".join(t["step"] for t in (trace if trace is not None else LAST_TRACE))
