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
_exclusions = {}


def load_data():
    """Load and cache features, scores, and labels. Precompute peer medians."""
    global _features, _scores, _labels, _merged, _peer_medians

    # Load features
    _features = pd.read_csv(config.FEATURES_FILE, dtype={"npi": str})

    # Load scores
    _scores = pd.read_csv(config.SCORES_FILE, dtype={"npi": str})

    # Load labels
    _labels = pd.read_csv(config.LABELS_FILE, dtype={"npi": str})

    global _exclusions
    _exclusions = {
        npi: (bool(any_), date)
        for npi, any_, date in zip(_labels["npi"], _labels["label_any"].fillna(0), _labels["exclusion_date"])
    }

    # Private pseudonyms: every scored provider must have one, or the app fails at startup
    pseudonyms = pd.read_csv(config.PSEUDONYMS_FILE, dtype={"npi": str})

    # Join features, scores and pseudonyms on npi
    _merged = _features.merge(_scores, on="npi", how="inner", suffixes=("_feat", "_score"))
    _merged = _merged.merge(pseudonyms, on="npi", how="left", validate="one_to_one")
    assert _merged["pseudonym"].notna().all(), "scored providers without a pseudonym"

    # Precompute peer medians: for each feature, compute the median within each peer group
    # Peer groups are defined by (Prscrbr_Type, Prscrbr_State_Abrvtn) for specialty_state peers
    _peer_medians = {}
    for feat in FEATURES.keys():
        medians = _merged.groupby(["Prscrbr_Type", "Prscrbr_State_Abrvtn"])[feat].median()
        _peer_medians[feat] = medians


def ranked_list(state=None, specialty=None, min_score=0, npi_search=None, show_exclusion=False):
    """
    Filter providers by state, specialty, minimum score, and NPI or pseudonym search.
    Return dataframe sorted by combined_rank, with pseudonyms in place of NPIs.
    Exclusion status is added only when show_exclusion is True (hidden by default).
    """
    if _merged is None:
        load_data()

    df = _merged
    mask = pd.Series(True, index=df.index)
    if state:
        mask &= df["Prscrbr_State_Abrvtn"] == state
    if specialty:
        mask &= df["Prscrbr_Type"] == specialty
    if min_score:
        mask &= df["combined_score"] >= min_score
    if npi_search:
        search_str = str(npi_search).strip().upper()
        mask &= (df["npi"] == search_str) | (df["pseudonym"] == search_str)

    cols = ["npi", "combined_rank", "pseudonym", "Prscrbr_Type", "Prscrbr_State_Abrvtn", "combined_score", "rules_score", "reason_1"]
    out = df.loc[mask, cols].sort_values("combined_rank").reset_index(drop=True)
    if show_exclusion:
        out["excluded_later"] = out["npi"].map(lambda n: "Yes" if _exclusions.get(n, (False, None))[0] else "No")
    return out.drop(columns="npi")


def npi_for_rank(rank):
    """Look up the full NPI for a combined_rank. Used so URLs never carry the full NPI."""
    if _merged is None:
        load_data()
    row = _merged[_merged["combined_rank"] == int(rank)]
    if len(row) == 0:
        return None
    return row.iloc[0]["npi"]


def provider_detail(npi, show_exclusion=False):
    """
    Get detailed view for a single provider.
    Returns dict with score, rules_score, three reasons with percentiles,
    peer group info, and all eight features with raw value, peer median, percentile.
    Exclusion status is included only when show_exclusion is True.
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
        "pseudonym": row["pseudonym"],
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

    if show_exclusion:
        excluded, date = _exclusions.get(npi_str, (False, None))
        result["exclusion_month"] = (
            pd.to_datetime(date).strftime("%B %Y") if excluded and pd.notna(date) else None
        )

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
