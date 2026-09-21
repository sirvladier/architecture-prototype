"""One calculated object; presentation never invokes the decision algorithm."""

from copy import deepcopy
import hashlib
import json
import math

from src.constraints import check_constraints
from src.factors import influential_factors
from src.models import ExplanationData, Model, validate_model
from src.risks import evaluate_risks
from src.scoring import normalize_weights, rank_alternatives
from src.sensitivity import analyze_sensitivity, reweight
from src.uncertainty import resolve_values


def build_explanation(model, include_sensitivity=True):
    validate_model(model)
    snapshot = model.to_dict()
    digest = hashlib.sha256(json.dumps(snapshot, sort_keys=True, ensure_ascii=False, allow_nan=False).encode("utf-8")).hexdigest()
    feasible, excluded = check_constraints(model.architectures, model.constraints)
    feasible_ids = {a["id"] for a in feasible}
    values, uncertain, blocking = resolve_values(model.architectures, feasible_ids, model.settings["missing_policy"])
    weights = normalize_weights({c["id"]: c["weight"] for c in model.criteria})
    result = ExplanationData(
        status="no_feasible" if not feasible else "insufficient_data" if blocking else "ok",
        excluded_alternatives=excluded,
        feasible_alternatives=[{"architecture": a["id"], "name": a["name"]} for a in feasible],
        uncertain_data=uncertain,
        blocking_data=blocking,
        normalized_weights=weights,
        based_on_incomplete_data=any(u["status"] == "missing" and u["architecture_is_feasible"] for u in uncertain),
        has_uncertain_data=any(u["architecture_is_feasible"] for u in uncertain),
        calculation_id=digest,
        input_snapshot=snapshot,
    )
    if result.status == "ok":
        result.ranking, result.winners, result.status = rank_alternatives(feasible, model.criteria, values, weights, model.settings["tie_tolerance"])
    if result.status == "ok":
        winner = result.ranking[0]
        result.recommended_architecture, result.score = winner["architecture"], winner["score"]
        result.runner_up, result.runner_up_candidates, result.main_positive_factors, result.main_negative_factors = influential_factors(result.ranking, model.criteria, model.settings["top_factor_count"], model.settings["tie_tolerance"])
        architecture = next(a for a in feasible if a["id"] == result.recommended_architecture)
        result.risks = evaluate_risks(architecture["id"], model.risks, values, architecture["ratings"])
    if include_sensitivity:
        result.sensitivity = analyze_sensitivity(feasible, model.criteria, values, weights, model.settings["sensitivity"], model.settings["tie_tolerance"], result.recommended_architecture, result.status)
    return result


def presentation(result, mode):
    if mode not in {"P1", "P2", "P3"}:
        raise ValueError("Unknown presentation mode")
    view = {
        "mode": mode, "calculation_id": result.calculation_id,
        "status": result.status,
        "recommended_architecture": result.recommended_architecture,
        "score": result.score, "winners": result.winners,
        "ranking": [{key: row[key] for key in ("architecture", "name", "score")} for row in result.ranking],
        "excluded_alternatives": [{key: row[key] for key in ("architecture", "name", "status")} for row in result.excluded_alternatives],
    }
    if mode in {"P2", "P3"}:
        view.update(excluded_alternatives=result.excluded_alternatives, runner_up=result.runner_up, runner_up_candidates=result.runner_up_candidates, main_positive_factors=result.main_positive_factors, main_negative_factors=result.main_negative_factors)
    if mode == "P3":
        view.update(risks=result.risks, uncertain_data=result.uncertain_data, sensitivity=result.sensitivity, based_on_incomplete_data=result.based_on_incomplete_data, has_uncertain_data=result.has_uncertain_data, blocking_data=result.blocking_data)
        view["summary"] = extended_summary(result)
    return deepcopy(view)


def format_weight(value):
    return f"{value:.12g}".replace(".", ",")


