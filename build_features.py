"""
Build the `features` file (Lane C) from Lane A's `panel` file.

Usage:
    python build_features.py panel_TX_2022.csv features_TX_2022.csv
    python build_features.py panel_TX_2022.csv features_TX_2022.csv --min-claims 50

Only pandas and numpy, so it runs on LinuxONE. Reads the panel only, never the labels.

Output: one row per NPI with
  - eight raw ratios, all pointing the same way (higher = more unusual)
  - the same eight as 0-1 rank percentiles within specialty x state (`<feature>_pct`)
  - peer group info: peer_n, peer_fallback, peer_level, peer_used_n
  - data quality info: n_imputed, is_suppressed, n_features_missing
  - eligible: True if Tot_Clms >= --min-claims. Ineligible rows keep their raw ratios
    but get blank percentiles, so scoring should filter on eligible == True.
"""

import argparse

import numpy as np
import pandas as pd

SUPPRESSED_GUESS = 5   # CMS blanks values of 1 to 10; CMS suggests imputing 5
MIN_PEERS = 20         # smallest group we trust for percentiles
MIN_DENOMINATOR = 11   # don't build a share on a denominator that was itself suppressed

# Feature name -> plain label, for D's reason sentences and C's app
FEATURES = {
    "cost_per_claim": "Drug cost per prescription",
    "cost_per_bene": "Drug cost per patient",
    "claims_per_bene": "Prescriptions per patient",
    "days_supply_per_bene": "Days of medication per patient",
    "brand_share": "Brand-name share of prescriptions",
    "opioid_rate": "Opioid share of prescriptions",
    "opioid_la_rate": "Long-acting share of opioid prescriptions",
    "antipsych_share_65": "Antipsychotic share of prescriptions for patients 65+",
}


def safe_div(num, den, min_den=1):
    """Divide, returning NaN where the denominator is missing or too small."""
    den = den.where(den >= min_den)
    return num / den


def clean_inputs(p):
    """Fill suppressed counts where the CMS rules let us; leave the rest blank."""
    q = pd.DataFrame(index=p.index)
    imputed = pd.DataFrame(index=p.index)

    # Beneficiaries: blank means 1 to 10. Kept blank because it is a denominator.
    q["benes"] = p["Tot_Benes"]

    # Brand claims: '*' means 1 to 10 -> 5. '#' was hidden to protect another cell,
    # so the true value is unknown and stays blank.
    brand = p["Brnd_Tot_Clms"].copy()
    star = p["Brnd_Sprsn_Flag"].eq("*")
    brand[star] = SUPPRESSED_GUESS
    q["brand"] = brand
    imputed["brand"] = star

    # Opioid and long-acting opioid claims: zeros are reported, blanks mean 1 to 10.
    for src, dst in [("Opioid_Tot_Clms", "opioid"), ("Opioid_LA_Tot_Clms", "opioid_la")]:
        blank = p[src].isna()
        q[dst] = p[src].fillna(SUPPRESSED_GUESS)
        imputed[dst] = blank

    # Claims for patients 65+: '*' means 1 to 10 -> 5. '#' means the under-65 group
    # was 1 to 10, so 65+ is roughly total claims minus 5.
    ge65 = p["GE65_Tot_Clms"].copy()
    star = p["GE65_Sprsn_Flag"].eq("*")
    hash_ = p["GE65_Sprsn_Flag"].eq("#")
    ge65[star] = SUPPRESSED_GUESS
    ge65[hash_] = p.loc[hash_, "Tot_Clms"] - SUPPRESSED_GUESS
    q["ge65"] = ge65
    imputed["ge65"] = star | hash_

    # Antipsychotics for 65+: '*' means 1 to 10 -> 5.
    anti = p["Antpsyct_GE65_Tot_Clms"].copy()
    star = p["Antpsyct_GE65_Sprsn_Flag"].eq("*") | anti.isna()
    anti[star] = SUPPRESSED_GUESS
    q["antipsych"] = anti
    imputed["antipsych"] = star

    return q, imputed


