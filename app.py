"""Local Streamlit UI over a single stored ExplanationData."""

from copy import deepcopy
import hashlib
import json

import pandas as pd
import streamlit as st

from src.explanation import build_explanation, presentation
from src.models import ConfigError, apply_case, load_cases, load_model
from src.p2_format import format_p2
from src.p3_format import format_p3
from src.scoring import normalize_weights
from src.user_cases import UserCase, build_user_model, configuration_identity, export_user_case, load_property_catalog


st.set_page_config(page_title="Выбор архитектуры", layout="wide", initial_sidebar_state="expanded")

STATUS = {
    "ok": "Рекомендация сформирована",
    "tie": "Равенство: единственный победитель не определён",
    "insufficient_data": "Расчёт остановлен: отсутствуют обязательные оценки",
    "no_feasible": "Рекомендация не сформирована: ни одна из рассматриваемых архитектур не удовлетворяет всем заданным обязательным ограничениям.",
}
SENSITIVITY_STATUS = {
    "switch_found": "Найдена смена победителя",
    "tie_found": "Потеря однозначности без смены победителя",
    "stable_sampled": "Смены нет на проверенной сетке",
    "partially_explored": "Диапазон проверен частично",
    "original_outside_range": "Исходный вес вне диапазона",
    "not_applicable_tie": "Не применимо: равенство",
    "not_applicable_insufficient_data": "Не применимо: пропуск данных",
    "not_applicable_no_feasible": "Не применимо: нет допустимых альтернатив",
}


def table(rows):
    if rows:
        st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)


def render_ranking(view, names):
    if view["status"] == "ok":
        st.subheader(f"{view['recommended_architecture']} · {names[view['recommended_architecture']]}")
        st.metric("Итоговый балл", f"{view['score']:.6f}")
    elif view["status"] == "tie":
        st.warning(STATUS[view["status"]])
        st.write("Равные лидеры: " + ", ".join(view["winners"]))
    else:
        st.warning(STATUS[view["status"]])
    table([{"Архитектура": row["architecture"], "Название": row["name"], "Балл": row["score"], "Статус": "допустима"} for row in view["ranking"]])
    table([{"Архитектура": row["architecture"], "Название": row["name"], "Статус": "excluded"} for row in view["excluded_alternatives"]])


def render_factors(view):
    st.subheader("Причины исключения")
    rows = []
    for excluded in view["excluded_alternatives"]:
        for violation in excluded["violated_constraints"]:
            st.write(f"{excluded['name']} исключена: обязательное требование «{violation['name']}» не выполнено.")
            rows.append({"Архитектура": excluded["architecture"], "Ограничение": violation["constraint_id"], "Название": violation["name"], "Свойство": violation["property"], "Фактически": json.dumps(violation["actual"], ensure_ascii=False), "Условие": f"{violation['operator']} {json.dumps(violation['expected'], ensure_ascii=False)}", "Причина": "Свойство отсутствует" if violation["reason"] == "missing_property" else "Условие не выполнено"})
    if rows:
        table(rows)
    else:
        st.write("Исключённых альтернатив нет.")
    if view["runner_up"] is None:
        st.write("Сравнение преимуществ и слабых сторон не применимо: нет единственного победителя или ближайшего конкурента.")
        return
    st.subheader(f"Сравнение с {view['runner_up']}")
    if len(view["runner_up_candidates"]) > 1:
        st.caption("Конкуренты с равными в пределах допуска баллами: " + ", ".join(view["runner_up_candidates"]) + ". Сравнение выполнено с первым по порядку балл ↓, ID ↑.")
    for title, key in (("Положительные факторы", "main_positive_factors"), ("Слабые стороны", "main_negative_factors")):
        st.write(f"**{title}**")
        rows = [{"Критерий": f"{f['criterion']} · {f['name']}", "Вклад победителя": f["winner_contribution"], "Вклад конкурента": f["runner_up_contribution"], "Разность вкладов": f["difference"]} for f in view[key]]
        if rows:
            table(rows)
        else:
            st.write("Нет отображаемых факторов.")