def extended_summary(result):
    """Deterministic text from calculated evidence; no new scoring or inference."""
    names = {a["id"]: a["name"] for a in result.input_snapshot["architectures"]}
    criteria = {c["id"]: c["name"] for c in result.input_snapshot["criteria"]}
    paragraphs = []
    if result.status == "ok":
        if result.risks:
            paragraphs.append("Для рекомендуемой архитектуры выявлены риски по заданным правилам: " + "; ".join(r["text"] for r in result.risks) + ".")
        else:
            paragraphs.append("Для рекомендуемой архитектуры ни одно заданное условие риска не сработало.")
    else:
        paragraphs.append({"tie": "Исходная рекомендация уже неоднозначна: равные лидеры " + ", ".join(names[a] for a in result.winners) + ".",
                           "no_feasible": "Все архитектуры исключены обязательными ограничениями; рекомендация не сформирована.",
                           "insufficient_data": "Рейтинг не рассчитан: для допустимых архитектур отсутствуют обязательные оценки без разрешённой модельной подстановки."}[result.status])
        paragraphs.append("Риски рекомендации не определены, поскольку нет единственного победителя.")
    if not result.uncertain_data:
        paragraphs.append("Исходные данные данного кейса не содержат оценочных или пропущенных значений. Оценки остаются параметрами модельной постановки.")
    else:
        estimated = sum(u["status"] == "estimated" for u in result.uncertain_data)
        missing = sum(u["status"] == "missing" for u in result.uncertain_data)
        paragraphs.append(f"В исходных данных оценочных значений: {estimated}; пропущенных: {missing}.")
        for item in result.uncertain_data:
            if item["model_value_used"]:
                scope = "Участвует в рейтинге." if item["used_in_ranking"] else "В рейтинге не использовано."
                paragraphs.append(f"{names[item['architecture']]} / {criteria[item['criterion']]}: исходное значение отсутствует; использована явная модельная подстановка {format_weight(item['used_value'])}; статус остаётся missing. {scope}")
        if all(not u["architecture_is_feasible"] for u in result.uncertain_data):
            paragraphs.append("Все оценочные и пропущенные значения относятся к исключённым альтернативам и не участвуют в рейтинге.")
    if result.status != "ok":
        paragraphs.append("Поиск потери однозначности и смены единственного победителя от этой исходной рекомендации не применим.")
        return paragraphs
    stable = []
    for row in result.sensitivity:
        parts = []
        original = row["original_weight"]
        tie, switch = row["nearest_tie_weight"], row["nearest_switch_weight"]
        if tie is not None:
            direction = "увеличении" if tie > original else "уменьшении"
            parts.append(f"при {direction} веса с {format_weight(original)} до {format_weight(tie)} возникает равенство лидеров (tie): " + ", ".join(names[a] for a in row["tie_winners"]))
        if switch is not None:
            direction = "увеличении" if switch > original else "уменьшении"
            parts.append(f"при {direction} веса с {format_weight(original)} до {format_weight(switch)} другим единственным победителем (switch) становится {names[row['new_winner']]}")
        if parts:
            paragraphs.append(f"{row['name']}: " + "; ".join(parts) + ".")
        if row["status"] == "stable_sampled":
            stable.append(row["name"])
        elif row["status"] == "partially_explored":
            paragraphs.append(f"{row['name']}: диапазон проверен частично; устойчивость не установлена.")
        elif row["status"] == "original_outside_range":
            paragraphs.append(f"{row['name']}: исходный вес вне заданного диапазона; чувствительность не проверена.")
    if stable:
        paragraphs.append("На проверенной сетке не найдены ни потеря однозначности, ни смена победителя для критериев: " + ", ".join(stable) + ".")
    if result.sensitivity:
        paragraphs.append("Точки относятся к исследованной сетке весов. Равенство или смена между узлами сетки могут быть пропущены.")
    return paragraphs


def validate_explanation(result):
    """Replay inputs, check evidence, and independently replay every reported switch."""
    errors = []
    model = Model(**deepcopy(result.input_snapshot))
    expected = build_explanation(model, include_sensitivity=False)
    for key, value in expected.to_dict().items():
        if key != "sensitivity" and result.to_dict()[key] != value:
            errors.append(f"Mismatch: {key}")
    if not math.isclose(math.fsum(result.normalized_weights.values()), 1, abs_tol=1e-12):
        errors.append("Weights do not sum to one")
    ranked = {row["architecture"] for row in result.ranking}
    if ranked & {row["architecture"] for row in result.excluded_alternatives}:
        errors.append("Excluded architecture is ranked")
    for row in result.ranking:
        if not math.isclose(row["score"], math.fsum(row["contributions"].values()), abs_tol=1e-12):
            errors.append("Score differs from contributions")
    if len(result.sensitivity) != len(model.criteria):
        errors.append("Sensitivity results are incomplete")
    feasible, _ = check_constraints(model.architectures, model.constraints)
    values, _, _ = resolve_values(model.architectures, {a["id"] for a in feasible}, model.settings["missing_policy"])
    for row in result.sensitivity:
        for tie in [dict(weight=row["nearest_tie_weight"], winners=row["tie_winners"]), *[dict(weight=d["first_tie_weight"], winners=d["tie_winners"]) for d in row["directions"].values()]]:
            if tie["weight"] is None:
                continue
            adjusted = reweight(result.normalized_weights, row["criterion"], tie["weight"], model.settings["sensitivity"]["zero_remainder_policy"])
            if adjusted is None:
                errors.append("Reported tie cannot be reweighted")
                continue
            _, winners, status = rank_alternatives(feasible, model.criteria, values, adjusted, model.settings["tie_tolerance"])
            if status != "tie" or winners != tie["winners"]:
                errors.append("Reported tie does not reproduce")
        for switch in [row, *row["directions"].values()]:
            if switch["switch_weight"] is None:
                continue
            weights = reweight(result.normalized_weights, row["criterion"], switch["switch_weight"], model.settings["sensitivity"]["zero_remainder_policy"])
            if weights is None:
                errors.append("Reported switch cannot be reweighted")
                continue
            _, winners, status = rank_alternatives(feasible, model.criteria, values, weights, model.settings["tie_tolerance"])
            if status != "ok" or winners != [switch["new_winner"]] or switch["new_winner"] == result.recommended_architecture:
                errors.append("Reported switch does not change the winner")
    views = [presentation(result, mode) for mode in ("P1", "P2", "P3")]
    for key in ("recommended_architecture", "score", "ranking", "status", "calculation_id"):
        if not all(view[key] == views[0][key] for view in views):
            errors.append(f"Presentation changes {key}")
    return errors
