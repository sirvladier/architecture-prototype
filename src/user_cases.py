"""Project inputs cannot override architecture ratings or research rules."""

from copy import deepcopy
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path

from src.models import ROOT, load_model, number, read_json, require, validate_model
from src.scoring import normalize_weights


@dataclass(frozen=True, slots=True)
class UserCase:
    weights: dict
    constraints: list

    @classmethod
    def from_dict(cls, data):
        require(isinstance(data, dict) and set(data) == {"weights", "constraints"},
                "Пользовательский кейс содержит только веса и ограничения. Оценки архитектур изменять нельзя.")
        require(isinstance(data["weights"], dict), "Веса должны быть объектом.")
        require(isinstance(data["constraints"], list), "Ограничения должны быть списком.")
        return cls(deepcopy(data["weights"]), deepcopy(data["constraints"]))


def configuration_identity(root=ROOT):
    documents = {name: read_json(Path(root) / "config" / f"{name}.json")
                 for name in ("architectures", "criteria", "constraints", "risks")}
    def digest(value):
        return "sha256:" + hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False).encode("utf-8")).hexdigest()
    return {"architecture_config_id": digest(documents["architectures"]), "model_config_id": digest(documents)}


def load_property_catalog(root=ROOT):
    properties = read_json(Path(root) / "config" / "constraints.json")["properties"]
    require(isinstance(properties, list) and bool(properties), "Каталог свойств пуст.")
    seen = set()
    for item in properties:
        require(isinstance(item, dict) and isinstance(item.get("property"), str), "Некорректное свойство.")
        require(item["property"] not in seen, "Свойство повторяется в каталоге.")
        require(isinstance(item.get("name"), str) and bool(item["name"].strip()), "У свойства отсутствует название.")
        require(item.get("type") in {"boolean", "numeric", "categorical"}, "Неизвестный тип свойства.")
        if item["type"] == "categorical":
            require(isinstance(item.get("value_labels"), dict) and bool(item["value_labels"]), "Нет значений категориального свойства.")
            require(all(isinstance(k, str) and isinstance(v, str) and v for k, v in item["value_labels"].items()), "Некорректные названия категорий.")
        seen.add(item["property"])
    return properties


def build_user_model(case, root=ROOT):
    """Translate requirements; the existing Model and decision engine do the rest."""
    require(type(case) is UserCase, "Ожидается пользовательский кейс.")
    model = load_model(root)
    catalog = {p["property"]: p for p in load_property_catalog(root)}
    require(isinstance(case.weights, dict) and set(case.weights) == {c["id"] for c in model.criteria}, "Задайте значимость всех шести критериев.")
    require(all(number(w) and w >= 0 for w in case.weights.values()), "Значимости должны быть конечными неотрицательными числами.")
    require(any(w > 0 for w in case.weights.values()), "Все веса равны нулю. Задайте положительную значимость хотя бы одного критерия.")
    normalize_weights(case.weights)
    for criterion in model.criteria:
        criterion["weight"] = case.weights[criterion["id"]]
    require(isinstance(case.constraints, list), "Ограничения должны быть списком.")
    rules = []
    for index, constraint in enumerate(case.constraints, 1):
        require(isinstance(constraint, dict) and set(constraint) == {"name", "property", "operator", "required_value"}, "У ограничения должны быть только название, свойство, оператор и требуемое значение.")
        name, prop = constraint["name"], constraint["property"]
        require(isinstance(name, str) and bool(name.strip()), "Укажите название ограничения.")
        require(isinstance(prop, str) and prop in catalog, "Выберите свойство из параметров модели.")
        kind = catalog[prop]["type"]
        operator, value = constraint["operator"], constraint["required_value"]
        rule = {"id": f"U{index}", "name": name.strip(), "property": prop, "enabled": True}
        if kind == "boolean":
            require(operator == "==" and isinstance(value, bool), "Для логического свойства выберите равно и Да/Нет.")
            rule.update(type="boolean", expected=value)
        elif kind == "numeric":
            require(operator in (">=", "<=") and number(value), "Для числового свойства выберите не меньше/не больше и конечное число.")
            rule.update(type="numeric_min" if operator == ">=" else "numeric_max", threshold=value)
        else:
            require(operator == "in" and isinstance(value, list) and bool(value), "Выберите хотя бы одно допустимое значение.")
            require(all(isinstance(v, str) and v in catalog[prop]["value_labels"] for v in value), "Неизвестная категория свойства.")
            rule.update(type="categorical", allowed_values=deepcopy(value))
        rules.append(rule)
    model.constraints = rules
    model.case_id = "user"
    model.labels.update(configuration_identity(root))
    validate_model(model)
    return model


def export_user_case(result):
    """Export the calculated snapshot, never unsaved UI edits."""
    snapshot = result.input_snapshot
    require(snapshot["case_id"] == "user", "Это не пользовательский кейс.")
    constraints = []
    for rule in snapshot["constraints"]:
        operator, value = {
            "boolean": ("==", rule.get("expected")),
            "numeric_min": (">=", rule.get("threshold")),
            "numeric_max": ("<=", rule.get("threshold")),
            "categorical": ("in", rule.get("allowed_values")),
        }[rule["type"]]
        constraints.append({"name": rule["name"], "property": rule["property"], "operator": operator, "required_value": deepcopy(value)})
    return {"schema_version": 1, "kind": "user", "weights": {c["id"]: c["weight"] for c in snapshot["criteria"]},
            "normalized_weights": deepcopy(result.normalized_weights), "constraints": constraints,
            "architecture_config_id": snapshot["labels"]["architecture_config_id"],
            "model_config_id": snapshot["labels"]["model_config_id"], "calculation_id": result.calculation_id}
