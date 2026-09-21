import math

import pytest

from src.constraints import check_constraints
from src.explanation import build_explanation
from src.models import apply_case, load_cases, load_model
from src.scoring import rank_alternatives
from src.sensitivity import candidate_weights, reweight
from src.uncertainty import resolve_values


def sensitive_model():
    case = next(c for c in load_cases() if c["id"] == "sensitive_weights")
    return apply_case(load_model(), case)


def test_every_reported_switch_and_tie_reproduces():
    model = sensitive_model()
    result = build_explanation(model)
    feasible, _ = check_constraints(model.architectures, model.constraints)
    values, _, _ = resolve_values(model.architectures, {a["id"] for a in feasible}, model.settings["missing_policy"])
    for row in result.sensitivity:
        for detail in row["directions"].values():
            for field, expected_status in (("switch_weight", "ok"), ("first_tie_weight", "tie")):
                if detail[field] is None:
                    continue
                weights = reweight(result.normalized_weights, row["criterion"], detail[field])
                _, winners, status = rank_alternatives(feasible, model.criteria, values, weights, model.settings["tie_tolerance"])
                assert status == expected_status
                if expected_status == "ok":
                    assert winners == [detail["new_winner"]]
                    assert winners[0] != result.recommended_architecture
                else:
                    assert winners == detail["tie_winners"]


def test_tie_and_switch_are_separate_nearest_points_in_both_directions():
    result = build_explanation(sensitive_model())
    by_id = {row["criterion"]: row for row in result.sensitivity}
    decreasing = by_id["K1"]
    assert decreasing["nearest_tie_weight"] == pytest.approx(0.5)
    assert decreasing["tie_delta"] == pytest.approx(0.01)
    assert decreasing["nearest_switch_weight"] == pytest.approx(0.49)
    assert decreasing["delta"] == pytest.approx(0.02)
    assert decreasing["new_winner"] == "A1"
    assert set(decreasing["tie_winners"]) == {"A1", "A2", "A3"}
    assert decreasing["directions"]["decrease"]["last_tested_weight"] == 0
    increasing = by_id["K4"]
    assert increasing["nearest_tie_weight"] == pytest.approx(0.5)
    assert increasing["nearest_switch_weight"] == pytest.approx(0.51)
    assert increasing["signed_delta"] > 0


def test_tie_at_boundary_is_loss_of_uniqueness_without_switch():
    model = sensitive_model()
    model.settings["sensitivity"]["min_weight"] = 0.5
    result = build_explanation(model)
    row = next(r for r in result.sensitivity if r["criterion"] == "K1")
    assert row["nearest_tie_weight"] == pytest.approx(0.5)
    assert row["nearest_switch_weight"] is None
    assert row["status"] == "tie_found"
    assert row["no_switch_in_explored_range"] is True
    assert row["unique_winner_preserved"] is False
    assert row["stable_in_explored_range"] is False


def test_search_continues_after_switch_to_find_later_tie():
    model = load_model()
    for criterion in model.criteria:
        criterion["weight"] = int(criterion["id"] == "K4")
    # At x=0 A1 wins; the A1/A2 crossing lies off-grid; A2/A3 tie at x=.8.
    for architecture, pair in zip(model.architectures, [(1, 5), (4, 4), (4.75, 1)], strict=True):
        architecture["ratings"]["K1"]["value"] = pair[0]
        architecture["ratings"]["K4"]["value"] = pair[1]
    model.settings["sensitivity"]["step"] = 0.1
    result = build_explanation(model)
    row = next(r for r in result.sensitivity if r["criterion"] == "K1")
    assert row["nearest_switch_weight"] == pytest.approx(0.3)
    assert row["nearest_tie_weight"] == pytest.approx(0.8)
    assert set(row["tie_winners"]) == {"A2", "A3"}
    assert row["directions"]["increase"]["last_tested_weight"] == 1


@pytest.mark.parametrize("key,target", [("K1", 0), ("K1", 1), ("K2", 0.37)])
def test_rescaling_preserves_sum_and_other_weight_ratios(key, target):
    original = {"K1": 0.2, "K2": 0.3, "K3": 0.5}
    weights = reweight(original, key, target)
    assert weights[key] == pytest.approx(target)
    assert math.fsum(weights.values()) == pytest.approx(1)
    others = [k for k in original if k != key]
    if target != 1:
        assert weights[others[0]] / weights[others[1]] == pytest.approx(original[others[0]] / original[others[1]])


def test_zero_remainder_policy_is_explicit():
    weights = {"K1": 1, "K2": 0, "K3": 0}
    assert reweight(weights, "K1", 0.6, "skip") is None
    assert reweight(weights, "K1", 0.6, "uniform") == pytest.approx({"K1": 0.6, "K2": 0.2, "K3": 0.2})
    model = load_model()
    for criterion in model.criteria:
        criterion["weight"] = int(criterion["id"] == "K1")
    model.settings["sensitivity"]["zero_remainder_policy"] = "skip"
    row = build_explanation(model).sensitivity[0]
    assert row["status"] == "partially_explored"
    assert row["stable_in_explored_range"] is None


def test_endpoints_checked_even_when_not_step_aligned():
    assert candidate_weights(0.13, 0, 0.1) == pytest.approx([0.03, 0])
    assert candidate_weights(0.95, 1, 0.1) == [1]
