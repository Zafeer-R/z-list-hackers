"""Data loading, caching, and lookups. No UI imports."""

import pandas as pd
import numpy as np
from . import config
from build_features import FEATURES

# Cache
_features = None
_scores = None
_labels = None
_merged = None
_peer_medians = None


def load_data():
    """Load and cache features, scores, and labels. Precompute peer medians."""
    global _features, _scores, _labels, _merged, _peer_medians

    # Load features
    _features = pd.read_csv(config.FEATURES_FILE, dtype={"npi": str})

    # Load scores
    _scores = pd.read_csv(config.SCORES_FILE, dtype={"npi": str})

    # Load labels
    _labels = pd.read_csv(config.LABELS_FILE, dtype={"npi": str})

    # Join features and scores on npi
    _merged = _features.merge(_scores, on="npi", how="inner", suffixes=("_feat", "_score"))

    # Precompute peer medians: for each feature, compute the median within each peer group
    # Peer groups are defined by (Prscrbr_Type, Prscrbr_State_Abrvtn) for specialty_state peers
    _peer_medians = {}
    for feat in FEATURES.keys():
        medians = _merged.groupby(["Prscrbr_Type", "Prscrbr_State_Abrvtn"])[feat].median()
        _peer_medians[feat] = medians


def mask_npi(npi):
    """Return masked NPI: ****** plus last 4 digits."""
    npi_str = str(npi).strip()
    if len(npi_str) >= 4:
        return f"**{npi_str[-4:]}"
    return "****"


def ranked_list(state=None, specialty=None, min_score=0, npi_search=None):
    """
    Filter providers by state, specialty, minimum score, and NPI search.
    Return dataframe sorted by combined_rank, with masked NPIs.
    """
    if _merged is None:
        load_data()

    df = _merged.copy()

    # Apply filters
    if state:
        df = df[df["Prscrbr_State_Abrvtn"] == state]
    if specialty:
        df = df[df["Prscrbr_Type"] == specialty]
    if min_score:
        df = df[df["combined_score"] >= min_score]
    if npi_search:
        # Search by last 4 digits or full NPI
        search_str = str(npi_search).strip()
        if len(search_str) <= 4:
            df = df[df["npi"].str.endswith(search_str)]
        else:
            df = df[df["npi"] == search_str]

    # Sort by combined_rank (ascending)
    df = df.sort_values("combined_rank").reset_index(drop=True)

    # Mask NPIs
    df["npi_masked"] = df["npi"].apply(mask_npi)

    return df[["combined_rank", "npi_masked", "Prscrbr_Type", "Prscrbr_State_Abrvtn", "combined_score", "rules_score", "reason_1"]]


def npi_for_rank(rank):
    """Look up the full NPI for a combined_rank. Used so URLs never carry the full NPI."""
    if _merged is None:
        load_data()
    row = _merged[_merged["combined_rank"] == int(rank)]
    if len(row) == 0:
        return None
    return row.iloc[0]["npi"]


def provider_detail(npi):
    """
    Get detailed view for a single provider.
    Returns dict with score, rules_score, three reasons with percentiles,
    peer group info, and all eight features with raw value, peer median, percentile.
    """
    if _merged is None:
        load_data()

    npi_str = str(npi).strip()
    row = _merged[_merged["npi"] == npi_str]

    if len(row) == 0:
        return None

    row = row.iloc[0]

    # Build result
    result = {
        "npi": npi_str,
        "npi_masked": mask_npi(npi_str),
        "specialty": row["Prscrbr_Type"],
        "state": row["Prscrbr_State_Abrvtn"],
        "combined_score": row["combined_score"],
        "rules_score": row["rules_score"],
        "peer_group": {
            "specialty": row["Prscrbr_Type"],
            "state": row["Prscrbr_State_Abrvtn"],
            "peer_used_n": int(row["peer_used_n"]),
            "peer_fallback": bool(row["peer_fallback"]),
            "peer_level": row["peer_level"],
        },
        "reasons": [],
        "features": [],
    }

    # Three reasons
    for i in [1, 2, 3]:
        reason_col = f"reason_{i}"
        feature_col = f"reason_{i}_feature"
        if reason_col in row and pd.notna(row[reason_col]) and len(str(row[reason_col])) > 0:
            feature_name = row[feature_col]
            pct_col = f"{feature_name}_pct"
            result["reasons"].append({
                "text": row[reason_col],
                "feature": feature_name,
                "percentile": row[pct_col] if pct_col in row and pd.notna(row[pct_col]) else None
            })

    # Eight features with raw value, peer median, percentile
    for feat in FEATURES.keys():
        raw_col = feat
        pct_col = f"{feat}_pct"
        raw_val = row[raw_col] if raw_col in row and pd.notna(row[raw_col]) else None
        pct_val = row[pct_col] if pct_col in row and pd.notna(row[pct_col]) else None

        # Get peer median
        peer_med = None
        if feat in _peer_medians:
            try:
                peer_med = _peer_medians[feat].loc[(row["Prscrbr_Type"], row["Prscrbr_State_Abrvtn"])]
            except KeyError:
                peer_med = None

        result["features"].append({
            "name": feat,
            "label": FEATURES[feat],
            "raw_value": raw_val,
            "peer_median": peer_med,
            "percentile": pct_val,
        })

    # Optional exclusion status
    if config.ENABLE_EXCLUSION_STATUS:
        label_row = _labels[_labels["npi"] == npi_str]
        if len(label_row) > 0:
            label_row = label_row.iloc[0]
            result["exclusion_status"] = {
                "is_excluded": bool(label_row["label_any"]),
                "exclusion_type": label_row["exclusion_type"] if pd.notna(label_row["exclusion_type"]) else None,
                "exclusion_date": label_row["exclusion_date"] if pd.notna(label_row["exclusion_date"]) else None,
            }

    return result


def get_stats():
    """Return basic statistics about the dataset."""
    if _merged is None:
        load_data()

    return {
        "total_providers": len(_merged),
        "states": sorted(_merged["Prscrbr_State_Abrvtn"].unique()),
        "specialties": sorted(_merged["Prscrbr_Type"].unique()),
    }
