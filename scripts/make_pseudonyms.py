"""Create private pseudonyms (STATE-SPECIALTY-SEQUENCE, e.g. TX-FP-0417) for scored providers.

Usage:
    python scripts/make_pseudonyms.py data/scores_TX_2022.csv data/pseudonyms.csv

The output contains NPIs, so it stays in data/ and is never committed.
The sequence is random within each state and specialty abbreviation (fixed seed),
so a pseudonym cannot be reversed to an NPI, rank, or claim count.
"""
import re
import sys
import numpy as np
import pandas as pd

SEED = 2026
SKIP_WORDS = {"and", "of", "the"}


def abbreviation(specialty):
    words = [w for w in re.split(r"[^A-Za-z]+", specialty) if w and w.lower() not in SKIP_WORDS]
    return "".join(w[0] for w in words).upper()


def main(scores_path, out_path):
    s = pd.read_csv(scores_path, dtype={"npi": str}, usecols=["npi", "specialty", "state"])
    s = s.sort_values("npi").reset_index(drop=True)
    s["abbr"] = s.specialty.map(abbreviation)
    rng = np.random.default_rng(SEED)
    s = s.iloc[rng.permutation(len(s))].reset_index(drop=True)
    s["seq"] = s.groupby(["state", "abbr"]).cumcount() + 1
    width = max(4, len(str(s.groupby(["state", "abbr"]).size().max())))
    s["pseudonym"] = s.state + "-" + s.abbr + "-" + s.seq.astype(str).str.zfill(width)
    assert s.pseudonym.is_unique, "pseudonym collision"
    s[["npi", "pseudonym"]].sort_values("npi").to_csv(out_path, index=False)
    print(f"wrote {out_path}: {len(s):,} pseudonyms, {s.abbr.nunique()} specialty abbreviations")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
