"""P3 display only: readable evidence and a bounded list of nearby events."""


NO_RISKS = "Для рекомендуемой архитектуры заданные правила риска не сработали."
NO_UNCERTAINTY = "Все использованные значения подтверждены; оценочных и пропущенных значений нет."
NO_EVENTS = "В пределах исследованной сетки весов потеря однозначности или смена рекомендации не обнаружена."
NOT_FOUND = "не обнаружено"


def percent(value):
    return NOT_FOUND if value is None else f"{value * 100:.1f}".replace(".", ",") + " %"


def rating_number(value):
    if value is None:
        return "не задано"
    return f"{value:.4f}".rstrip("0").rstrip(".").replace(".", ",")


def sensitivity_events(result):
    """Order already found events; do not search for new transition points."""
    if result.status != "ok":
        return []
    names = {a["id"]: a["name"] for a in result.input_snapshot["architectures"]}
    events = []
    for row in result.sensitivity:
        for kind, field in (("tie", "nearest_tie_weight"), ("switch", "nearest_switch_weight")):
            target = row[field]
            if target is None:
                continue
            original = row["original_weight"]
            direction = "увеличении" if target > original else "снижении"
            prefix = f"При {direction} веса критерия «{row['name']}» с {percent(original)} примерно до {percent(target)} "
            if kind == "tie":
                text = prefix + "рекомендация теряет однозначность."
            else:
                text = prefix + f"предпочтительной становится «{names[row['new_winner']]}»."
            events.append({"kind": kind, "criterion": row["criterion"], "original_weight": original,
                           "weight": target, "delta": abs(target - original), "text": text})
    return sorted(events, key=lambda e: (e["delta"], e["criterion"], 0 if e["kind"] == "tie" else 1))


def _uncertainty_text(item, names, criteria):
    subject = f"по критерию «{criteria[item['criterion']]}» для архитектуры «{names[item['architecture']]}»"
    used = item["used_in_ranking"]
    if item["status"] == "estimated":
        prefix = "В расчёте используется" if used else "В исходных данных задано"
        text = f"{prefix} оценочное значение {rating_number(item['used_value'])} {subject}."
    else:
        text = f"Исходное значение {subject} отсутствует."
        if item["model_value_used"]:
            prefix = "Для расчёта использовано" if used else "Для заполнения пропуска предусмотрено"
            text += f" {prefix} явно заданное модельное значение {rating_number(item['model_value'])}. Оно не считается подтверждённым исходным значением."
        elif item["model_value"] is not None:
            text += f" Модельное значение {rating_number(item['model_value'])} задано, но его использование не разрешено настройками расчёта."
        else:
            text += " Явная модельная подстановка не задана."
    if not item["architecture_is_feasible"]:
        text += " Архитектура исключена обязательными ограничениями; это значение не повлияло на выбор."
    elif not used:
        text += " Расчёт итогового рейтинга не выполнен."
    return text


