"""Technical fixture validation, not a user or expert study."""

import argparse
import json
from pathlib import Path

import pandas as pd

from src.explanation import build_explanation, validate_explanation
from src.models import ROOT, apply_case, load_cases, load_model, read_json
from src.user_cases import configuration_identity


def validate_case(result, expected):
    errors = []
    actual = {"status": result.status, "recommended_architecture": result.recommended_architecture, "excluded_count": len(result.excluded_alternatives), "uncertain_count": len(result.uncertain_data), "based_on_incomplete_data": result.based_on_incomplete_data}
    for key, value in expected.items():
        if key == "max_runner_up_gap":
            passed = len(result.ranking) >= 2 and result.ranking[0]["score"] - result.ranking[1]["score"] <= value
        elif key == "max_switch_delta":
            deltas = [s["delta"] for s in result.sensitivity if s["delta"] is not None]
            passed = bool(deltas) and min(deltas) <= value + 1e-12
        else:
            passed = key in actual and actual[key] == value
        if not passed:
            errors.append(f"Case expectation failed: {key}={value}")
    return errors


def run_experiment(root=ROOT, output=None):
    root = Path(root)
    output = Path(output) if output is not None else root / "data" / "experiment_results.csv"
    output.parent.mkdir(parents=True, exist_ok=True)
    base = load_model(root)
    snapshot = {"schema_version": 1, **configuration_identity(root),
                "configuration": {name: read_json(root / "config" / f"{name}.json")
                                  for name in ("architectures", "criteria", "constraints", "risks")},
                "model_cases": read_json(root / "data" / "example_cases.json")}
    snapshot_path = output.with_name(output.stem + "_config_snapshot.json")
    rows, records = [], []
    for case in snapshot["model_cases"]["cases"]:
        result = build_explanation(apply_case(base, case))
        errors = validate_explanation(result) + validate_case(result, case.get("expected", {}))
        deltas = [row["delta"] for row in result.sensitivity if row["delta"] is not None]
        tie_deltas = [row["tie_delta"] for row in result.sensitivity if row["tie_delta"] is not None]
        rows.append({
            "model_config_id": snapshot["model_config_id"], "config_snapshot": snapshot_path.name,
            "case_id": case["id"], "recommended_architecture": result.recommended_architecture,
            "excluded_count": len(result.excluded_alternatives),
            "positive_factor_count": len(result.main_positive_factors),
            "negative_factor_count": len(result.main_negative_factors),
            "risk_count": len(result.risks), "uncertain_count": len(result.uncertain_data),
            "nearest_sensitivity_delta": min(deltas) if deltas else None,
            "nearest_tie_delta": min(tie_deltas) if tie_deltas else None,
            "validation_passed": not errors, "status": result.status,
            "based_on_incomplete_data": result.based_on_incomplete_data,
            "calculation_id": result.calculation_id,
            "validation_errors": " | ".join(errors),
        })
        records.append({"case_id": case["id"], "expected": case.get("expected", {}), "validation_errors": errors, "explanation": result.to_dict()})
    frame = pd.DataFrame(rows)
    frame.to_csv(output, index=False, encoding="utf-8-sig", lineterminator="\n", float_format="%.12g")
    output.with_suffix(".json").write_text(json.dumps(records, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    snapshot_path.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    return frame


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    frame = run_experiment(args.root, args.output)
    print(frame[["case_id", "status", "recommended_architecture", "validation_passed"]].to_string(index=False))
    return 0 if frame["validation_passed"].all() else 1


if __name__ == "__main__":
    raise SystemExit(main())
