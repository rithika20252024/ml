# Business Entity Resolution Pipeline

This repository contains the end-to-end reproducible pipeline for the ML Challenge 2026 Business Entity Resolution Hackathon.

## Pipeline Architecture

1. **Country Partitioning**:
   - Matches strictly obey geographical domains (US, India, France).
   - Each country is indexed and processed independently to conserve memory and optimize speed.

2. **Multilingual Normalization & Preprocessing**:
   - Devanagari script transliteration (Hindi / Marathi) to ASCII.
   - Comprehensive legal suffix stripping for all jurisdictions (US, India, France): `Private Limited`, `Pvt Ltd`, `LLC`, `Inc`, `Corp`, `SARL`, `SASU`, `SAS`, `EURL`, `SA`, `SCI`, `SNC`, `et fils`, etc.
   - Address normalization: abbreviation standardisation (`st` -> `street`, `av` / `bd` / `che` / `r` -> `avenue`, `boulevard`, `chemin`, `rue`), ordinal number mapping, and leading zero elimination.
   - Removal of noisy phone numbers and entity identifiers appended to business names.

3. **High-Recall, Low-Cardinality Blocking**:
   - Inverted indexing on exact compact names, distinctive lexical tokens (frequency pruned <= 250), and spatial address keys `(house_number, address_token)`.
   - Generates an average candidate set <= 35 candidates per entity, optimizing blocking reduction ratio.

4. **High-Precision Matching Filter (Optimized for $F_{0.5}$)**:
   - Hard address conflict detection (incompatible house numbers and non-overlapping tokens) to eliminate false merges.
   - Exact compact name matching.
   - Bounded typo edit similarity using Levenshtein / SequenceMatcher ($\ge 0.80$).
   - High token overlap ($\ge 0.70$).
   - Verified same-address DBA/rebrand detection with name correlation constraints.

## Requirements

Python 3.8+ with:
```bash
pip install -r requirements.txt
```

## Running the Pipeline

From the root project directory:
```bash
python3 code/business_entity_resolution/src/run_pipeline.py --test-dir dataset/test --output-dir output
```

This generates:
- `output/matching_results.tsv` (Leaderboard submission)
- `output/candidate_pairs.tsv` (Blocking candidate pairs)

## Validation

Verify formatting and constraints using the official validator:
```bash
python3 utils/validate_submission.py \
    --matching output/matching_results.tsv \
    --candidate output/candidate_pairs.tsv \
    --test-dir dataset/test
```