def build_ratios(p, q):
    f = pd.DataFrame(index=p.index)
    f["cost_per_claim"] = safe_div(p["Tot_Drug_Cst"], p["Tot_Clms"])
    f["cost_per_bene"] = safe_div(p["Tot_Drug_Cst"], q["benes"])
    f["claims_per_bene"] = safe_div(p["Tot_Clms"], q["benes"])
    f["days_supply_per_bene"] = safe_div(p["Tot_Day_Suply"], q["benes"])
    f["brand_share"] = safe_div(q["brand"], p["Tot_Clms"])
    f["opioid_rate"] = safe_div(q["opioid"], p["Tot_Clms"])
    # CMS definition: long-acting claims as a share of opioid claims. Only defined
    # when the provider has a reported (11+) opioid count; otherwise blank.
    reported_opioid = p["Opioid_Tot_Clms"].where(p["Opioid_Tot_Clms"] >= MIN_DENOMINATOR)
    f["opioid_la_rate"] = safe_div(q["opioid_la"], reported_opioid)
    f["antipsych_share_65"] = safe_div(q["antipsych"], q["ge65"], MIN_DENOMINATOR)
    return f.clip(lower=0, upper=None)


def peer_percentiles(df, feats):
    """0-1 rank percentile within specialty x state, falling back to specialty nationwide
    when the state group has fewer than MIN_PEERS eligible providers."""
    elig = df[df["eligible"]]
    state_keys = ["Prscrbr_Type", "Prscrbr_State_Abrvtn"]
    nat_keys = ["Prscrbr_Type"]

    state_n = elig.groupby(state_keys).size().rename("peer_n")
    nat_n = elig.groupby(nat_keys).size().rename("nat_n")
    df = df.join(state_n, on=state_keys).join(nat_n, on=nat_keys)
    df["peer_n"] = df["peer_n"].fillna(0).astype(int)
    df["nat_n"] = df["nat_n"].fillna(0).astype(int)

    df["peer_fallback"] = df["peer_n"] < MIN_PEERS
    df["peer_level"] = np.where(~df["peer_fallback"], "specialty_state",
                                np.where(df["nat_n"] >= MIN_PEERS, "specialty_national", "too_small"))
    df["peer_used_n"] = np.where(df["peer_fallback"], df["nat_n"], df["peer_n"])

    for col in feats:
        # Percentiles and non-blank counts at both levels, eligible providers only
        st_pct = elig.groupby(state_keys)[col].rank(pct=True, method="average")
        st_cnt = elig.groupby(state_keys)[col].transform("count")
        na_pct = elig.groupby(nat_keys)[col].rank(pct=True, method="average")
        na_cnt = elig.groupby(nat_keys)[col].transform("count")

        pct = pd.Series(np.nan, index=df.index)
        use_state = df["eligible"] & (df["peer_level"] == "specialty_state")
        use_nat = df["eligible"] & (df["peer_level"] == "specialty_national")
        pct[use_state] = st_pct.where(st_cnt >= MIN_PEERS).reindex(df.index)[use_state]
        pct[use_nat] = na_pct.where(na_cnt >= MIN_PEERS).reindex(df.index)[use_nat]
        df[f"{col}_pct"] = pct.round(4)

    return df.drop(columns=["nat_n"])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("panel")
    ap.add_argument("out")
    ap.add_argument("--min-claims", type=int, default=30,
                    help="providers below this claim count are kept but not scored")
    args = ap.parse_args()

    p = pd.read_csv(args.panel, dtype={"Prscrbr_NPI": str})
    q, imputed = clean_inputs(p)
    feats = build_ratios(p, q)

    out = pd.DataFrame({
        "npi": p["Prscrbr_NPI"].str.strip(),
        "Prscrbr_Type": p["Prscrbr_Type"],
        "Prscrbr_State_Abrvtn": p["Prscrbr_State_Abrvtn"],
        "Prscrbr_RUCA": p["Prscrbr_RUCA"],
        "Tot_Clms": p["Tot_Clms"],
        "Tot_Drug_Cst": p["Tot_Drug_Cst"],
        "Tot_Benes": p["Tot_Benes"],
        "eligible": p["Tot_Clms"] >= args.min_claims,
    })
    for col in FEATURES:
        out[col] = feats[col].round(6)

    out = peer_percentiles(out, list(FEATURES))

    out["n_imputed"] = imputed.sum(axis=1).astype(int) + p["Tot_Benes"].isna().astype(int)
    out["is_suppressed"] = out["n_imputed"] > 0
    out["n_features_missing"] = out[list(FEATURES)].isna().sum(axis=1)

    out.to_csv(args.out, index=False)

    e = out[out["eligible"]]
    print(f"wrote {args.out}: {len(out):,} rows, {len(e):,} eligible (Tot_Clms >= {args.min_claims})")
    print("peer levels among eligible:", e["peer_level"].value_counts().to_dict())


if __name__ == "__main__":
    main()
