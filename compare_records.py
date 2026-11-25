#!/usr/bin/env python3
"""Compare diversity profiles and fingerprints of several records side by side.
usage: python compare_records.py OUTPREFIX "Label=file.csv=Your Name" ["Label=file.csv=Name" ...]"""
import io, contextlib, json, sys
import numpy as np
import matplotlib as mpl, matplotlib.pyplot as plt
from matplotlib.lines import Line2D
import pubfingerprint as pf

DIMS = ["Co-authors", "Co-authors (fractional)", "Senior / corresponding authors", "Venues", "Countries", "Research lines", "Approaches"]


def main(out, specs):
    pf._style(); recs = {}
    for s in specs:
        lab, fn, me = s.split("=")
        with contextlib.redirect_stdout(io.StringIO()):
            recs[lab] = pf.Record(pf.read(fn), [me])
    labs = list(recs); col = {l: pf.C[i] for i, l in enumerate(labs)}
    fig = plt.figure(figsize=(7.4, 7.0))
    a = fig.add_axes([0.3, 0.5, 0.66, 0.45]); b = fig.add_axes([0.3, 0.07, 0.66, 0.26])
    res = {}
    for j, l in enumerate(labs):
        d = recs[l].diversity(); res[l] = {k: v for k, v in d.items()}
        for i, k in enumerate(DIMS[::-1]):
            if k in d:
                y = i + (j - (len(labs) - 1) / 2) * 0.14
                a.plot([d[k]["q1"], d[k]["richness"]], [y, y], color=col[l], lw=1, alpha=0.5)
                a.scatter(d[k]["q1"], y, s=30, color=col[l], zorder=3, edgecolor="white", lw=0.6)
                a.scatter(d[k]["richness"], y, s=16, facecolor="white", edgecolor=col[l], lw=1.1, zorder=3)
    a.set_xscale("log"); a.set_xticks([1, 2, 5, 10, 20, 50, 100, 250]); a.get_xaxis().set_major_formatter(mpl.ticker.ScalarFormatter())
    a.set_yticks(range(len(DIMS))); a.set_yticklabels(DIMS[::-1]); a.grid(axis="y", visible=False)
    a.set_xlabel("Number of categories (log scale): filled = effective number (q = 1), open = richness")
    a.set_title("a  Diversity profiles of five 50-paper records", loc="left", fontsize=9.5, fontweight="bold", x=-0.38)
    a.legend(handles=[Line2D([], [], marker="o", ls="", color=col[l], label=l) for l in labs], fontsize=6.8,
             loc="upper center", bbox_to_anchor=(0.42, -0.12), ncol=3)
    # b: role composition and collaborator recurrence
    rows = []
    for l in labs:
        fp = dict(recs[l].fingerprint())
        rows.append((l, fp["Own role"], fp["Co-author slots"]))
    cat = ["First / co-first", "Senior / corresp.", "Middle"]; ccol = ["#3d3c39", "#8a8985", "#cfcdc7"]
    for i, (l, role, slots) in enumerate(rows[::-1]):
        rd = dict(role); tot = sum(rd.values()); left = 0
        for c, cc in zip(cat, ccol):
            w = rd.get(c, 0) / tot * 100
            b.barh(i, w, left=left, color=cc, height=0.6, edgecolor="white", lw=1.2); left += w
        sd = dict(slots); rec = sd.get("Recurring collaborators", 0) / max(1, sum(sd.values())) * 100
        b.text(103, i, f"{rec:.0f}%", va="center", fontsize=7, color=pf.INK2)
    b.text(103, len(rows) - 0.35, "recurring\nco-author\nslots", fontsize=6.2, color=pf.INK2, va="bottom")
    b.set_yticks(range(len(rows))); b.set_yticklabels([r[0] for r in rows[::-1]], fontsize=7.4)
    b.set_xlim(0, 118); b.set_xticks([0, 25, 50, 75, 100]); b.grid(axis="y", visible=False)
    b.set_xlabel("Own authorship role (% of papers)")
    b.legend(handles=[mpl.patches.Patch(color=cc, label=c) for c, cc in zip(cat, ccol)], fontsize=6.8, loc="upper center",
             bbox_to_anchor=(0.45, -0.22), ncol=3)
    b.set_title("b  Role mix", loc="left", fontsize=9.5, fontweight="bold", x=-0.38)
    fig.savefig(out + ".png", bbox_inches="tight"); fig.savefig(out + ".pdf", bbox_inches="tight"); plt.close(fig)
    json.dump({l: {"diversity": res[l], "fingerprint": recs[l].fingerprint(), "summary": recs[l].summary()} for l in labs},
              open(out + ".json", "w"), indent=1, ensure_ascii=False)
    print("wrote", out + ".png/.pdf/.json")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2:])
