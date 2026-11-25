#!/usr/bin/env python3
"""Sensitivity of thematic results to the classification, and a permutation null
model for the agreement between thematic research lines and the co-authorship network.

usage: python robustness.py my_papers.csv "Your Name" OUTPREFIX line_coarse line line_fine
Each named column holds one classification of research lines ("line" is the default one)."""
import io, contextlib, json, random, sys
import numpy as np, networkx as nx
from collections import Counter
import pubfingerprint as pf


def ari(a, b):
    from math import comb
    n = len(a); ct = Counter(zip(a, b)); ra = Counter(a); rb = Counter(b)
    s = sum(comb(v, 2) for v in ct.values()); sa = sum(comb(v, 2) for v in ra.values()); sb = sum(comb(v, 2) for v in rb.values())
    e = sa * sb / comb(n, 2); m = (sa + sb) / 2
    return (s - e) / (m - e) if m != e else 0.0


def main(csvf, me, out, cols, perms=1000, seed=1):
    with contextlib.redirect_stdout(io.StringIO()):
        papers = pf.read(csvf)
        for p in papers:
            p["line"] = ""  # let publication_map detect network groups for the reference partition
        rec_net = pf.Record([dict(p) for p in papers], [me])
        rec = pf.Record(pf.read(csvf), [me])
    G = nx.Graph(); G.add_nodes_from(p["id"] for p in rec.papers); G.add_weighted_edges_from(rec.links)
    netlab = {p["id"]: p["line"] for p in rec_net.papers}
    nodes = [p["id"] for p in rec.papers]
    def stats(lab):
        groups = {}
        for n in nodes: groups.setdefault(lab[n], set()).add(n)
        cross = sum(1 for i, j, _ in rec.links if lab[i] != lab[j]) / max(1, len(rec.links))
        return dict(modularity=nx.algorithms.community.modularity(G, groups.values(), weight="weight"),
                    cross_share=cross, ari_vs_network=ari([lab[n] for n in nodes], [netlab[n] for n in nodes]))
    rng = random.Random(seed); res = {}
    sizes = sorted(set([m for m in range(5, len(nodes) + 1, 5)] + [len(nodes)]))
    for c in cols:
        lab = {p["id"]: (p["line"] if c == "line" else p["extra"].get(c, "")) for p in rec.papers}
        obs = stats(lab); vals = list(lab[n] for n in nodes); null = []
        for _ in range(perms):
            rng.shuffle(vals); null.append(stats(dict(zip(nodes, vals))))
        dim = "Research lines" if c == "line" else c
        rare = rec.rarefy(dim, sizes, reps=200)
        full = rare[-1]["q1"]; sat = next(e["papers"] for e in rare if e["q1"] >= 0.9 * full)
        co = rec.rarefy("Co-authors", sizes, reps=200); cfull = co[-1]["q1"]
        csat = next(e["papers"] for e in co if e["q1"] >= 0.9 * cfull)
        tmp = rec.temporal("line" if c == "line" else c)
        res[c] = dict(n_lines=len(set(lab.values())), q1=pf.profile(Counter(lab.values()))["q1"],
                      papers_to_90pct_q1=sat, coauthors_papers_to_90pct_q1=csat,
                      switches=tmp["switches"], mean_run_length=tmp["mean_run_length"],
                      observed=obs, **{f"null_{k}": dict(mean=float(np.mean([x[k] for x in null])),
                                                         lo=float(np.percentile([x[k] for x in null], 2.5)),
                                                         hi=float(np.percentile([x[k] for x in null], 97.5)),
                                                         p_extreme=float(np.mean([x[k] >= obs[k] for x in null]) if k != "cross_share"
                                                                         else np.mean([x[k] <= obs[k] for x in null])))
                                         for k in obs})
    res["network_partition"] = dict(groups=len(set(netlab.values())), **stats(netlab))
    json.dump(res, open(out + "_robustness.json", "w"), indent=1)
    for c, r in res.items():
        if c == "network_partition":
            print(c, {k: round(v, 3) if isinstance(v, float) else v for k, v in r.items()}); continue
        o = r["observed"]
        print(f"{c}: {r['n_lines']} lines, q1={r['q1']:.1f}, 90% of q1 at {r['papers_to_90pct_q1']} papers "
              f"(co-authors: {r['coauthors_papers_to_90pct_q1']}); switches={r['switches']}, mean run={r['mean_run_length']:.2f}")
        for k in o:
            nl = r[f"null_{k}"]
            print(f"   {k}: obs {o[k]:.3f}  null {nl['mean']:.3f} [{nl['lo']:.3f}, {nl['hi']:.3f}]  P={nl['p_extreme']:.3f}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4:])
