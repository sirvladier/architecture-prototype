from copy import deepcopy
import json
import re

import pytest
from streamlit.testing.v1 import AppTest

from src.explanation import build_explanation, presentation
from src.models import ROOT, apply_case, load_cases, load_model
from src.p2_format import NO_COMPETITOR, NO_EXCLUSIONS, NO_FEASIBLE, TIED_RESULT, format_p2


def case_result(case_id):
    return build_explanation(apply_case(load_model(), next(c for c in load_cases() if c["id"] == case_id)))


def main_text(display):
    return "\n".join([*display["summary"], *display["exclusion_texts"],
                       *(display[key] or "" for key in ("status_text", "comparison_title", "comparison_message", "positive_text", "negative_text"))])


def test_p2_uses_full_names_and_russian_criteria_without_technical_numbers():
    result = build_explanation(load_model())
    display = format_p2(result)
    text = main_text(display)
    names = {a["id"]: a["name"] for a in result.input_snapshot["architectures"]}
    assert names[result.recommended_architecture] in text
    assert names[result.runner_up] in text
    assert not re.search(r"\b(?:A[123]|K[1-6])\b", text)
    assert not re.search(r"\d+[.,]\d+", text)
    for factor in result.main_positive_factors + result.main_negative_factors:
        assert factor["name"] in text
    assert display["comparison_title"] == "Сравнение с ближайшей допустимой альтернативой: " + names[result.runner_up]


@pytest.mark.parametrize("field,table,names,sign", [
    ("main_positive_factors", "positive_table", "positive_names", 1),
    ("main_negative_factors", "negative_table", "negative_names", -1),
])
def test_factor_text_limited_to_three_ordered_by_absolute_difference_and_full_table_kept(field, table, names, sign):
    result = build_explanation(load_model())
    factors = []
    for criterion, magnitude in zip(result.input_snapshot["criteria"], (0.1, 0.4, 0.2, 0.5, 0.3), strict=False):
        factors.append({"criterion": criterion["id"], "name": criterion["name"], "difference": sign * magnitude,
                        "winner_contribution": 0.5 + sign * magnitude, "runner_up_contribution": 0.5})
    setattr(result, field, factors)
    before = deepcopy(result.to_dict())
    display = format_p2(result)
    expected = sorted(factors, key=lambda f: -abs(f["difference"]))
    assert display[names] == [f["name"] for f in expected[:3]]
    assert len(display[names]) == 3
    assert display[table] == expected
    assert len(display[table]) == 5
    paragraph = display["summary"][0 if sign == 1 else 1]
    assert all(f["name"] in paragraph for f in expected[:3])
    assert all(f["name"] not in paragraph for f in expected[3:])
    assert result.to_dict() == before
    display[table][0]["difference"] = 999
    assert result.to_dict() == before


def test_no_exclusions_message_is_exact():
    display = format_p2(build_explanation(load_model()))
    assert display["exclusion_texts"] == [NO_EXCLUSIONS]
    assert NO_EXCLUSIONS in display["summary"]


def test_exclusion_reason_separate_from_factors_of_preference():
    result = case_result("one_excluded")
    display = format_p2(result)
    assert display["exclusion_texts"] == ["Монолитная архитектура исключена, поскольку не удовлетворяет обязательному требованию «Независимое развёртывание компонентов»; требуемое значение: «Да»."]
    assert "Независимое развёртывание компонентов»" not in display["summary"][0]
    assert display["positive_table"] == result.main_positive_factors
    assert display["negative_table"] == result.main_negative_factors


def test_absent_property_is_not_misrepresented_as_known_false():
    model = load_model()
    model.constraints[0]["enabled"] = True
    del model.architectures[0]["properties"]["independent_component_deployment"]
    display = format_p2(build_explanation(model))
    assert "не подтверждено выполнение обязательного требования" in display["exclusion_texts"][0]
    assert "свойство не задано" in display["exclusion_texts"][0]


