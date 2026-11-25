"""
web_adapter.py: builds the paper list for pubfingerprint from data fetched by a web browser.

The web version (docs/index.html) runs pubfingerprint in the browser with Pyodide. Browsers
cannot use urllib, so the page fetches the public ORCID record and the matching OpenAlex works
with JavaScript and passes the JSON here. The rules are the same as in the command-line ORCID
mode: works with a DOI only, published versions preferred over preprints, preprints without a
published version and corrections/errata left out, group authors not counted as people.
Author lists come from OpenAlex (the command line uses Crossref), so values can differ slightly.
"""
import re
import publication_map as pm


def orcid_dois(works_json):
    """One entry per ORCID work group: (title, [DOIs, published ones first])."""
    out = []
    for g in (works_json or {}).get("group", []):
        dois, title = [], ""
        for ws in g.get("work-summary", []) or []:
            title = title or (((ws.get("title") or {}).get("title") or {}).get("value") or "")
            for eid in ((ws.get("external-ids") or {}).get("external-id") or []):
                if (eid.get("external-id-type") or "").lower() == "doi":
                    d = (eid.get("external-id-value") or "").strip().lower()
                    d = re.sub(r"^(https?://(dx\.)?doi\.org/|doi:)", "", d)
                    if d and d not in dois:
                        dois.append(d)
        dois.sort(key=lambda d: pm._is_preprint(d))
        out.append((title, dois))
    return out


def all_dois(works_json):
    """Every DOI to look up in OpenAlex (the page fetches them in batches of 50)."""
    return sorted({d for _, ds in orcid_dois(works_json) for d in ds})


def person_names(person_json):
    nm = (person_json or {}).get("name") or {}
    given = ((nm.get("given-names") or {}).get("value") or "").strip()
    family = ((nm.get("family-name") or {}).get("value") or "").strip()
    credit = ((nm.get("credit-name") or {}).get("value") or "").strip()
    variants = [x for x in [f"{given} {family}".strip(), credit] if x]
    for o in (((person_json or {}).get("other-names") or {}).get("other-name") or []):
        if (o.get("content") or "").strip():
            variants.append(o["content"].strip())
    return credit or f"{given} {family}".strip(), list(dict.fromkeys(variants)), family


def _doi(w):
    return re.sub(r"^https?://doi\.org/", "", (w.get("doi") or "")).lower()


def build_papers(orcid, person_json, works_json, openalex_works, include_preprints=False):
    """Return (papers, me, display_name, report) for pubfingerprint.run()."""
    display, variants, family = person_names(person_json)
    oa = {_doi(w): w for w in openalex_works or [] if w.get("doi")}
    oid = orcid.strip().replace("https://orcid.org/", "")
    papers, report = [], dict(groups=0, kept=0, no_doi=[], not_in_openalex=[], preprints=[], corrections=[])
    names = []
    for title, dois in orcid_dois(works_json):
        report["groups"] += 1
        if not dois:
            report["no_doi"].append(title); continue
        w = next((oa[d] for d in dois if d in oa and not _is_pre(oa[d], d)), None)
        if w is None:
            pre = next((oa[d] for d in dois if d in oa), None)
            if pre is None:
                report["not_in_openalex"].append(title or dois[0]); continue
            if not include_preprints:
                report["preprints"].append(title or dois[0]); continue
            w = pre
        ttl = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", w.get("title") or title or "")).strip()
        if pm.NOT_A_PAPER.match(ttl):
            report["corrections"].append(ttl); continue
        authors, corr, countries, own_inst = [], [], set(), ""
        for a in w.get("authorships") or []:
            nm = (a.get("raw_author_name") or (a.get("author") or {}).get("display_name") or "").strip()
            if not nm or pm.ORG_NAME.search(nm):
                continue
            authors.append(nm)
            if a.get("is_corresponding"):
                corr.append(nm)
            countries.update(a.get("countries") or [])
            countries.update(i.get("country_code") for i in (a.get("institutions") or []) if i.get("country_code"))
            if ((a.get("author") or {}).get("orcid") or "").endswith(oid):
                names.append(nm)
                inst = [i.get("display_name") for i in (a.get("institutions") or []) if i.get("display_name")]
                own_inst = own_inst or (inst[0] if inst else "")
        if not authors or not w.get("publication_year"):
            report["not_in_openalex"].append(ttl); continue
        pt = w.get("primary_topic") or {}
        extra = {}
        if pt:
            extra["line_openalex_topic"] = pt.get("display_name") or "Unclassified"
            for lv in ("subfield", "field", "domain"):
                extra[f"line_openalex_{lv}"] = (pt.get(lv) or {}).get("display_name") or "Unclassified"
        src = ((w.get("primary_location") or {}).get("source") or {})
        papers.append(dict(id=None, year=int(w["publication_year"]), title=ttl, journal=src.get("display_name") or "",
                           line=extra.get("line_openalex_subfield", "Unclassified"), authors=authors,
                           doi=_doi(w), type=w.get("type", ""), countries=sorted(countries), corresponding=corr,
                           equal_first=[], approaches=[], own_institution=own_inst, extra=extra))
    # the same work can appear in two ORCID groups
    seen, uniq = set(), []
    for p in papers:
        k = re.sub(r"[^a-z]", "", p["title"].lower())[:80]
        if p["doi"] not in seen and k not in seen:
            seen.update([p["doi"], k]); uniq.append(p)
    report["kept"] = len(uniq)
    me, found = pm.find_me(uniq, variants + list(dict.fromkeys(names)), family)
    report["recognised"] = found
    return uniq, me, display, report


def _is_pre(w, doi):
    return (w.get("type") or "") == "preprint" or pm._is_preprint(doi)