def p2_table(rows, numeric_columns=()):
    if rows:
        st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True,
            column_config={name: st.column_config.NumberColumn(name, format="%.4f") for name in numeric_columns})


def render_p2(result, view):
    display = format_p2(result)
    names = {a["id"]: a["name"] for a in result.input_snapshot["architectures"]}
    if display["status_text"]:
        st.warning(display["status_text"])
        if result.status == "tie":
            st.write("Равные лидеры: " + ", ".join(names[a] for a in result.winners))
    else:
        st.subheader(names[result.recommended_architecture])
        st.metric("Итоговый балл", f"{result.score:.4f}")
    p2_table([{"Архитектура": row["name"], "ID": row["architecture"], "Балл": row["score"], "Статус": "допустима"} for row in view["ranking"]], ("Балл",))
    p2_table([{"Архитектура": row["name"], "ID": row["architecture"], "Статус": "исключена"} for row in view["excluded_alternatives"]])

    if display["summary_title"]:
        st.subheader(display["summary_title"])
    for paragraph in display["summary"]:
        st.write(paragraph)

    st.subheader("Причины исключения")
    for paragraph in display["exclusion_texts"]:
        st.write(paragraph)
    if view["excluded_alternatives"]:
        with st.expander("Проверка обязательных требований"):
            p2_table([{"Архитектура": row["name"], "Требование": v["name"], "ID": v["constraint_id"],
                       "Свойство": {p["property"]: p["name"] for p in load_property_catalog()}.get(v["property"], v["name"]),
                       "Фактически": "Не задано" if v["actual"] is None else "Да" if v["actual"] else "Нет",
                       "Требуемое значение": "Да" if v["expected"] else "Нет"}
                      for row in view["excluded_alternatives"] for v in row["violated_constraints"]])

    if display["comparison_title"]:
        st.subheader(display["comparison_title"])
    if display["comparison_message"]:
        st.write(display["comparison_message"])
    if display["comparison_title"] is None:
        return
    st.subheader("Положительные факторы")
    st.write(display["positive_text"])
    st.subheader("Слабые стороны")
    st.write(display["negative_text"])
    st.subheader("Технические таблицы вкладов")
    for title, key in (("Положительные факторы", "positive_table"), ("Слабые стороны", "negative_table")):
        st.write(f"**{title}**")
        rows = [{"Критерий": f"{f['name']} ({f['criterion']})", "Вклад победителя": f["winner_contribution"],
                 "Вклад конкурента": f["runner_up_contribution"], "Разность вкладов": f["difference"]} for f in display[key]]
        if rows:
            p2_table(rows, ("Вклад победителя", "Вклад конкурента", "Разность вкладов"))
        else:
            st.write("Нет факторов для отображения.")
    with st.expander("Вклады всех критериев допустимых альтернатив"):
        criteria = result.input_snapshot["criteria"]
        columns = {c["id"]: f"{c['name']} ({c['id']})" for c in criteria}
        p2_table([{"Архитектура": row["name"], **{columns[key]: value for key, value in row["contributions"].items()}} for row in result.ranking], tuple(columns.values()))


def render_sensitivity(rows):
    table([{"Критерий": f"{r['criterion']} · {r['name']}", "Исходный вес": r["original_weight"], "Вес tie": r["nearest_tie_weight"], "|Δ| до tie": r["tie_delta"], "Участники tie": ", ".join(r["tie_winners"]), "Вес switch": r["nearest_switch_weight"], "|Δ| до switch": r["delta"], "Новый победитель": r["new_winner"], "Результат": SENSITIVITY_STATUS[r["status"]]} for r in rows])
    if rows:
        st.caption(f"Шаг: {rows[0]['step']:g}; диапазон: {rows[0]['range']}. Результат относится к проверенной сетке весов. tie: потеря однозначности; switch: другой единственный победитель.")
    with st.expander("Оба направления и точки равенства"):
        table([{"Критерий": row["criterion"], "Направление": "Уменьшение" if direction == "decrease" else "Увеличение", "Вес смены": detail["switch_weight"], "Новый победитель": detail["new_winner"], "Первое равенство": detail["first_tie_weight"], "Участники равенства": ", ".join(detail["tie_winners"]), "Последний проверенный вес": detail["last_tested_weight"], "Проверено точек": detail["tested_count"], "Статус": detail["status"]} for row in rows for direction, detail in row["directions"].items()])


