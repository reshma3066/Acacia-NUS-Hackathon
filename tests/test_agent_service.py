"""Tests for saf/agent.py and saf/service.py (owner: Syakir). No API credit needed.

Run:  python -m pytest tests/test_agent_service.py -q
"""
import copy
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from saf import agent, service

MOCKS = Path(__file__).resolve().parents[1] / "mocks"

INLINE_SCENARIO = {
    "schema_version": "1.0", "scenario_id": "demo-v1",
    "assumptions_status": "DEMO_NOT_ORGANISER_CONFIRMED", "period_years": 1,
    "demand_t_per_year": {"PNK": 25, "PKN": 25, "BPN": 25, "TRK": 25},
    "depot_yield": 1.0, "refinery_yield": 0.5, "refinery_capacity_basis": "input",
    "use_all_supply": False, "distance_method": "haversine", "distance_multiplier": 1.0,
    "annualisation_years": 20, "discount_rate": 0.0,
    "depot_opex_usd_per_input_t": 0.0, "refinery_opex_usd_per_input_t": 0.0,
    "opex_status": "excluded_pending_clarification",
    "transport_usd_per_t_km": {"source_depot": 0.1, "depot_refinery": 0.12, "refinery_airport": 0.08},
    "solver_time_limit_s": 30, "solver_rel_gap": 0.01,
}
INLINE_RESULT = {
    "schema_version": "1.0", "scenario_id": "demo-v1", "provenance": "mock", "status": "feasible",
    "runtime_s": 0.0, "mip_gap": None, "message": "Synthetic fixture, not an optimum",
    "facilities": [{"candidate_id": "D1", "kind": "depot", "size": "small",
                    "input_t_per_year": 200, "output_t_per_year": 200}],
    "flows": [{"from_id": "S1", "to_id": "D1", "stage": "source_depot", "tonnes_per_year": 200}],
    "deliveries_t_per_year": {"PNK": 25, "PKN": 25, "BPN": 25, "TRK": 25},
    "costs": {"capex_usd": 482250000, "annualised_capex_usd_per_year": 24112500, "opex_usd_per_year": 0,
              "transport_usd_per_year": 800, "total_usd_per_year": 24113300},
}
VALID = {"valid": True, "checks": [{"name": "material_balance", "passed": True,
                                    "detail": "200 input -> 100 SAF at 0.5 yield"}], "errors": []}


def _load(name, fallback):
    p = MOCKS / name
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else copy.deepcopy(fallback)


@pytest.fixture
def scenario():
    return _load("scenario.json", INLINE_SCENARIO)


@pytest.fixture
def mock_result():
    return _load("result.json", INLINE_RESULT)


BUNDLE = {"sources": [], "airports": [], "candidates": [], "distances": [], "facility_options": {}}


# ---------------------------- fake Claude client ---------------------------- #
class FakeClient:
    """Returns queued responses; an Exception in the queue is raised instead."""

    def __init__(self, *responses):
        self.queue, self.calls = list(responses), []
        self.messages = SimpleNamespace(create=self._create)

    def _create(self, **kwargs):
        self.calls.append(kwargs)
        r = self.queue.pop(0) if self.queue else RuntimeError("no more fake responses")
        if isinstance(r, Exception):
            raise r
        return r


def tool(**inp):
    return SimpleNamespace(content=[SimpleNamespace(type="tool_use", name=agent.PATCH_TOOL["name"], input=inp)])


def text(t):
    return SimpleNamespace(content=[SimpleNamespace(type="text", text=t)])


@pytest.fixture
def fake(monkeypatch):
    def install(*responses):
        c = FakeClient(*responses)
        monkeypatch.setattr(agent, "_get_client", lambda: c)
        return c
    return install


@pytest.fixture
def deps(monkeypatch, mock_result):
    """Fixture solver/validator that record calls."""
    calls = {"solve": 0, "validate": 0}

    def solve(bundle, sc):
        calls["solve"] += 1
        return {**copy.deepcopy(mock_result), "scenario_id": sc["scenario_id"]}

    def validate(bundle, sc, res):
        calls["validate"] += 1
        return copy.deepcopy(VALID)

    monkeypatch.setattr(service, "_solve", solve)
    monkeypatch.setattr(service, "_validate", validate)
    return calls