@pytest.mark.parametrize("case_id,message", [("tie", TIED_RESULT), ("none_feasible", NO_FEASIBLE)])
def test_no_fictitious_recommendation_or_factors_for_tie_and_no_feasible(case_id, message):
    result = case_result(case_id)
    display = format_p2(result)
    assert result.recommended_architecture is None
    assert display["status_text"] == message
    assert display["summary_title"] is None and not display["summary"]
    assert display["comparison_title"] is None
    assert not display["positive_table"] and not display["negative_table"]
    if case_id == "none_feasible":
        for excluded in result.excluded_alternatives:
            assert any(excluded["name"] in reason for reason in display["exclusion_texts"])


def test_single_feasible_is_explained_as_eligibility_not_ranking_victory():
    result = case_result("single_feasible")
    display = format_p2(result)
    text = main_text(display)
    assert "Монолитная архитектура является единственной допустимой альтернативой" in text
    assert "получила преимущество" not in text
    assert display["comparison_message"] == NO_COMPETITOR
    assert display["comparison_title"] is None
    assert not display["positive_table"] and not display["negative_table"]


def test_empty_factor_selection_does_not_claim_no_actual_disadvantages():
    model = load_model()
    model.settings["top_factor_count"] = 0
    display = format_p2(build_explanation(model))
    assert display["positive_text"] == "Основные преимущества не выделены в данном объяснении."
    assert display["negative_text"] == "Слабые стороны относительно ближайшей допустимой альтернативы не выделены в данном объяснении."


@pytest.mark.parametrize("case_id", [c["id"] for c in load_cases()])
def test_p2_has_no_p3_material_and_does_not_mutate_results(case_id, monkeypatch):
    result = case_result(case_id)
    before = deepcopy(result.to_dict())
    original_p1, original_p3 = presentation(result, "P1"), presentation(result, "P3")
    def forbidden(*args, **kwargs):
        raise AssertionError("Formatter may not call the calculation engine")
    monkeypatch.setattr("src.explanation.build_explanation", forbidden)
    monkeypatch.setattr("src.explanation.rank_alternatives", forbidden)
    monkeypatch.setattr("src.explanation.influential_factors", forbidden)
    display = format_p2(result)
    text = main_text(display).lower()
    assert not any(term in text for term in ("риски", "риск ", "uncertainty", "sensitivity", "missing", "estimated", "чувствительност", "подстановк", "switch", "tie"))
    assert not {"risks", "uncertain_data", "sensitivity"}.intersection(display)
    assert presentation(result, "P1") == original_p1
    assert presentation(result, "P3") == original_p3
    assert result.to_dict() == before


@pytest.mark.parametrize("case_id", ["clear_winner", "one_excluded", "tie", "single_feasible", "none_feasible", "missing_blocked"])
def test_streamlit_p2_renders_summary_and_edge_states_without_p3_sections(case_id):
    app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=30).run()
    app.selectbox(key="case_id").set_value(case_id).run()
    before = deepcopy(app.session_state["result"].to_dict())
    app.radio(key="presentation_mode").set_value("P2").run()
    assert not app.exception
    panel = next(tab for tab in app.tabs if tab.label == "Объяснение")
    headings = [heading.value for heading in panel.subheader]
    paragraphs = [m.value for m in panel.markdown]
    display = format_p2(app.session_state["result"])
    assert "Причины исключения" in headings
    assert all(text in paragraphs for text in display["summary"] + display["exclusion_texts"])
    assert "Риски по заданным правилам" not in headings
    assert "Неопределённость и пропуски" not in headings
    assert "Чувствительность к весам" not in headings
    if display["comparison_title"]:
        assert display["comparison_title"] in headings
        assert headings.index("Почему сформирована эта рекомендация") < headings.index("Причины исключения") < headings.index(display["comparison_title"])
        assert headings.index("Положительные факторы") < headings.index("Слабые стороны") < headings.index("Технические таблицы вкладов")
        factor_frames = [frame for frame in panel.dataframe if "Разность вкладов" in frame.value.columns]
        assert factor_frames
        for frame in factor_frames:
            assert all("(" in label for label in frame.value["Критерий"])
            column_config = json.loads(frame.proto.columns)
            assert column_config["Разность вкладов"]["type_config"]["format"] == "%.4f"
    else:
        assert "Технические таблицы вкладов" not in headings
    if display["status_text"]:
        assert any(message.value == display["status_text"] for message in panel.warning)
    assert app.session_state["result"].to_dict() == before
