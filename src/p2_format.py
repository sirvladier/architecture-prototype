"""Human-readable P2 only: format existing evidence without recalculation."""

from copy import deepcopy


NO_EXCLUSIONS = "Все рассматриваемые архитектуры удовлетворяют обязательным ограничениям."
NO_COMPETITOR = "Других допустимых альтернатив для сравнительного анализа нет."
TIED_RESULT = "Однозначная рекомендация не сформирована: несколько допустимых архитектур получили одинаковый итоговый результат."
NO_FEASIBLE = "Рекомендация не сформирована: ни одна из рассматриваемых архитектур не удовлетворяет всем обязательным ограничениям."


def _criterion_list(factors):
    return ", ".join(f"«{factor['name']}»" for factor in factors)


def format_p2(result):
    names = {a["id"]: a["name"] for a in result.input_snapshot["architectures"]}
    exclusions = []
    for excluded in result.excluded_alternatives:
        for violation in excluded["violated_constraints"]:
            if violation["reason"] == "missing_property":
                reason = f"не подтверждено выполнение обязательного требования «{violation['name']}»: соответствующее свойство не задано"
            else:
                reason = f"не удовлетворяет обязательному требованию «{violation['name']}»"
            exclusions.append(f"{names[excluded['architecture']]} исключена, поскольку {reason}.")

    display = {
        "summary_title": None,
        "summary": [],
        "status_text": None,
        "exclusion_texts": exclusions or [NO_EXCLUSIONS],
        "comparison_title": None,
        "comparison_message": None,
        "positive_names": [],
        "negative_names": [],
        "positive_table": [],
        "negative_table": [],
        "positive_text": None,
        "negative_text": None,
    }
    if result.status == "tie":
        display["status_text"] = TIED_RESULT
        display["comparison_message"] = "Сравнение победителя с ближайшей альтернативой не выполняется: единственный победитель не определён."
        return display
    if result.status == "no_feasible":
        display["status_text"] = NO_FEASIBLE
        display["comparison_message"] = NO_COMPETITOR
        return display
    if result.status != "ok":
        display["status_text"] = "Рекомендация не сформирована: итоговый рейтинг не рассчитан."
        return display

    winner = names[result.recommended_architecture]
    display["summary_title"] = "Почему сформирована эта рекомендация"
    if result.runner_up is None:
        display["summary"] = [f"{winner} является единственной допустимой альтернативой после проверки обязательных ограничений. Сравнение факторов с ближайшим допустимым конкурентом не выполняется."]
        display["comparison_message"] = NO_COMPETITOR
        return display

    runner = names[result.runner_up]
    positive = sorted(result.main_positive_factors, key=lambda factor: (-abs(factor["difference"]), factor["criterion"]))
    negative = sorted(result.main_negative_factors, key=lambda factor: (-abs(factor["difference"]), factor["criterion"]))
    display["positive_names"] = [factor["name"] for factor in positive[:3]]
    display["negative_names"] = [factor["name"] for factor in negative[:3]]
    display["positive_table"] = deepcopy(positive)
    display["negative_table"] = deepcopy(negative)
    display["comparison_title"] = f"Сравнение с ближайшей допустимой альтернативой: {runner}"
    if len(result.runner_up_candidates) > 1:
        display["comparison_message"] = "Несколько ближайших альтернатив имеют равные в пределах допуска баллы: " + ", ".join(names[a] for a in result.runner_up_candidates) + f". В готовом результате для сравнения выбрана «{runner}»."
    if positive:
        advantage = f"{winner} получила преимущество перед ближайшей допустимой альтернативой «{runner}» прежде всего по критериям: {_criterion_list(positive[:3])}."
        display["positive_text"] = "Основные преимущества: " + _criterion_list(positive[:3]) + "."
    else:
        advantage = f"{winner} получила наибольший итоговый балл среди допустимых альтернатив. Ближайшая допустимая альтернатива: {runner}."
        display["positive_text"] = "Основные преимущества не выделены в данном объяснении."
    if negative:
        weakness = f"Слабые стороны рекомендации относительно альтернативы «{runner}»: {_criterion_list(negative[:3])}."
        display["negative_text"] = "Основные слабые стороны: " + _criterion_list(negative[:3]) + "."
    else:
        weakness = "Слабые стороны относительно ближайшей допустимой альтернативы не выделены в данном объяснении."
        display["negative_text"] = weakness
    exclusion_note = NO_EXCLUSIONS if not result.excluded_alternatives else "Обязательные ограничения исключили из сравнения: " + ", ".join(names[a["architecture"]] for a in result.excluded_alternatives) + ". Причины исключения приведены отдельно."
    display["summary"] = [advantage, weakness, exclusion_note]
    return display
