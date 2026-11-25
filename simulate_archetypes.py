#!/usr/bin/env python3
"""Simulate contrasting 50-paper publication records ("archetypes") to show that
the fingerprint and diversity profile separate different ways of doing research
even when paper counts are identical. All records are SIMULATED; no real person."""
import csv, os, random, sys
import numpy as np

ME = "Focal Researcher"
APPR = ["theory & modelling", "comparative / molecular evolution", "population genomics",
        "experimental & omics data", "methods & resources", "synthesis & opinion"]

ARCH = {
 "Focused theorist": dict(nauth=lambda r: r.choice([1, 2, 2, 2, 3, 3]), p_new=0.25, core=["Long-term Partner"], p_core=0.7,
     journals=6, zipf_j=1.5, lines=[0.7, 0.3], countries=["Home", "Partner country", "Third"], k_c=(1, 2),
     role=dict(first=0.5, last=0.4, middle=0.1), appr=lambda r: ["theory & modelling"] + (["comparative / molecular evolution"] if r.random() < 0.2 else [])),
 "Large-consortium member": dict(nauth=lambda r: int(min(80, max(12, r.lognormvariate(3.2, 0.4)))), p_new=0.3, core=[f"Consortium {i}" for i in range(40)], p_core=0.55,
     journals=15, zipf_j=1.0, lines=[0.5, 0.3, 0.2], countries=[f"C{i}" for i in range(20)], k_c=(4, 10),
     role=dict(first=0.1, last=0.1, middle=0.8), appr=lambda r: ["experimental & omics data", "population genomics"]),
 "Interdisciplinary collaborator": dict(nauth=lambda r: r.randint(4, 12), p_new=0.8, core=["Partner A", "Partner B"], p_core=0.15,
     journals=40, zipf_j=0.6, lines=[1 / 7] * 7, countries=[f"C{i}" for i in range(15)], k_c=(2, 4),
     role=dict(first=0.3, last=0.3, middle=0.4), appr=lambda r: r.sample(APPR[:5], 2)),
 "Specialised experimental PI": dict(nauth=lambda r: r.randint(4, 9), p_new=None, core=["Technician", "Local collaborator"], p_core=0.8,
     journals=8, zipf_j=1.2, lines=[0.75, 0.25], countries=["Home", "Neighbour"], k_c=(1, 2),
     role=dict(first=0.1, last=0.8, middle=0.1), appr=lambda r: ["experimental & omics data"] + (["comparative / molecular evolution"] if r.random() < 0.4 else [])),
}


_used = set()
def pseudo(r):
    """Unique invented name made of letters only (names are matched on surname + initial)."""
    V, K = "aeiou", "bcdfghklmnprstvz"
    while True:
        g = "".join(r.choice(K) + r.choice(V) for _ in range(2)).capitalize()
        f = "".join(r.choice(K) + r.choice(V) for _ in range(3)).capitalize()
        if (f, g[0]) not in _used:
            _used.add((f, g[0])); return f"{g} {f}"


def zipf_pick(r, n, s):
    w = np.array([1 / (i + 1) ** s for i in range(n)]); w /= w.sum()
    return int(r.choices(range(n), weights=w)[0])


def simulate(name, spec, n=50, seed=7, years=(2010, 2026)):
    r = random.Random(seed + sum(map(ord, name)))
    rows, pool, cnt, newid = [], [], {}, [0]
    yrs = sorted(r.randint(*years) for _ in range(n))
    def new_person():
        return pseudo(r)
    names = {}
    def fixed(label):  # stable invented name for core collaborators / trainees
        if label not in names: names[label] = pseudo(r)
        return names[label]
    for i in range(n):
        k = spec["nauth"](r); co = []
        if spec["p_new"] is None:  # rotating trainees: cohorts of ~6 papers
            cohort = [fixed(f"Trainee {i // 6}-{j}") for j in range(3)] + [fixed(f"Trainee {i // 6 - 1}-{j}") for j in range(2) if i >= 6]
            co = r.sample(cohort, min(len(cohort), max(1, k - 2)))
        for c in map(fixed, spec["core"]):
            if len(co) < k - 1 and r.random() < spec["p_core"] and c not in co:
                co.append(c)
        while len(co) < k - 1:
            if pool and r.random() > spec["p_new"] if spec["p_new"] is not None else False:
                c = r.choices(pool, weights=[cnt.get(p, 1) for p in pool])[0]
            else:
                c = new_person(); pool.append(c)
            if c not in co:
                co.append(c)
        for c in co:
            cnt[c] = cnt.get(c, 0) + 1
            if c not in pool: pool.append(c)
        rl = r.random(); role = "first" if rl < spec["role"]["first"] else "last" if rl < spec["role"]["first"] + spec["role"]["last"] else "middle"
        r.shuffle(co)
        if k == 1: authors = [ME]
        elif role == "first": authors = [ME] + co
        elif role == "last": authors = co + [ME]
        else:
            pos = r.randint(1, max(1, k - 2)); authors = co[:pos] + [ME] + co[pos:]
        corr = [authors[-1]] if role != "first" or r.random() < 0.5 else [ME]
        line = f"Line {zipf_pick(r, len(spec['lines']), 0) + 1}" if len(set(spec["lines"])) == 1 else \
               f"Line {r.choices(range(len(spec['lines'])), weights=spec['lines'])[0] + 1}"
        kc = r.randint(*spec["k_c"]); cs = list({spec["countries"][0]} | {spec["countries"][zipf_pick(r, len(spec["countries"]), 0.8)] for _ in range(kc - 1)})
        rows.append(dict(id=i + 1, year=yrs[i], title=f"Simulated paper {i + 1}", journal=f"Journal {zipf_pick(r, spec['journals'], spec['zipf_j']) + 1}",
                         line=line, authors="; ".join(authors), countries="; ".join(cs), corresponding="; ".join(corr),
                         equal_first="", approaches="; ".join(spec["appr"](r))))
    return rows


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else "simulated"
    os.makedirs(out, exist_ok=True)
    for name, spec in ARCH.items():
        rows = simulate(name, spec)
        fn = os.path.join(out, "SIMULATED_" + name.replace(" ", "_").replace("-", "_") + ".csv")
        with open(fn, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
        print("wrote", fn)