def render_extended(result):
    display = format_p3(result)
    names = {a["id"]: a["name"] for a in result.input_snapshot["architectures"]}
    criteria = {c["id"]: c["name"] for c in result.input_snapshot["criteria"]}
    st.subheader("Риски, неопределённость и устойчивость")
    st.write(display["risk_summary"])
    st.write(display["uncertainty_summary"])
    for paragraph in display["sensitivity_summary"]:
        st.write(paragraph)
    st.caption(display["sensitivity_note"])

    st.subheader("Риски")
    for paragraph in display["risk_texts"]:
        st.write(paragraph)
    if result.risks:
        with st.expander("Подробные данные о рисках", expanded=False):
            p2_table([{"Правило": r["id"].split("_")[0], "Архитектура": names[r["architecture"]],
                       "Критерий": f"{criteria[r['criterion']]} ({r['criterion']})",
                       "Оператор": r["operator"], "Порог": json.dumps(r["threshold"], ensure_ascii=False),
                       "Использованное значение": r["used_value"], "Статус данных": r["data_status"],
                       "Модельная подстановка": r["model_value_used"], "Риск": r["text"]} for r in result.risks],
                     ("Использованное значение",))

    st.subheader("Неопределённость и пропуски")
    for paragraph in display["uncertainty_texts"]:
        st.write(paragraph)
    if result.uncertain_data:
        with st.expander("Подробные данные о неопределённости", expanded=False):
            p2_table([{"Архитектура": names[u["architecture"]], "ID архитектуры": u["architecture"],
                       "Критерий": f"{criteria[u['criterion']]} ({u['criterion']})",
                       "Статус": u["status"], "Исходное значение": u["original_value"],
                       "Модельное значение": u["model_value"], "Использованное значение": u["used_value"],
                       "Модельная подстановка": u["model_value_used"], "Архитектура допустима": u["architecture_is_feasible"],
                       "В расчёте рейтинга": u["used_in_ranking"], "Источник": u["source"]} for u in result.uncertain_data],
                     ("Исходное значение", "Модельное значение", "Использованное значение"))
            for item in result.uncertain_data:
                if item["model_value_used"]:
                    st.write(f"{item['architecture']} / {item['criterion']}: model_value = {item['model_value']:g}; status = {item['status']}.")

    st.subheader("Чувствительность рекомендации")
    st.caption(display["sensitivity_note"])
    table(display["sensitivity_table"])
    with st.expander("Подробный анализ чувствительности", expanded=False):
        rows = []
        for row in result.sensitivity:
            for direction, detail in row["directions"].items():
                rows.append({
                    "Критерий": f"{row['name']} ({row['criterion']})",
                    "Направление": "Снижение" if direction == "decrease" else "Увеличение",
                    "Исходный вес": row["original_weight"], "Точка потери однозначности": detail["first_tie_weight"],
                    "Изменение до потери однозначности": detail["tie_delta"],
                    "Участники равенства": ", ".join(names[a] for a in detail["tie_winners"]) or "не обнаружено",
                    "Точка смены рекомендации": detail["switch_weight"], "Изменение до смены": detail["delta"],
                    "Новая рекомендуемая архитектура": names.get(detail["new_winner"], "не обнаружено"),
                    "Последний проверенный вес": detail["last_tested_weight"], "Проверено точек": detail["tested_count"],
                    "Шаг": row["step"], "Нижняя граница": row["range"][0], "Верхняя граница": row["range"][1],
                    "Статус направления": detail["status"], "Статус критерия": row["status"],
                })
        p2_table(rows, ("Исходный вес", "Точка потери однозначности", "Изменение до потери однозначности",
                       "Точка смены рекомендации", "Изменение до смены", "Последний проверенный вес",
                       "Шаг", "Нижняя граница", "Верхняя граница"))
        st.json(result.sensitivity)


