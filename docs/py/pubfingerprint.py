#!/usr/bin/env python3
"""
pubfingerprint.py: describe a publication record without ranking it.

Produces, from one CSV file (or an ORCID iD), four outputs:
  1. fingerprint      compositions that each sum to 100% (role, team size, credit,
                      collaborator recurrence, countries, approaches, research lines)
  2. diversity        Hill numbers (richness, Shannon and Simpson effective numbers)
                      for co-authors (whole and fractional counting), senior authors,
                      journals, countries, research lines and approaches
  3. rarefaction      expected diversity for 5..N papers (random subsamples) and
                      accumulation in chronological order, so that records of
                      different size can be compared
  4. map              the connection map of papers sharing co-authors
                      (via publication_map.py in the same folder)

CSV columns (UTF-8; one row per paper). Only 'year' and 'authors' are required:
  year         publication year
  authors      all authors in order, separated by ';'
  journal      journal or venue
  line         your research line/theme (otherwise detected from shared co-authors)
  countries    affiliation countries of all authors, separated by ';'
  corresponding  corresponding author(s), separated by ';'
  equal_first  authors marked as contributing equally as first authors, ';'
  approaches   approaches used, separated by ';' (e.g. theory; population genomics)
  own_institution  your own (first-listed) institution on the paper
  line_*       alternative classifications of research lines (e.g. line_coarse,
               line_fine) used by robustness.py for sensitivity analyses
  title, id    optional

Usage:
  python pubfingerprint.py --csv my_papers.csv --me "Jane A. Doe" --out results/jane
  python pubfingerprint.py --orcid 0000-0002-1825-0097          (name and papers are read from ORCID)

Nothing here is a score. Every number describes how a record is composed;
greater diversity is a mathematical property, not evidence of quality; never combine them into an index.

Requirements: Python >= 3.8, matplotlib, networkx, numpy. Licence: MIT.
"""
import argparse, csv, json, math, os, random, sys
from collections import Counter, defaultdict

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import publication_map as pm  # noqa: E402

C = pm.PALETTE
INK, INK2, MUTED = pm.INK, pm.INK2, pm.MUTED


# ------------------------------------------------------------------ input
def split(v):
    return [x.strip() for x in (v or "").split(";") if x.strip()]


