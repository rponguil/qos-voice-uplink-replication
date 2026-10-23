"""EXPLORATORY/DESCRIPTIVE figures (dataviz rules: fixed categorical order, one y-axis, thin marks, recessive grid, markers as
secondary encoding, legend for >= 2 series). Output: results/fig_*.png"""
import csv, math, os, sys
from collections import defaultdict
import numpy as np
import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import core as C
RES = os.path.join(HERE, "..", "results"); CAMP = os.path.join(HERE, "..", "..", "F4_campana", "campaign")
SER = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300"]; MK = ["o", "s", "^", "D", "v", "P"]
TXT, TXT2, GRID, SURF = "#0b0b0b", "#52514e", "#e4e3df", "#fcfcfb"
plt.rcParams.update({"font.size": 9, "axes.edgecolor": TXT2, "axes.labelcolor": TXT, "xtick.color": TXT2, "ytick.color": TXT2,
                     "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.6, "axes.spines.top": False, "axes.spines.right": False,
                     "figure.facecolor": SURF, "axes.facecolor": SURF, "savefig.facecolor": SURF, "legend.frameon": False})
main = C.prep([r for r in csv.DictReader(open(os.path.join(RES, "runs.csv"))) if r["main"] == "True"])
cells = defaultdict(list)
for r in main:
    cells[r["cell"]].append(r["p99f"])
med = lambda c: float(np.median(cells[c])); q = lambda c, p: float(np.quantile(cells[c], p))
POL = [("IOU", "FIFO", "FIFO-C (IOU)"), ("IOU", "CBWFQ", "CBWFQ (IOU)"), ("IOU", "LLQ", "LLQ (IOU)"), ("LXR", "FIFO", "FIFO-L (Linux)"),
       ("LXR", "FQC", "fq_codel (Linux)"), ("LXR", "CAKE", "CAKE (Linux)")]

# F1: voice p99 vs L, E1 k=3
fig, ax = plt.subplots(figsize=(7, 4.4))
for i, (pl, po, lab) in enumerate(POL):
    Ls = [L for L in (500, 1000, 2000, 3000, 5000, 10000) if f"E1_{pl}_{po}_L{L}k_k3_m0.2_c1_f1514" in cells]
    y = [med(f"E1_{pl}_{po}_L{L}k_k3_m0.2_c1_f1514") for L in Ls]
    lo = [y_ - q(f"E1_{pl}_{po}_L{L}k_k3_m0.2_c1_f1514", .25) for L, y_ in zip(Ls, y)]; hi = [q(f"E1_{pl}_{po}_L{L}k_k3_m0.2_c1_f1514", .75) - y_ for L, y_ in zip(Ls, y)]
    ax.plot([L / 1000 for L in Ls], y, color=SER[i], marker=MK[i], ms=6, lw=2, label=lab, markeredgecolor=SURF, markeredgewidth=1,
            ls="--" if po == "FQC" else "-", zorder=4 if po == "FQC" else 3)
ax.set_xscale("log"); ax.set_yscale("log"); ax.set_xticks([0.5, 1, 2, 3, 5, 10]); ax.set_xticklabels(["0.5", "1", "2", "3", "5", "10"])
ax.set_xlabel("Line capacity L (Mbit/s)"); ax.set_ylabel("Voice one-way delay p99 (ms), median of 17 runs")
ax.set_title("Voice p99 with three saturated competing classes (E1, k = 3)", color=TXT, loc="left", fontsize=10)
ax.text(10.6, 1.62, "fq_codel = CAKE\nat 3-10 Mbit/s", fontsize=7, color=TXT2, va="center")
ax.legend(ncol=2, fontsize=8, loc="upper right"); fig.tight_layout(); fig.savefig(os.path.join(RES, "fig_E1_k3_p99.png"), dpi=200); plt.close(fig)

# F2: H3 — observed CBWFQ cell mean vs RFC 2212 bound 2 T_r + T_s
fig, ax = plt.subplots(figsize=(5.6, 4.6))
xs, ys = [], []
for r in csv.DictReader(open(os.path.join(RES, "H3_residuos.csv"))):
    if r["model"] == "p99_CBWFQ":
        xs.append(2 * float(r["T_r"]) + float(r["T_s"])); ys.append(float(r["cell_mean"]))
