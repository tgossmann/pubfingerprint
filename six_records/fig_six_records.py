"""Figure 7 of the article: six anonymised publication records side by side, drawn from aggregated values
(six_records_aggregated.json). Per-researcher inputs are not distributed.
usage: python3 six_records/fig_six_records.py"""
import json, sys, numpy as np, matplotlib as mpl, matplotlib.pyplot as plt
import os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import pubfingerprint as pf
pf._style(); C = pf.C
HERE = os.path.dirname(os.path.abspath(__file__))
d = json.load(open(os.path.join(HERE, "six_records_aggregated.json")))
labs = sorted(d, key=lambda x: (x != "Demonstration record", x))
col = {l: C[i] for i, l in enumerate(labs)}
mk = {l: m for l, m in zip(labs, ["o", "s", "^", "D", "v", "P"])}
short = {l: ("Demo" if l.startswith("Demo") else l.split()[-1]) for l in labs}
fig = plt.figure(figsize=(7.4, 10.4))
gs = fig.add_gridspec(3, 1, height_ratios=[1.0, 1.15, 1.1], hspace=0.95)
# a: rarefaction curves, full length
ga = gs[0].subgridspec(1, 3, wspace=0.32); dims_a = ["Co-authors", "Venues", "Research lines"]
for k, dm in enumerate(dims_a):
    ax = fig.add_subplot(ga[k])
    for l in labs:
        r = d[l]["rare"][dm]; x = [e["papers"] for e in r]; y = [e["q1"] for e in r]
        ax.plot(x, y, color=col[l], lw=1.6, label=f"{l} (n={d[l]['papers']})")
        ax.scatter([x[-1]], [y[-1]], color=col[l], marker=mk[l], s=18, zorder=3, edgecolor="white", lw=0.6)
    ax.set_xscale("log"); ax.set_yscale("log"); ax.set_title(dm, fontsize=8.5)
    ax.get_yaxis().set_major_formatter(mpl.ticker.FuncFormatter(lambda v, p: f"{v:g}")); ax.get_yaxis().set_minor_formatter(mpl.ticker.NullFormatter())
    ax.set_xlabel("Number of papers", fontsize=7.5); ax.axvline(45, color=pf.MUTED, lw=0.8, ls=":")
    ax.get_xaxis().set_major_formatter(mpl.ticker.ScalarFormatter()); ax.set_xticks([5, 20, 50, 200, 500])
    if k == 0:
        ax.set_ylabel("Effective number (q = 1)", fontsize=7.5)
        ax.text(-0.42, 1.18, "a  Each record over its full length (rarefaction; dotted line: 45 papers)", transform=ax.transAxes,
                fontsize=9, fontweight="bold")
h, lb = ax.get_legend_handles_labels()
ax.legend(h, lb, loc="upper center", bbox_to_anchor=(-0.75, -0.26), ncol=3, fontsize=6.6, frameon=False)
# b: roles by period
gb = gs[1].subgridspec(2, 3, wspace=0.42, hspace=0.95)
RC = {"First author": C[0], "Last / corresponding": C[1], "Middle author": C[2]}
for i, l in enumerate(labs):
    ax = fig.add_subplot(gb[i // 3, i % 3]); rows = d[l]["roles"]
    for j, r in enumerate(rows):
        y = len(rows) - 1 - j; left = 0
        for role in pf.ROLES:
            w = r["counts"][role] / r["n"] * 100
            ax.barh(y, w, left=left, color=RC[role], height=0.7, edgecolor="white", lw=0.8)
            left += w
    ax.set_yticks(range(len(rows))); ax.set_yticklabels([r["period"] for r in rows][::-1], fontsize=5.8)
    ax.set_xlim(0, 100); ax.set_xticks([0, 50, 100]); ax.tick_params(axis="x", labelsize=6); ax.grid(False)
    ax.set_title(f"{l} ({d[l]['papers']} papers)", fontsize=7.5, color=pf.INK)
    if i == 0:
        ax.text(-0.42, 1.45, "b  Role in the author list by career period (% of papers)", transform=ax.transAxes,
                fontsize=9, fontweight="bold")
fig.legend([plt.Rectangle((0, 0), 1, 1, color=c) for c in RC.values()],
           ["First author (≈ specialized)", "Last / corresponding (≈ leader)", "Middle (≈ supporting)"],
           loc="upper center", bbox_to_anchor=(0.5, 0.36), ncol=3, fontsize=6.6, frameon=False)
# c: profile at 45 papers
ax = fig.add_subplot(gs[2]); dims = ["Co-authors", "Senior / corresponding authors", "Venues", "Countries", "Research lines", "Own institutions"]
def at(r, n): return next(e["q1"] for e in r if e["papers"] == n)
for j, dm in enumerate(dims[::-1]):
    vals = [at(d[l]["rare"][dm], 45) for l in labs]
    ax.plot([min(vals), max(vals)], [j, j], color="#dcdad5", lw=2, zorder=1)
    for k, l in enumerate(labs):
        ax.scatter(vals[k], j + (k - 2.5) * 0.07, color=col[l], marker=mk[l], s=30, zorder=3, edgecolor="white", lw=0.6)
ax.set_xscale("log"); ax.set_yticks(range(len(dims))); ax.set_yticklabels(dims[::-1], fontsize=7.5)
ax.get_xaxis().set_major_formatter(mpl.ticker.ScalarFormatter()); ax.set_xticks([1, 2, 5, 10, 20, 50, 100, 300, 1000])
ax.set_xlabel("Effective number (q = 1) in a random set of 45 papers (log scale)", fontsize=7.5); ax.grid(axis="y", visible=False)
ax.set_title("c  Six records compared at the same size: the order changes between dimensions", loc="left", fontsize=9,
             fontweight="bold", x=-0.36)
fig.savefig(os.path.join(HERE, "six_records.pdf"), bbox_inches="tight"); fig.savefig(os.path.join(HERE, "six_records.png"), bbox_inches="tight", dpi=200)