# --------------------------------- parse ----------------------------------- #
def test_bpn_plus_20_percent_gives_30(fake, scenario):
    fake(tool(status="ready", changes=[{"airport_id": "BPN", "mode": "percent_change", "value": 20}]))
    p = agent.parse_request("Increase BPN demand by 20%", scenario)
    assert p == {"schema_version": "1.0", "status": "ready",
                 "changes": [{"airport_id": "BPN", "new_demand_t_per_year": 30.0}], "question": None}


def test_set_mode(fake, scenario):
    fake(tool(status="ready", changes=[{"airport_id": "TRK", "mode": "set", "value": 40}]))
    assert agent.parse_request("Set Tarakan to 40", scenario)["changes"] == [
        {"airport_id": "TRK", "new_demand_t_per_year": 40.0}]


def test_unknown_airport_clarifies(fake, scenario):
    fake(tool(status="ready", changes=[{"airport_id": "SIN", "mode": "set", "value": 10}]))
    p = agent.parse_request("Set Changi to 10", scenario)
    assert p["status"] == "clarify" and p["changes"] == [] and p["question"]


def test_negative_demand_rejected_by_parser(fake, scenario):
    fake(tool(status="ready", changes=[{"airport_id": "BPN", "mode": "percent_change", "value": -150}]))
    p = agent.parse_request("Cut BPN by 150%", scenario)
    assert p["status"] == "clarify" and "negative" in p["question"]


def test_unknown_fields_rejected(fake, scenario):
    fake(tool(status="ready", changes=[{"airport_id": "BPN", "mode": "set", "value": 30, "yield": 0.9}]))
    assert agent.parse_request("BPN to 30", scenario)["status"] == "clarify"
    fake(tool(status="ready", changes=[], refinery_yield=0.9))
    assert agent.parse_request("x", scenario)["status"] == "clarify"


def test_unsupported_request(fake, scenario):
    fake(tool(status="unsupported", changes=[], question="Only airport demand changes are supported."))
    p = agent.parse_request("Make refineries cheaper", scenario)
    assert p["status"] == "unsupported" and p["changes"] == []


# ------------------------------ apply_patch -------------------------------- #
def test_apply_patch_does_not_mutate_and_gets_fresh_id(scenario):
    original = copy.deepcopy(scenario)
    patch = {"schema_version": "1.0", "status": "ready",
             "changes": [{"airport_id": "BPN", "new_demand_t_per_year": 30}], "question": None}
    new = service.apply_patch(scenario, patch)
    assert scenario == original
    assert new["demand_t_per_year"]["BPN"] == 30.0
    assert new["scenario_id"] != scenario["scenario_id"]
    new["demand_t_per_year"]["PNK"] = 999
    assert scenario["demand_t_per_year"]["PNK"] == original["demand_t_per_year"]["PNK"]


@pytest.mark.parametrize("change", [
    {"airport_id": "BPN", "new_demand_t_per_year": -1},
    {"airport_id": "BPN", "new_demand_t_per_year": float("inf")},
    {"airport_id": "BPN", "new_demand_t_per_year": float("nan")},
    {"airport_id": "XXX", "new_demand_t_per_year": 5},
    {"airport_id": "BPN", "new_demand_t_per_year": "30"},
    {"airport_id": "BPN", "new_demand_t_per_year": 30, "extra": 1},
])
def test_apply_patch_rejects_bad_changes(scenario, change):
    with pytest.raises(ValueError):
        service.apply_patch(scenario, {"schema_version": "1.0", "status": "ready",
                                       "changes": [change], "question": None})


# ------------------------------ run_scenario ------------------------------- #
def test_happy_path_trace_and_schema(fake, deps, scenario):
    original = copy.deepcopy(scenario)
    c = fake(tool(status="ready", changes=[{"airport_id": "BPN", "mode": "percent_change", "value": 20}]),
             text("The plan is feasible with a total annual cost of $24,113,300."))
    r = service.run_scenario(BUNDLE, scenario, "Increase BPN demand by 20%")
    assert tuple(r) == service.RESPONSE_KEYS
    assert r["scenario"]["demand_t_per_year"]["BPN"] == 30.0 and r["clarification"] is None
    assert r["validation"]["valid"] and "24,113,300" in r["explanation"]
    assert scenario == original
    assert service.format_trace() == ("request_received -> patch_requested -> patch_validated -> "
                                      "solver_completed -> checks_passed -> explanation_ready")
    assert len(c.calls) == 2 and deps["solve"] == 1


def test_clarification_never_calls_solver(fake, deps, scenario):
    fake(tool(status="clarify", changes=[], question="Which airport?"))
    r = service.run_scenario(BUNDLE, scenario, "increase demand a bit")
    assert r["result"] is None and r["validation"] is None and r["clarification"] == "Which airport?"
    assert deps["solve"] == 0


