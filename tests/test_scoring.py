import math

import pytest

from src.explanation import build_explanation
from src.models import ConfigError, apply_case, load_cases, load_model, validate_model
from src.scoring import normalize_weights, normalized_value


@pytest.mark.parametrize("weights", [{"a": 1, "b": 2, "c": 0}, {"a": 0.3, "b": 0.7}, {"a": 1e308, "b": 1e308}])
def test_normalized_weights_sum_to_one(weights):
    normalized = normalize_weights(weights)
    assert math.fsum(normalized.values()) == pytest.approx(1)
    assert all(0 <= value <= 1 for value in normalized.values())


@pytest.mark.parametrize("weights", [{}, {"a": 0}, {"a": -1}, {"a": float("nan")}, {"a": float("inf")}, {"a": True}])
def test_invalid_weights_rejected(weights):
    with pytest.raises(ConfigError):
        normalize_weights(weights)


def test_weighted_sum_and_contributions_match_hand_calculation():
    model = load_model()
    for criterion in model.criteria:
        criterion["weight"] = {"K1": 1, "K4": 3}.get(criterion["id"], 0)
    result = build_explanation(model)
    monolith = next(row for row in result.ranking if row["architecture"] == "A1")
    assert monolith["contributions"]["K1"] == pytest.approx(0.25 * 2 / 5)
    assert monolith["contributions"]["K4"] == pytest.approx(0.75 * 5 / 5)
    assert monolith["score"] == pytest.approx(0.85)
    assert all(0 <= row["score"] <= 1 for row in result.ranking)


def test_direction_from_configuration_changes_recommendation():
    model = load_model()
    for criterion in model.criteria:
        criterion["weight"] = 1 if criterion["id"] == "K1" else 0
    assert build_explanation(model).recommended_architecture == "A3"
    model.criteria[0]["direction"] = "minimize"
    result = build_explanation(model)
    assert result.recommended_architecture == "A1"
    assert result.score == pytest.approx((6 - 2) / 5)
    assert normalized_value(1, "minimize") == 1
    assert normalized_value(5, "minimize") == pytest.approx(0.2)
    assert normalized_value(5, "maximize") == 1


def test_tie_has_no_hidden_winner():
    case = next(c for c in load_cases() if c["id"] == "tie")
    result = build_explanation(apply_case(load_model(), case))
    assert result.status == "tie"
    assert set(result.winners) == {"A1", "A2", "A3"}
    assert result.recommended_architecture is None and result.score is None
    assert not result.main_positive_factors and not result.risks


@pytest.mark.parametrize("rating", [{"value": 6, "status": "confirmed"}, {"value": 3, "status": "unknown"}, {"value": 4, "status": "missing"}, {"value": None, "status": "missing", "model_value": float("inf")}])
def test_bad_ratings_are_rejected(rating):
    model = load_model()
    model.architectures[0]["ratings"]["K1"] = rating
    with pytest.raises(ConfigError):
        validate_model(model)


def test_unknown_direction_and_architecture_rejected():
    model = load_model()
    model.criteria[0]["direction"] = "bigger"
    with pytest.raises(ConfigError):
        validate_model(model)
    model = load_model()
    model.architectures[0]["id"] = "A4"
    with pytest.raises(ConfigError):
        validate_model(model)
