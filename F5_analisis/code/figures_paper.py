"""Paper figures: no internal titles (IEEE captions); dataviz rules (fixed categorical order, one y-axis, thin marks,
markers as secondary encoding, IOU solid / Linux dashed). Output: results/paper_fig*.png + results/FIGURAS_PIES.md"""
import csv, os, sys
from collections import defaultdict
import numpy as np
import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import core as C
RES = os.path.join(HERE, "..", "results"); CAMP = os.path.join(HERE, "..", "..", "F4_campana", "campaign")
SER = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300"]; MK = ["o", "s", "^", "D", "v", "P"]
TXT, TXT2, GRID, SURF = "#0b0b0b", "#52514e", "#e4e3df", "#ffffff"
plt.rcParams.update({"font.size": 9, "axes.edgecolor": TXT2, "axes.labelcolor": TXT, "xtick.color": TXT2, "ytick.color": TXT2,
                     "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.6, "axes.spines.top": False, "axes.spines.right": False,
                     "figure.facecolor": SURF, "axes.facecolor": SURF, "savefig.facecolor": SURF, "legend.frameon": False})
main = C.prep([r for r in csv.DictReader(open(os.path.join(RES, "runs.csv"))) if r["main"] == "True"])
cells = defaultdict(list)
for r in main:
    cells[r["cell"]].append(r["p99f"])
med = lambda c: float(np.median(cells[c])); qq = lambda c, p: float(np.quantile(cells[c], p))
POL = [("IOU", "FIFO", "FIFO-C (IOU)"), ("IOU", "CBWFQ", "CBWFQ (IOU)"), ("IOU", "LLQ", "LLQ (IOU)"), ("LXR", "FIFO", "FIFO-L (Linux)"),
       ("LXR", "FQC", "fq_codel (Linux)"), ("LXR", "CAKE", "CAKE (Linux)")]
caps = ['Fig. 0 (paper_fig0_topologia.pdf/.png). Emulated testbed (GNS3 3.0.6, single host). Three Docker endpoints (voice, work data and residential) reach, through an 802.1Q switch, one of three border routers in parallel; only one branch carries traffic in each run: the Cisco IOS router emulated with IOU (two access interfaces; hierarchical policy with a parent shaper at R = 0.95·L), the Linux router with tc, or the c7200 under Dynamips (E4(b) only, dashed). The modem node models the uplink with netem at rate L and a 64-packet queue. Circles: timestamps (send time written in the probe payload, kernel receive time at the sink; one host clock); squares: packet captures; diamonds: queue and policy counters.']   # Fig. 0 is drawn by fig_topologia.py

# Fig 1: E1 k=3, p99 vs L, median + IQR band, IOU solid / Linux dashed
fig, ax = plt.subplots(figsize=(7, 4.3))
for i, (pl, po, lab) in enumerate(POL):
    Ls = [L for L in (500, 1000, 2000, 3000, 5000, 10000) if f"E1_{pl}_{po}_L{L}k_k3_m0.2_c1_f1514" in cells]
    cid = lambda L: f"E1_{pl}_{po}_L{L}k_k3_m0.2_c1_f1514"; x = [L / 1000 for L in Ls]
    ax.fill_between(x, [qq(cid(L), .25) for L in Ls], [qq(cid(L), .75) for L in Ls], color=SER[i], alpha=0.18, lw=0)
    ax.plot(x, [med(cid(L)) for L in Ls], color=SER[i], marker=MK[i], ms=6, lw=2, ls="-" if pl == "IOU" else "--", label=lab,
            markeredgecolor=SURF, markeredgewidth=1, zorder=4 if po == "FQC" else 3)
ax.set_xscale("log"); ax.set_yscale("log"); ax.set_xticks([0.5, 1, 2, 3, 5, 10]); ax.set_xticklabels(["0.5", "1", "2", "3", "5", "10"])
ax.set_xlabel("Line capacity L (Mbit/s)"); ax.set_ylabel("Voice one-way delay, 99th percentile (ms)")
ax.text(10.6, 1.62, "fq_codel = CAKE\nat 3-10 Mbit/s", fontsize=7, color=TXT2, va="center")
ax.legend(ncol=2, fontsize=8, loc="upper right", handlelength=3); fig.tight_layout(); fig.savefig(os.path.join(RES, "paper_fig1_E1_k3_p99.png"), dpi=300); plt.close(fig)
caps.append("Fig. 1 (paper_fig1_E1_k3_p99.png). Voice one-way delay p99 against line capacity with three saturated competing classes (E1, k = 3, one call, m = 0.2). "
            "Lines: median of 17 runs; bands: interquartile range (IQR bands are narrower than the markers in most cells). Solid: Cisco IOS (IOU); dashed: Linux. Both axes logarithmic. "
            "LLQ, FIFO-C and CBWFQ were not run at 10 Mbit/s (IOU input limit).")

