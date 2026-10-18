"""Lane D (Scoring): features_TX_2022.csv -> scores_TX_2022.csv, following the contract in CLAUDE.md.

Usage:
    python score.py data/features_TX_2022.csv data/scores_TX_2022.csv
    python score.py data/features_TX_2022.csv data/scores_TX_2022.csv --labels data/labels.csv

Libraries: pandas, numpy, scikit-learn (IsolationForest). Backtest comparison also uses xgboost.
The features file has no label columns. Labels are only read (optionally) for the backtest
printout and are never used to build scores_TX_2022.csv.
"""
import argparse
import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest
from build_features import FEATURES as PLAIN

FEATURES = list(PLAIN)
TOP_PCT = 0.90          # "top 10%" in specialty (percentiles are 0..1 in the features file)
SEED = 0
LATER_FROM = "2023-01-01"   # exclusions before this are not later exclusions (CLAUDE.md window)
LABEL_COLS = {"NPI", "EXCLDATE", "EXCLTYPE", "future_exclusion_match",
              "known_pre2023_exclusion", "evaluation_eligible"}

# Contract columns, in order (CLAUDE.md, scores_TX_2022.csv)
COLS = ["npi", "specialty", "state", "tot_clms", "tot_drug_cst", "rules_score", "anomaly_score",
        "combined_score", "combined_rank", "rules_rank", "anomaly_rank", "baseline_rank",
        "reason_1", "reason_2", "reason_3",
        "reason_1_feature", "reason_2_feature", "reason_3_feature",
        "low_peer_flag", "is_suppressed"]


def load_features(path):
    f = pd.read_csv(path, dtype={"npi": str}, low_memory=False)
    need = (["npi", "Prscrbr_Type", "Prscrbr_State_Abrvtn", "Tot_Clms", "Tot_Drug_Cst",
             "eligible", "peer_level"] + FEATURES + [c + "_pct" for c in FEATURES])
    missing = [c for c in need if c not in f.columns]
    assert not missing, f"features file is missing columns: {missing}"   # fail loudly
    assert not (LABEL_COLS & set(f.columns)), "label column found in features file (leakage)"
    assert f.npi.is_unique, "duplicate NPIs"
    f["eligible"] = f["eligible"].astype(str).str.lower().eq("true")
    return f


def sentence(feature, pct, specialty, state):
    top = max(1, round((1 - pct) * 100))
    return f"{PLAIN[feature]} is in the top {top}% of {specialty} peers in {state}"


def score(f):
    # Only providers that have real peer percentiles are scored
    s = f[f.eligible & (f.peer_level != "too_small")].reset_index(drop=True)
    R = s[FEATURES].to_numpy(dtype=float)                       # raw ratios
    P = s[[c + "_pct" for c in FEATURES]].to_numpy(dtype=float)  # 0..1 percentiles, NaN = blank

    # Rules score: value above zero AND in the top 10% of specialty. Blank never flags.
    flags = (R > 0) & (P >= TOP_PCT)                             # NaN compares as False
    s["rules_score"] = flags.sum(axis=1).astype(int)

    # Anomaly score: IsolationForest on percentiles (blank -> 0.5 for this step only)
    iso = IsolationForest(n_estimators=300, random_state=SEED, n_jobs=1).fit(np.nan_to_num(P, nan=0.5))
    s["anomaly_score"] = -iso.score_samples(np.nan_to_num(P, nan=0.5))   # higher = more unusual

    rr = s.rules_score.rank(pct=True, method="average")
    ar = s.anomaly_score.rank(pct=True, method="average")
    s["combined_score"] = (100 * (rr + ar) / 2).round(2)
    s["combined_rank"] = s.combined_score.rank(ascending=False, method="first").astype(int)
    s["rules_rank"] = s.rules_score.rank(ascending=False, method="min").astype(int)
    s["anomaly_rank"] = s.anomaly_score.rank(ascending=False, method="first").astype(int)
    s["baseline_rank"] = s.Tot_Drug_Cst.rank(ascending=False, method="first").astype(int)

    # Three reasons: highest percentiles among measures with value > 0
    cand = np.where(R > 0, P, np.nan)
    order = np.argsort(-np.nan_to_num(cand, nan=-1.0), axis=1)[:, :3]
    names = np.array(FEATURES)
    spec, state = s.Prscrbr_Type.to_numpy(), s.Prscrbr_State_Abrvtn.to_numpy()
    for k in range(3):
        idx = order[:, k]
        v = cand[np.arange(len(s)), idx]
        ok = ~np.isnan(v)
        feat = np.where(ok, names[idx], "")
        s[f"reason_{k+1}_feature"] = feat
        s[f"reason_{k+1}"] = [sentence(ft, pv, sp, st) if o else ""
                              for ft, pv, sp, st, o in zip(feat, v, spec, state, ok)]

    s["specialty"], s["state"] = s.Prscrbr_Type, s.Prscrbr_State_Abrvtn
    s["tot_clms"], s["tot_drug_cst"] = s.Tot_Clms, s.Tot_Drug_Cst
    s["low_peer_flag"] = (s.peer_fallback.astype(str).str.lower().eq("true")
                          if "peer_fallback" in s else s.peer_level != "specialty_state")
    s["is_suppressed"] = (s.is_suppressed.astype(str).str.lower().eq("true")
                          if "is_suppressed" in s else False)
    return s, P


