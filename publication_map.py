#!/usr/bin/env python3
"""
publication_map.py: draw your own "publication connection map".

Each of your papers is a node on an outer ring, grouped by research line and
ordered by year. Two papers are linked when they share at least one co-author
other than you; links within a line are coloured arcs, links across lines are
grey chords, and line width grows with the number of shared co-authors.
The map is descriptive: it shows how your work is connected through people,
not how much you have published.

Two ways to provide your papers
-------------------------------
1) A CSV file (UTF-8) with one row per paper and these columns:
     year     publication year (required)
     authors  all authors in order, separated by ";"   (required)
     title    (optional, used in the table output)
     journal  (optional)
     line     your research line / theme for the paper (optional; if the
              column is missing or empty, groups are found automatically
              from the co-authorship network)
     id       (optional; papers are numbered by year otherwise)

   python publication_map.py --csv my_papers.csv --me "Jane A. Doe"

2) Your ORCID iD (needs internet access; authors are looked up via Crossref
   from the DOIs listed in your ORCID record):

   python publication_map.py --orcid 0000-0002-1825-0097 --me "Jane A. Doe"

   This also writes <out>_papers.csv. Check it, fill in the "line" column if
   you like, and rerun with --csv for the final figure.

Requirements: Python >= 3.8, matplotlib, networkx (pip install matplotlib networkx)

Output: <out>.png, <out>.pdf, <out>.svg and <out>_links.csv (default out = publication_map)

Licence: MIT. Originally written for Gossmann, "Forty-nine plus one" (2026).
"""
import argparse, csv, os, itertools, json, math, re, sys, time, unicodedata, urllib.request, urllib.error
from collections import Counter, defaultdict

PALETTE = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"]
OTHER = "#8a8985"
INK, INK2, MUTED = "#0b0b0b", "#52514e", "#9a9893"


# ---------------------------------------------------------------- names
def _ascii(s):
    s = s.replace("ß", "ss").replace("ø", "o").replace("Ø", "O").replace("æ", "ae").replace("ð", "d").replace("ł", "l")
    return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()

def name_key(name):
    """Robust key for matching the same person across papers: 'surname|first initial'.
    Handles 'Given Family', 'Family, Given', initials, hyphens and diacritics
    (e.g. 'T.I. Gossmann', 'Toni Ingolf Goßmann' and 'Gossmann, Toni' all match)."""
    name = _ascii(name).strip()
    if not name:
        return ""
    if "," in name:
        fam, given = [x.strip() for x in name.split(",", 1)]
    else:
        parts = re.split(r"\s+", name.replace(".", ". ").strip())
        parts = [p for p in parts if p]
        # keep particles such as van, de, von with the surname
        i = len(parts) - 1
        while i > 1 and parts[i - 1].lower().strip(".") in {"van", "von", "de", "der", "den", "da", "di", "del", "le", "la"}:
            i -= 1
        fam, given = " ".join(parts[i:]), " ".join(parts[:i])
    fam = re.sub(r"[^a-z]", "", fam.lower())
    g = re.sub(r"[^a-z]", "", given.lower())
    return f"{fam}|{g[:1]}"


