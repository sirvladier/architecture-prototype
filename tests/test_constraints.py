from copy import deepcopy

import pytest

from src.constraints import check_constraints
from src.explanation import build_explanation
from src.models import apply_case, load_cases, load_model


@pytest.mark.parametrize("kind,parameters,valid,invalid", [
    ("boolean", {"expected": True}, True, False),
    ("boolean", {"expected": False}, False, True),
    ("numeric_min", {"threshold": 3}, 3, 2),
    ("numeric_max", {"threshold": 3}, 3, 4),
    ("categorical", {"allowed_values": ["single"]}, "single", "distributed"),
])
def test_constraint_types_and_evidence(kind, parameters, valid, invalid):
    architecture = {"id": "A1", "name": "Test", "properties": {"p": valid}}
    rule = {"id": "C", "name": "Required property", "type": kind, "property": "p", "enabled": True, **parameters}
    feasible, excluded = check_constraints([architecture], [rule])
    assert feasible == [architecture] and not excluded
    architecture["properties"]["p"] = invalid
    feasible, excluded = check_constraints([architecture], [rule])
    assert not feasible
    violation = excluded[0]["violated_constraints"][0]
    assert violation["actual"] == invalid
    assert violation["constraint_id"] == "C"
    assert violation["reason"] == "condition_failed"


@pytest.mark.parametrize("kind,parameters,value", [
    ("boolean", {"expected": True}, 1),
    ("numeric_min", {"threshold": 0}, True),
    ("numeric_max", {"threshold": 5}, "3"),
    ("numeric_max", {"threshold": 5}, float("nan")),
])
def test_wrong_property_type_fails_closed(kind, parameters, value):
    feasible, excluded = check_constraints([{"id": "A1", "name": "Test", "properties": {"p": value}}], [{"id": "C", "name": "Test", "type": kind, "property": "p", "enabled": True, **parameters}])
    assert not feasible and len(excluded) == 1


def test_missing_property_is_specific_violation():
    model = load_model()
    model.constraints[0]["enabled"] = True
    del model.architectures[0]["properties"]["independent_component_deployment"]
    result = build_explanation(model)
    violation = result.excluded_alternatives[0]["violated_constraints"][0]
    assert violation["reason"] == "missing_property"
    assert violation["actual"] is None


def test_excluded_is_not_ranked_and_reason_is_real():
    model = load_model()
    model.constraints[0]["enabled"] = True
    result = build_explanation(model)
    assert "A1" not in {r["architecture"] for r in result.ranking}
    assert result.excluded_alternatives == [{"architecture": "A1", "name": model.architectures[0]["name"], "status": "excluded", "violated_constraints": [{"constraint_id": "C1", "name": model.constraints[0]["name"], "property": "independent_component_deployment", "actual": False, "operator": "==", "expected": True, "reason": "condition_failed"}]}]


@pytest.mark.parametrize("case_id,status,ranked_count", [("none_feasible", "no_feasible", 0), ("single_feasible", "ok", 1)])
def test_no_or_single_feasible(case_id, status, ranked_count):
    case = next(c for c in load_cases() if c["id"] == case_id)
    result = build_explanation(apply_case(load_model(), case))
    assert result.status == status
    assert len(result.ranking) == ranked_count
    assert not result.main_positive_factors and not result.main_negative_factors
    if ranked_count == 1:
        assert all(row["stable_in_explored_range"] for row in result.sensitivity)


def test_all_violations_are_retained_and_disabled_rules_ignored():
    model = load_model()
    rules = deepcopy(model.constraints)
    rules[1]["property"] = rules[0]["property"]
    for rule in rules[:2]:
        rule["enabled"] = True
    _, excluded = check_constraints(model.architectures, rules)
    assert [v["constraint_id"] for v in excluded[0]["violated_constraints"]] == ["C1", "C2"]