def render_model_parameters(model):
    st.subheader("Параметры модели")
    st.caption("Оценки архитектур являются параметрами модельной постановки и в текущей версии не редактируются пользователем")
    st.caption("Оценки 1–5 являются порядковой исследовательской моделью качественных различий между архитектурными альтернативами и не являются универсальными нормативными значениями.")
    from src.models import ROOT, read_json
    scale = read_json(ROOT / "config" / "criteria.json")["scale"]
    st.caption("Шкала: " + "; ".join(f"{value} — {meaning}" for value, meaning in scale.items()) + ".")
    st.caption(next(c["description"] for c in model.criteria if c["id"] == "K6"))
    table([{"Архитектура": a["name"], **{key: str(r["value"]) if r["status"] != "missing" else f"missing; model={r.get('model_value')}" for key, r in a["ratings"].items()}} for a in model.architectures])
    with st.expander("Статусы оценок и свойства архитектур"):
        table([{"Архитектура": a["name"], "Критерий": key, "Значение": r.get("value"), "Статус": r["status"], "Модельное значение": r.get("model_value")} for a in model.architectures for key, r in a["ratings"].items()])
        properties = {p["property"]: p["name"] for p in load_property_catalog()}
        table([{"Архитектура": a["name"], **{properties[key]: "Да" if value else "Нет" for key, value in a["properties"].items()}} for a in model.architectures])
    with st.expander("Правила риска модели"):
        st.caption("Каждое правило применяется к рекомендуемой архитектуре по фактически использованной оценке критерия.")
        rules = read_json(ROOT / "config" / "risks.json")["risks"]
        table([{"Правило": r["id"], "Условие": f"{r['criterion']} ≤ {r['threshold']}", "Риск": r["text"]} for r in rules])


