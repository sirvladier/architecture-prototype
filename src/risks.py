"""Evaluate only configured conditions, using the actual scoring values."""

import operator


OPERATORS = {"<": operator.lt, "<=": operator.le, ">": operator.gt, ">=": operator.ge, "==": operator.eq, "in": lambda value, threshold: value in threshold}


def evaluate_risks(architecture, rules, values, ratings):
    results = []
    for rule in rules:
        if rule["architecture"] != architecture:
            continue
        criterion = rule["criterion"]
        value = values[architecture][criterion]
        if value is not None and OPERATORS[rule["operator"]](value, rule["threshold"]):
            results.append({**rule, "used_value": value, "data_status": ratings[criterion]["status"], "model_value_used": ratings[criterion]["status"] == "missing"})
    return results
