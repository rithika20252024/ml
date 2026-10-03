#!/usr/bin/env python3
"""
End-to-End Pipeline for Business Entity Resolution Challenge.
Generates output/matching_results.tsv and output/candidate_pairs.tsv.
"""

import os
import sys
import gc
import time
import argparse
import pandas as pd
from resolver import CountryResolver

def main():
    parser = argparse.ArgumentParser(description="Run Entity Resolution Pipeline")
    parser.add_argument("--test-dir", default="dataset/test", help="Path to test directory")
    parser.add_argument("--output-dir", default="output", help="Path to output directory")
    args = parser.parse_args()

    test_dir = args.test_dir
    output_dir = args.output_dir
    os.makedirs(output_dir, exist_ok=True)

    t_start = time.time()
    print(f"[{time.strftime('%X')}] Starting Entity Resolution Pipeline...")

    s1_path = os.path.join(test_dir, "test_source1.tsv")
    s2_path = os.path.join(test_dir, "test_source2.tsv")
    s3_path = os.path.join(test_dir, "test_source3.tsv")

    print(f"[{time.strftime('%X')}] Loading Source 1 test records...")
    s1_df = pd.read_csv(s1_path, sep="\t")
    print(f"Loaded {len(s1_df)} Source 1 records across countries:")
    print(s1_df['country'].value_counts())

    all_cands = {}
    all_matches = {}

    countries = ["France", "US", "India"]

    for country in countries:
        c_start = time.time()
        s1_c = s1_df[s1_df['country'] == country]
        if len(s1_c) == 0:
            continue
        print(f"\n[{time.strftime('%X')}] ========== Processing Country: {country} ({len(s1_c)} entities) ==========")

        print(f"[{time.strftime('%X')}] Reading Source 2 for {country}...")
        s2_chunks = []
        for chunk in pd.read_csv(s2_path, sep="\t", chunksize=500000):
            sub = chunk[chunk['country'] == country]
            if len(sub) > 0:
                s2_chunks.append(sub)
        s2_c = pd.concat(s2_chunks, ignore_index=True) if s2_chunks else pd.DataFrame(columns=['entity_id', 'business_name', 'business_address'])
        del s2_chunks; gc.collect()
        print(f"Loaded {len(s2_c)} Source 2 records for {country}.")

        print(f"[{time.strftime('%X')}] Reading Source 3 for {country}...")
        s3_chunks = []
        for chunk in pd.read_csv(s3_path, sep="\t", chunksize=500000):
            sub = chunk[chunk['country'] == country]
            if len(sub) > 0:
                s3_chunks.append(sub)
        s3_c = pd.concat(s3_chunks, ignore_index=True) if s3_chunks else pd.DataFrame(columns=['entity_id', 'business_name', 'business_address'])
        del s3_chunks; gc.collect()
        print(f"Loaded {len(s3_c)} Source 3 records for {country}.")

        print(f"[{time.strftime('%X')}] Indexing resolver for {country}...")
        t_idx = time.time()
        resolver = CountryResolver(s2_c, s3_c, country)
        del s2_c, s3_c; gc.collect()
        print(f"Indexed in {time.time() - t_idx:.2f}s.")

        print(f"[{time.strftime('%X')}] Resolving {len(s1_c)} entities for {country}...")
        t_res = time.time()
        count = 0
        names = s1_c['business_name'].fillna('').values
        addrs = s1_c['business_address'].fillna('').values
        eids = s1_c['entity_id'].values

        for i in range(len(eids)):
            eid = eids[i]
            nm = str(names[i])
            ad = str(addrs[i])
            cands, matches = resolver.resolve(nm, ad)
            all_cands[eid] = ",".join(cands)
            all_matches[eid] = ",".join(matches)
            count += 1
            if count % 100000 == 0:
                print(f"  Processed {count}/{len(eids)} ({count / (time.time() - t_res):.1f} qps)...")

        print(f"Completed {country} in {time.time() - c_start:.2f}s.")
        del resolver; gc.collect()

    print(f"\n[{time.strftime('%X')}] Writing final submission files...")
    matching_path = os.path.join(output_dir, "matching_results.tsv")
    candidate_path = os.path.join(output_dir, "candidate_pairs.tsv")

    with open(matching_path, "w", encoding="utf-8") as fm, open(candidate_path, "w", encoding="utf-8") as fc:
        fm.write("source1_entity_id\tmatched_entity_ids\n")
        fc.write("source1_entity_id\tcandidate_entity_ids\n")

        total_rows = 0
        non_empty_matches = 0
        total_cands = 0
        for s1_id in s1_df['entity_id']:
            m = all_matches.get(s1_id, "")
            c = all_cands.get(s1_id, "")
            fm.write(f"{s1_id}\t{m}\n")
            fc.write(f"{s1_id}\t{c}\n")
            total_rows += 1
            if m:
                non_empty_matches += 1
            if c:
                total_cands += len(c.split(","))

    print(f"Generated {total_rows} rows:")
    print(f"  Matching rows: {total_rows} ({non_empty_matches} non-empty, {total_rows - non_empty_matches} singletons)")
    print(f"  Total candidate pairs: {total_cands} (avg {total_cands / total_rows:.1f} cands/entity)")
    print(f"Files written to:\n  - {matching_path}\n  - {candidate_path}")
    print(f"Total time elapsed: {time.time() - t_start:.2f}s")

if __name__ == "__main__":
    main()
