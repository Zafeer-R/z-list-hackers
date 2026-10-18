"""Sanity-check data loading and functions."""

import time
import sys
sys.path.insert(0, '.')

from app import data


def main():
    # Time the data loading
    print("Loading data...", flush=True)
    start = time.time()
    data.load_data()
    elapsed = time.time() - start
    print(f"Loaded in {elapsed:.2f} seconds\n")

    # Check NPI format
    print("Checking NPI format...")
    features = data._features
    scores = data._scores
    merged = data._merged

    # Every NPI should be 10 characters
    bad_npis_feat = features[features["npi"].str.len() != 10]
    bad_npis_score = scores[scores["npi"].str.len() != 10]
    if len(bad_npis_feat) == 0 and len(bad_npis_score) == 0:
        print("✓ All NPIs are 10-character strings")
    else:
        print(f"✗ Found {len(bad_npis_feat)} bad NPIs in features, {len(bad_npis_score)} in scores")

    # Every scored NPI should join to features
    print("\nChecking joins...")
    unmatched = scores[~scores["npi"].isin(features["npi"])]
    if len(unmatched) == 0:
        print(f"✓ All {len(scores):,} scored NPIs join to features")
    else:
        print(f"✗ {len(unmatched)} scored NPIs don't join to features")

    # Check pseudonyms: one per scored provider, unique, and in the TX-SPEC-NNNNN format
    print("\nChecking pseudonyms...")
    pseudo = merged["pseudonym"]
    well_formed = pseudo.str.match(r"^[A-Z]{2}-[A-Z]+-\d{4,}$").all()
    if pseudo.is_unique and well_formed and pseudo.notna().all():
        print(f"✓ {len(pseudo):,} unique pseudonyms, all well formed")
    else:
        print(f"✗ pseudonym problem: unique={pseudo.is_unique}, well formed={well_formed}")
    pseudo_set = set(pseudo)
    leaked = int(merged["npi"].isin(pseudo_set).sum())
    print("✓ no NPI appears as a pseudonym" if leaked == 0 else f"✗ {leaked} NPIs used as pseudonyms")

    # Test ranked_list() and provider_detail() for top 3
    print("\nTesting ranked_list() and provider_detail()...")
    top3 = data.ranked_list().head(3)
    print(f"✓ ranked_list() returned {len(top3)} rows")
    print("\nTop 3 providers:")
    for idx, row in top3.iterrows():
        print(f"  {idx+1}. {row['pseudonym']} - {row['Prscrbr_Type']}, {row['Prscrbr_State_Abrvtn']}, score={row['combined_score']}")

    print("\nProvider details for top 3:")
    # Get original NPIs from merged data for provider_detail
    top3_npis = merged.nlargest(3, "combined_score")["npi"].values
    for npi in top3_npis:
        detail = data.provider_detail(npi)
        if detail:
            print(f"\n  {detail['pseudonym']} - {detail['specialty']}, {detail['state']}")
            print(f"    Combined score: {detail['combined_score']}")
            print(f"    Rules score: {detail['rules_score']}")
            print(f"    Peer group: {detail['peer_group']['specialty']} in {detail['peer_group']['state']} (n={detail['peer_group']['peer_used_n']})")
            for reason in detail['reasons']:
                print(f"      Reason: {reason['text']}")
            print(f"    Features with top percentiles:")
            for feat in detail['features']:
                if feat['percentile'] and feat['percentile'] >= 0.8:
                    print(f"      {feat['label']}: {feat['raw_value']} (median: {feat['peer_median']}, {feat['percentile']:.1%})")
        else:
            print(f"  ✗ provider_detail() failed for {npi}")

    # Summary
    print("\n" + "="*60)
    print("Summary:")
    stats = data.get_stats()
    print(f"Total providers: {stats['total_providers']:,}")
    print(f"States: {len(stats['states'])}")
    print(f"Specialties: {len(stats['specialties'])}")
    print("="*60)


if __name__ == "__main__":
    main()
