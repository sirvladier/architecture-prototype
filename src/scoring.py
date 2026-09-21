"""Weighted sum and explicit ties; no random tie-breaking."""

import math

from src.models import ConfigError, number


def normalize_weights(weights):
    if not weights or any(not number(w) or w < 0 for w in weights.values()):
        raise ConfigError("Weights must be finite and nonnegative")
    largest = max(weights.values())
    if largest == 0:
        raise ConfigError("At least one weight must be positive")
    scaled = {key: value / largest for key, value in weights.items()}
    total = math.fsum(scaled.values())
    return {key: value / total for key, value in scaled.items()}


def normalized_value(value, direction):
    if not number(value) or not 1 <= value <= 5:
        raise ConfigError("A rating must be a finite number in [1, 5]")
    if direction == "maximize":
        return value / 5
    if direction == "minimize":
        return (6 - value) / 5
    raise ConfigError(f"Unknown preference direction: {direction}")


def rank_alternatives(architectures, criteria, values, weights, tolerance):
    weights = normalize_weights(weights)
    ranking = []
    for architecture in architectures:
        arch_id = architecture["id"]
        contributions = {c["id"]: weights[c["id"]] * normalized_value(values[arch_id][c["id"]], c["direction"]) for c in criteria}
        ranking.append({"architecture": arch_id, "name": architecture["name"], "score": min(1.0, max(0.0, math.fsum(contributions.values()))), "contributions": contributions})
    ranking.sort(key=lambda row: (-row["score"], row["architecture"]))
    if not ranking:
        return ranking, [], "no_feasible"
    winners = [row["architecture"] for row in ranking if ranking[0]["score"] - row["score"] <= tolerance]
    return ranking, winners, "ok" if len(winners) == 1 else "tie"