def test_infeasible_stays_infeasible(fake, monkeypatch, scenario):
    monkeypatch.setattr(service, "_solve", lambda b, s: {
        "schema_version": "1.0", "scenario_id": s["scenario_id"], "provenance": "solver",
        "status": "infeasible", "runtime_s": 0.1, "mip_gap": None, "message": "Demand exceeds supply after yield",
        "facilities": [], "flows": [], "deliveries_t_per_year": {}, "costs": None})
    monkeypatch.setattr(service, "_validate", lambda b, s, r: {"valid": True, "checks": [], "errors": []})
    c = fake(tool(status="ready", changes=[{"airport_id": "BPN", "mode": "percent_change", "value": 20}]))
    r = service.run_scenario(BUNDLE, scenario, "BPN +20%")
    assert r["result"]["status"] == "infeasible"
    assert r["validation"]["valid"] is False
    assert "NO VALID PLAN" in r["explanation"]
    assert len(c.calls) == 1  # Claude is not asked to explain an infeasible plan


def test_api_failure_is_actionable_and_skips_solver(fake, deps, scenario):
    fake(RuntimeError("timeout"), RuntimeError("timeout"))
    r = service.run_scenario(BUNDLE, scenario, "BPN +20%")
    assert r["result"] is None and "Manual solve" in r["explanation"]
    assert deps["solve"] == 0


def test_retry_once_then_succeed_and_budget(fake, deps, scenario):
    c = fake(RuntimeError("blip"),
             tool(status="ready", changes=[{"airport_id": "BPN", "mode": "set", "value": 30}]),
             RuntimeError("blip again"))
    r = service.run_scenario(BUNDLE, scenario, "BPN to 30")
    assert r["validation"]["valid"]
    assert len(c.calls) == 3  # parse(fail) + parse(retry) + explain(fail, no retry left) - never more
    assert "factual summary" in r["explanation"]


def test_manual_solve_works_without_api(monkeypatch, deps, scenario):
    def boom():
        raise agent.AgentUnavailable("no key")
    monkeypatch.setattr(agent, "_get_client", boom)
    r = service.run_scenario(BUNDLE, scenario, None)
    assert r["validation"]["valid"] and "$24,113,300" in r["explanation"]


def test_ungrounded_numbers_fall_back(fake, deps, scenario):
    fake(tool(status="ready", changes=[{"airport_id": "BPN", "mode": "set", "value": 30}]),
         text("Total cost is $99,999,999."))
    r = service.run_scenario(BUNDLE, scenario, "BPN to 30")
    assert "99,999,999" not in r["explanation"] and "$24,113,300" in r["explanation"]


def test_solver_exception_becomes_error_result(fake, monkeypatch, scenario):
    def crash(b, s):
        raise RuntimeError("HiGHS crashed")
    monkeypatch.setattr(service, "_solve", crash)
    monkeypatch.setattr(service, "_validate", lambda b, s, r: {"valid": False, "checks": [], "errors": ["no solution"]})
    fake(tool(status="ready", changes=[{"airport_id": "BPN", "mode": "set", "value": 30}]))
    r = service.run_scenario(BUNDLE, scenario, "BPN to 30")
    assert r["result"]["status"] == "error" and r["result"]["costs"] is None
    assert r["validation"]["valid"] is False


def test_kt_unit_converted_in_python(fake, scenario):
    fake(tool(status="ready", changes=[{"airport_id": "BPN", "mode": "set", "value": 360, "unit": "kt"}]))
    assert agent.parse_request("Set BPN to 360 kt", scenario)["changes"] == [
        {"airport_id": "BPN", "new_demand_t_per_year": 360000.0}]


def test_millions_and_kt_in_explanation_are_grounded(fake, deps, scenario):
    fake(tool(status="ready", changes=[{"airport_id": "BPN", "mode": "set", "value": 30}]),
         text("Feasible plan costing $24.1 million per year; BPN receives 30.0 kt... no wait, 25 t."))
    r = service.run_scenario(BUNDLE, scenario, "BPN to 30")
    assert "24.1 million" in r["explanation"]


def test_text_reply_without_tool_call_becomes_clarify(fake, scenario):
    fake(text("Sure, I can help with that."))
    p = agent.parse_request("BPN +20%", scenario)
    assert p["status"] == "clarify" and p["changes"] == []
