from copy import deepcopy
import json
import shutil

import pytest
from streamlit.testing.v1 import AppTest

from src.explanation import build_explanation, extended_summary, format_weight, presentation, validate_explanation
from src.models import ROOT, ConfigError, apply_case, load_cases, load_model
from src.user_cases import UserCase, build_user_model, configuration_identity, export_user_case, load_property_catalog


def user_case(weights=None, constraints=None):
    return UserCase.from_dict({"weights": weights if weights is not None else {f"K{i}": 1 for i in range(1, 7)}, "constraints": constraints or []})


def requirement(prop="independent_component_deployment", operator="==", value=True):
    return {"name": "Обязательное требование", "property": prop, "operator": operator, "required_value": value}


@pytest.mark.parametrize("forbidden", ["ratings", "architectures", "risks", "criteria", "settings", "uncertain_data"])
def test_user_case_rejects_research_parameter_overrides(forbidden):
    with pytest.raises(ConfigError, match="только веса и ограничения"):
        UserCase.from_dict({"weights": {}, "constraints": [], forbidden: {}})
    with pytest.raises(TypeError):
        UserCase(weights={}, constraints=[], **{forbidden: {}})


def test_user_model_loads_architecture_values_and_directions_from_configuration(tmp_path):
    shutil.copytree(ROOT / "config", tmp_path / "config")
    # Only the isolated test fixture changes. The project's model is untouched.
    path = tmp_path / "config" / "architectures.json"
    document = json.loads(path.read_text(encoding="utf-8"))
    document["architectures"][0]["ratings"]["K1"]["value"] = 4.125
    path.write_text(json.dumps(document), encoding="utf-8")
    path = tmp_path / "config" / "criteria.json"
    criteria = json.loads(path.read_text(encoding="utf-8"))
    criteria["criteria"][0]["direction"] = "minimize"
    path.write_text(json.dumps(criteria), encoding="utf-8")
    model = build_user_model(user_case(), root=tmp_path)
    assert model.architectures == document["architectures"]
    assert model.criteria[0]["direction"] == "minimize"
    assert model.labels["architecture_config_id"] == configuration_identity(tmp_path)["architecture_config_id"]
    assert model.labels["architecture_config_id"] != configuration_identity()["architecture_config_id"]


def test_weights_are_normalized_and_can_change_winner_without_changing_architectures():
    baseline = deepcopy(load_model().architectures)
    first = build_explanation(build_user_model(user_case({"K1": 1, "K2": 1, "K3": 1, "K4": 4, "K5": 4, "K6": 3})))
    second = build_explanation(build_user_model(user_case({"K1": 5, "K2": 0, "K3": 0, "K4": 0, "K5": 0, "K6": 0})))
    assert sum(first.normalized_weights.values()) == pytest.approx(1)
    assert first.normalized_weights["K4"] == pytest.approx(4 / 14)
    assert first.recommended_architecture == "A1"
    assert second.recommended_architecture == "A3"
    assert first.input_snapshot["architectures"] == second.input_snapshot["architectures"] == baseline


@pytest.mark.parametrize("value", [0, -1, float("nan"), float("inf"), True])
def test_invalid_user_weights_rejected(value):
    with pytest.raises(ConfigError):
        build_user_model(user_case({f"K{i}": value for i in range(1, 7)}))


@pytest.mark.parametrize("constraint,excluded", [
    (requirement(), {"A1"}),
    (requirement(value=False), {"A2", "A3"}),
    (requirement("single_deployment_unit", "==", True), {"A2", "A3"}),
    (requirement("single_deployment_unit", "==", False), {"A1"}),
])
def test_user_constraints_use_existing_eligibility_checks(constraint, excluded):
    result = build_explanation(build_user_model(user_case(constraints=[constraint])))
    assert {r["architecture"] for r in result.excluded_alternatives} == excluded
    assert not excluded.intersection(r["architecture"] for r in result.ranking)
    assert all(r["violated_constraints"][0]["name"] == constraint["name"] for r in result.excluded_alternatives)


@pytest.mark.parametrize("constraint", [
    requirement("not_a_property"), requirement(operator=">="), requirement(value=1),
    requirement("single_deployment_unit", "in", []), requirement("single_deployment_unit", "==", "Да"),
    requirement("K1", ">=", 4), {**requirement(), "ratings": {}}, {**requirement(), "name": " "},
])
def test_invalid_requirements_are_rejected(constraint):
    with pytest.raises(ConfigError):
        build_user_model(user_case(constraints=[constraint]))


def test_model_and_user_paths_share_decision_results():
    case = next(c for c in load_cases() if c["id"] == "one_excluded")
    model_result = build_explanation(apply_case(load_model(), case))
    user_result = build_explanation(build_user_model(user_case(constraints=[requirement()])))
    assert model_result.ranking == user_result.ranking
    assert model_result.risks == user_result.risks
    assert model_result.sensitivity == user_result.sensitivity
    for mode in ("P1", "P2", "P3"):
        assert presentation(user_result, mode)["recommended_architecture"] == model_result.recommended_architecture
    assert validate_explanation(user_result) == []


