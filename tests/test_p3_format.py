from copy import deepcopy
import json
import re

import pytest
from streamlit.testing.v1 import AppTest

from src.explanation import build_explanation, presentation
from src.models import ROOT, apply_case, load_cases, load_model
from src.p2_format import format_p2
from src.p3_format import NO_EVENTS, NO_RISKS, NO_UNCERTAINTY, format_p3, percent, sensitivity_events


def case_result(case_id):
    return build_explanation(apply_case(load_model(), next(c for c in load_cases() if c["id"] == case_id)))


def prose(display):
    return "\n".join([display["risk_summary"], display["uncertainty_summary"],
                      *display["risk_texts"], *display["uncertainty_texts"],
                      *display["sensitivity_summary"], display["sensitivity_note"]])


@pytest.mark.parametrize("value,expected", [(1 / 6, "16,7 %"), (0.08666666666667, "8,7 %"),
                                          (0, "0,0 %"), (1, "100,0 %"), (None, "не обнаружено")])
def test_percent_formatting(value, expected):
    assert percent(value) == expected


def test_absent_value_and_explicit_substitution_are_visible_in_summary():
    result = case_result("missing_with_model")
    display = format_p3(result)
    text = display["uncertainty_summary"]
    assert "Интеграционная гибкость" in text
    assert "Сервис-ориентированная архитектура (SOA)" in text
    assert "отсутствует" in text
    assert "Для расчёта использовано явно заданное модельное значение 5" in text
    assert "не считается подтверждённым исходным значением" in text
    assert len(display["closest_events"]) == 3
    assert any(event["kind"] == "switch" for event in display["closest_events"])


def test_estimated_value_is_described_in_russian():
    display = format_p3(case_result("estimated_data"))
    assert "В расчёте используется оценочное значение 5" in display["uncertainty_summary"]
    assert "Интеграционная гибкость" in display["uncertainty_summary"]
    assert "estimated" not in prose(display)


def test_no_risk_and_no_uncertainty_have_correct_phrases():
    display = format_p3(build_explanation(load_model()))
    assert display["risk_summary"] == NO_RISKS
    assert display["risk_texts"] == [NO_RISKS]
    assert display["uncertainty_summary"] == NO_UNCERTAINTY


def test_risk_is_described_with_criterion_and_actual_rating():
    result = case_result("clear_winner")
    display = format_p3(result)
    assert result.risks
    for risk in result.risks:
        assert risk["text"] in "\n".join(display["risk_texts"])
    assert "Масштабируемость» составляет 2 из 5" in display["risk_texts"][0]
    assert "R1" not in display["risk_texts"][0]


def test_multiple_uncertain_values_have_counts_and_all_details():
    model = load_model()
    model.architectures[0]["ratings"]["K1"] = {"value": 2, "status": "estimated"}
    model.architectures[1]["ratings"]["K3"] = {"value": None, "model_value": 5, "status": "missing"}
    result = build_explanation(model)
    display = format_p3(result)
    assert "оценочных значений: 1" in display["uncertainty_summary"]
    assert "отсутствующих исходных значений: 1" in display["uncertainty_summary"]
    assert "Число использованных в расчёте явных модельных подстановок: 1" in display["uncertainty_summary"]
    assert len(display["uncertainty_texts"]) == 2
    assert "модельное значение 5" in display["uncertainty_texts"][1]


def test_excluded_uncertain_data_is_not_presented_as_used_for_selection():
    model = load_model()
    model.constraints[0]["enabled"] = True
    model.architectures[0]["ratings"]["K1"] = {"value": None, "model_value": 2, "status": "missing"}
    display = format_p3(build_explanation(model))
    assert "Архитектура исключена обязательными ограничениями" in display["uncertainty_summary"]
    assert "это значение не повлияло на выбор" in display["uncertainty_summary"]
    assert "Для расчёта использовано" not in display["uncertainty_summary"]


def test_blocked_calculation_never_claims_that_estimates_were_used():
    model = load_model()
    model.architectures[0]["ratings"]["K1"] = {"value": None, "status": "missing"}
    model.architectures[1]["ratings"]["K3"] = {"value": 5, "status": "estimated"}
    display = format_p3(build_explanation(model))
    assert "В исходных данных задано оценочное значение" in display["uncertainty_texts"][1]
    assert "Расчёт итогового рейтинга не выполнен" in display["uncertainty_texts"][1]
    assert not display["closest_events"]


def test_three_nearest_events_are_selected_across_all_criteria_by_absolute_delta():
    result = case_result("sensitive_weights")
    before = deepcopy(result.to_dict())
    events = sensitivity_events(result)
    assert len(events) > 3
    assert [e["delta"] for e in events] == sorted(e["delta"] for e in events)
    for event in events:
        assert event["delta"] == abs(event["weight"] - event["original_weight"])
    assert format_p3(result)["closest_events"] == events[:3]
    assert len(format_p3(result)["sensitivity_summary"]) == 3
    assert result.to_dict() == before


