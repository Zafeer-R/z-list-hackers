# Medicare Part D Fraud Risk: Lane C (Features + App)

24-hour hackathon project. We rank Medicare Part D prescribers by how unusual their prescribing looks against specialty peers, and show three plain-language reasons for every flag. I own Lane C: the `features` file and the dashboard. Four other lanes feed into or depend on my work, so the file layouts below are contracts. Don't change them without telling the team first.

## Team lanes

- **A, Data + Infra:** builds `panel` from CMS data, owns the LinuxONE server and deploys the app.
- **B, Labels + Story:** OIG exclusion labels (LEIE), slides, demo script.
- **C, Features + App (me):** `features` file and the dashboard.
- **D, Scoring:** reads `features`, writes `scores` (risk score, ranks, reasons).

## Deadlines

- `features` handed to D by H8
- App wired to real `scores` by H10
- Full app by H14, live on LinuxONE by H16 (A deploys)
- Code freeze at H21; after that, crash fixes only

## Hard constraints

- Production runs on **IBM LinuxONE (s390x, big-endian)**. Use pandas and numpy only. No DuckDB (it doesn't support big-endian), no Polars, no pyarrow or Parquet. All shared files are CSV.
- Dashboard library is **not decided yet**: A is confirming what installs on LinuxONE. Streamlit needs pyarrow, which may not build on s390x; Dash or Flask are the fallbacks. So keep all data logic in `app/data.py`, which must not import any UI library. Then only `app/main.py` changes if we switch.
- NPI is always a string, 10 characters. Read CSVs with `dtype={"npi": str}` or `dtype={"Prscrbr_NPI": str}`.
- Keep the original CMS column names in `panel` (A's decision). Don't rename them.
- Never use label columns (`future_exclusion_match`, `EXCLDATE`, `EXCLTYPE`, etc.) when building features. That's leakage.

## Wording and ethics rules for the app

- A high score means "unusual, needs review", never "fraud". Don't put the words fraud, fraudster or kickback in the UI.
- Show only the last 4 digits of an NPI (for example `******4821`). Never show provider names.
- Exclusion status (whether a provider was later excluded) is hidden by default behind a toggle, until B decides.
- Footer on every page: "Scores flag statistically unusual prescribing for review. They are not findings of wrongdoing."

## Files

### `panel_TX_2022.csv` (from A, input)
One row per prescriber, Texas only, 2022, 88,848 rows. Key columns: `Prscrbr_NPI`, `Prscrbr_Ent_Cd` (all `I` in TX), `Prscrbr_Type`, `Prscrbr_State_Abrvtn`, `Prscrbr_RUCA`, `Tot_Clms`, `Tot_30day_Fills`, `Tot_Drug_Cst`, `Tot_Day_Suply`, `Tot_Benes`, `Brnd_Tot_Clms`, `Brnd_Sprsn_Flag`, `Opioid_Tot_Clms`, `Opioid_LA_Tot_Clms`, `Antpsyct_GE65_Tot_Clms`, `Antpsyct_GE65_Sprsn_Flag`, `GE65_Tot_Clms`, `GE65_Sprsn_Flag`, `Bene_Avg_Age`, `Bene_Avg_Risk_Scre`, plus `_suppressed` and `_missing` indicator columns.

Suppression: blank counts mean 1 to 10 (CMS privacy rule). Flag `*` = the value itself was 1 to 10. Flag `#` = hidden to protect another cell. A kept blanks as NaN; `build_features.py` handles them.

### `features_TX_2022.csv` (mine, output, built by `build_features.py`)
Columns:
- `npi`, `Prscrbr_Type`, `Prscrbr_State_Abrvtn`, `Prscrbr_RUCA`, `Tot_Clms`, `Tot_Drug_Cst`, `Tot_Benes`
- `eligible`: True if `Tot_Clms >= 30` (cutoff is `--min-claims`, default 30, agreed with the team). Ineligible rows have raw ratios but blank percentiles.
- Eight raw ratios, all pointing the same way (higher = more unusual): `cost_per_claim`, `cost_per_bene`, `claims_per_bene`, `days_supply_per_bene`, `brand_share`, `opioid_rate`, `opioid_la_rate`, `antipsych_share_65`
- `<feature>_pct` for each: 0 to 1 rank percentile within specialty x state
- `peer_n` (eligible providers in the specialty x state group), `peer_fallback` (True if `peer_n < 20`), `peer_level` (`specialty_state`, `specialty_national` or `too_small`), `peer_used_n`
- `n_imputed`, `is_suppressed`, `n_features_missing`

Feature definitions and suppression handling:
- `cost_per_claim` = Tot_Drug_Cst / Tot_Clms
- `cost_per_bene` = Tot_Drug_Cst / Tot_Benes (blank if Tot_Benes is blank)
- `claims_per_bene` = Tot_Clms / Tot_Benes
- `days_supply_per_bene` = Tot_Day_Suply / Tot_Benes
- `brand_share` = Brnd_Tot_Clms / Tot_Clms. Flag `*` uses 5; flag `#` stays blank (~21% of eligible).
- `opioid_rate` = Opioid_Tot_Clms / Tot_Clms. Blank opioid count uses 5.
- `opioid_la_rate` = Opioid_LA_Tot_Clms / Opioid_Tot_Clms, only when opioid claims are reported and 11+ (CMS definition). Blank for ~63%, which is expected.
- `antipsych_share_65` = Antpsyct_GE65_Tot_Clms / GE65_Tot_Clms, only when the 65+ count is 11+. GE65 flag `#` means 65+ is about Tot_Clms minus 5.
- Percentiles need at least 20 non-blank values in the peer group; otherwise blank. Groups under 20 fall back to specialty nationwide. In the TX sample, nationwide equals Texas, so 188 providers in 34 tiny specialties stay `too_small`.

Expected run output on the TX sample (`--min-claims` 30, the default):
```
wrote features_TX_2022.csv: 88,848 rows, 75,477 eligible (Tot_Clms >= 30)
peer levels among eligible: {'specialty_state': 75284, 'too_small': 193}
```

Plain labels for the app (also in `FEATURES` in `build_features.py`; import from there, don't duplicate):
cost_per_claim = "Drug cost per prescription", cost_per_bene = "Drug cost per patient", claims_per_bene = "Prescriptions per patient", days_supply_per_bene = "Days of medication per patient", brand_share = "Brand-name share of prescriptions", opioid_rate = "Opioid share of prescriptions", opioid_la_rate = "Long-acting share of opioid prescriptions", antipsych_share_65 = "Antipsychotic share of prescriptions for patients 65+".

### `scores_TX_2022.csv` (from D, input, arrives ~H10)
Columns: `npi` (string), `specialty`, `state`, `tot_clms`, `tot_drug_cst`, `rules_score` (0 to 8, number of measures in the specialty's top 10%), `anomaly_score`, `combined_score` (0 to 100), `combined_rank`, `rules_rank`, `anomaly_rank`, `baseline_rank` (rank by total drug cost), `reason_1`, `reason_2`, `reason_3` (finished English sentences), `reason_1_feature`, `reason_2_feature`, `reason_3_feature` (feature names; look up `<feature>_pct` in `features` for the exact percentile), `low_peer_flag`, `is_suppressed`.

Until D delivers, use `data/scores_fake.csv` generated by `scripts/make_fake_scores.py` with exactly these columns, built from the real features file so the numbers look plausible. The app must switch to the real file by changing one path.

## The app

Two views, plus one optional:

1. **Ranked list:** sorted by `combined_rank`. Columns: masked NPI, specialty, state, combined score, rules score ("5 of 8 measures"), top reason. Filters: state, specialty, minimum score. Search by NPI. Clicking a row opens the provider view.
2. **Provider view:** combined score, rules score, the three reasons with their percentiles, peer group used (specialty, state, `peer_used_n`, with a note if `peer_fallback`), and a chart of all eight percentiles as horizontal bars with a line at 0.9. Show raw value next to the peer median for each feature.
3. **Optional results view:** D's backtest numbers (later-excluded providers found in our top 100 and top 500 vs `baseline_rank`). Static is fine.

Performance: load both CSVs once at startup and cache. Every click in the demo must be instant. B will name three demo providers; make sure they render well.

## Layout

```
build_features.py        # panel -> features
app/data.py              # load, join on npi, mask NPIs, lookups; no UI imports
app/main.py              # UI only
scripts/make_fake_scores.py
data/                    # CSVs, not committed (shared folder instead)
```

## Commands

```
python build_features.py data/panel_TX_2022.csv data/features_TX_2022.csv
python scripts/make_fake_scores.py data/features_TX_2022.csv data/scores_fake.csv
```
App run command depends on the library A confirms.

## Open questions (update this list as answers come in)

- A (answered): dashboard is Flask (Streamlit avoided because of pyarrow on s390x). Server is Ubuntu 24.04, system Python 3.12 (to verify), app dir `/home/linux1/z-list-hackers/`. Proposed port 8501 is pending network confirmation. Flask install via `sudo apt install python3-flask` not yet confirmed. Pandas and numpy reported installed; versions unknown.
- RESOLVED (2026-10-18): `panel` will not add `Gnrc_Tot_Clms` or `Othr_Tot_Clms` for the demo. A confirmed. Brand claims flagged `#` stay blank (~21% of eligible). Revisit after the demo if time allows.
- A and D: the claim cutoff is 30 (team decision). Confirm the 2023 to 2026 LEIE window.
- B: NPI masking rule, the three demo providers, whether to show exclusion status.

## Working style

- Small, checkable steps. After any change to `build_features.py`, rerun it and compare against the expected output above.
- Libraries allowed: pandas, numpy, scikit-learn (team approved), and Flask for the UI. Anything else needs a check that it installs on s390x.
- Anything outside this file's scope waits until after the demo.
