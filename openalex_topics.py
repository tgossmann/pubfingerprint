#!/usr/bin/env python3
"""
openalex_topics.py: add an independent, external topic classification from OpenAlex
to a publication CSV, so that thematic analyses do not rest only on your own research lines.

For every row with a DOI, the script asks the free OpenAlex API for the work's
primary topic and writes four new columns:
  line_openalex_domain     e.g. Life Sciences
  line_openalex_field      e.g. Biochemistry, Genetics and Molecular Biology
  line_openalex_subfield   e.g. Genetics
  line_openalex_topic      e.g. Genetic diversity and population structure
Rows without a DOI, or that OpenAlex cannot classify, get "Unclassified".

usage:
  python openalex_topics.py my_papers.csv my_papers_openalex.csv --mailto you@uni.edu
then, for example:
  python robustness.py my_papers_openalex.csv "Your Name" results/you line line_openalex_subfield line_openalex_topic

Needs internet access; no account or key. --mailto puts you in OpenAlex's "polite pool"
(faster, more reliable). Licence: MIT.
"""
import argparse, csv, json, sys, time, urllib.parse, urllib.request, urllib.error

LEVELS = ["domain", "field", "subfield", "topic"]


def fetch(doi, mailto="", tries=3):
    doi = doi.strip().lower().replace("https://doi.org/", "").replace("doi:", "")
    url = "https://api.openalex.org/works/doi:" + urllib.parse.quote(doi, safe="/")
    if mailto:
        url += "?mailto=" + urllib.parse.quote(mailto)
    for k in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "pubfingerprint/1.0"}), timeout=30) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            time.sleep(2 * (k + 1))
        except Exception:
            time.sleep(2 * (k + 1))
    return None


def classify(work):
    """Return {level: display_name} from an OpenAlex work record (primary topic)."""
    out = {lv: "Unclassified" for lv in LEVELS}
    pt = (work or {}).get("primary_topic") or {}
    if pt:
        out["topic"] = pt.get("display_name") or "Unclassified"
        for lv in ("subfield", "field", "domain"):
            out[lv] = (pt.get(lv) or {}).get("display_name") or "Unclassified"
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("infile"); ap.add_argument("outfile")
    ap.add_argument("--mailto", default="", help="your e-mail (recommended by OpenAlex)")
    ap.add_argument("--doi-column", default="doi")
    a = ap.parse_args()
    with open(a.infile, newline="", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    if not rows or a.doi_column not in rows[0]:
        sys.exit(f"No '{a.doi_column}' column in {a.infile}. Add the DOIs of your papers first.")
    found = 0
    for i, r in enumerate(rows, 1):
        doi = (r.get(a.doi_column) or "").strip()
        cl = classify(fetch(doi, a.mailto)) if doi else classify(None)
        found += cl["topic"] != "Unclassified"
        for lv in LEVELS:
            r[f"line_openalex_{lv}"] = cl[lv]
        print(f"[{i}/{len(rows)}] {doi or '(no DOI)'} -> {cl['subfield']} | {cl['topic']}")
        time.sleep(0.15)
    fields = list(rows[0].keys())
    with open(a.outfile, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields); w.writeheader(); w.writerows(rows)
    print(f"\nClassified {found} of {len(rows)} papers. Wrote {a.outfile}.")
    for lv in LEVELS:
        print(f"  {lv}: {len(set(r[f'line_openalex_{lv}'] for r in rows))} categories")


if __name__ == "__main__":
    main()