def test_tie_and_switch_are_different_events_and_direction_is_automatic():
    result = case_result("sensitive_weights")
    events = sensitivity_events(result)
    tied = next(e for e in events if e["criterion"] == "K1" and e["kind"] == "tie")
    switched = next(e for e in events if e["criterion"] == "K1" and e["kind"] == "switch")
    assert "снижении" in tied["text"] and "рекомендация теряет однозначность" in tied["text"]
    assert "предпочтительной становится «Монолитная архитектура»" in switched["text"]
    assert tied["weight"] == pytest.approx(0.5)
    assert switched["weight"] == pytest.approx(0.49)
    increased = next(e for e in events if e["criterion"] == "K4" and e["kind"] == "switch")
    assert "увеличении" in increased["text"]


def test_no_events_is_limited_to_examined_grid():
    display = format_p3(case_result("single_feasible"))
    assert display["sensitivity_summary"] == [NO_EVENTS]
    assert "шагу сетки" in display["sensitivity_note"]
    assert "только одна допустимая архитектура" in display["sensitivity_note"]
    assert "гарантированно" not in prose(display)


def test_incomplete_sensitivity_is_not_called_stable():
    model = load_model()
    for criterion in model.criteria:
        criterion["weight"] = int(criterion["id"] == "K1")
    model.settings["sensitivity"]["zero_remainder_policy"] = "skip"
    display = format_p3(build_explanation(model))
    assert "Исследование выполнено не полностью" in display["sensitivity_note"]


@pytest.mark.parametrize("case_id", [c["id"] for c in load_cases()])
def test_p3_has_no_technical_tokens_or_long_floats_and_preserves_all_results(case_id, monkeypatch):
    result = case_result(case_id)
    before = deepcopy(result.to_dict())
    p1, p2 = presentation(result, "P1"), presentation(result, "P2")
    formatted_p2 = format_p2(result)
    def forbidden(*args, **kwargs):
        raise AssertionError("P3 formatter must not recalculate")
    monkeypatch.setattr("src.explanation.build_explanation", forbidden)
    monkeypatch.setattr("src.explanation.analyze_sensitivity", forbidden)
    monkeypatch.setattr("src.explanation.evaluate_risks", forbidden)
    display = format_p3(result)
    text = prose(display)
    assert not re.search(r"\b(?:A[123]|K[1-6]|R\d+|None|missing|estimated|confirmed|tie|switch)\b", text)
    assert not re.search(r"\d+[.,]\d{5,}", text)
    assert "участвует в рейтинге" not in text
    assert "None" not in json.dumps(display["sensitivity_table"], ensure_ascii=False)
    assert presentation(result, "P1") == p1
    assert presentation(result, "P2") == p2
    assert format_p2(result) == formatted_p2
    assert presentation(result, "P3")["recommended_architecture"] == p1["recommended_architecture"] == p2["recommended_architecture"]
    assert result.to_dict() == before


def outside_expanders(block):
    values = []
    for element in block.children.values():
        if element.type == "expander":
            continue
        if hasattr(element, "children"):
            values.extend(outside_expanders(element))
        elif element.type in {"markdown", "caption", "warning", "subheader"}:
            values.append(element.value)
    return values


@pytest.mark.parametrize("case_id", ["missing_with_model", "clear_winner", "estimated_data", "tie", "none_feasible", "single_feasible"])
def test_streamlit_p3_reuses_p2_and_keeps_diagnostics_closed(case_id):
    app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=30).run()
    app.selectbox(key="case_id").set_value(case_id).run()
    app.radio(key="presentation_mode").set_value("P2").run()
    before = deepcopy(app.session_state["result"].to_dict())
    p2_panel = next(t for t in app.tabs if t.label == "Объяснение")
    p2_headings = [h.value for h in p2_panel.subheader]
    p2_paragraphs = outside_expanders(p2_panel)
    app.radio(key="presentation_mode").set_value("P3").run()
    assert not app.exception
    panel = next(t for t in app.tabs if t.label == "Объяснение")
    headings = [h.value for h in panel.subheader]
    extras = ["Риски, неопределённость и устойчивость", "Риски", "Неопределённость и пропуски", "Чувствительность рекомендации"]
    assert headings == p2_headings + extras
    main = outside_expanders(panel)
    for paragraph in p2_paragraphs:
        assert paragraph in main
    assert not re.search(r"\b(?:A[123]|K[1-6]|R\d+|None|missing|estimated|confirmed|tie|switch)\b", "\n".join(main))
    detailed = next(e for e in panel.expander if e.label == "Подробный анализ чувствительности")
    assert detailed.proto.expanded is False
    assert detailed.json
    for expander in panel.expander:
        if expander.label.startswith("Подробные данные"):
            assert expander.proto.expanded is False
    expected = format_p3(app.session_state["result"])
    assert expected["risk_summary"] in main
    assert expected["uncertainty_summary"] in main
    assert all(paragraph in main for paragraph in expected["sensitivity_summary"])
    assert app.session_state["result"].to_dict() == before
