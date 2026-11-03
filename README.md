# icd10-guard

Small Python library that checks a set of ICD-10-CM codes against the official CMS FY2026 release:

- **billable or not**: is each code a complete code for this year, a category header that still needs more characters (`E11`, `M54.5`, `S22.49` without its 7th character), or not a code at all?
- **Excludes1 conflicts**: does the set contain two codes that an Excludes1 note says can never be reported together (`E10.9` + `E11.9`, `R10.9` + `R52`)? Notes are inherited from the category, section and chapter, and 7th-character codes resolve to their parent entry.

It also has a small scorer (set F1, category-level F1, and an F1 that is penalized per invalid code or Excludes1 pair) so it can sit inside an eval or a reward function for a coding model. I wrote it after reading about reinforcement fine-tuning for ICD-10 coding: exact-match F1 alone will happily reward a prediction that can't be billed as written, and these two checks are cheap and deterministic.

No dependencies beyond the Python standard library.

## Result: auditing the CodiEsp gold labels

[CodiEsp](https://zenodo.org/records/3837305) (CLEF eHealth 2020, CC BY 4.0) is 1,000 Spanish clinical case reports hand-coded by experts with CIE-10-ES diagnosis codes, the Spanish adaptation of ICD-10-CM. I ran the FY2026 checks over every gold diagnosis label:

| split | cases | code labels | billable | header (needs more chars) | not in FY2026 | cases with an Excludes1 pair |
|---|---|---|---|---|---|---|
| train | 500 | 5639 | 5187 | 377 | 75 | 207 |
| dev | 250 | 2677 | 2456 | 178 | 43 | 97 |
| test | 250 | 2842 | 2580 | 218 | 44 | 103 |
| all | 1000 | 11158 | 10223 | 773 | 162 | 407 |

Most common Excludes1 pairs in the gold labels:

```
 23  R10.9 + R52    R52 excludes abdomen pain (R10.-)
 22  B19.20 + K75.9 K75.9 excludes viral hepatitis (B15-B19)
 19  B19.10 + K75.9 K75.9 excludes viral hepatitis (B15-B19)
 15  M54.5 + R52    R52 excludes lumbar region pain (M54.5-)
 14  N18.9 + N28.9  N28.9 excludes chronic renal insufficiency (N18.9)
```

What I take from it:

- **About 8% of the gold labels (935 of 11,158) are not billable FY2026 codes as written.** Many of the 773 "header" labels are codes that later releases split into children: `R51` (headache, split in FY2021), `M54.5` (low back pain, FY2022), `R05` (cough, FY2023), `T14.8`, `E87.2`. 146 of the 162 unknown ones are injury and external-cause codes written without their 7th character (`W19.XXX`, `T81.4XX`). A model trained on this data learns to emit codes that would be rejected today.
- **41% of cases (407 of 1000) contain at least one Excludes1 pair.** Most are the classic "unspecified symptom plus the specific one" pattern (`R52` pain unspecified next to `R10.9` abdominal pain). Excludes1 has a documented exception when the two conditions are truly unrelated, so not every flagged pair is a coding error, but each one is worth a second look and a good reward signal should know about them.

Caveats: CodiEsp was coded against the 2018 Spanish edition, so part of the gap is version drift, which is exactly the point for anyone training on older labels. 205 of the 5,433 Excludes1 notes use free-text forms ("see categories ...", "with 7th character B") that I skip rather than guess at.

## Usage

```sh
sh scripts/fetch_data.sh             # CMS FY2026 tables + CodiEsp into ./data
python3 -m unittest -v               # fixture tests
ICD10_DATA=data python3 -m unittest  # plus checks against the real CMS tables
python3 scripts/audit_codiesp.py data data/codiesp/final_dataset_v4_to_publish
```

```python
from icd10guard import CodeSet
from icd10guard.score import score

cs = CodeSet.load("data/icd10cm_tabular_2026.xml", "data/icd10cm_codes_2026.txt")
cs.status("M54.5")                    # 'not_billable'
cs.check(["E10.9", "E11.9", "M54.5"])  # Excludes1 pair + header code
score(["E10.9", "E11.9"], ["E11.9"], cs)
# {'f1': 0.667, 'category_f1': 0.667, 'issues': [...], 'penalized_f1': 0.417}
```

Loading the full FY2026 tabular takes about 0.1 s.
