"""Bidirectional, discrete one-weight sensitivity with proportional rescaling."""

import math

import numpy as np

from src.scoring import normalize_weights, rank_alternatives


def reweight(weights, criterion, target, zero_remainder_policy="uniform"):
    if not 0 <= target <= 1:
        raise ValueError("Target weight must be in [0, 1]")
    weights = normalize_weights(weights)
    others = [key for key in weights if key != criterion]
    remainder = math.fsum(weights[key] for key in others)
    if remainder == 0 and target < 1:
        if zero_remainder_policy == "skip":
            return None
        if zero_remainder_policy != "uniform":
            raise ValueError("Unknown zero remainder policy")
        result = {key: (1 - target) / len(others) for key in others}
    else:
        result = {key: (1 - target) * weights[key] / remainder if remainder else 0.0 for key in others}
    result[criterion] = float(target)
    return {key: result[key] for key in weights}


def candidate_weights(original, bound, step):
    distance = abs(bound - original)
    if distance == 0:
        return []
    sign = 1 if bound > original else -1
    count = int(math.ceil(distance / step))
    candidates = original + sign * np.arange(1, count + 1, dtype=float) * step
    candidates = np.clip(candidates, min(original, bound), max(original, bound))
    candidates[-1] = bound
    return list(dict.fromkeys(float(value) for value in candidates))


def analyze_sensitivity(architectures, criteria, values, weights, settings, tolerance, winner, baseline_status):
    weights = normalize_weights(weights)
    rows = []
    for criterion in criteria:
        key = criterion["id"]
        original = weights[key]
        row = {"criterion": key, "name": criterion["name"], "original_weight": original, "nearest_switch_weight": None, "switch_weight": None, "delta": None, "signed_delta": None, "new_winner": None, "nearest_tie_weight": None, "tie_delta": None, "tie_signed_delta": None, "tie_winners": [], "stable_in_explored_range": None, "no_switch_in_explored_range": None, "unique_winner_preserved": None, "range": [settings["min_weight"], settings["max_weight"]], "step": settings["step"], "directions": {}}
        if baseline_status != "ok":
            row["status"] = f"not_applicable_{baseline_status}"
            rows.append(row)
            continue
        if not settings["min_weight"] <= original <= settings["max_weight"]:
            row["status"] = "original_outside_range"
            rows.append(row)
            continue
        switches, ties = [], []
        for direction, bound in (("decrease", settings["min_weight"]), ("increase", settings["max_weight"])):
            detail = {"switch_weight": None, "delta": None, "new_winner": None, "first_tie_weight": None, "tie_delta": None, "tie_winners": [], "tested_count": 0, "status": "stable_sampled", "last_tested_weight": original}
            for target in candidate_weights(original, bound, settings["step"]):
                adjusted = reweight(weights, key, target, settings["zero_remainder_policy"])
                if adjusted is None:
                    detail["status"] = "not_testable_zero_remainder"
                    break
                _, winners, status = rank_alternatives(architectures, criteria, values, adjusted, tolerance)
                detail["tested_count"] += 1
                detail["last_tested_weight"] = target
                if status == "tie" and detail["first_tie_weight"] is None:
                    detail["first_tie_weight"] = target
                    detail["tie_delta"] = abs(target - original)
                    detail["tie_winners"] = winners
                    ties.append(detail)
                # A tie is recorded separately; a switch requires a different unique winner.
                if status == "ok" and winners[0] != winner and detail["switch_weight"] is None:
                    detail.update(switch_weight=target, delta=abs(target - original), new_winner=winners[0], status="switch_found")
                    switches.append(detail)
            if detail["first_tie_weight"] is not None and detail["switch_weight"] is None:
                detail["status"] = "tie_found"
            row["directions"][direction] = detail
        if ties:
            nearest_tie = min(ties, key=lambda item: (item["tie_delta"], item["first_tie_weight"]))
            row.update(nearest_tie_weight=nearest_tie["first_tie_weight"], tie_delta=nearest_tie["tie_delta"], tie_signed_delta=nearest_tie["first_tie_weight"] - original, tie_winners=nearest_tie["tie_winners"])
        fully_explored = all(d["status"] != "not_testable_zero_remainder" for d in row["directions"].values())
        row["no_switch_in_explored_range"] = not switches if fully_explored else None
        row["unique_winner_preserved"] = not ties and not switches if fully_explored else None
        if switches:
            nearest = min(switches, key=lambda item: (item["delta"], item["switch_weight"]))
            row.update(nearest_switch_weight=nearest["switch_weight"], switch_weight=nearest["switch_weight"], delta=nearest["delta"], signed_delta=nearest["switch_weight"] - original, new_winner=nearest["new_winner"], status="switch_found", stable_in_explored_range=False)
        elif any(d["status"] == "not_testable_zero_remainder" for d in row["directions"].values()):
            row["status"] = "partially_explored"
        elif ties:
            row.update(status="tie_found", stable_in_explored_range=False)
        else:
            row.update(status="stable_sampled", stable_in_explored_range=True)
        rows.append(row)
    return rows