def render_user_inputs(base, catalog):
    state = st.session_state
    state.setdefault("user_weights", {c["id"]: float(c["weight"]) for c in base.criteria})
    state.setdefault("user_constraints", [])
    state.setdefault("user_row_counter", 0)
    def restore_widget(key, value):
        # Keep widget defaults stable; changing defaults can discard browser edits.
        if key not in state:
            state[key] = deepcopy(value)
    st.subheader("Приоритеты проекта")
    st.caption("Значимость критериев выражает приоритеты конкретного проекта.")
    columns = st.columns(2)
    for index, criterion in enumerate(base.criteria):
        with columns[index % 2]:
            key = criterion["id"]
            restore_widget(f"user_weight_{key}", float(state["user_weights"][key]))
            state["user_weights"][key] = st.number_input(criterion["name"], min_value=0.0,
                step=0.1, format="%g", key=f"user_weight_{key}")
    weights = deepcopy(state["user_weights"])
    try:
        normalized = normalize_weights(weights)
        table([{"Критерий": c["name"], "Направление": c["direction"], "Введённая значимость": weights[c["id"]], "Нормированный вес": normalized[c["id"]]} for c in base.criteria])
    except ConfigError:
        st.error("Все веса равны нулю. Задайте положительную значимость хотя бы одного критерия.")

    st.subheader("Обязательные требования проекта")
    st.caption("Задайте обязательное значение свойства. «Нет» означает требование отсутствия свойства, а не отключение ограничения. Чтобы снять требование, удалите его. Все требования проверяются до рейтинга.")
    properties = {item["property"]: item for item in catalog}
    if st.button("Добавить ограничение", icon=":material/add:", key="add_constraint"):
        state["user_row_counter"] += 1
        state["user_constraints"].append({"row_id": state["user_row_counter"], "property": catalog[0]["property"],
            "name": catalog[0]["name"], "operator": "==", "required_value": True})
    constraints = []
    for row in state["user_constraints"][:]:
        token = row["row_id"]
        st.divider()
        left, right = st.columns([5, 1])
        with right:
            if st.button("", icon=":material/delete:", help="Удалить ограничение", key=f"remove_constraint_{token}"):
                state["user_constraints"].remove(row)
                st.rerun()
        with left:
            previous = row["property"]
            restore_widget(f"user_property_{token}", previous)
            prop = st.selectbox("Свойство архитектуры", list(properties),
                format_func=lambda value: properties[value]["name"], key=f"user_property_{token}")
        spec = properties[prop]
        if prop != previous:
            row.update(property=prop, name=spec["name"], operator="==", required_value=True)
        restore_widget(f"user_name_{token}_{prop}", row["name"])
        row["name"] = st.text_input("Название требования", key=f"user_name_{token}_{prop}")
        first, second = st.columns(2)
        operators = ["=="]
        with first:
            restore_widget(f"user_operator_{token}_{prop}", row["operator"])
            row["operator"] = st.selectbox("Условие", operators,
                format_func=lambda value: {"==": "Равно"}[value],
                key=f"user_operator_{token}_{prop}")
        with second:
            value_key = f"user_required_{token}_{prop}"
            restore_widget(value_key, row["required_value"])
            row["required_value"] = st.selectbox("Требуемое значение", [True, False],
                format_func=lambda value: "Да" if value else "Нет", key=value_key)
        constraints.append({key: deepcopy(row[key]) for key in ("name", "property", "operator", "required_value")})
    return UserCase.from_dict({"weights": weights, "constraints": constraints})