def test_export_contains_calculated_weights_constraints_and_config_identifiers():
    case = user_case(constraints=[requirement(), requirement("single_deployment_unit", "==", False)])
    result = build_explanation(build_user_model(case))
    saved = json.loads(json.dumps(export_user_case(result), allow_nan=False))
    assert saved["weights"] == case.weights
    assert saved["normalized_weights"] == result.normalized_weights
    assert saved["constraints"] == case.constraints
    assert saved["architecture_config_id"] == configuration_identity()["architecture_config_id"]
    assert saved["model_config_id"] == configuration_identity()["model_config_id"]
    replay = build_explanation(build_user_model(UserCase.from_dict({k: saved[k] for k in ("weights", "constraints")})))
    assert replay.to_dict() == result.to_dict()
    case.weights["K1"] = 99
    case.constraints.clear()
    assert export_user_case(result) == saved


@pytest.mark.parametrize("case_id", [c["id"] for c in load_cases()])
def test_p3_summary_matches_risks_uncertainty_and_sensitivity(case_id):
    result = build_explanation(apply_case(load_model(), next(c for c in load_cases() if c["id"] == case_id)))
    before = deepcopy(result.to_dict())
    paragraphs = extended_summary(result)
    text = "\n".join(paragraphs)
    assert presentation(result, "P3")["summary"] == paragraphs
    assert result.to_dict() == before
    for risk in result.risks:
        assert risk["text"] in text
    if not result.uncertain_data:
        assert "не содержат оценочных или пропущенных" in text
    else:
        assert f"оценочных значений: {sum(u['status'] == 'estimated' for u in result.uncertain_data)}" in text
        for item in result.uncertain_data:
            if item["model_value_used"]:
                assert "модельная подстановка " + format_weight(item["used_value"]) in text
                assert "статус остаётся missing" in text
    names = {a["id"]: a["name"] for a in result.input_snapshot["architectures"]}
    for row in result.sensitivity:
        relevant = "\n".join(p for p in paragraphs if p.startswith(row["name"] + ":"))
        if row["nearest_tie_weight"] is not None:
            assert "до " + format_weight(row["nearest_tie_weight"]) in relevant and "(tie)" in relevant
        if row["nearest_switch_weight"] is not None:
            assert "до " + format_weight(row["nearest_switch_weight"]) in relevant and "(switch)" in relevant
            assert names[row["new_winner"]] in relevant
    assert validate_explanation(result) == []


def test_user_ui_is_read_only_for_model_and_calculates_only_on_explicit_action(monkeypatch):
    import src.explanation as module
    original = module.build_explanation
    calls = []
    def counted(*args, **kwargs):
        calls.append(args[0].case_id)
        return original(*args, **kwargs)
    monkeypatch.setattr(module, "build_explanation", counted)
    app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=30).run()
    app.radio(key="work_mode").set_value("Пользовательский кейс").run()
    assert not app.exception
    assert app.session_state["result"] is None
    initial_count = len(calls)
    assert not app.get("data_editor")
    assert all("rating" not in (widget.key or "") for widget in app.number_input)
    app.number_input(key="user_weight_K1").set_value(5).run()
    app.button(key="add_constraint").click().run()
    assert len(calls) == initial_count
    app.button(key="calculate_user").click().run()
    assert not app.exception
    assert len(calls) == initial_count + 1
    result = app.session_state["result"]
    assert result.input_snapshot["architectures"] == load_model().architectures
    assert {r["architecture"] for r in result.excluded_alternatives} == {"A1"}
    assert len(app.get("download_button")) == 2
    for mode in ("P1", "P2", "P3"):
        app.radio(key="presentation_mode").set_value(mode).run()
        assert not app.exception
        assert app.session_state["result"].calculation_id == result.calculation_id
    assert len(calls) == initial_count + 1
    app.button(key="remove_constraint_1").click().run()
    assert not app.exception
    assert len(calls) == initial_count + 1
    assert app.session_state["result"] is None
    assert not app.get("download_button")
    app.button(key="calculate_user").click().run()
    assert not app.exception
    assert not app.session_state["result"].excluded_alternatives


def test_user_ui_zero_weights_do_not_run_engine(monkeypatch):
    app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=30).run()
    app.radio(key="work_mode").set_value("Пользовательский кейс").run()
    def forbidden(*args, **kwargs):
        raise AssertionError("Invalid inputs must not reach the calculation engine")
    monkeypatch.setattr("src.explanation.build_explanation", forbidden)
    for i in range(1, 7):
        app.number_input(key=f"user_weight_K{i}").set_value(0)
    app.button(key="calculate_user").click().run()
    assert not app.exception
    assert app.session_state["result"] is None
    assert any("Все веса равны нулю" in message.value for message in app.error)


def test_user_ui_boolean_controls_and_mode_persistence():
    app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=30).run()
    app.radio(key="work_mode").set_value("Пользовательский кейс").run()
    app.button(key="add_constraint").click().run()
    assert app.selectbox(key="user_property_1").options == ["Независимое развёртывание компонентов", "Единая развёртываемая единица"]
    app.selectbox(key="user_property_1").set_value("single_deployment_unit").run()
    assert app.selectbox(key="user_operator_1_single_deployment_unit").options == ["Равно"]
    assert app.selectbox(key="user_required_1_single_deployment_unit").options == ["Да", "Нет"]
    app.button(key="add_constraint").click().run()
    app.selectbox(key="user_required_2_independent_component_deployment").set_value(False).run()
    app.button(key="calculate_user").click().run()
    assert not app.exception
    result = app.session_state["result"]
    assert result.recommended_architecture == "A1"
    assert len(result.excluded_alternatives) == 2
    app.radio(key="work_mode").set_value("Модельный кейс").run()
    app.radio(key="work_mode").set_value("Пользовательский кейс").run()
    assert not app.exception
    assert app.session_state["result"].calculation_id == result.calculation_id
    assert len(app.session_state["user_constraints"]) == 2
