from copy import deepcopy

import pytest

from src.explanation import build_explanation
from src.models import apply_case, load_cases, load_model
from src.risks import evaluate_risks


def test_top_factors_are_actual_contribution_differences():
    case = next(c for c in load_cases() if c["id"] == "clear_winner")
    model = apply_case(load_model(), case)
    model.settings["top_factor_count"] = 2
    result = build_explanation(model)
    winner, runner_up = result.ranking[:2]
    differences = {key: winner["contributions"][key] - runner_up["contributions"][key] for key in winner["contributions"]}
    positive = sorted((key for key, value in differences.items() if value > 0), key=lambda key: (-differences[key], key))[:2]
    negative = sorted((key for key, value in differences.items() if value < 0), key=lambda key: (differences[key], key))[:2]
    assert [f["criterion"] for f in result.main_positive_factors] == positive
    assert [f["criterion"] for f in result.main_negative_factors] == negative
    assert all(f["difference"] == differences[f["criterion"]] for f in result.main_positive_factors + result.main_negative_factors)
    assert sum(differences.values()) == pytest.approx(winner["score"] - runner_up["score"])
    model.settings["top_factor_count"] = 0
    empty = build_explanation(model)
    assert not empty.main_positive_factors and not empty.main_negative_factors


@pytest.mark.parametrize("operator,threshold,passing,failing", [
    ("<", 3, 2, 3), ("<=", 3, 3, 4), (">", 3, 4, 3),
    (">=", 3, 3, 2), ("==", 3, 3, 4), ("in", [2, 3], 2, 4),
])
def test_risk_only_when_configured_condition_matches(operator, threshold, passing, failing):
    rule = {"id": "R", "architecture": "A3", "criterion": "K5", "operator": operator, "threshold": threshold, "text": "Model risk"}
    ratings = {"K5": {"value": passing, "status": "confirmed"}}
    assert len(evaluate_risks("A3", [rule], {"A3": {"K5": passing}}, ratings)) == 1
    assert evaluate_risks("A3", [rule], {"A3": {"K5": failing}}, ratings) == []
    assert evaluate_risks("A1", [rule], {}, {}) == []


def test_risk_keeps_model_value_provenance():
    model = load_model()
    for criterion in model.criteria:
        criterion["weight"] = int(criterion["id"] == "K1")
    model.architectures[2]["ratings"]["K5"] = {"value": None, "status": "missing", "model_value": 2}
    result = build_explanation(model)
    risk = next(r for r in result.risks if r["id"] == "R2")
    assert risk["used_value"] == 2
    assert risk["data_status"] == "missing" and risk["model_value_used"]
    changed = deepcopy(model)
    changed.risks[1]["threshold"] = 1
    assert "R2" not in {r["id"] for r in build_explanation(changed).risks}