def main():
    st.header("Выбор архитектуры")
    st.caption("Исследовательский прототип · A1 / A2 / A3")
    st.info("Литературно-информированная порядковая модель. Оценки 1–5 используются для формализации качественных различий между архитектурными альтернативами в рамках данного исследования и не являются универсальными нормативными значениями.")
    try:
        base, cases, catalog = load_model(), load_cases(), load_property_catalog()
        identity = configuration_identity()
    except (ConfigError, KeyError, TypeError) as exc:
        st.error(f"Ошибка конфигурации: {exc}")
        return
    with st.sidebar:
        work_mode = st.radio("Режим работы", ["Модельный кейс", "Пользовательский кейс"], key="work_mode")
        if work_mode == "Модельный кейс":
            selected = st.selectbox("Кейс", [c["id"] for c in cases], format_func=lambda value: next(c["name"] for c in cases if c["id"] == value), key="case_id")
            st.caption("SYNTHETIC / MODEL CASES")
        else:
            selected = "user"
    user_mode = work_mode == "Пользовательский кейс"
    model = base
    result = None
    if not user_mode:
        case = next(c for c in cases if c["id"] == selected)
        try:
            model = apply_case(base, case)
            input_key = hashlib.sha256(json.dumps(model.to_dict(), sort_keys=True).encode()).hexdigest()
            if st.session_state.get("model_input_key") != input_key:
                st.session_state["model_result"] = build_explanation(model)
                st.session_state["model_input_key"] = input_key
            result = st.session_state["model_result"]
        except (ConfigError, KeyError, TypeError) as exc:
            st.error(f"Ошибка кейса: {exc}")
            return

    source_tab, comparison_tab, explanation_tab, sensitivity_tab = st.tabs(["Исходные данные", "Сравнение", "Объяснение", "Анализ чувствительности"])
    with source_tab:
        if user_mode:
            user_case = render_user_inputs(base, catalog)
            signature = json.dumps({"weights": user_case.weights, "constraints": user_case.constraints, **identity}, sort_keys=True)
            submitted = st.button("Сформировать рекомендацию", type="primary", icon=":material/calculate:", key="calculate_user")
            if submitted:
                try:
                    calculated = build_explanation(build_user_model(user_case))
                    st.session_state["user_result"] = calculated
                    st.session_state["user_calculated_signature"] = signature
                    st.session_state.pop("user_error", None)
                except (ConfigError, ValueError, TypeError) as exc:
                    st.session_state.pop("user_result", None)
                    st.session_state["user_error"] = (signature, str(exc))
            if st.session_state.get("user_calculated_signature") == signature:
                result = st.session_state.get("user_result")
            if st.session_state.get("user_error", (None,))[0] == signature:
                st.error(st.session_state["user_error"][1])
            if result is None:
                st.info("Текущие исходные данные ещё не рассчитаны.")
        else:
            st.subheader("Приоритеты модельного кейса")
            table([{"Критерий": c["name"], "Направление": c["direction"], "Введённая значимость": c["weight"], "Нормированный вес": result.normalized_weights[c["id"]]} for c in model.criteria])
            st.subheader("Обязательные требования модельного кейса")
            enabled = [r for r in model.constraints if r["enabled"]]
            if enabled:
                table([{"Требование": r["name"], "Условие": "Равно", "Требуемое значение": "Да" if r["expected"] else "Нет"} for r in enabled])
            else:
                st.write("Обязательные ограничения не заданы.")
        render_model_parameters(model)
        if result is not None:
            st.caption(f"Сохранённый расчёт: {result.calculation_id[:16]} · {STATUS[result.status]}")
    st.session_state["result"] = result
    if result is None:
        return

    names = {a["id"]: a["name"] for a in result.input_snapshot["architectures"]}
    with comparison_tab:
        render_ranking(presentation(result, "P1"), names)
        if result.status == "insufficient_data":
            st.write("Допустимы по ограничениям, но не ранжированы: " + ", ".join(a["name"] for a in result.feasible_alternatives))
            table([{"Архитектура": names[u["architecture"]], "Отсутствующий критерий": u["criterion"]} for u in result.blocking_data])
        st.subheader("Веса проекта")
        table([{"Критерий": c["name"], "Введённая значимость": c["weight"], "Нормированный вес": result.normalized_weights[c["id"]]} for c in result.input_snapshot["criteria"]])
        st.subheader("Вклады критериев")
        table([{"Архитектура": r["name"], **r["contributions"], "Итого": r["score"]} for r in result.ranking])
        if result.ranking:
            st.bar_chart(pd.DataFrame([{"Архитектура": r["architecture"], **r["contributions"]} for r in result.ranking]).set_index("Архитектура"), height=250)
    with explanation_tab:
        mode = st.radio("Представление", ["P1", "P2", "P3"], format_func=lambda value: {"P1": "P1 · Рейтинг", "P2": "P2 · Базовое объяснение", "P3": "P3 · Расширенное объяснение"}[value], horizontal=True, key="presentation_mode")
        view = presentation(result, mode)
        if mode in {"P2", "P3"}:
            render_p2(result, view)
            if mode == "P3":
                render_extended(result)
        else:
            render_ranking(view, names)
        st.caption(f"Расчёт: {view['calculation_id'][:16]}")
    with sensitivity_tab:
        st.subheader("Точки смены рекомендации")
        render_sensitivity(result.sensitivity)
    with st.sidebar:
        st.divider()
        st.write(STATUS[result.status])
        if user_mode:
            st.download_button("Скачать исходные данные кейса", data=json.dumps(export_user_case(result), ensure_ascii=False, indent=2, allow_nan=False),
                file_name="user_case.json", mime="application/json", icon=":material/download:")
        st.download_button("Результат JSON", data=json.dumps(result.to_dict(), ensure_ascii=False, indent=2, allow_nan=False),
            file_name=f"{selected}_explanation.json", mime="application/json", icon=":material/download:")


if __name__ == "__main__":
    main()
