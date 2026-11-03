#!/bin/sh
# Downloads the CMS FY2026 ICD-10-CM tables and the CodiEsp corpus into ./data
set -e
mkdir -p data/tmp data/codiesp
cd data/tmp
curl -sSL -o tabular.zip "https://www.cms.gov/files/zip/2026-code-tables-tabular-and-index.zip"
curl -sSL -o order.zip "https://www.cms.gov/files/zip/2026-code-descriptions-tabular-order.zip"
curl -sSL -o codiesp.zip "https://zenodo.org/api/records/3837305/files/codiesp.zip/content"
unzip -o -q tabular.zip
unzip -o -q order.zip
cp "Table and Index/icd10cm_tabular_2026.xml" icd10cm_codes_2026.txt ..
unzip -o -q codiesp.zip -d ../codiesp
cd .. && rm -rf tmp
echo "done: data/icd10cm_tabular_2026.xml data/icd10cm_codes_2026.txt data/codiesp/"
