"""Keep observed values, substitutes and their provenance separate."""


def resolve_values(architectures, feasible_ids, missing_policy):
    values, uncertain, blocking = {}, [], []
    for architecture in architectures:
        arch_id = architecture["id"]
        values[arch_id] = {}
        for criterion, rating in architecture["ratings"].items():
            missing = rating["status"] == "missing"
            use_model = missing and missing_policy == "model_or_block" and rating.get("model_value") is not None
            used = rating.get("model_value") if use_model else rating.get("value")
            values[arch_id][criterion] = used
            if rating["status"] != "confirmed":
                item = {"architecture": arch_id, "criterion": criterion, "status": rating["status"], "original_value": rating.get("value"), "model_value": rating.get("model_value"), "used_value": used, "model_value_used": use_model, "architecture_is_feasible": arch_id in feasible_ids, "used_in_ranking": arch_id in feasible_ids, "source": "model_value" if use_model else "missing" if missing else "value"}
                uncertain.append(item)
                if used is None and arch_id in feasible_ids:
                    blocking.append(item)
    if blocking:
        for item in uncertain:
            item["used_in_ranking"] = False
    return values, uncertain, blocking