def oof_xgboost(X, y):
    """Out-of-fold probabilities, averaged over 3 seeds. Comparison only."""
    import xgboost as xgb
    from sklearn.model_selection import StratifiedKFold
    spw = (len(y) - y.sum()) / max(y.sum(), 1)
    out = np.zeros(len(y))
    for seed in (0, 1, 2):
        for tr, va in StratifiedKFold(5, shuffle=True, random_state=seed).split(X, y):
            m = xgb.XGBClassifier(n_estimators=150, max_depth=3, learning_rate=0.05,
                                  scale_pos_weight=spw, random_state=seed, verbosity=0)
            m.fit(X[tr], y[tr])
            out[va] += m.predict_proba(X[va])[:, 1] / 3
    return out


def compare(s, P, labels_path):
    """Print backtest: later-excluded providers found in the top N, vs ranking by cost."""
    from sklearn.metrics import roc_auc_score
    m = pd.read_csv(labels_path, dtype={"npi": str}, usecols=["npi", "label_any", "exclusion_date"])
    d = s[["npi", "combined_score", "anomaly_score", "rules_score", "tot_drug_cst"]].merge(
        m, on="npi", how="left")
    label = d.label_any.fillna(0).eq(1)
    before_window = label & (pd.to_datetime(d.exclusion_date, errors="coerce") < LATER_FROM)
    keep = ~before_window.to_numpy()
    y = label.to_numpy()[keep].astype(int)
    X = np.nan_to_num(P, nan=0.5)[keep]
    cols = {"Combined score": d.combined_score.to_numpy()[keep],
            "IsolationForest": d.anomaly_score.to_numpy()[keep],
            "Rules score": d.rules_score.to_numpy()[keep].astype(float),
            "Total drug cost (baseline)": d.tot_drug_cst.to_numpy()[keep]}
    try:
        import xgboost
        cols[f"xgboost {xgboost.__version__} (out-of-fold)"] = oof_xgboost(X, y)
    except ImportError:
        print("NOTE: xgboost not installed, comparison column skipped")
    print(f"\nBacktest on {len(y):,} scored providers; {int(y.sum())} later excluded "
          f"(base rate {100*y.mean():.3f}%)")
    print(f"{'Score':<34}{'AUC':>7}{'top 100':>9}{'top 500':>9}{'top 1000':>10}")
    for name, v in cols.items():
        top = np.argsort(-v, kind="stable")
        hits = [int(y[top[:n]].sum()) for n in (100, 500, 1000)]
        print(f"{name:<34}{roc_auc_score(y, v):>7.3f}{hits[0]:>9}{hits[1]:>9}{hits[2]:>10}")
    print(f"Chance would find about {y.mean()*100:.2f} / {y.mean()*500:.2f} / {y.mean()*1000:.2f}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("features"), ap.add_argument("scores")
    ap.add_argument("--labels", help="data/labels.csv, only for the backtest printout")
    a = ap.parse_args()
    f = load_features(a.features)
    s, P = score(f)
    out = s[COLS].sort_values("combined_rank")      # explicit columns: a missing one fails loudly
    out.to_csv(a.scores, index=False)
    print(f"wrote {a.scores}: {len(out):,} scored providers of {len(f):,} "
          f"(eligible {int(f.eligible.sum()):,}, too_small peer group excluded)")
    print("rules_score counts:", s.rules_score.value_counts().sort_index().to_dict())
    if a.labels:
        compare(s, P, a.labels)


if __name__ == "__main__":
    main()