def read(path):
    rows = []
    with open(path, newline="", encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            r = {k.strip().lower(): (v or "").strip() for k, v in r.items() if k}
            if not r.get("year") or not r.get("authors"):
                continue
            rows.append(dict(id=r.get("id") or None, year=int(float(r["year"])), title=r.get("title", ""),
                             journal=r.get("journal", ""), line=r.get("line", ""), authors=split(r["authors"]),
                             countries=split(r.get("countries")), corresponding=split(r.get("corresponding")),
                             equal_first=split(r.get("equal_first")), approaches=split(r.get("approaches")),
                             own_institution=r.get("own_institution", ""),
                             extra={k: v for k, v in r.items() if k.startswith("line_")}))
    if not rows:
        sys.exit("No usable rows: 'year' and 'authors' are required.")
    return rows


# ------------------------------------------------------------------ diversity

LARGE = 120     # above this many papers the connection map shows research lines, not single papers
MAX_SHOWN = 8   # research lines shown individually in figures; the rest are pooled for display only


def display_lines(papers, k=MAX_SHOWN):
    """Map each research line to the label shown in figures: the k-1 largest lines keep their name,
    the rest are pooled as 'Other (n lines)'. Diversity is always computed on all lines."""
    cnt = Counter(p["line"] for p in papers)
    if len(cnt) <= k:
        return {l: l for l in cnt}
    keep = [l for l, _ in cnt.most_common(k - 1)]
    other = f"Other ({len(cnt) - len(keep)} lines)"
    return {l: (l if l in keep else other) for l in cnt}


def year_ticks(years, max_ticks=10):
    """Indices of the first paper of a year, at least len/max_ticks papers apart so labels never collide."""
    gap = len(years) / max_ticks; out = []
    for i in range(len(years)):
        if (i == 0 or years[i] != years[i - 1]) and (not out or i - out[-1] >= gap):
            out.append(i)
    return out


ROLES = ["First author", "Last / corresponding", "Middle author"]
ROLE_NOTE = ("Byline position as a proxy for the archetypes of Robinson-Garcia et al. (2020): "
             "first author \u2248 specialized, last/corresponding \u2248 leader, middle \u2248 supporting.")


def role_of(p, me_keys):
    if p.get("pos") is None:
        return None
    if p["n"] == 1 or p["pos"] == 1 or pm.name_key(p["authors"][p["pos"] - 1]) in p["eq_keys"]:
        return ROLES[0]
    if p["pos"] == p["n"] or p["akeys"][p["pos"] - 1] in p["corr_keys"]:
        return ROLES[1]
    return ROLES[2]


def career_periods(years, max_periods=6):
    """Split the career into consecutive periods of equal length (at least 3 years each)."""
    y0, y1 = min(years), max(years); span = y1 - y0 + 1
    w = max(3, math.ceil(span / max_periods))
    out, s = [], y0
    while s <= y1:
        out.append((s, min(s + w - 1, y1))); s += w
    return out


def role_mix(rec):
    """Role composition per career period: a description of how the role changed, not a type."""
    rows = []
    for a, b in career_periods([p["year"] for p in rec.papers]):
        P = [p for p in rec.papers if a <= p["year"] <= b]
        c = Counter(role_of(p, rec.me) for p in P)
        n = sum(c[r] for r in ROLES)
        if not n:
            continue
        top, v = max(((r, c[r]) for r in ROLES), key=lambda x: x[1])
        label = f"mostly {top.lower()}" if v / n >= 0.5 else "mixed"
        rows.append(dict(period=f"{a}\u2013{b}" if a != b else str(a), counts={r: c[r] for r in ROLES}, n=n, label=label))
    return rows


def plot_roles(rec, out):
    import matplotlib.pyplot as plt
    _style(); rows = role_mix(rec)
    fig, a = plt.subplots(figsize=(7.4, 0.36 * len(rows) + 1.0))
    cols = [C[0], C[1], C[2]]
    for i, r in enumerate(rows):
        y = len(rows) - 1 - i; left = 0
        for k, role in enumerate(ROLES):
            w = r["counts"][role] / r["n"] * 100
            a.barh(y, w, left=left, color=cols[k], height=0.62, edgecolor="white", linewidth=1.5,
                   label=role if i == 0 else None)
            if w >= 9:
                a.text(left + w / 2, y, str(r["counts"][role]), ha="center", va="center", fontsize=6.3, color="white")
            left += w
        a.text(101, y, f"n={r['n']}  ({r['label']})", va="center", fontsize=6.3, color=INK2)
    a.set_yticks(range(len(rows))); a.set_yticklabels([r["period"] for r in rows][::-1])
    a.set_xlim(0, 130); a.set_xticks([0, 25, 50, 75, 100]); a.grid(axis="y", visible=False)
    a.set_xlabel("Share of papers in the period (%)")
    a.legend(fontsize=6.5, ncol=3, loc="lower center", bbox_to_anchor=(0.4, 1.0), frameon=False)
    fig.savefig(out + "_roles.png", bbox_inches="tight"); fig.savefig(out + "_roles.pdf", bbox_inches="tight"); plt.close(fig)
    return rows


def switches(seq):
    """Number of changes of category between consecutive papers."""
    return sum(a != b for a, b in zip(seq, seq[1:]))


def switch_null(seq, reps=1000, seed=1):
    """Expected switches if the papers were in random order, and a 95% permutation interval.
    For a random permutation of a fixed record of n papers with category shares p_i,
    E[S] = n (1 - sum p_i^2) exactly (the pair probability is sampled without replacement)."""
    n = len(seq)
    if n < 2:
        return 0.0, 0, 0
    p = np.array(list(Counter(seq).values()), float) / n
    exp = float(n * (1 - (p ** 2).sum()))
    rng = random.Random(seed); s = list(seq); vals = []
    for _ in range(reps):
        rng.shuffle(s); vals.append(switches(s))
    vals.sort()
    return exp, vals[int(0.025 * reps)], vals[int(0.975 * reps) - 1]

def hill(abund, q):
    v = np.array([x for x in abund if x > 0], float)
    if v.size == 0:
        return 0.0
    p = v / v.sum()
    if q == 0:
        return float(v.size)
    if q == 1:
        return float(np.exp(-(p * np.log(p)).sum()))
    return float((p ** q).sum() ** (1 / (1 - q)))


def profile(counter):
    a = list(counter.values())
    tot = sum(a)
    return dict(n=round(tot, 2), richness=hill(a, 0), q1=hill(a, 1), q2=hill(a, 2),
                top_share=(max(a) / tot) if tot else float("nan"))


# ------------------------------------------------------------------ core
class Record:
    def __init__(self, papers, me):
        self.me = {pm.name_key(m) for m in me}
        self.papers, self.links = pm.build(papers, me)   # sorts, numbers, assigns lines, finds links
        for p in self.papers:
            keys = [pm.name_key(a) for a in p["authors"]]
            p["akeys"] = keys
            p["pos"] = next((i + 1 for i, k in enumerate(keys) if k in self.me), None)
            p["n"] = len(keys)
            p["corr_keys"] = {pm.name_key(x) for x in p.get("corresponding", [])}
            p["eq_keys"] = {pm.name_key(x) for x in p.get("equal_first", [])}
            p["seniors"] = ({keys[-1]} | p["corr_keys"]) - self.me if p["n"] > 1 else set()
        self.name = {}
        for p in self.papers:
            for a, k in zip(p["authors"], p["akeys"]):
                self.name.setdefault(k, a)

    # observations per dimension: list (per paper) of (category, weight)
    def obs(self, dim):
        out = []
        for p in self.papers:
            co = [k for k in p["akeys"] if k not in self.me]
            if dim == "Co-authors":
                o = [(k, 1.0) for k in co]
            elif dim == "Co-authors (fractional)":
                o = [(k, 1.0 / len(co)) for k in co] if co else []
            elif dim == "Senior / corresponding authors":
                o = [(k, 1.0) for k in p["seniors"]]
            elif dim == "Venues":
                o = [(p["journal"], 1.0)] if p["journal"] else []
            elif dim == "Countries":
                o = [(c, 1.0) for c in set(p["countries"])]
            elif dim == "Research lines":
                o = [(p["line"], 1.0)] if p["line"] else []
            elif dim == "Approaches":
                o = [(a, 1.0) for a in set(p["approaches"])]
            elif dim == "Own institutions":
                o = [(p.get("own_institution"), 1.0)] if p.get("own_institution") else []
            elif dim.startswith("line_"):
                o = [(p["extra"][dim], 1.0)] if p.get("extra", {}).get(dim) else []
            else:
                raise KeyError(dim)
            out.append(o)
        return out

    def dims(self):
        d = ["Co-authors", "Co-authors (fractional)", "Senior / corresponding authors", "Venues"]
        if any(p["countries"] for p in self.papers):
            d.append("Countries")
        d.append("Research lines")
        if any(p["approaches"] for p in self.papers):
            d.append("Approaches")
        if any(p.get("own_institution") for p in self.papers):
            d.append("Own institutions")
        return d

    @staticmethod
    def pool(obs, idx):
        c = Counter()
        for i in idx:
            for k, w in obs[i]:
                c[k] += w
        return c

    def diversity(self):
        return {d: profile(self.pool(self.obs(d), range(len(self.papers)))) for d in self.dims()}

    @staticmethod
    def matrix(obs):
        """Papers x categories matrix of observation weights (for fast pooling)."""
        cats = {}
        for o in obs:
            for k, _ in o:
                cats.setdefault(k, len(cats))
        W = np.zeros((len(obs), max(1, len(cats))))
        for i, o in enumerate(obs):
            for k, w in o:
                W[i, cats[k]] += w
        return W

    @staticmethod
    def hill3(v):
        """Hill numbers q = 0, 1, 2 of one abundance vector."""
        v = v[v > 0]
        if v.size == 0:
            return (0.0, 0.0, 0.0)
        p = v / v.sum()
        return (float(v.size), float(np.exp(-(p * np.log(p)).sum())), float(1.0 / (p ** 2).sum()))

    def rarefy(self, dim, sizes, reps=200, seed=1):
        # same random subsets as a plain loop (random.sample with a fixed seed), pooled with numpy
        obs = self.obs(dim); N = len(obs); rng = random.Random(seed); res = []
        W = self.matrix(obs)
        for m in sizes:
            # one subset per order q (as in the original implementation, which keeps published values reproducible)
            vals = np.array([[self.hill3(W[rng.sample(range(N), m)].sum(0))[i] for i in range(3)]
                             for _ in range(reps if m < N else 1)])
            res.append(dict(papers=m, **{f"q{q}": float(vals[:, i].mean()) for i, q in enumerate((0, 1, 2))},
                            **{f"q{q}_lo": float(np.percentile(vals[:, i], 2.5)) for i, q in enumerate((0, 1, 2))},
                            **{f"q{q}_hi": float(np.percentile(vals[:, i], 97.5)) for i, q in enumerate((0, 1, 2))}))
        return res

    def accumulate(self, dim):
        obs = self.obs(dim); res = []
        C = np.cumsum(self.matrix(obs), axis=0)
        for m in range(1, len(obs) + 1):
            q0, q1, _ = self.hill3(C[m - 1])
            res.append(dict(papers=m, year=self.papers[m - 1]["year"], q0=q0, q1=q1))
        return res

    def rolling(self, dim, window=10):
        obs = self.obs(dim); res = []
        for s in range(0, len(obs) - window + 1):
            c = self.pool(obs, range(s, s + window))
            yrs = [self.papers[i]["year"] for i in range(s, s + window)]
            res.append(dict(start=s + 1, mid_year=float(np.mean(yrs)), q1=hill(list(c.values()), 1)))
        return res

    def temporal(self, key="line", reps=1000, seed=1):
        """Temporal organisation of a categorical attribute (default: research line):
        number of switches between consecutive papers, mean run length, and mean
        effective number in rolling windows of 10 papers."""
        seq = [p["line"] if key == "line" else p.get("extra", {}).get(key, "") for p in self.papers]
        years = [p["year"] for p in self.papers]
        sw = switches(seq)
        runs = sw + 1
        roll = [hill(list(Counter(seq[s:s + 10]).values()), 1) for s in range(0, max(1, len(seq) - 9))]
        exp, lo, hi = switch_null(seq)
        # papers from the same year have no defined order: how much does that matter?
        rng = random.Random(seed); vals = []
        for _ in range(reps):
            s = []
            for y in sorted(set(years)):
                g = [x for x, yy in zip(seq, years) if yy == y]; rng.shuffle(g); s += g
            vals.append(switches(s))
        vals.sort()
        return dict(switches=sw, expected_switches_random=exp, random_order_95=[lo, hi],
                    within_year_order_95=[vals[int(0.025 * reps)], vals[int(0.975 * reps) - 1]],
                    mean_run_length=len(seq) / runs, rolling10_q1_mean=float(np.mean(roll)),
                    rolling10_q1=roll, sequence=seq)

    def fingerprint(self):
        P = self.papers; rows = []
        def role(p):
            if p["pos"] is None: return "Not found"
            if p["n"] == 1 or p["pos"] == 1 or pm.name_key(p["authors"][p["pos"] - 1]) in p["eq_keys"]:
                return "First / co-first"
            if p["pos"] == p["n"] or (p["akeys"][p["pos"] - 1] in p["corr_keys"]):
                return "Senior / corresp."
            return "Middle"
        rc = Counter(role(p) for p in P)
        rows.append(("Own role", [(k, rc[k]) for k in ["First / co-first", "Senior / corresp.", "Middle", "Not found"] if rc[k]]))
        rows.append(("Team size", [("≤3 authors", sum(p["n"] <= 3 for p in P)), ("4–9", sum(3 < p["n"] < 10 for p in P)),
                                   ("≥10", sum(p["n"] >= 10 for p in P))]))
        if any(p["corr_keys"] or p["eq_keys"] for p in P):
            sh = sum(len(p["eq_keys"]) > 1 or len(p["corr_keys"]) > 1 for p in P)
            rows.append(("Credit", [("Single first & corresp.", len(P) - sh), ("Shared first and/or corresp.", sh)]))
        cnt = Counter(k for p in P for k in p["akeys"] if k not in self.me)
        slots = [k for p in P for k in p["akeys"] if k not in self.me]
        rows.append(("Co-author slots", [("One-off collaborators", sum(cnt[k] == 1 for k in slots)),
                                         ("Recurring collaborators", sum(cnt[k] > 1 for k in slots))]))
        if any(p["countries"] for p in P):
            nc = [len(set(p["countries"])) for p in P]
            rows.append(("Countries per paper", [("1", nc.count(1)), ("2–3", sum(1 < x < 4 for x in nc)), ("≥4", sum(x >= 4 for x in nc))]))
        if any(p["approaches"] for p in P):
            na = [len(set(p["approaches"])) for p in P]
            rows.append(("Approaches per paper", [(str(k), na.count(k)) for k in sorted(set(na))]))
        disp = display_lines(P)
        lc = Counter(disp[p["line"]] for p in P)
        rows.append(("Research line", sorted(lc.items(), key=lambda x: (x[0].startswith("Other ("), -x[1]))))
        return rows

    def summary(self):
        P = self.papers
        cnt = Counter(k for p in P for k in p["akeys"] if k not in self.me)
        yrs = defaultdict(list)
        for p in P:
            for k in p["akeys"]:
                if k not in self.me: yrs[k].append(p["year"])
        G = pm_graph(P, self.links)
        return dict(papers=len(P), years=[P[0]["year"], P[-1]["year"]], distinct_coauthors=len(cnt),
                    coauthors_once=sum(v == 1 for v in cnt.values()),
                    collaborators_spanning_5y=sum(max(v) - min(v) >= 5 for v in yrs.values()),
                    links=len(self.links), links_across_lines=sum(1 for i, j, _ in self.links
                        if self.byid(i)["line"] != self.byid(j)["line"]),
                    network_density=round(G["density"], 3), components=G["components"], largest_component=G["largest"])

    def byid(self, i):
        return next(p for p in self.papers if p["id"] == i)


def pm_graph(papers, links):
    import networkx as nx
    G = nx.Graph(); G.add_nodes_from(p["id"] for p in papers); G.add_weighted_edges_from(links)
    cc = list(nx.connected_components(G))
    return dict(density=nx.density(G), components=len(cc), largest=max(len(c) for c in cc))


# ------------------------------------------------------------------ plots
def _style():
    import matplotlib as mpl
    mpl.rcParams.update({"font.family": "DejaVu Sans", "font.size": 8.5, "axes.spines.top": False, "axes.spines.right": False,
                         "axes.edgecolor": "#8a8985", "xtick.color": INK2, "ytick.color": INK2, "axes.grid": True,
                         "grid.color": "#e6e5e1", "grid.linewidth": 0.6, "axes.axisbelow": True, "savefig.dpi": 300,
                         "legend.frameon": False})


def plot_fingerprint(rec, out):
    import matplotlib.pyplot as plt
    _style(); rows = rec.fingerprint()
    fig, a = plt.subplots(figsize=(7.4, 0.48 * len(rows) + 1.2))
    for r, (lab, parts) in enumerate(rows):
        tot = sum(v for _, v in parts) or 1; left = 0; y = len(rows) - 1 - r
        for k, (nm, v) in enumerate(parts):
            w = v / tot * 100; col = C[k % len(C)]
            a.barh(y, w, left=left, color=col, height=0.62, edgecolor="white", linewidth=1.5)
            if w >= 8:
                a.text(left + w / 2, y, f"{nm}\n{v}" if w >= 17 else f"{v}", ha="center", va="center",
                       fontsize=5.9, color="#0b0b0b" if col == "#eda100" else "white", linespacing=1.0)
            left += w
        a.text(101, y, f"n={tot}", va="center", fontsize=6.3, color=INK2)
    a.set_yticks(range(len(rows))); a.set_yticklabels([l for l, _ in rows][::-1])
    a.set_xlim(0, 108); a.set_xticks([0, 25, 50, 75, 100]); a.grid(axis="y", visible=False)
    a.set_xlabel("Share (%) — each row is a composition, not a score")
    fig.savefig(out + "_fingerprint.png", bbox_inches="tight"); fig.savefig(out + "_fingerprint.pdf", bbox_inches="tight"); plt.close(fig)


def plot_diversity(rec, out, rare=None):
    import matplotlib.pyplot as plt, matplotlib as mpl
    from matplotlib.lines import Line2D
    _style(); div = rec.diversity(); ks = list(div)[::-1]
    fig, ax = plt.subplots(figsize=(7.2, 0.42 * len(ks) + 1.2))
    for i, k in enumerate(ks):
        r = div[k]
        ax.plot([r["q2"], r["richness"]], [i, i], color="#dcdad5", lw=2, zorder=1)
        ax.scatter(r["richness"], i, s=44, facecolor="white", edgecolor=C[0], lw=1.6, zorder=3)
        ax.scatter(r["q1"], i, s=44, color=C[0], zorder=4)
        ax.scatter(r["q2"], i, s=38, color=C[1], marker="D", zorder=4)
        ax.text(r["richness"] * 1.12, i, f"{r['richness']:.0f}", va="center", fontsize=6.8, color=INK2)
    hi = max(r["richness"] for r in div.values())
    ticks = [t for t in [1, 2, 5, 10, 20, 50, 100, 250, 500, 1000, 2500, 5000, 10000] if t <= hi * 1.5]
    ax.set_xscale("log"); ax.set_xticks(ticks); ax.get_xaxis().set_major_formatter(mpl.ticker.ScalarFormatter())
    ax.set_xlim(0.9, max(450, hi * 2.6)); ax.set_yticks(range(len(ks))); ax.set_yticklabels(ks); ax.grid(axis="y", visible=False)
    ax.axvline(1, color=MUTED, lw=0.8, ls=":"); ax.set_xlabel("Number of categories (log scale)")
    ax.legend(handles=[Line2D([], [], marker="o", ls="", mfc="white", mec=C[0], label="Richness (q = 0)"),
                       Line2D([], [], marker="o", ls="", color=C[0], label="Effective number, Shannon (q = 1)"),
                       Line2D([], [], marker="D", ls="", color=C[1], label="Effective number, Simpson (q = 2)")],
              fontsize=6.8, loc="lower right")
    fig.savefig(out + "_diversity.png", bbox_inches="tight"); fig.savefig(out + "_diversity.pdf", bbox_inches="tight"); plt.close(fig)


def plot_rarefaction(rec, out, dims=None):
    import matplotlib.pyplot as plt
    _style(); dims = dims or [d for d in rec.dims() if d != "Co-authors (fractional)"]
    N = len(rec.papers)
    step = 5 if N <= 125 else 5 * math.ceil(N / 125)      # ~25 sizes for large records
    sizes = sorted(set([m for m in range(5, N + 1, step)] + [m for m in (25, 45) if m < N] + [N]))
    fig, axs = plt.subplots(1, 2, figsize=(7.4, 3.3), gridspec_kw=dict(wspace=0.28))
    res = {}
    for k, d in enumerate(dims):
        r = rec.rarefy(d, sizes); res[d] = r; col = C[k % len(C)]
        x = [e["papers"] for e in r]
        axs[0].fill_between(x, [e["q1_lo"] for e in r], [e["q1_hi"] for e in r], color=col, alpha=0.15, lw=0)
        axs[0].plot(x, [e["q1"] for e in r], color=col, lw=2, label=d)
        acc = rec.accumulate(d)
        axs[1].plot([e["papers"] for e in acc], [e["q1"] for e in acc], color=col, lw=2)
    for ax in axs:
        ax.set_yscale("log"); ax.set_xlabel("Number of papers")
    axs[0].set_ylabel("Effective number (q = 1, log scale)")
    axs[0].set_title("a  Rarefaction (random subsets)", loc="left", fontsize=9, fontweight="bold")
    axs[1].set_title("b  Accumulation (chronological)", loc="left", fontsize=9, fontweight="bold")
    yrs = [p["year"] for p in rec.papers]
    tick = [i + 1 for i in year_ticks(yrs, 8)]
    sec = axs[1].secondary_xaxis("top"); sec.set_xticks(tick); sec.set_xticklabels([yrs[t - 1] for t in tick], fontsize=6)
    axs[0].legend(fontsize=6.3, loc="upper left")
    fig.savefig(out + "_rarefaction.png", bbox_inches="tight"); fig.savefig(out + "_rarefaction.pdf", bbox_inches="tight"); plt.close(fig)
    return res


# ------------------------------------------------------------------ main
def _at(rare, dim, n):
    """Rarefied effective number (q=1) of a dimension at n papers, if available."""
    for r in rare.get(dim, []):
        if r["papers"] == n:
            return r["q1"]
    return None


def plot_sheet(rec, res, out, name="", source=""):
    """One PDF (two A4 pages) that brings the whole profile together. It contains no score."""
    import matplotlib.pyplot as plt
    from matplotlib.backends.backend_pdf import PdfPages
    import matplotlib.image as mpimg
    S, D, T = res["summary"], res["diversity"], res["temporal_lines"]
    n = S["papers"]; ref = 25 if n >= 25 else (n // 5) * 5
    W, H = 8.27, 11.69

    def header(fig, page):
        fig.text(0.06, 0.965, "Publication profile" + (f": {name}" if name else ""), fontsize=15, fontweight="bold", color=INK)
        fig.text(0.06, 0.945, f"{n} papers, {S['years'][0]}–{S['years'][1]}" + (f"  ·  source: {source}" if source else "")
                 + f"  ·  page {page} of 2", fontsize=8.5, color=INK2)
        fig.text(0.06, 0.012, "A description of how this record is composed, not a score. No dimension has a universally desirable "
                 "direction; do not rank people or combine dimensions into one number.\nMade with pubfingerprint "
                 "(Gossmann 2026). Values depend on the input file; check it before sharing.",
                 fontsize=6.5, color=INK2, va="bottom")

    def img(fig, path, box, title):
        if not os.path.exists(path):
            return
        ax = fig.add_axes(box); ax.imshow(mpimg.imread(path)); ax.axis("off")
        fig.text(box[0], box[1] + box[3] + 0.004, title, fontsize=9.5, fontweight="bold", color=INK)

    with PdfPages(out + "_profile.pdf") as pdf:
        # ---------------- page 1: key descriptors, fingerprint, diversity
        fig = plt.figure(figsize=(W, H)); header(fig, 1)
        rows = [("Distinct co-authors", f"{S['distinct_coauthors']}  ({S['coauthors_once']} on one paper only; "
                                       f"{S['collaborators_spanning_5y']} over ≥5 years)")]
        for dim in ["Senior / corresponding authors", "Venues", "Countries", "Research lines", "Approaches", "Own institutions"]:
            if dim in D:
                r = D[dim]; s = f"{r['richness']:.0f} different, effectively {r['q1']:.1f}"
                v = _at(res["rarefaction"], dim, ref)
                if v is not None and ref < n:
                    s += f"  (at {ref} papers: {v:.1f})"
                rows.append((dim, s))
        rm = res.get("roles", [])
        if rm:
            short = {"mostly first author": "first", "mostly last / corresponding": "last/corr.",
                     "mostly middle author": "middle", "mixed": "mixed"}
            spans = []   # merge consecutive periods with the same role
            for r in rm:
                a, b = r["period"].split("\u2013") if "\u2013" in r["period"] else (r["period"], r["period"])
                if spans and spans[-1][2] == r["label"]:
                    spans[-1][1] = b
                else:
                    spans.append([a, b, r["label"]])
            txt = "; ".join(f"{a}\u2013{b} {short[l]}" if a != b else f"{a} {short[l]}" for a, b, l in spans)
            rows.append(("Role over time (mostly)", txt))
        rows.append(("Paper connections", f"{S['links']} pairs of papers share a co-author; "
                                         f"{S['links_across_lines']} of them cross research lines"))
        lo, hi = T.get("random_order_95", [None, None])
        rows.append(("Order of research lines", f"{T['switches']} switches "
                     f"(random order: {T.get('expected_switches_random', float('nan')):.0f}, {lo}–{hi}); "
                     f"{T['rolling10_q1_mean']:.1f} lines per 10 papers"))
        fig.text(0.06, 0.915, "Key descriptors", fontsize=9.5, fontweight="bold", color=INK)
        y = 0.895
        for k, v in rows:
            fig.text(0.06, y, k, fontsize=8, color=INK2); fig.text(0.33, y, v, fontsize=8, color=INK); y -= 0.017
        fig.text(0.06, y - 0.004, "“effectively” = Shannon effective number (Hill number q = 1): how many equally common "
                 "categories would give the same diversity.", fontsize=6.5, color=INK2, style="italic")
        top = y - 0.03
        img(fig, out + "_fingerprint.png", [0.04, top - 0.25, 0.92, 0.23], "a  Composition (each bar adds up to 100%)")
        img(fig, out + "_roles.png", [0.04, top - 0.43, 0.92, 0.15], "b  Role in the author list, by career period")
        fig.text(0.06, top - 0.445, ROLE_NOTE, fontsize=6.3, color=INK2, style="italic")
        img(fig, out + "_diversity.png", [0.04, 0.05, 0.92, top - 0.51], "c  Diversity profile")
        pdf.savefig(fig); plt.close(fig)
        # ---------------- page 2: map, accumulation, temporal
        fig = plt.figure(figsize=(W, H)); header(fig, 2)
        img(fig, out + "_map.png", [0.17, 0.53, 0.66, 0.38], "d  Connections between papers (shared co-authors other than you)")
        img(fig, out + "_rarefaction.png", [0.04, 0.24, 0.92, 0.26], "e  Diversity as the record grows (compare records at equal size)")
        disp = display_lines(rec.papers)
        seq = [disp[p["line"]] for p in rec.papers]
        cats = sorted(set(seq), key=lambda c: (c.startswith("Other ("), seq.index(c)))
        col = {c: ("#b4b2ac" if c.startswith("Other (") else C[i % len(C)]) for i, c in enumerate(cats)}
        ax = fig.add_axes([0.06, 0.135, 0.88, 0.035])
        for i, s in enumerate(seq):
            ax.add_patch(plt.Rectangle((i, 0), 1, 1, color=col[s], lw=0))
        ax.set_xlim(0, len(seq)); ax.set_ylim(0, 1); ax.set_yticks([]); ax.grid(False)
        yrs = [p["year"] for p in rec.papers]; tick = year_ticks(yrs, 16)
        ax.set_xticks([i + 0.5 for i in tick]); ax.set_xticklabels([str(yrs[i]) for i in tick], fontsize=6, rotation=90)
        fig.text(0.06, 0.18, "f  Research line of each paper in chronological order", fontsize=9.5, fontweight="bold", color=INK)
        hs = [plt.Rectangle((0, 0), 1, 1, color=col[c]) for c in cats]
        fig.legend(hs, [c if len(c) <= 38 else c[:36] + "\u2026" for c in cats], loc="lower left",
                   bbox_to_anchor=(0.05, 0.045), ncol=3, fontsize=6.5, frameon=False)
        pdf.savefig(fig); plt.close(fig)
    return out + "_profile.pdf"


def run(papers, me, out, map_centre=None, make_map=True, name="", source=""):
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    rec = Record(papers, me)
    plot_fingerprint(rec, out); plot_diversity(rec, out); rare = plot_rarefaction(rec, out)
    if make_map:
        # for drawing only: at most MAX_SHOWN lines; large records get a map of lines instead of papers
        disp = display_lines(rec.papers)
        show = [dict(p, line=disp[p["line"]]) for p in rec.papers]
        if len(show) > LARGE:
            pm.draw_lines(show, rec.links, out + "_map", map_centre)
        else:
            pm.draw(show, rec.links, out + "_map", None, map_centre, True)
    res = dict(summary=rec.summary(), fingerprint=rec.fingerprint(), diversity=rec.diversity(), rarefaction=rare,
               rolling_q1={d: rec.rolling(d) for d in ["Co-authors", "Venues", "Research lines"]},
               temporal_lines={k: v for k, v in rec.temporal().items() if k != "sequence"},
               roles=plot_roles(rec, out))
    with open(out + "_results.json", "w", encoding="utf-8") as f:
        json.dump(res, f, indent=1, ensure_ascii=False)
    with open(out + "_diversity.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f); w.writerow(["dimension", "n", "richness", "effective_q1", "effective_q2", "top_share"])
        for d, r in res["diversity"].items():
            w.writerow([d, r["n"], round(r["richness"], 2), round(r["q1"], 2), round(r["q2"], 2), round(r["top_share"], 3)])
    sheet = plot_sheet(rec, res, out, name or me[0], source) if make_map else None
    print(f"Wrote {out}_fingerprint/_diversity/_rarefaction (.png/.pdf), {out}_map.*, {out}_results.json, {out}_diversity.csv")
    if sheet:
        print(f"One-file profile: {sheet}")
    return rec, res


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--csv"); src.add_argument("--orcid")
    ap.add_argument("--me", action="append", default=[], help="your name as on papers; repeat for variants "
                    "(required with --csv; with --orcid it is read from the ORCID record)")
    ap.add_argument("--out", default=None, help="output prefix (default: results/<ORCID iD> or results/fingerprint)")
    ap.add_argument("--centre", default=None, help="text in the centre of the map")
    ap.add_argument("--mailto", default="")
    ap.add_argument("--name", default="", help="name shown on the profile sheet (default: first --me)")
    ap.add_argument("--no-openalex", action="store_true", help="ORCID mode: do not add countries, corresponding "
                    "authors, institutions and topics from OpenAlex")
    ap.add_argument("--lines", default="subfield", choices=["domain", "field", "subfield", "topic", "network"],
                    help="ORCID mode: research lines from this OpenAlex level, or 'network' for groups of papers "
                         "sharing co-authors (default: subfield)")
    ap.add_argument("--include-preprints", action="store_true", help="ORCID mode: keep preprints (default: peer-reviewed only)")
    a = ap.parse_args()
    if a.orcid:
        try:
            a.orcid = pm.check_orcid(a.orcid)
        except ValueError as e:
            sys.exit(str(e))
    a.out = a.out or (f"results/{a.orcid}/{a.orcid}" if a.orcid else "results/fingerprint")
    name = a.name
    if a.csv:
        if not a.me:
            ap.error("--me is required with --csv")
        papers = read(a.csv)
    else:
        display, variants, family = pm.orcid_names(a.orcid, a.mailto)
        papers = pm.from_orcid(a.orcid, a.mailto, a.include_preprints)
        if not papers:
            sys.exit("No works with a DOI and an author list were found on this ORCID record.")
        for p in papers:
            p.setdefault("countries", []); p.setdefault("corresponding", []); p.setdefault("equal_first", [])
            p.setdefault("approaches", []); p.setdefault("extra", {})
        oa_names = [] if a.no_openalex else pm.openalex_enrich(papers, a.orcid, a.mailto, a.lines)
        a.me, found = pm.find_me(papers, a.me + variants + oa_names, family)
        if not a.me:
            sys.exit("Could not read a name from the ORCID record; give it with --me.")
        name = name or display
        print(f"Profile of {display or a.me[0]}: recognised on {found} of {len(papers)} works as "
              + "; ".join(a.me[:6]))
        if a.lines == "network":
            for p in papers:
                p["line"] = ""
        pm.write_csv(papers, a.out + "_from_orcid.csv")
        print("Not available automatically: shared first authorship and approaches (and anything OpenAlex lacks). "
              f"Add them to {a.out}_from_orcid.csv and rerun with --csv for the full fingerprint.")
    src = (f"ORCID {a.orcid} via Crossref" + ("" if a.no_openalex else f" + OpenAlex (lines: {a.lines})")) if a.orcid \
        else os.path.basename(a.csv)
    run(papers, a.me, a.out, a.centre.replace("\\n", "\n") if a.centre else None, name=name, source=src)


if __name__ == "__main__":
    main()