def format_p3(result):
    names = {a["id"]: a["name"] for a in result.input_snapshot["architectures"]}
    criteria = {c["id"]: c["name"] for c in result.input_snapshot["criteria"]}
    risk_texts = []
    if result.status != "ok":
        risk_texts.append("Рекомендация не сформирована однозначно; риски единственной рекомендуемой архитектуры не определяются.")
    else:
        for risk in result.risks:
            text = f"Выявлен риск: {risk['text'].rstrip('.')}. Оценка рекомендуемой архитектуры по критерию «{criteria[risk['criterion']]}» составляет {rating_number(risk['used_value'])} из 5."
            if risk["model_value_used"]:
                text += " Эта оценка получена явной модельной подстановкой и не является подтверждённым исходным значением."
            elif risk["data_status"] == "estimated":
                text += " Для проверки правила использовано оценочное значение."
            risk_texts.append(text)
        if not risk_texts:
            risk_texts.append(NO_RISKS)
    risk_summary = risk_texts[0] if len(risk_texts) == 1 else f"Для рекомендуемой архитектуры выявлены риски по {len(result.risks)} заданным правилам. Описания приведены ниже."

    uncertainty_texts = [_uncertainty_text(u, names, criteria) for u in result.uncertain_data]
    if not uncertainty_texts:
        uncertainty_texts = [NO_UNCERTAINTY]
    if len(result.uncertain_data) <= 1:
        uncertainty_summary = uncertainty_texts[0]
    else:
        estimated = sum(u["status"] == "estimated" for u in result.uncertain_data)
        missing = sum(u["status"] == "missing" for u in result.uncertain_data)
        substituted = sum(u["model_value_used"] and u["used_in_ranking"] for u in result.uncertain_data)
        uncertainty_summary = f"В исходных данных оценочных значений: {estimated}; отсутствующих исходных значений: {missing}. Число использованных в расчёте явных модельных подстановок: {substituted}. Подстановки не считаются подтверждёнными исходными значениями."

    events = sensitivity_events(result)
    sensitivity_summary = [e["text"] for e in events[:3]]
    if result.status != "ok":
        sensitivity_note = {
            "tie": "Однозначная рекомендация уже отсутствует. Анализ потери однозначности и смены единственного победителя от такой исходной рекомендации не выполняется.",
            "no_feasible": "Рекомендация не сформирована: все архитектуры исключены обязательными ограничениями. Анализ чувствительности победителя не выполняется.",
            "insufficient_data": "Итоговый рейтинг не рассчитан. Анализ чувствительности рекомендации не выполняется.",
        }[result.status]
    else:
        explored = [r for r in result.sensitivity if r["status"] in {"stable_sampled", "switch_found", "tie_found"}]
        partial = len(explored) != len(result.sensitivity) or not result.sensitivity
        if not events:
            sensitivity_summary = [NO_EVENTS] if explored else ["В заданных условиях нет полностью исследованных направлений для вывода о чувствительности."]
        sensitivity_note = "Вывод относится только к исследованному диапазону и шагу сетки. События между проверенными точками могут быть пропущены."
        if partial:
            sensitivity_note += " Исследование выполнено не полностью: часть весов вне диапазона, направление недоступно или результаты отсутствуют."
        if len(result.feasible_alternatives) == 1:
            sensitivity_note = "После проверки ограничений осталась только одна допустимая архитектура. Изменение весов не добавляет допустимых конкурентов. " + sensitivity_note

    statuses = {
        "stable_sampled": "Изменений на проверенной сетке нет", "switch_found": "Найдена смена рекомендации",
        "tie_found": "Найдена потеря однозначности", "partially_explored": "Проверено частично",
        "original_outside_range": "Исходный вес вне диапазона", "not_applicable_tie": "Нет единственного победителя",
        "not_applicable_no_feasible": "Нет допустимых альтернатив", "not_applicable_insufficient_data": "Рейтинг не рассчитан",
    }
    sensitivity_table = []
    for row in result.sensitivity:
        applicable = row["status"] in {"stable_sampled", "switch_found", "tie_found", "partially_explored"}
        absent = NOT_FOUND if applicable else "не определялось"
        sensitivity_table.append({
            "Критерий": row["name"], "Исходный вес": percent(row["original_weight"]),
            "Вес при потере однозначности": percent(row["nearest_tie_weight"]) if row["nearest_tie_weight"] is not None else absent,
            "Равные лидеры": ", ".join(names[a] for a in row["tie_winners"]) or absent,
            "Вес при смене рекомендации": percent(row["nearest_switch_weight"]) if row["nearest_switch_weight"] is not None else absent,
            "Новая рекомендуемая архитектура": names[row["new_winner"]] if row["new_winner"] is not None else absent,
            "Результат": statuses[row["status"]],
        })
    return {"risk_summary": risk_summary, "risk_texts": risk_texts,
            "uncertainty_summary": uncertainty_summary, "uncertainty_texts": uncertainty_texts,
            "sensitivity_summary": sensitivity_summary, "sensitivity_note": sensitivity_note,
            "closest_events": events[:3], "sensitivity_table": sensitivity_table}