# Fig 2: H3 — CBWFQ cell median vs RFC 2212 bound, k = 1, 2, 3
fig, ax = plt.subplots(figsize=(5.6, 4.6)); mx = 0
for i, k in enumerate(("1", "2", "3")):
    xs, ys = [], []
    for L in (500, 1000, 2000, 3000, 5000):
        for m in ((0.2,) if k != "3" else (0.2, 0.5, 1.0, 3.0)):
            cid = f"E1_IOU_CBWFQ_L{L}k_k{k}_m0.2_c1_f1514" if m == 0.2 else f"E1R_IOU_CBWFQ_L{L}k_k3_m{m:g}_c1_f1514"
            if cid in cells:
                xs.append(2 * C.Tr(m) + C.Ts(L * 1000)); ys.append(float(np.median(cells[cid])))
    ax.scatter(xs, ys, s=42, color=SER[i], marker=MK[i], edgecolor=SURF, linewidth=1, zorder=3,
               label=f"k = {k}" + (" (E1, m = 0.2)" if k != "3" else " (E1 + E1-R, m = 0.2-3)")); mx = max(mx, max(xs), max(ys))
lim = [0, mx * 1.08]; ax.plot(lim, lim, color=TXT2, lw=1.2, ls="--", label="RFC 2212 bound (measured = bound)")
ax.set_xlim(lim); ax.set_ylim(lim); ax.set_xlabel(r"RFC 2212 bound $2T_r + T_s$ (ms)"); ax.set_ylabel("Measured voice p99, CBWFQ (ms)")
ax.legend(fontsize=8, loc="lower right"); fig.tight_layout(); fig.savefig(os.path.join(RES, "paper_fig2_H3_cota.png"), dpi=300); plt.close(fig)
caps.append("Fig. 2 (paper_fig2_H3_cota.png). CBWFQ voice p99 (cell median of 17 runs) against the weighted-fair-queuing bound of RFC 2212, "
            "2·T_r + T_s, for k = 1, 2 and 3 competing classes. Points above the dashed line exceed the bound.")

# Fig 3: MOS vs playout buffer, 1 Mbit/s, k=3, T_resto 100 ms; two curves per panel (Bpl 4.3 without / 25.1 with loss concealment)
mos = defaultdict(lambda: defaultdict(dict))
for r in csv.DictReader(open(os.path.join(RES, "expl_mos_sens.csv"))):
    if r["T_resto"] == "100.0":
        mos[r["cell"]][r["Bpl"]][float(r["B"])] = float(r["MOS_median"])
fig, axs = plt.subplots(2, 3, figsize=(7.6, 4.6), sharex=True, sharey=True)
for i, ((pl, po, lab), ax) in enumerate(zip(POL, axs.flat)):
    c = f"E1_{pl}_{po}_L1000k_k3_m0.2_c1_f1514"
    for j, (bpl, blab) in enumerate((("4.3", "Bpl 4.3 (no loss concealment)"), ("25.1", "Bpl 25.1 (loss concealment)"))):
        Bs = sorted(mos[c][bpl]); ys = [mos[c][bpl][b] for b in Bs]
        ax.plot(Bs, ys, color=SER[j], marker=MK[j], ms=5.5, lw=2, ls="-" if j == 0 else "--", label=blab, markeredgecolor=SURF, markeredgewidth=1)
        other = mos[c]["25.1" if bpl == "4.3" else "4.3"]
        for b, y in zip(Bs, ys):
            if j == 0 and f"{max(y, 1.0):.1f}" == f"{max(other[b], 1.0):.1f}":
                continue   # same value at one decimal: a single label (drawn by the other curve)
            ax.annotate(f"{max(y, 1.0):.1f}", (b, y), textcoords="offset points", xytext=(0, 7 if j == 1 else -12), ha="center", fontsize=6.5, color=TXT2)
    ax.set_title(lab, fontsize=8.5, color=TXT, loc="left"); ax.set_xticks([40, 60, 100]); ax.set_xlim(25, 115); ax.set_ylim(0.5, 4.9)
for ax in axs[1]:
    ax.set_xlabel("Playout buffer (ms)")
for ax in axs[:, 0]:
    ax.set_ylabel("Estimated MOS")
