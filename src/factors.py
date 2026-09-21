"""Differences against the closest feasible competitor."""


def influential_factors(ranking, criteria, count, tolerance):
    if len(ranking) < 2:
        return None, [], [], []
    winner, competitor = ranking[:2]
    candidates = [row["architecture"] for row in ranking[1:] if competitor["score"] - row["score"] <= tolerance]
    factors = [{"criterion": c["id"], "name": c["name"], "winner_contribution": winner["contributions"][c["id"]], "runner_up_contribution": competitor["contributions"][c["id"]], "difference": winner["contributions"][c["id"]] - competitor["contributions"][c["id"]]} for c in criteria]
    positive = sorted((f for f in factors if f["difference"] > 0), key=lambda f: (-f["difference"], f["criterion"]))[:count]
    negative = sorted((f for f in factors if f["difference"] < 0), key=lambda f: (f["difference"], f["criterion"]))[:count]
    return competitor["architecture"], candidates, positive, negative
