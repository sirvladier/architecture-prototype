"""Mandatory eligibility checks, before any ranking."""

from src.models import number


def check_constraints(architectures, constraints):
    feasible, excluded = [], []
    for architecture in architectures:
        violations = []
        for rule in constraints:
            if not rule["enabled"]:
                continue
            value = architecture["properties"].get(rule["property"])
            kind = rule["type"]
            if kind == "boolean":
                expected, operator = rule["expected"], "=="
                passed = isinstance(value, bool) and value is expected
            elif kind == "numeric_min":
                expected, operator = rule["threshold"], ">="
                passed = number(value) and value >= expected
            elif kind == "numeric_max":
                expected, operator = rule["threshold"], "<="
                passed = number(value) and value <= expected
            elif kind == "categorical":
                expected, operator = rule["allowed_values"], "in"
                passed = isinstance(value, str) and value in expected
            else:
                raise ValueError(f"Unknown constraint type: {kind}")
            if not passed:
                violations.append({"constraint_id": rule["id"], "name": rule["name"], "property": rule["property"], "actual": value, "operator": operator, "expected": expected, "reason": "missing_property" if value is None else "condition_failed"})
        if violations:
            excluded.append({"architecture": architecture["id"], "name": architecture["name"], "status": "excluded", "violated_constraints": violations})
        else:
            feasible.append(architecture)
    return feasible, excluded