axs[0, 0].legend(fontsize=7, loc="center left", bbox_to_anchor=(0.0, 0.55))
fig.tight_layout(); fig.savefig(os.path.join(RES, "paper_fig3_MOS_buffer.png"), dpi=300); plt.close(fig)
caps.append("Fig. 3 (paper_fig3_MOS_buffer.png). Estimated MOS (E-model, ITU-T G.107 with G.711 parameters of G.113) against the static playout buffer, "
            "at 1 Mbit/s with k = 3 and a rest-of-path delay of 100 ms, for Bpl = 4.3 (no packet-loss concealment, solid) and Bpl = 25.1 "
            "(concealment, dashed); median of 17 runs; where both curves give the same value, one label is shown. Values below 1.0 produced by the G.107 polynomial for small R are shown as 1.0. "
            "CBWFQ stays at or below 1.8 with buffers up to 60 ms and reaches 3.0-3.5 only with a 100-ms buffer and concealment; "
            "LLQ and CAKE stay at 4.2-4.4 in all 18 combinations (buffer 40/60/100 ms, rest-of-path 50/100/150 ms, Bpl 4.3/25.1).")

# Fig 4: forest plot of H4 (mean d with 90 % CI, +-EMI band), FQC and CAKE side by side
h4 = list(csv.DictReader(open(os.path.join(RES, "H4_direccion.csv"))))
fam_order = ["H4 E1 k=1", "H4 E1 k=2", "H4 E1 k=3", "H4 E2 k=3"]
rows = sorted({(r["family"], r["cell"], int(r["L"])) for r in h4}, key=lambda x: (fam_order.index(x[0]), x[2], x[1]))
XL = (-6, 12)
fig, axs = plt.subplots(1, 2, figsize=(8.2, 9.6), sharey=True)
for j, (pol, ax) in enumerate(zip(("FQC", "CAKE"), axs)):
    for y, (fam, cell, L) in enumerate(rows):
        r = next(x for x in h4 if x["policy"] == pol and x["cell"] == cell)
        mu = float(r["mean_d"]); lo, hi = [float(v) for v in r["ci90"].strip("()").split(",")]; emi = float(r["margin"])
        ax.add_patch(plt.Rectangle((-emi, y - 0.42), 2 * emi, 0.84, color=GRID, lw=0, zorder=0))
        eq = r["decision"] == "equivalent"
        if XL[0] <= mu <= XL[1]:
            ax.plot([max(lo, XL[0]), min(hi, XL[1])], [y, y], color=SER[j], lw=1.6, zorder=2)
            ax.plot(mu, y, marker=MK[j], ms=5.5, zorder=3, markeredgewidth=1.3, color=SER[j],
                    markerfacecolor=SER[j] if eq else SURF, markeredgecolor=SER[j])
        else:
            t = f"{mu:+.0f} (CI {lo:+.0f} to {hi:+.0f}) →" if lo < XL[1] else f"{mu:+.0f} ms →"
            ax.annotate(t, (XL[1], y), xytext=(-2, 0), textcoords="offset points", ha="right", va="center", fontsize=7, color=SER[j])
    ax.axvline(0, color=TXT2, lw=0.8); ax.set_xlim(*XL); ax.set_title(f"{'fq_codel' if pol == 'FQC' else 'CAKE'} − LLQ", fontsize=9, color=TXT, loc="left")
    ax.set_xlabel("Difference in voice p99 (ms), mean and 90 % CI"); ax.grid(axis="y", visible=False)
def nice(c, L):
    t = c.split(" ")[0] + f" {L/1e6:g} Mbit/s, k = " + c.split("k=")[1].split(" ")[0]
    if "frame=590" in c: t += ", 590 B"
    if "calls=4" in c: t += ", 4 calls"
    return t
labels = [nice(c, L) for f_, c, L in rows]
axs[0].set_yticks(range(len(rows))); axs[0].set_yticklabels(labels, fontsize=7); axs[0].invert_yaxis()
fig.tight_layout(); fig.savefig(os.path.join(RES, "paper_fig4_H4_forest.png"), dpi=300); plt.close(fig)
caps.append("Fig. 4 (paper_fig4_H4_forest.png). H4: difference in voice p99 between each Linux policy and LLQ (IOU), mean over 17 paired runs with 90 % CI. "
            "Grey band: equivalence margin ±MEI (3.02 ms at 0.5 Mbit/s, 2 ms elsewhere). Filled marker: equivalent (TOST, Holm-adjusted p < 0.05); "
            "hollow marker: not shown equivalent. Values beyond the axis are printed at the right edge (with the CI when it reaches the plotted range: "
            "fq_codel, E2, 5 Mbit/s, 590 B, whose mean is driven by one run with a voice collapse). "
            "Negative values mean lower delay than LLQ; part of that difference may be platform-specific (Section V-E).")

