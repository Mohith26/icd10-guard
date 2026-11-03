"""Run the FY2026 ICD-10-CM checks over the CodiEsp gold diagnosis labels.

CodiEsp (CLEF eHealth 2020, CC BY 4.0) is 1,000 Spanish clinical case reports
hand-coded by experts with CIE-10-ES diagnosis codes, the Spanish adaptation
of ICD-10-CM. Usage:

    python scripts/audit_codiesp.py data/ data/codiesp/final_dataset_v4_to_publish
"""

import collections
import csv
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from icd10guard import CodeSet, normalize  # noqa: E402


def load_cases(path):
    cases = collections.defaultdict(list)
    with open(path, encoding="utf-8") as f:
        for row in csv.reader(f, delimiter="\t"):
            if len(row) >= 2:
                cases[row[0]].append(normalize(row[1]))
    return cases


def main(cms_dir, codiesp_dir):
    cs = CodeSet.load(os.path.join(cms_dir, "icd10cm_tabular_2026.xml"),
                      os.path.join(cms_dir, "icd10cm_codes_2026.txt"))
    print(f"ICD-10-CM {cs.version}: {len(cs.billable)} billable codes, "
          f"{sum(1 for _ in cs.parent)} tabular entries, "
          f"{len(cs.unparsed_notes)} Excludes1 notes skipped as unparseable\n")

    all_pairs = collections.Counter()
    print("| split | cases | code labels | billable | header (needs more chars) | not in FY2026 | cases with an Excludes1 pair |")
    print("|---|---|---|---|---|---|---|")
    totals = collections.Counter()
    for split in ("train", "dev", "test"):
        cases = load_cases(os.path.join(codiesp_dir, split, f"{split}D.tsv"))
        st = collections.Counter()
        conflict_cases = 0
        for case_id, codes in cases.items():
            for c in codes:
                st[cs.status(c)] += 1
            pairs = [i for i in cs.check(codes) if i.kind == "excludes1"]
            if pairs:
                conflict_cases += 1
                for p in pairs:
                    all_pairs[(p.codes, p.detail)] += 1
        n = sum(st.values())
        row = (split, len(cases), n, st["billable"], st["not_billable"], st["unknown"], conflict_cases)
        for k, v in zip(("cases", "labels", "billable", "header", "unknown", "conflict"), row[1:]):
            totals[k] += v
        print("| " + " | ".join(str(x) for x in row) + " |")
    print(f"| all | {totals['cases']} | {totals['labels']} | {totals['billable']} | {totals['header']} | "
          f"{totals['unknown']} | {totals['conflict']} |")

    print("\nMost common Excludes1 pairs in the gold labels:")
    for (codes, detail), k in all_pairs.most_common(10):
        print(f"  {k:3d}  {codes[0]} + {codes[1]}   [{detail}]")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
