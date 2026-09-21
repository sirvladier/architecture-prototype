"""JSON configuration, explicit data contracts and input validation."""

from copy import deepcopy
from dataclasses import asdict, dataclass, field
import json
import math
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class ConfigError(ValueError):
    pass


def number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def require(condition, message):
    if not condition:
        raise ConfigError(message)


def read_json(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as exc:
        raise ConfigError(f"Cannot read {path}: {exc}") from exc


@dataclass
class Model:
    architectures: list
    criteria: list
    constraints: list
    risks: list
    settings: dict
    labels: dict
    case_id: str = "custom"

    def to_dict(self):
        return asdict(self)


@dataclass
class ExplanationData:
    status: str
    recommended_architecture: str | None = None
    score: float | None = None
    winners: list = field(default_factory=list)
    ranking: list = field(default_factory=list)
    excluded_alternatives: list = field(default_factory=list)
    feasible_alternatives: list = field(default_factory=list)
    runner_up: str | None = None
    runner_up_candidates: list = field(default_factory=list)
    main_positive_factors: list = field(default_factory=list)
    main_negative_factors: list = field(default_factory=list)
    risks: list = field(default_factory=list)
    uncertain_data: list = field(default_factory=list)
    sensitivity: list = field(default_factory=list)
    normalized_weights: dict = field(default_factory=dict)
    based_on_incomplete_data: bool = False
    has_uncertain_data: bool = False
    blocking_data: list = field(default_factory=list)
    calculation_id: str = ""
    input_snapshot: dict = field(default_factory=dict)

    def to_dict(self):
        return asdict(self)


def _unique_ids(rows, name):
    require(isinstance(rows, list), f"{name}: expected a list")
    ids = [row["id"] for row in rows]
    require(all(isinstance(i, str) and i for i in ids), f"{name}: invalid ID")
    require(len(ids) == len(set(ids)), f"{name}: duplicate IDs")
    return set(ids)


def validate_model(model):
    try:
        arch_ids = _unique_ids(model.architectures, "architectures")
        criterion_ids = _unique_ids(model.criteria, "criteria")
        _unique_ids(model.constraints, "constraints")
        risk_ids = _unique_ids(model.risks, "risks")
        require(arch_ids == {"A1", "A2", "A3"}, "Exactly A1, A2, A3 are required")
        require(criterion_ids == {f"K{i}" for i in range(1, 7)}, "Exactly K1..K6 are required")
        for criterion in model.criteria:
            require(criterion["direction"] in {"maximize", "minimize"}, "Invalid criterion direction")
            require(number(criterion["weight"]) and criterion["weight"] >= 0, "Weights must be finite and nonnegative")
            require(bool(criterion["name"]) and bool(criterion["description"]), "Criterion needs name and description")
        require(any(c["weight"] > 0 for c in model.criteria), "At least one weight must be positive")
        for architecture in model.architectures:
            require(set(architecture["ratings"]) == criterion_ids, f"{architecture['id']}: incomplete criteria")
            require(isinstance(architecture["properties"], dict), "Properties must be an object")
            require(set(architecture["risk_ids"]) <= risk_ids, "Unknown linked risk")
            for rating in architecture["ratings"].values():
                require(rating["status"] in {"confirmed", "estimated", "missing"}, "Invalid rating status")
                if rating["status"] == "missing":
                    require(rating.get("value") is None, "missing must have value=null; use model_value separately")
                else:
                    require(number(rating.get("value")) and 1 <= rating["value"] <= 5, "Ratings must be in [1, 5]")
                if rating.get("model_value") is not None:
                    require(number(rating["model_value"]) and 1 <= rating["model_value"] <= 5, "model_value must be in [1, 5]")
        for constraint in model.constraints:
            kind = constraint["type"]
            require(kind in {"boolean", "numeric_min", "numeric_max", "categorical"}, "Invalid constraint type")
            require(isinstance(constraint["enabled"], bool), "enabled must be boolean")
            require(isinstance(constraint["property"], str) and bool(constraint["property"]), "Invalid property")
            if kind == "boolean":
                require(isinstance(constraint["expected"], bool), "expected must be boolean")
            elif kind.startswith("numeric"):
                require(number(constraint["threshold"]), "Constraint threshold must be finite")
            else:
                require(isinstance(constraint["allowed_values"], list), "allowed_values must be a list")
                require(all(isinstance(v, str) for v in constraint["allowed_values"]), "Categories must be strings")
        for risk in model.risks:
            require(risk["architecture"] in arch_ids and risk["criterion"] in criterion_ids, "Unknown risk target")
            require(risk["operator"] in {"<", "<=", ">", ">=", "==", "in"}, "Invalid risk operator")
            threshold = risk["threshold"]
            require((isinstance(threshold, list) and all(number(v) for v in threshold)) if risk["operator"] == "in" else number(threshold), "Invalid risk threshold")
            require(isinstance(risk["text"], str) and bool(risk["text"]), "Risk needs text")
            target = next(a for a in model.architectures if a["id"] == risk["architecture"])
            require(risk["id"] in target["risk_ids"], "Risk must be linked from its architecture")
        for architecture in model.architectures:
            require(all(r["architecture"] == architecture["id"] for r in model.risks if r["id"] in architecture["risk_ids"]), "Risk linked to wrong architecture")
        settings = model.settings
        require(settings["tie_policy"] == "tie", "Only explicit tie policy is supported")
        require(number(settings["tie_tolerance"]) and 0 <= settings["tie_tolerance"] <= 1, "Invalid tie tolerance")
        require(type(settings["top_factor_count"]) is int and settings["top_factor_count"] >= 0, "Invalid factor count")
        require(settings["missing_policy"] in {"block", "model_or_block"}, "Invalid missing policy")
        sensitivity = settings["sensitivity"]
        require(number(sensitivity["step"]) and 0.0001 <= sensitivity["step"] <= 1, "Sensitivity step must be in [0.0001, 1]")
        require(number(sensitivity["min_weight"]) and number(sensitivity["max_weight"]) and 0 <= sensitivity["min_weight"] <= sensitivity["max_weight"] <= 1, "Invalid sensitivity range")
        require(sensitivity["zero_remainder_policy"] in {"uniform", "skip"}, "Invalid zero remainder policy")
    except (KeyError, TypeError, AttributeError) as exc:
        raise ConfigError(f"Malformed configuration: {exc}") from exc


def load_model(root=ROOT):
    root = Path(root)
    documents = {name: read_json(root / "config" / f"{name}.json") for name in ("architectures", "criteria", "constraints", "risks")}
    # Expand criterion-level configuration into the existing architecture-bound
    # risk contract. Validation and the calculation engine remain unchanged.
    configured_risks = documents["risks"]["risks"]
    _unique_ids(configured_risks, "configured risks")
    risks = []
    for rule in configured_risks:
        if "scope" in rule:
            require(rule["scope"] == "all_architectures" and "architecture" not in rule,
                    "Invalid risk scope")
            for architecture in documents["architectures"]["architectures"]:
                risks.append({**{key: value for key, value in rule.items() if key != "scope"},
                              "id": f"{rule['id']}_{architecture['id']}",
                              "architecture": architecture["id"]})
        else:
            risks.append(rule)
    model = Model(
        architectures=documents["architectures"]["architectures"],
        criteria=documents["criteria"]["criteria"],
        constraints=documents["constraints"]["constraints"],
        risks=risks,
        settings=documents["criteria"]["settings"],
        labels={key: value["data_label"] for key, value in documents.items()},
    )
    validate_model(model)
    return model


def load_cases(root=ROOT):
    cases = read_json(Path(root) / "data" / "example_cases.json")["cases"]
    _unique_ids(cases, "cases")
    return cases


def apply_case(model, case):
    result = deepcopy(model)
    result.case_id = case["id"]
    criterion_ids = {c["id"] for c in result.criteria}
    if "weights" in case:
        require(set(case["weights"]) == criterion_ids, "Case must specify all criterion weights")
        for criterion in result.criteria:
            criterion["weight"] = case["weights"][criterion["id"]]
    arch_lookup = {a["id"]: a for a in result.architectures}
    for arch_id, ratings in case.get("ratings", {}).items():
        require(arch_id in arch_lookup, f"Unknown architecture: {arch_id}")
        require(set(ratings) <= criterion_ids, "Unknown criterion in case")
        arch_lookup[arch_id]["ratings"].update(deepcopy(ratings))
    constraint_ids = {c["id"] for c in result.constraints}
    if "enabled_constraints" in case:
        require(set(case["enabled_constraints"]) <= constraint_ids, "Unknown constraint in case")
        for constraint in result.constraints:
            constraint["enabled"] = constraint["id"] in case["enabled_constraints"]
    overrides = case.get("constraint_overrides", {})
    require(set(overrides) <= constraint_ids, "Unknown constraint override")
    for constraint in result.constraints:
        changes = overrides.get(constraint["id"], {})
        allowed = {"boolean": {"expected"}, "numeric_min": {"threshold"}, "numeric_max": {"threshold"}, "categorical": {"allowed_values"}}[constraint["type"]]
        require(set(changes) <= allowed, "Only constraint parameters may be overridden")
        constraint.update(deepcopy(changes))
    validate_model(result)
    return result
