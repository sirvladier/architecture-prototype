from copy import deepcopy
import json

import pytest

from src.experiment import run_experiment, validate_case
from src.explanation import build_explanation, presentation, validate_explanation
from src.models import ROOT, apply_case, load_cases, load_model


@pytest.mark.parametrize("case_id", [case["id"] for case in load_cases()])
def test_all_synthetic_cases_validate(case_id):
    case = next(c for c in load_cases() if c["id"] == case_id)
    result = build_explanation(apply_case(load_model(), case))
    assert validate_explanation(result) == []
    assert validate_case(result, case.get("expected", {})) == []
    assert json.loads(json.dumps(result.to_dict(), allow_nan=False))["calculation_id"] == result.calculation_id


def test_uncertainty_keeps_status_observation_and_model_value_separate():
    model = load_model()
    model.architectures[0]["ratings"]["K1"] = {"value": 2, "status": "estimated"}
    model.architectures[1]["ratings"]["K3"] = {"value": None, "status": "missing", "model_value": 5}
    result = build_explanation(model)
    assert len(result.uncertain_data) == 2
    missing = next(u for u in result.uncertain_data if u["status"] == "missing")
    assert missing["original_value"] is None
    assert missing["model_value"] == missing["used_value"] == 5
    assert missing["model_value_used"] is True
    assert missing["source"] == "model_value"
    assert result.based_on_incomplete_data is True
    assert missing in presentation(result, "P3")["uncertain_data"]


def test_missing_blocks_even_with_zero_weight_and_never_silently_disappears():
    model = load_model()
    model.criteria[0]["weight"] = 0
    model.architectures[0]["ratings"]["K1"] = {"value": None, "status": "missing"}
    result = build_explanation(model)
    assert result.status == "insufficient_data"
    assert result.recommended_architecture is None
    assert not result.ranking
    assert result.blocking_data[0]["used_value"] is None


def test_block_policy_disallows_model_substitution():
    case = next(c for c in load_cases() if c["id"] == "missing_with_model")
    model = apply_case(load_model(), case)
    model.settings["missing_policy"] = "block"
    result = build_explanation(model)
    assert result.status == "insufficient_data"
    assert result.uncertain_data[0]["model_value"] == 5
    assert result.uncertain_data[0]["used_value"] is None
    assert result.uncertain_data[0]["model_value_used"] is False


def test_missing_excluded_alternative_does_not_block_feasible_ranking():
    model = load_model()
    model.constraints[0]["enabled"] = True
    model.architectures[0]["ratings"]["K1"] = {"value": None, "status": "missing"}
    result = build_explanation(model)
    assert result.status == "ok"
    assert result.uncertain_data[0]["used_in_ranking"] is False
    assert not result.based_on_incomplete_data


def test_presentations_share_calculations_do_not_recompute_or_mutate(monkeypatch):
    result = build_explanation(load_model())
    before = deepcopy(result.to_dict())
    def forbidden(*args, **kwargs):
        raise AssertionError("Presentation must not run calculations")
    monkeypatch.setattr("src.explanation.build_explanation", forbidden)
    monkeypatch.setattr("src.explanation.rank_alternatives", forbidden)
    views = [presentation(result, mode) for mode in ("P1", "P2", "P3")]
    for field in ("status", "recommended_architecture", "score", "ranking", "calculation_id"):
        assert views[0][field] == views[1][field] == views[2][field]
    assert "risks" not in views[0] and "risks" not in views[1]
    assert "main_positive_factors" not in views[0]
    assert "contributions" not in views[0]["ranking"][0]
    views[2]["ranking"][0]["score"] = -1
    assert result.to_dict() == before


def test_identical_inputs_have_identical_results():
    assert build_explanation(load_model()).to_dict() == build_explanation(load_model()).to_dict()


def test_experiment_writes_csv_and_replayable_json(tmp_path):
    output = tmp_path / "experiment.csv"
    frame = run_experiment(output=output)
    assert frame["validation_passed"].all()
    assert len(frame) == len(load_cases())
    assert output.exists()
    records = json.loads(output.with_suffix(".json").read_text(encoding="utf-8"))
    assert len(records) == len(frame)
    assert "input_snapshot" in records[0]["explanation"]


def test_validation_detects_corrupted_explanation():
    result = build_explanation(load_model())
    result.ranking[0]["score"] = -1
    assert validate_explanation(result)


def test_streamlit_modes_reuse_result_and_show_missing_model_value(monkeypatch):
    from streamlit.testing.v1 import AppTest
    import src.explanation as explanation_module

    calls = []
    original = explanation_module.build_explanation
    def counted(*args, **kwargs):
        calls.append(1)
        return original(*args, **kwargs)
    monkeypatch.setattr(explanation_module, "build_explanation", counted)
    app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=30).run()
    assert not app.exception
    assert len(calls) == 1
    initial = app.session_state["result"].to_dict()
    for mode in ("P2", "P3", "P1"):
        app.radio(key="presentation_mode").set_value(mode).run()
        assert not app.exception
        assert app.session_state["result"].to_dict() == initial
    assert len(calls) == 1
    app.selectbox(key="case_id").set_value("missing_with_model").run()
    app.radio(key="presentation_mode").set_value("P3").run()
    assert not app.exception
    assert len(calls) == 2
    assert any("model_value = 5" in element.value for element in app.markdown)
    assert app.session_state["result"].uncertain_data[0]["model_value_used"] is True