# Fig 5: CBWFQ p99 vs over-reservation m, one panel per L, LLQ reference, budget lines
fig, axs = plt.subplots(1, 5, figsize=(9.6, 3.2), sharey=True)
for ax, L in zip(axs, (500, 1000, 2000, 3000, 5000)):
    for j, pol in enumerate(("CBWFQ", "LLQ")):
        ms = [m for m in (0.2, 0.5, 1.0, 3.0) if (f"E1_IOU_{pol}_L{L}k_k3_m0.2_c1_f1514" if m == 0.2 else f"E1R_IOU_{pol}_L{L}k_k3_m{m:g}_c1_f1514") in cells]
        cid = lambda m: f"E1_IOU_{pol}_L{L}k_k3_m0.2_c1_f1514" if m == 0.2 else f"E1R_IOU_{pol}_L{L}k_k3_m{m:g}_c1_f1514"
        x = [1 + m for m in ms]
        ax.fill_between(x, [qq(cid(m), .25) for m in ms], [qq(cid(m), .75) for m in ms], color=SER[[1, 2][j]], alpha=0.18, lw=0)
        ax.plot(x, [med(cid(m)) for m in ms], color=SER[[1, 2][j]], marker=MK[[1, 2][j]], ms=5.5, lw=2, label=f"{pol} (IOU)",
                markeredgecolor=SURF, markeredgewidth=0.8)
    for b in (20, 50, 100):
        ax.axhline(b, color=TXT2, lw=0.8, ls=":"); ax.text(4.05, b, f"{b} ms", fontsize=6.5, color=TXT2, va="bottom", ha="right")
    ax.set_xscale("log"); ax.set_xticks([1.2, 1.5, 2, 4]); ax.set_xticklabels(["0.2", "0.5", "1", "3"]); ax.minorticks_off()
    ax.set_title(f"L = {L/1000:g} Mbit/s", fontsize=8.5, color=TXT, loc="left"); ax.set_xlabel("Over-reservation m")
axs[0].set_ylabel("Voice p99 (ms), k = 3"); axs[0].legend(fontsize=7.5, loc="upper right"); axs[0].set_ylim(0, 140)
fig.tight_layout(); fig.savefig(os.path.join(RES, "paper_fig5_m_star.png"), dpi=300); plt.close(fig)
caps.append("Fig. 5 (paper_fig5_m_star.png). Voice p99 against the voice over-reservation m (B_v = 85.6·(1 + m) kbit/s), k = 3, one panel per capacity; "
            "median of 17 runs and interquartile band; x axis in log(1 + m). Dotted lines: illustrative budgets of 20, 50 and 100 ms. "
            "m = 3 is infeasible at 0.5 Mbit/s.")

# Fig 6: collapse example (no title)
fig, axs = plt.subplots(1, 2, figsize=(8, 3.4), sharey=True)
for ax, rep in zip(axs, (5, 6)):
    d = os.path.join(CAMP, f"CNEG_IOU_CBWFQ_L2000k_k3_m0.2_c1_f1514_unmarked_r{rep:02d}")
    t0 = min(int(x["send_ns"]) for x in csv.DictReader(open(f"{d}/send_0.csv")))
    for i, (f_, lab) in enumerate(((0, "voice"), (1, "residential UDP"))):
        rr = [((int(x["send_ns"]) - t0) / 1e9, (int(x["recv_ns"]) - int(x["send_ns"])) / 1e6) for x in csv.DictReader(open(f"{d}/recv_{f_}.csv"))]
        rr = [p for p in rr if 20 <= p[0] < 60]
        ax.plot([a for a, b in rr], [b for a, b in rr], color=SER[i], lw=0.8, label=lab)
    ax.set_title(f"({'a' if rep == 5 else 'b'}) run {rep:02d}: {'typical' if rep == 5 else 'voice collapse'}", color=TXT, loc="left", fontsize=8.5)
    ax.set_xlabel("Time since first voice packet (s)")
axs[0].set_ylabel("One-way delay (ms)"); axs[1].legend(fontsize=8, loc="lower right")
fig.tight_layout(); fig.savefig(os.path.join(RES, "paper_fig6_colapso.png"), dpi=300); plt.close(fig)
caps.append("Fig. 6 (paper_fig6_colapso.png). Per-packet one-way delay of voice and of the residential UDP flow, unmarked traffic under CBWFQ "
            "(class-default fair-queue), 2 Mbit/s, k = 3: (a) a typical run; (b) a run in which voice follows the residential flow (exploratory).")
open(os.path.join(RES, "FIGURAS_PIES.md"), "w").write("# Figure captions (draft, English; exploratory figures marked)\n\n" + "\n\n".join(caps) + "\n")
print("ok")