# ---------------------------------------------------------------- input
def read_csv(path):
    papers = []
    with open(path, newline="", encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            r = {k.strip().lower(): (v or "").strip() for k, v in r.items() if k}
            if not r.get("authors") or not r.get("year"):
                continue
            papers.append(dict(
                id=r.get("id") or None,
                year=int(float(r["year"])),
                title=r.get("title", ""),
                journal=r.get("journal", ""),
                line=r.get("line", ""),
                authors=[a.strip() for a in r["authors"].split(";") if a.strip()],
            ))
    if not papers:
        sys.exit(f"No usable rows in {path}: the columns 'year' and 'authors' are required.")
    return papers


def _get_json(url, headers=None, tries=3):
    req = urllib.request.Request(url, headers=headers or {})
    for k in range(tries):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            time.sleep(1.5 * (k + 1))
        except Exception:
            time.sleep(1.5 * (k + 1))
    return None


# preprint servers; 10.1101 is shared by bioRxiv/medRxiv and Cold Spring Harbor journals
# (e.g. Genome Research, 10.1101/gr.*), so only numeric bioRxiv-style suffixes count
PREPRINT_PREFIXES = ("10.48550/", "10.21203/", "10.20944/", "10.31219/", "10.22541/", "10.2139/ssrn", "10.64898/")
BIORXIV = re.compile(r"^10\.1101/(\d{4}\.\d{2}\.\d{2}\.)?\d+(v\d+)?$", re.I)
ORG_NAME = re.compile(r"\b(consortium|collaboration|group|network|initiative|project|team)\b", re.I)
NOT_WORK_TYPES = {"component", "dataset", "peer-review", "grant", "database", "report-component"}
NOT_A_PAPER = re.compile(r"^\s*(author correction|publisher correction|correction|corrigendum|erratum|retraction|editorial expression)\b", re.I)


def _is_preprint(doi, cr_type=None):
    """Crossref's work type decides when known; the DOI pattern is only a fallback."""
    if cr_type:
        return cr_type == "posted-content"
    d = (doi or "").lower().strip()
    return d.startswith(PREPRINT_PREFIXES) or bool(BIORXIV.match(d))


def check_orcid(text):
    """Return the ORCID iD in canonical form (0000-0000-0000-000X), or raise ValueError
    with a readable message. Accepts the bare iD, an orcid.org URL, or 16 characters without dashes."""
    s = re.sub(r"^\s*(https?://)?(www\.)?orcid\.org/", "", str(text or "").strip(), flags=re.I)
    s = s.replace(" ", "").replace("-", "").upper()
    if not re.fullmatch(r"\d{15}[\dX]", s):
        raise ValueError(f"'{text}' is not an ORCID iD. An ORCID iD has 16 characters in four "
                         "blocks, e.g. 0000-0002-1825-0097 (the last one may be X).")
    total = 0
    for ch in s[:15]:
        total = (total + int(ch)) * 2
    r = (12 - total % 11) % 11
    if s[15] != ("X" if r == 10 else str(r)):
        raise ValueError(f"'{text}' is not a valid ORCID iD: the check digit does not match. "
                         "Please check for a typing error.")
    return "-".join(s[i:i + 4] for i in range(0, 16, 4))


def from_orcid(orcid, mailto="", include_preprints=False):
    """Read the works on a public ORCID record and fetch their author lists from Crossref.

    By default only peer-reviewed outputs are kept: preprints are replaced by their
    published version when Crossref links one ('is-preprint-of'), otherwise dropped;
    corrections and errata are dropped. Use include_preprints=True to keep preprints."""
    ua = {"User-Agent": f"publication_map/1.0 (mailto:{mailto})" if mailto else "publication_map/1.0"}
    data = _get_json(f"https://pub.orcid.org/v3.0/{orcid}/works", {"Accept": "application/json", **ua})
    if not data:
        sys.exit("Could not read the ORCID record (check the iD and your internet connection).")

    def crossref(doi):
        cr = _get_json("https://api.crossref.org/works/" + urllib.request.quote(doi), ua)
        time.sleep(0.2)
        return cr.get("message") if cr else None

    papers, skipped, dropped, replaced = [], [], [], []
    for g in data.get("group", []):
        # a group can hold several versions of one work: collect every DOI, published ones first
        dois, title = [], ""
        for ws in g.get("work-summary", []) or []:
            title = title or (((ws.get("title") or {}).get("title") or {}).get("value") or "")
            for eid in ((ws.get("external-ids") or {}).get("external-id") or []):
                if (eid.get("external-id-type") or "").lower() == "doi":
                    d = (eid.get("external-id-value") or "").strip()
                    if d and d.lower() not in [x.lower() for x in dois]:
                        dois.append(d)
        if not dois:
            skipped.append(title); continue
        dois.sort(key=lambda d: _is_preprint(d))
        # try the DOIs in turn: a group can also hold DOIs of data sets, supplements or reviews
        doi, m = None, None
        for d in dois:
            md = crossref(d)
            if md and md.get("author") and md.get("type", "") not in NOT_WORK_TYPES:
                doi, m = d, md; break
        if not m:
            skipped.append(title); continue
        if _is_preprint(doi, m.get("type", "")) and not include_preprints:
            pub = [r.get("id") for r in (m.get("relation") or {}).get("is-preprint-of", []) if r.get("id-type") == "doi"]
            m2 = crossref(pub[0]) if pub else None
            if m2:
                replaced.append(f"{doi} -> {pub[0]}"); doi, m = pub[0], m2
            else:
                dropped.append(f"preprint: {title[:70]}"); continue
        ttl = re.sub(r"<[^>]+>", "", (m.get("title") or [title])[0])
        ttl = re.sub(r"\s+", " ", ttl).strip()
        if NOT_A_PAPER.match(ttl):
            dropped.append(f"correction: {ttl[:70]}"); continue
        authors = []
        for a in m.get("author", []):
            # Crossref lists groups ("The X Consortium") as authors with 'name' only: not a person
            if not (a.get("given") or a.get("family")) or ORG_NAME.search(a.get("family", "")):
                continue
            nm = " ".join(x for x in [a.get("given", ""), a.get("family", "")] if x)
            if nm:
                authors.append(nm)
        year = None
        for k in ("published-print", "published-online", "issued", "created"):
            dp = (m.get(k) or {}).get("date-parts")
            if dp and dp[0] and dp[0][0]:
                year = dp[0][0]; break
        if not authors or not year:
            skipped.append(title); continue
        papers.append(dict(id=None, year=int(year), title=ttl,
                           journal=(m.get("container-title") or [""])[0], line="", authors=authors, doi=doi,
                           type=m.get("type", "")))
    # the same work can still appear in two groups: keep one per DOI and per title
    seen, uniq = set(), []
    for p in sorted(papers, key=lambda p: (_is_preprint(p["doi"], p["type"]), p["year"])):
        k1 = p["doi"].lower(); k2 = re.sub(r"[^a-z]", "", p["title"].lower())[:80]
        if k1 not in seen and k2 not in seen:
            seen.update([k1, k2]); uniq.append(p)
    print(f"ORCID: {len(uniq)} works kept.")
    if replaced:
        print(f"  {len(replaced)} preprints replaced by their published version: " + "; ".join(replaced))
    if dropped:
        print(f"  {len(dropped)} works left out (use --include-preprints to keep preprints):")
        for d in dropped: print("    - " + d)
    if skipped:
        print(f"  {len(skipped)} ORCID works had no DOI or no Crossref author list and were skipped:")
        for s in skipped: print("    - " + (s or "(untitled)")[:70])
    print("  Works missing from your ORCID record are missing here too: add them to the CSV.")
    return uniq



def orcid_names(orcid, mailto=""):
    """Name of the ORCID holder and the name variants listed on the record.
    Returns (display name, [variants], family name)."""
    ua = {"Accept": "application/json",
          "User-Agent": f"publication_map/1.0 (mailto:{mailto})" if mailto else "publication_map/1.0"}
    d = _get_json(f"https://pub.orcid.org/v3.0/{orcid}/person", ua) or {}
    nm = d.get("name") or {}
    given = ((nm.get("given-names") or {}).get("value") or "").strip()
    family = ((nm.get("family-name") or {}).get("value") or "").strip()
    credit = ((nm.get("credit-name") or {}).get("value") or "").strip()
    variants = [x for x in [f"{given} {family}".strip(), credit] if x]
    for o in ((d.get("other-names") or {}).get("other-name") or []):
        v = (o.get("content") or "").strip()
        if v:
            variants.append(v)
    display = credit or f"{given} {family}".strip()
    return display, list(dict.fromkeys(variants)), family


def find_me(papers, variants, family):
    """Make sure the ORCID holder is recognised on every paper: start from the ORCID name
    variants and add any author whose surname matches the ORCID family name on papers where
    none of the variants matched (e.g. 'Gossmann' vs 'Goßmann', or a different first initial)."""
    keys = {name_key(v) for v in variants}
    fam = re.sub(r"[^a-z]", "", _ascii(family).lower())
    me = list(variants)
    for p in papers:
        if any(name_key(a) in keys for a in p["authors"]):
            continue
        for a in p["authors"]:
            sur = re.sub(r"[^a-z]", "", name_key(a).split("|")[0])
            if fam and (sur == fam or sur.replace("ss", "s") == fam.replace("ss", "s")):
                me.append(a); keys.add(name_key(a)); break
    found = sum(any(name_key(a) in keys for a in p["authors"]) for p in papers)
    return list(dict.fromkeys(me)), found



def openalex_enrich(papers, orcid="", mailto="", lines="subfield"):
    """Add what ORCID/Crossref lack, from OpenAlex (free, no key): the countries of all
    authors' institutions, the corresponding author(s), the ORCID holder's own institution,
    and a named topic for every paper (OpenAlex primary topic; 'lines' chooses the level
    used as research line: domain, field, subfield or topic). Also returns the names under
    which OpenAlex links the ORCID holder to each paper, which helps recognise them."""
    q = ("?mailto=" + urllib.request.quote(mailto)) if mailto else ""
    ua = {"User-Agent": f"pubfingerprint/1.0 (mailto:{mailto})" if mailto else "pubfingerprint/1.0"}
    oid = (orcid or "").strip().replace("https://orcid.org/", "")
    names, hit = [], Counter()
    for p in papers:
        if not p.get("doi"):
            continue
        w = _get_json("https://api.openalex.org/works/doi:" + urllib.request.quote(p["doi"].lower(), safe="/") + q, ua)
        time.sleep(0.12)
        if not w:
            continue
        hit["found"] += 1
        auths = w.get("authorships") or []
        ckeys = {name_key(a) for a in p["authors"]}
        # countries of all author institutions
        cc = set()
        for a in auths:
            cc.update(a.get("countries") or [])
            cc.update(i.get("country_code") for i in (a.get("institutions") or []) if i.get("country_code"))
        if cc:
            p["countries"] = sorted(cc); hit["countries"] += 1
        # corresponding authors, mapped onto the Crossref byline
        corr = []
        for k, a in enumerate(auths):
            if not a.get("is_corresponding"):
                continue
            raw = a.get("raw_author_name") or (a.get("author") or {}).get("display_name") or ""
            nk = name_key(raw)
            if nk in ckeys:
                corr.append(next(x for x in p["authors"] if name_key(x) == nk))
            elif len(auths) == len(p["authors"]):
                corr.append(p["authors"][k])
        if corr:
            p["corresponding"] = corr; hit["corresponding"] += 1
        # the ORCID holder on this paper: own institution and name as printed
        for a in auths:
            ao = ((a.get("author") or {}).get("orcid") or "").replace("https://orcid.org/", "")
            if oid and ao == oid:
                inst = [i.get("display_name") for i in (a.get("institutions") or []) if i.get("display_name")]
                if inst:
                    p["own_institution"] = inst[0]; hit["institution"] += 1
                for nm in [a.get("raw_author_name"), (a.get("author") or {}).get("display_name")]:
                    if nm:
                        names.append(nm)
        # named topic
        pt = w.get("primary_topic") or {}
        if pt:
            lab = {"topic": pt.get("display_name")}
            for lv in ("subfield", "field", "domain"):
                lab[lv] = (pt.get(lv) or {}).get("display_name")
            p.setdefault("extra", {})
            for lv, v in lab.items():
                p["extra"][f"line_openalex_{lv}"] = v or "Unclassified"
            if lab.get(lines):
                p["line"] = lab[lines]; hit["topic"] += 1
    n = len(papers)
    print(f"OpenAlex: {hit['found']} of {n} works found; countries for {hit['countries']}, corresponding author for "
          f"{hit['corresponding']}, own institution for {hit['institution']}, named topic for {hit['topic']}.")
    return list(dict.fromkeys(names))


def write_csv(papers, path):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        extra = sorted({k for p in papers for k in (p.get("extra") or {})})
        w.writerow(["id", "year", "title", "journal", "line", "authors", "doi", "countries", "corresponding",
                    "equal_first", "approaches", "own_institution"] + extra)
        for p in papers:
            w.writerow([p["id"], p["year"], p["title"], p["journal"], p.get("line", ""), "; ".join(p["authors"]),
                        p.get("doi", ""), "; ".join(p.get("countries") or []), "; ".join(p.get("corresponding") or []),
                        "; ".join(p.get("equal_first") or []), "; ".join(p.get("approaches") or []),
                        p.get("own_institution", "")] + [(p.get("extra") or {}).get(k, "") for k in extra])


# ---------------------------------------------------------------- analysis
def build(papers, me):
    import networkx as nx
    mekeys = {name_key(m) for m in me}
    papers = sorted(papers, key=lambda p: (p["year"], p["title"]))
    for i, p in enumerate(papers, 1):
        p["id"] = str(p["id"] or i)
        p["keys"] = {name_key(a) for a in p["authors"]} - {""}
        p["is_mine"] = bool(p["keys"] & mekeys)
        p["co"] = p["keys"] - mekeys
    missing = [p["title"] or p["id"] for p in papers if not p["is_mine"]]
    if missing:
        print(f"Warning: your name (--me) was not found on {len(missing)} paper(s); check spelling or add variants with another --me.")
    links = []
    for p, q in itertools.combinations(papers, 2):
        sh = p["co"] & q["co"]
        if sh:
            links.append((p["id"], q["id"], len(sh)))
    # research lines: given, or detected from the co-authorship network
    if not any(p["line"] for p in papers):
        G = nx.Graph()
        G.add_nodes_from(p["id"] for p in papers)
        G.add_weighted_edges_from(links)
        comms = sorted(nx.algorithms.community.greedy_modularity_communities(G, weight="weight"), key=len, reverse=True)
        big = [c for c in comms if len(c) > 1]
        lab = {}
        for k, c in enumerate(big):
            for n in c:
                lab[n] = f"Group {k + 1}"
        for p in papers:
            p["line"] = lab.get(p["id"], "Unconnected papers")
        print(f"No research lines given: found {len(big)} groups from shared co-authors.")
    else:
        for p in papers:
            p["line"] = p["line"] or "Unassigned"
    return papers, links


# ---------------------------------------------------------------- drawing

def draw_lines(papers, links, out, centre=None):
    """Connection map for large records: one node per research line (size = number of papers),
    edges = pairs of papers in two lines that share a co-author other than you (width ~ log count).
    The ring of a node shows the share of links that stay within the line."""
    import matplotlib as mpl, matplotlib.pyplot as plt
    mpl.rcParams.update({"font.family": "DejaVu Sans", "savefig.dpi": 300})
    counts = Counter(p["line"] for p in papers)
    order = [l for l, _ in counts.most_common() if not l.startswith("Other")] + [l for l in counts if l.startswith("Other")]
    colour = {l: (OTHER if l.startswith("Other") or i >= len(PALETTE) else PALETTE[i]) for i, l in enumerate(order)}
    line_of = {p["id"]: p["line"] for p in papers}
    within, between = Counter(), Counter()
    for i, j, w in links:
        a, b = line_of[i], line_of[j]
        if a == b:
            within[a] += 1
        else:
            between[tuple(sorted((a, b)))] += 1
    n = len(order); R = 1.25
    pos = {l: (R * math.cos(math.pi / 2 - 2 * math.pi * k / n), R * math.sin(math.pi / 2 - 2 * math.pi * k / n))
           for k, l in enumerate(order)}
    fig, ax = plt.subplots(figsize=(7.4, 7.6)); ax.set_aspect("equal"); ax.axis("off")
    mx = max(between.values()) if between else 1
    for (a, b), c in sorted(between.items(), key=lambda x: x[1]):
        lw = 0.6 + 6 * math.log1p(c) / math.log1p(mx)
        ax.plot([pos[a][0], pos[b][0]], [pos[a][1], pos[b][1]], color="#b9b7b1", lw=lw, alpha=0.75, zorder=1,
                solid_capstyle="round")
    big = max(counts.values())
    for l in order:
        x, y = pos[l]; s = 300 + 2600 * math.sqrt(counts[l] / big)
        ax.scatter(x, y, s=s, color=colour[l], edgecolor="white", lw=2, zorder=3)
        tot = within[l] + sum(c for k, c in between.items() if l in k)
        share = f"{100 * within[l] / tot:.0f}% of links within" if tot else "no links"
        ang = math.atan2(y, x); lx, ly = 1.72 * math.cos(ang), 1.72 * math.sin(ang)
        ax.text(lx, ly, "\n".join(_wrap(l, 22)) + f"\n{counts[l]} papers \u00b7 {share}", ha="center", va="center",
                fontsize=6.6, color=INK, linespacing=1.1)
    ax.text(0, 0, centre or f"{len(papers)}\npapers", ha="center", va="center", fontsize=11, fontweight="bold", color=INK)
    ax.set_xlim(-2.25, 2.25); ax.set_ylim(-2.35, 2.2)
    cross = sum(between.values())
    ax.text(-2.25, -2.33, f"{len(papers)} papers in {len(order)} research lines (circle size \u221d papers). "
            f"{len(links)} pairs of papers share a co-author other than you;\n{cross} of them connect two lines "
            f"(grey bands, width \u221d log number of pairs). Large record: lines are shown instead of single papers.",
            fontsize=6.4, color=INK2, va="bottom")
    for ext in ("png", "pdf", "svg"):
        fig.savefig(f"{out}.{ext}", bbox_inches="tight")
    plt.close(fig)
    print(f"Wrote {out}.png/.pdf/.svg (line-level map: {len(papers)} papers, {len(order)} lines, {cross} links across lines).")


def draw(papers, links, out, title=None, centre=None, label_years=True):
    import matplotlib as mpl, matplotlib.pyplot as plt
    from matplotlib.patches import FancyArrowPatch
    mpl.rcParams.update({"font.family": "DejaVu Sans", "savefig.dpi": 300})
    counts = Counter(p["line"] for p in papers)
    order = [l for l, _ in counts.most_common() if l not in ("Unconnected papers", "Unassigned")]
    if len(order) > len(PALETTE):  # fold small lines into "Other"
        keep = order[:len(PALETTE) - 1]
        for p in papers:
            if p["line"] not in keep and p["line"] not in ("Unconnected papers", "Unassigned"):
                p["line"] = "Other"
        order = keep + ["Other"]
    order += [l for l in ("Unconnected papers", "Unassigned") if l in counts]
    colour = {l: (PALETTE[i] if l not in ("Other", "Unconnected papers", "Unassigned") and i < len(PALETTE) else OTHER) for i, l in enumerate(order)}
    byid = {p["id"]: p for p in papers}
    N = len(papers); gap = 0.9; tot = N + gap * len(order)
    pos, ang, hub, cur = {}, {}, {}, 0
    R = 1.55
    for l in order:
        mem = sorted([p for p in papers if p["line"] == l], key=lambda p: (p["year"], p["id"]))
        if not mem:
            continue
        a0 = math.pi / 2 - 2 * math.pi * cur / tot
        for t, p in enumerate(mem):
            a = a0 - 2 * math.pi * t / tot
            pos[p["id"]] = (R * math.cos(a), R * math.sin(a)); ang[p["id"]] = a
        mid = a0 - 2 * math.pi * (len(mem) - 1) / tot / 2
        hub[l] = (0.95 * math.cos(mid), 0.95 * math.sin(mid))
        cur += len(mem) + gap
    size = 0.65 if N > 120 else 1.0
    fig, ax = plt.subplots(figsize=(7.4, 7.6)); ax.set_aspect("equal"); ax.axis("off")
    for i, j, w in sorted(links, key=lambda e: byid[e[0]]["line"] == byid[e[1]]["line"]):
        li, lj = byid[i]["line"], byid[j]["line"]; same = li == lj
        ax.add_patch(FancyArrowPatch(pos[i], pos[j], connectionstyle="arc3,rad=%s" % (-0.35 if same else 0.18),
                     arrowstyle="-", color=colour[li] if same else "#c4c2bc", alpha=0.85 if same else 0.45,
                     lw=(0.6 + 0.7 * min(w, 4)) if same else 0.4 + 0.35 * min(w, 4), zorder=1))
    ax.scatter([0], [0], s=2300, color="#2b2b2a", zorder=4)
    ax.text(0, 0, centre or f"{N}\npapers", color="white", ha="center", va="center", fontsize=8.5, fontweight="bold", zorder=5)
    for l in order:
        if l not in hub:
            continue
        hx, hy = hub[l]; ax.plot([0, hx], [0, hy], color=colour[l], lw=2.2, zorder=2)
        wrapped = "\n".join(_wrap(l, 16))
        ax.text(hx, hy, f"{wrapped}\n({counts.get(l, sum(1 for p in papers if p['line'] == l))})", ha="center", va="center",
                fontsize=6.6, fontweight="bold", color=INK, linespacing=1.1,
                bbox=dict(boxstyle="round,pad=0.35", fc="white", ec=colour[l], lw=1.3), zorder=6)
    for p in papers:
        x, y = pos[p["id"]]
        s = (55 + 40 * math.sqrt(len(p["authors"]))) * size
        ax.scatter(x, y, s=s, color=colour[p["line"]], edgecolor="white", linewidth=1.2, zorder=3)
        ax.text(x, y, p["id"], ha="center", va="center", fontsize=6 * size + 0.5, color="white", fontweight="bold", zorder=4)
        if label_years:
            a = ang[p["id"]]; r = 1.79
            ax.text(r * math.cos(a), r * math.sin(a), str(p["year"]), ha="center", va="center", fontsize=5.4 * size + 0.4,
                    color=MUTED, rotation=math.degrees(a) + (180 if math.cos(a) < 0 else 0), rotation_mode="anchor")
    ax.set_xlim(-1.95, 1.95); ax.set_ylim(-2.1, 1.95)
    cross = sum(1 for i, j, _ in links if byid[i]["line"] != byid[j]["line"])
    ax.text(-1.95, -2.08, f"{N} papers (outer ring; size ∝ √authors; grey = year), grouped by research line and ordered by year. "
            f"{len(links)} pairs share\n≥1 co-author other than you: coloured arcs within a line, grey chords across lines "
            f"({cross} of {len(links)}); width ∝ number of shared co-authors.", fontsize=6.4, color=INK2, va="bottom")
    if title:
        ax.set_title(title, fontsize=11, fontweight="bold", loc="left")
    import os
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    for ext in ("png", "pdf", "svg"):
        fig.savefig(f"{out}.{ext}", bbox_inches="tight")
    plt.close(fig)
    with open(f"{out}_links.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f); w.writerow(["paper_a", "paper_b", "shared_coauthors", "same_line"])
        for i, j, n in links:
            w.writerow([i, j, n, byid[i]["line"] == byid[j]["line"]])
    with open(f"{out}_papers.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f); w.writerow(["id", "year", "title", "journal", "line", "n_authors", "authors"])
        for p in sorted(papers, key=lambda p: int(p["id"]) if p["id"].isdigit() else p["id"]):
            w.writerow([p["id"], p["year"], p["title"], p["journal"], p["line"], len(p["authors"]), "; ".join(p["authors"])])
    print(f"Wrote {out}.png/.pdf/.svg, {out}_links.csv and {out}_papers.csv "
          f"({N} papers, {len(links)} links, {cross} across lines).")


def _wrap(s, n):
    words, lines, cur = s.split(), [], ""
    for w in words:
        if len(cur) + len(w) + 1 > n and cur:
            lines.append(cur); cur = w
        else:
            cur = (cur + " " + w).strip()
    return lines + [cur] if cur else lines


# ---------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser(description="Draw a publication connection map from your papers.",
                                 formatter_class=argparse.RawDescriptionHelpFormatter, epilog=__doc__.split("Requirements")[0])
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--csv", help="CSV with columns year, authors (';'-separated), optional title, journal, line, id")
    src.add_argument("--orcid", help="ORCID iD, e.g. 0000-0002-1825-0097 (needs internet)")
    ap.add_argument("--me", action="append", required=True,
                    help='Your name as it appears on papers; repeat for variants, e.g. --me "Toni I. Gossmann" --me "T. Goßmann"')
    ap.add_argument("--out", default="publication_map", help="Output file prefix (default: publication_map)")
    ap.add_argument("--title", default=None, help="Optional figure title")
    ap.add_argument("--centre", default=None, help="Text in the central circle (default: '<N> papers')")
    ap.add_argument("--mailto", default="", help="Your e-mail for polite Crossref requests (ORCID mode)")
    ap.add_argument("--include-preprints", action="store_true", help="ORCID mode: keep preprints (default: peer-reviewed only)")
    ap.add_argument("--no-years", action="store_true", help="Do not print years around the ring")
    a = ap.parse_args()
    if a.csv:
        papers = read_csv(a.csv)
    else:
        papers = from_orcid(a.orcid, a.mailto, a.include_preprints)
        write_csv(papers, f"{a.out}_from_orcid.csv")
        print(f"Wrote {a.out}_from_orcid.csv: edit the 'line' column and rerun with --csv for your final map.")
    papers, links = build(papers, a.me)
    draw(papers, links, a.out, a.title, a.centre.replace("\\n", "\n") if a.centre else None, not a.no_years)


if __name__ == "__main__":
    main()
