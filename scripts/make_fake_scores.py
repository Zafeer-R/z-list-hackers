"""
Generate fake scores from features for testing until D's real scores arrive.
Usage:
    python scripts/make_fake_scores.py data/features_TX_2022.csv data/scores_fake.csv
"""

import argparse
import sys
import numpy as np
import pandas as pd

# Import FEATURES labels from build_features.py
sys.path.insert(0, '.')
from build_features import FEATURES


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("features_file")
    ap.add_argument("output_file")
    args = ap.parse_args()

    # Load features
    features = pd.read_csv(args.features_file, dtype={"npi": str})

    # Filter: eligible and not too_small
    mask = (features["eligible"]) & (features["peer_level"] != "too_small")
    df = features[mask].copy()

    # Get feature percentile columns
    pct_cols = [f"{feat}_pct" for feat in FEATURES.keys()]

    # Calculate rules_score: count of percentiles >= 0.9
    rules_score = (df[pct_cols] >= 0.9).sum(axis=1)

    # Calculate anomaly_score: mean of available percentiles
    anomaly_score = df[pct_cols].mean(axis=1)

    # Calculate combined_score: blend rules and anomaly, scaled to 0-100
    # Normalize both to 0-1, then blend: 50% rules + 50% anomaly
    rules_norm = rules_score / 8.0
    combined_raw = 0.5 * rules_norm + 0.5 * anomaly_score
    combined_score = (combined_raw * 100).round(1)

    # Calculate ranks (1 = most unusual, i.e., highest score)
    combined_rank = ((-combined_score).argsort() + 1).argsort() + 1
    rules_rank = ((-rules_score).argsort() + 1).argsort() + 1
    anomaly_rank = ((-anomaly_score).argsort() + 1).argsort() + 1
    baseline_rank = ((-df["Tot_Drug_Cst"]).argsort() + 1).argsort() + 1

    # Build output dataframe
    out = pd.DataFrame({
        "npi": df["npi"],
        "specialty": df["Prscrbr_Type"],
        "state": df["Prscrbr_State_Abrvtn"],
        "tot_clms": df["Tot_Clms"],
        "tot_drug_cst": df["Tot_Drug_Cst"],
        "rules_score": rules_score,
        "anomaly_score": anomaly_score.round(4),
        "combined_score": combined_score,
        "combined_rank": combined_rank,
        "rules_rank": rules_rank,
        "anomaly_rank": anomaly_rank,
        "baseline_rank": baseline_rank,
        "low_peer_flag": df["peer_fallback"],
        "is_suppressed": df["is_suppressed"],
    })

    # Generate reasons: three highest percentiles with plain labels
    # For each provider, find top 3 percentiles and create reason sentences
    reasons_data = {1: [], 2: [], 3: []}
    features_data = {1: [], 2: [], 3: []}

    for i, (orig_idx, row) in enumerate(df.iterrows()):
        if i % 10000 == 0:
            print(f"Processing row {i}...", flush=True)
        # Get all available percentiles with feature info
        pct_list = []
        for feat in FEATURES.keys():
            pct_col = f"{feat}_pct"
            if pd.notna(row[pct_col]):
                pct_list.append({
                    "feature": feat,
                    "label": FEATURES[feat],
                    "pct": row[pct_col]
                })

        # Sort by percentile (highest first)
        pct_list.sort(key=lambda x: x["pct"], reverse=True)

        # Generate reason sentences for top 3
        for reason_num in [1, 2, 3]:
            if reason_num - 1 < len(pct_list):
                data = pct_list[reason_num - 1]
                pct_val = data["pct"]
                percentile_text = f"top {max(1, round(100 * (1 - pct_val)))}%"
                reason_text = (
                    f"{data['label']} is in the {percentile_text} of "
                    f"{row['Prscrbr_Type']} peers in {row['Prscrbr_State_Abrvtn']}"
                )
                reasons_data[reason_num].append(reason_text)
                features_data[reason_num].append(data["feature"])
            else:
                reasons_data[reason_num].append("")
                features_data[reason_num].append("")

    for reason_num in [1, 2, 3]:
        out[f"reason_{reason_num}"] = reasons_data[reason_num]
        out[f"reason_{reason_num}_feature"] = features_data[reason_num]

    # Reorder columns to match expected schema
    cols = [
        "npi", "specialty", "state", "tot_clms", "tot_drug_cst",
        "rules_score", "anomaly_score", "combined_score",
        "combined_rank", "rules_rank", "anomaly_rank", "baseline_rank",
        "reason_1", "reason_2", "reason_3",
        "reason_1_feature", "reason_2_feature", "reason_3_feature",
        "low_peer_flag", "is_suppressed"
    ]
    out = out[cols]

    out.to_csv(args.output_file, index=False)
    print(f"wrote {args.output_file}: {len(out):,} providers")


if __name__ == "__main__":
    main()
