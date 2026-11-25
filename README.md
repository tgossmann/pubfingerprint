# pubfingerprint: describe a publication record without ranking it

[![DOI](https://zenodo.org/badge/DOI/ZENODO_DOI.svg)](https://doi.org/ZENODO_DOI) *(replace ZENODO_DOI after the first Zenodo release)*

This software accompanies Gossmann, *Forty-nine plus one: reading a scientific career without ranking it* (2026). From one spreadsheet of your papers, or from your ORCID iD, it produces:

| Output | What it shows |
|---|---|
| `*_profile.pdf` | **The one-file profile sheet (two A4 pages):** key descriptors in words, composition, diversity profile, connection map, rarefaction/accumulation and the research line of each paper over time. It contains no score |
| `*_roles.png/.pdf` | Role in the author list per career period (first, last/corresponding, middle), a byline proxy for the leader / specialized / supporting archetypes of Robinson-Garcia et al. (2020, eLife 9:e60586). A description of how the role changed, not a type assigned to the person |
| `*_fingerprint.png/.pdf` | Compositions that each add up to 100%: own authorship role, team size, credit sharing, recurring vs one-off collaborators, countries per paper, approaches per paper, research lines |
| `*_diversity.png/.pdf/.csv` | Diversity profile: richness and effective numbers (Hill numbers, q = 0, 1, 2) for co-authors (whole and fractional counting), senior/corresponding authors, venues, countries, research lines and approaches |
| `*_rarefaction.png/.pdf` | Expected diversity for random subsets of 5…N papers, and accumulation in chronological order. Use these curves to compare records of different length |
| `*_map.png/.pdf/.svg` | Connection map: papers linked when they share a co-author other than you |
| `*_results.json` | All numbers, including rarefied values, rolling-window profiles and network statistics |

None of these numbers is a score. Higher diversity is a mathematical property of a record, not evidence of greater quality. The numbers describe how a record is composed, they have no universally desirable direction, and they should never be combined into one index. Rarefied values make diversity comparable with respect to the number of papers only, not with respect to career stage, field or opportunity.

**Web version:** enter an ORCID iD at https://tgossmann.github.io/pubfingerprint/ (runs in your browser; nothing is stored).

## Install

You need Python 3.8 or later and these packages:

```
python3 -m pip install matplotlib networkx numpy
```

## Run it

**From an ORCID iD only (one command, one PDF):**

```
python3 pubfingerprint.py --orcid 0000-0002-1825-0097
```

The script reads the name and all works with a DOI from the public ORCID record, fetches the author lists from Crossref, adds from OpenAlex the countries of all authors' institutions, the corresponding author(s), the person's own institution and a named topic for every paper, recognises the person on each paper (including spelling variants such as "Gossmann"/"Goßmann"), and writes everything to `results/<ORCID iD>/`. The page to look at is **`<ORCID iD>_profile.pdf`**. Adding `--mailto you@uni.edu` is polite to Crossref and makes requests more reliable. Research lines are OpenAlex subfields by default; `--lines topic` (finer), `--lines field` (coarser) or `--lines network` (groups of papers sharing co-authors) change this, and `--no-openalex` skips OpenAlex. Shared first authorship and approaches cannot be retrieved automatically.

**From your own spreadsheet (more dimensions: countries, corresponding authors, approaches, your own research lines):**

```
python3 pubfingerprint.py --csv my_papers.csv --me "Jane A. Doe" --out results/jane
```

If your name appears in different forms on your papers, repeat `--me` for each form. `--name "Jane Doe"` sets the name printed on the profile sheet. A good workflow is to start from ORCID, open the `*_from_orcid.csv` it writes, add the missing columns, and rerun with `--csv`.

## Input CSV

Make one row per paper. Only `year` and `authors` are required; every other column you fill in adds a dimension to the output.

| column | content |
|---|---|
| year | publication year |
| authors | all authors in order, separated by `;` |
| doi | DOI of the paper (needed for `openalex_topics.py`) |
| journal | journal or venue |
| line | your research line or theme. If you leave it empty, groups are detected from shared co-authors |
| countries | affiliation countries of all authors, separated by `;` |
| corresponding | corresponding author(s), separated by `;` |
| equal_first | authors marked as equal-contribution first authors, separated by `;` |
| approaches | approaches used, separated by `;` (e.g. `theory & modelling; population genomics`) |
| own_institution | your own (first-listed) institution on the paper |
| line_coarse, line_fine, … | optional alternative classifications of research lines, used by `robustness.py` |
| title, id | optional |

`examples/template_my_papers.csv` is a minimal example. `examples/example_Gossmann_49plus1.csv` is the full demonstration record from the article.

ORCID mode reads your works and their DOIs, looks up the author lists on Crossref, and writes `*_from_orcid.csv`. ORCID and Crossref do not record countries, corresponding authors, equal contributions or approaches. Add those columns to the CSV and rerun with `--csv` to get the full fingerprint.

## Reproduce the article figures

```
python3 pubfingerprint.py --csv examples/example_Gossmann_49plus1.csv --me "Toni I. Gossmann" --out example_output/Gossmann --centre "49 + 1\npapers"
python3 simulate_archetypes.py simulated
python3 compare_records.py example_output/comparison \
  "This record (real)=examples/example_Gossmann_49plus1.csv=Toni I. Gossmann" \
  "Focused theorist (sim.)=simulated/SIMULATED_Focused_theorist.csv=Focal Researcher" \
  "Specialised experimental PI (sim.)=simulated/SIMULATED_Specialised_experimental_PI.csv=Focal Researcher" \
  "Large-consortium member (sim.)=simulated/SIMULATED_Large_consortium_member.csv=Focal Researcher" \
  "Interdisciplinary collaborator (sim.)=simulated/SIMULATED_Interdisciplinary_collaborator.csv=Focal Researcher"
python3 robustness.py examples/example_Gossmann_49plus1.csv "Toni I. Gossmann" example_output/Gossmann line_coarse line line_fine
python3 simulate_temporal.py example_output/temporal examples/example_Gossmann_49plus1.csv "Toni I. Gossmann"

# independent classification (needs internet):
python3 openalex_topics.py examples/example_Gossmann_49plus1.csv examples/example_Gossmann_openalex.csv --mailto you@uni.edu
python3 robustness.py examples/example_Gossmann_openalex.csv "Toni I. Gossmann" example_output/Gossmann_openalex line line_openalex_subfield line_openalex_topic
```

`compare_records.py` also works for real records. Pass one `Label=file.csv=Name` argument per person, with their consent.

## How to read the output

1. Decide your research lines and approach categories before you look at the results.
2. Check whether your results depend on how you classified your research lines: run `robustness.py` with a coarser and a finer classification.
3. Read the compositions, not the totals. Ask what each one describes, not whether it is high.
4. Compare records at an equal number of papers, using the rarefaction curves or the rarefied values in `*_results.json`.
5. A large gap between richness and effective number means that a few categories dominate.
6. A large gap between whole and fractional co-author counts means that a few large-team papers drive your collaborator diversity.
7. Look at the order of your papers, not only the totals: `temporal_lines` in `*_results.json` gives the number of switches between research lines and rolling-window diversity.
8. Compare your own research lines with the groups detected from the network (`publication_map.py` without a `line` column). Where they disagree, look for the people who connect your topics.
9. Never combine the dimensions into one number. Pair the profile with a narrative that explains it.

## Files

- `pubfingerprint.py`: produces the fingerprint, diversity profile, rarefaction and accumulation curves, and connection map
- `publication_map.py`: draws the connection map on its own, and also contains the ORCID/Crossref import
- `simulate_archetypes.py`: simulates the four illustrative 50-paper records. These are simulated data, not real people
- `compare_records.py`: draws diversity profiles and role mixes side by side
- `robustness.py`: tests sensitivity to the resolution of your research-line classification, and runs a permutation null model (1000 shuffles of line labels, group sizes preserved) for how well your lines align with the co-authorship network
- `openalex_topics.py`: adds an independent topic classification from OpenAlex (domain, field, subfield, topic) to your CSV, based on the DOIs. Needs internet access. Then run `robustness.py` with `line_openalex_subfield` and `line_openalex_topic`
- `simulate_temporal.py`: simulates two careers with identical topic diversity, one sequential and one parallel, and shows how the temporal profile tells them apart

Licence: MIT.


## Large records

Records of any length are analysed in full; nothing is truncated. For readability only, figures show the 7 largest research lines by name and pool the rest as "Other (n lines)"; diversity is always computed on all lines. Above 120 papers the connection map shows research lines as nodes (size = papers, bands = shared co-authors between lines) instead of single papers.

## Known limitations of automatically retrieved metadata

- **Completeness:** ORCID mode finds only works on your ORCID record that have a DOI. In the demonstration record, ORCID first returned 42 of 49 journal articles; the rest were missing from the record or listed only as preprints. Check `*_from_orcid.csv` against your own list.
- **Author lists:** Crossref sometimes lists consortium members as authors, which inflates co-author counts for consortium papers. Group names ("… Consortium") are removed automatically; individual consortium members are not.
- **Byline roles:** first, last and corresponding position are proxies for contribution; conventions differ between fields (alphabetical order, consortium papers) and corresponding authors are missing for some papers in OpenAlex, which shifts papers into the 'middle author' category.
- **Roles and places:** ORCID and Crossref do not record corresponding authors, countries or institutions; these come from OpenAlex, whose affiliation and corresponding-author data are incomplete for some papers (the script reports for how many it found them). Shared first authorship and approaches are never retrieved automatically.
- **Topics:** OpenAlex assigns one primary topic per paper from its own classification. It describes journals and texts, not the researcher's intentions, and can differ from how researchers would group their own work.
- **Names:** authors are matched on surname plus first initial, so two different people with the same surname and initial are merged, and inconsistent spellings of one person can be split.
- **Ordering:** papers from the same year have no defined order; temporal statistics report how much this matters (`within_year_order_95` in `*_results.json`).

## Repository layout

| Path | Content |
|---|---|
| `*.py` | the tool (`pubfingerprint.py` is the entry point) |
| `examples/` | the demonstration record (50 papers, with DOIs and three classifications), its OpenAlex-classified version, and an empty template |
| `simulated/` | the four simulated records used in the article (invented names) |
| `example_output/` | every output produced by the commands above |
| `six_records/` | Figure 7 of the article: aggregated, anonymised values of six automatically generated profiles and the script that draws them. Per-researcher inputs are not distributed |
| `data/DataS1_publication_dataset.csv` | per-paper dataset of the demonstration record (Data S1). It contains no inferred gender of individual people |

## Citation

If you use this software, please cite the article and the archived release (see `CITATION.cff`).

Author: Toni I. Gossmann, TU Dortmund University, ORCID [0000-0001-6609-4116](https://orcid.org/0000-0001-6609-4116).

## Licence

MIT, see `LICENSE`.
