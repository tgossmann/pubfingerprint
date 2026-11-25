#!/usr/bin/env python3
"""Two SIMULATED careers with identical topic diversity but different temporal organisation:
A works on five topics one after another (sequential specialisation), B on five topics in
parallel. Both have 50 papers, 10 per topic, so richness, Shannon and Simpson effective numbers
of topics are identical (5.0). Optionally the real record is added for comparison.
usage: python simulate_temporal.py OUTPREFIX [real.csv "Real Name"]"""
import io, contextlib, json, random, sys
from collections import Counter
import numpy as np
import matplotlib.pyplot as plt
import pubfingerprint as pf


def records(seed=3):
    r = random.Random(seed)
    A = [f"Topic {i // 10 + 1}" for i in range(50)]
    B = [f"Topic {k + 1}" for k in range(5) for _ in range(10)]; r.shuffle(B)
    return {"A: sequential (sim.)": A, "B: parallel (sim.)": B}


def metrics(seq, w=10):
    c = Counter(seq).values()
    roll = [pf.hill(list(Counter(seq[s:s + w]).values()), 1) for s in range(len(seq) - w + 1)]
    exp, lo, hi = pf.switch_null(seq)
    return dict(richness=pf.hill(list(c), 0), q1=pf.hill(list(c), 1), q2=pf.hill(list(c), 2),
                switches=pf.switches(seq), expected_switches_random=exp, random_order_95=[lo, hi],
                rolling_q1=roll, rolling_q1_mean=float(np.mean(roll)))


def main(out, real=None, me=None):
    pf._style(); recs = records()
    if real:
        with contextlib.redirect_stdout(io.StringIO()):
            rec = pf.Record(pf.read(real), [me])
        recs["Demonstration record (real)"] = [p["line"] for p in rec.papers]
    res = {k: metrics(v) for k, v in recs.items()}
    fig = plt.figure(figsize=(7.4, 4.6))
    a = fig.add_axes([0.2, 0.62, 0.77, 0.3]); b = fig.add_axes([0.2, 0.1, 0.77, 0.38])
    for i, (k, seq) in enumerate(list(recs.items())[::-1]):
        cats = sorted(set(seq), key=lambda x: seq.index(x)); col = {c: pf.C[j % len(pf.C)] for j, c in enumerate(cats)}
        for x, s in enumerate(seq):
            a.add_patch(plt.Rectangle((x + 0.5, i - 0.35), 1, 0.7, color=col[s], lw=0))
    a.set_xlim(0.5, 50.5); a.set_ylim(-0.6, len(recs) - 0.4)
    a.set_yticks(range(len(recs))); a.set_yticklabels(list(recs)[::-1], fontsize=7.5); a.grid(False)
    a.set_xlabel("Papers in chronological order", fontsize=7.5)
    a.set_title("a  Research line of each paper (colour)", loc="left", fontsize=9, fontweight="bold", x=-0.25)
    lines = ["#2a78d6", "#eb6834", "#1baf7a"]
    for (k, r), c in zip(res.items(), lines):
        x = np.arange(len(r["rolling_q1"])) + 5.5
        b.plot(x, r["rolling_q1"], color=c, lw=2,
               label=f"{k}: whole record $^0D$={r['richness']:.0f}, $^1D$={r['q1']:.1f}; {r['switches']} switches")
    b.set_xlim(0.5, 50.5); b.set_ylim(0, 7.5)
    b.set_ylabel("Effective number of lines\nin 10-paper window ($q=1$)", fontsize=7.5)
    b.set_xlabel("Centre of 10-paper window (paper number)", fontsize=7.5)
    b.legend(fontsize=6.4, loc="upper center", bbox_to_anchor=(0.45, -0.22), ncol=1)
    b.set_title("b  Diversity within the career at any one time", loc="left", fontsize=9, fontweight="bold", x=-0.25)
    fig.savefig(out + ".png", bbox_inches="tight"); fig.savefig(out + ".pdf", bbox_inches="tight"); plt.close(fig)
    json.dump({k: {kk: vv for kk, vv in v.items()} for k, v in res.items()}, open(out + ".json", "w"), indent=1)
    for k, v in res.items():
        print(k, {kk: (round(vv, 2) if isinstance(vv, float) else vv) for kk, vv in v.items() if kk != "rolling_q1"})


if __name__ == "__main__":
    main(sys.argv[1], *(sys.argv[2:4] if len(sys.argv) > 3 else []))