ax.scatter(xs, ys, s=40, color=SER[0], edgecolor=SURF, linewidth=1, zorder=3, label="CBWFQ (IOU), cell mean of 17 runs, k = 3")
lim = [0, max(max(xs), max(ys)) * 1.08]
ax.plot(lim, lim, color=TXT2, lw=1.2, ls="--", label="RFC 2212 bound (measured = bound)")
ax.set_xlim(lim); ax.set_ylim(lim); ax.set_xlabel("RFC 2212 bound 2·T_r + T_s (ms)"); ax.set_ylabel("Measured voice p99 (ms)")
ax.set_title("CBWFQ against the weighted-fair-queuing bound (19 cells)", color=TXT, loc="left", fontsize=10)
ax.legend(fontsize=8, loc="lower right"); fig.tight_layout(); fig.savefig(os.path.join(RES, "fig_H3_cota_RFC2212.png"), dpi=200); plt.close(fig)

# F3: MOS vs T_resto, E1 k=3, L = 1 Mbit/s (B = 60 ms, Bpl = 4.3)
mos = defaultdict(dict)
for r in csv.DictReader(open(os.path.join(RES, "expl_mos_sens.csv"))):
    if r["B"] == "60.0" and r["Bpl"] == "4.3":
        mos[r["cell"]][float(r["T_resto"])] = float(r["MOS_median"])
fig, axs = plt.subplots(2, 3, figsize=(7.6, 4.6), sharex=True, sharey=True)
for i, ((pl, po, lab), ax) in enumerate(zip(POL, axs.flat)):
    c = f"E1_{pl}_{po}_L1000k_k3_m0.2_c1_f1514"; T = sorted(mos[c])
    ax.plot(T, [mos[c][t] for t in T], color=SER[i], marker=MK[i], ms=6, lw=2, markeredgecolor=SURF, markeredgewidth=1)
    for t in T:
        ax.annotate(f"{mos[c][t]:.2f}", (t, mos[c][t]), textcoords="offset points", xytext=(0, 7), ha="center", fontsize=7, color=TXT2)
    ax.set_title(lab, fontsize=8.5, color=TXT, loc="left"); ax.set_xticks([50, 100, 150]); ax.set_xlim(30, 170); ax.set_ylim(0.8, 4.8)
for ax in axs[1]:
    ax.set_xlabel("T_resto (ms)")
for ax in axs[:, 0]:
    ax.set_ylabel("Estimated MOS")
fig.suptitle("Estimated MOS (E-model) at 1 Mbit/s, k = 3; median of 17 runs; playout buffer 60 ms, Bpl 4.3", color=TXT, x=0.01, ha="left", fontsize=9.5)
fig.tight_layout(); fig.savefig(os.path.join(RES, "fig_MOS_1M_k3.png"), dpi=200); plt.close(fig)

# F4: collapse example — voice and residential UDP delay over time (CNEG CBWFQ 2 Mbit/s k=3 r06) vs a normal run (r05)
fig, axs = plt.subplots(1, 2, figsize=(8, 3.6), sharey=True)
for ax, rep in zip(axs, (5, 6)):
    d = os.path.join(CAMP, f"CNEG_IOU_CBWFQ_L2000k_k3_m0.2_c1_f1514_unmarked_r{rep:02d}")
    t0 = min(int(x["send_ns"]) for x in csv.DictReader(open(f"{d}/send_0.csv")))
    for i, (f_, lab) in enumerate(((0, "voice"), (1, "residential UDP"))):
        rr = [(int(x["send_ns"]), (int(x["recv_ns"]) - int(x["send_ns"])) / 1e6) for x in csv.DictReader(open(f"{d}/recv_{f_}.csv"))]
        rr = [((s - t0) / 1e9, v) for s, v in rr if 20 <= (s - t0) / 1e9 < 60]
        ax.plot([a for a, b in rr], [b for a, b in rr], color=SER[i], lw=0.8, label=lab)
    ax.set_title(f"r{rep:02d} ({'collapse' if rep == 6 else 'typical run'})", color=TXT, loc="left", fontsize=9); ax.set_xlabel("Time since first voice packet (s)")
axs[0].set_ylabel("One-way delay (ms)"); axs[1].legend(fontsize=8, loc="lower right")
fig.suptitle("Unmarked CBWFQ (fair-queue), 2 Mbit/s, k = 3: voice and residential UDP delay", color=TXT, x=0.01, ha="left", fontsize=10)
fig.tight_layout(); fig.savefig(os.path.join(RES, "fig_colapso_CNEG_2M_r06.png"), dpi=200); plt.close(fig)
print("ok")
