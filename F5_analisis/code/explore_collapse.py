"""EXPLORATORY: voice collapses with per-flow queues, and the ~8 ms of IOU at 1-3 Mbit/s.
Output: results/EXPLORATORIO_COLAPSOS_8ms.txt, results/expl_colapso_correlacion.csv"""
import csv, json, math, os, sys
from collections import defaultdict
import numpy as np
from scipy import stats as SS
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import core as C, load_runs as LR
RES = os.path.join(HERE, "..", "results"); CAMP = LR.CAMP; W = 20.0
out = []; P = out.append
P("EXPLORATORY ANALYSIS — not part of the confirmatory plan. Tables only.")
allrows = C.prep(list(csv.DictReader(open(os.path.join(RES, "runs.csv")))))
main = [r for r in allrows if r["main"] == "True"]
cells = defaultdict(list)
for r in main:
    if r["floor"] != "True":
        cells[r["cell"]].append(r)
med_loss = {c: float(np.median([float(x["loss_w"]) for x in v])) for c, v in cells.items()}
is_col = lambda r: float(r["loss_w"]) >= 0.02 and med_loss[r["cell"]] < 0.005
col = [r for r in main if r["floor"] != "True" and is_col(r)]
P(f"collapse runs (voice loss in window >= 2 % in a cell whose median loss < 0.5 %): {len(col)}")


def delays(run, i):
    """(send time from first voice send, delay ms) of probe i, packets received, sorted by send time."""
    d = os.path.join(CAMP, run); rows = list(csv.DictReader(open(f"{d}/recv_{i}.csv")))
    return np.array(sorted(((int(r["send_ns"]), (int(r["recv_ns"]) - int(r["send_ns"])) / 1e6) for r in rows)))


def corr_with(run, dur, i):
    v = delays(run, 0); o = delays(run, i)
    if len(o) < 50:
        return None
    t0 = min(int(x["send_ns"]) for x in csv.DictReader(open(os.path.join(CAMP, run, "send_0.csv"))))
    m = (v[:, 0] - t0 >= W * 1e9) & (v[:, 0] - t0 < dur * 1e9)
    vt, vd = v[m, 0], v[m, 1]
    od = np.interp(vt, o[:, 0], o[:, 1])   # delay of the other flow at the voice send instants (linear interpolation)
    return float(SS.pearsonr(vd, od)[0]) if len(vd) > 10 and np.std(vd) > 0 and np.std(od) > 0 else None


# ---------- 1. shared-queue test: voice delay vs residential UDP (probe 1) and video (probe 3) delay
P("\n1. VOICE DELAY vs RESIDENTIAL-UDP DELAY, packet by packet (Pearson r at voice send instants, window [20, 60) s); same for video when present")
recs = []
for c in sorted({r["cell"] for r in col}):
    v = cells[c]; m0 = json.load(open(os.path.join(CAMP, v[0]["run"], "meta.json")))
    probes = [i for i, f in enumerate(m0["flows"]) if f["kind"] == "probe" and i > 0]
    res_i = next((i for i in probes if m0["flows"][i]["port"] == 5201), None); vid_i = next((i for i in probes if m0["flows"][i]["port"] == 5101), None)
    for r in v:
        rr = dict(cell=c, rep=int(r["rep"]), collapse=is_col(r), loss_w=float(r["loss_w"]), p99=r["p99f"],
                  r_res=corr_with(r["run"], int(r["dur"]), res_i) if res_i is not None else None,
                  r_video=corr_with(r["run"], int(r["dur"]), vid_i) if vid_i is not None else None)
        recs.append(rr)
with open(os.path.join(RES, "expl_colapso_correlacion.csv"), "w", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=list(recs[0].keys())); w.writeheader(); w.writerows(recs)
for c in sorted({x["cell"] for x in recs}):
    v = [x for x in recs if x["cell"] == c]; cc = [x for x in v if x["collapse"]]; nn = [x for x in v if not x["collapse"]]
    f = lambda xs, k: [x[k] for x in xs if x[k] is not None]
    for x in cc:
        rn = f(nn, "r_res"); rv = f(nn, "r_video")
        P(f"  {c[:50]:50s} r{x['rep']:02d} loss {x['loss_w']:.3f}: r(voice,res UDP) {x['r_res'] if x['r_res'] is None else round(x['r_res'],3)} "
          f"[other runs median {np.median(rn) if rn else float('nan'):.3f}, range {min(rn) if rn else float('nan'):.3f}..{max(rn) if rn else float('nan'):.3f}]"
          + (f" | r(voice,video) {x['r_video']:.3f} [others median {np.median(rv):.3f}, range {min(rv):.3f}..{max(rv):.3f}]" if x["r_video"] is not None and rv else ""))

# ---------- 2. frequency per policy group
P("\n2. COLLAPSE FREQUENCY PER POLICY GROUP (eligible runs = runs in cells whose median voice loss < 0.5 %)")
grp = lambda r: ("FQC (fq_codel, LXR)" if r["policy"] == "FQC" else "CAKE (LXR)" if r["policy"] == "CAKE" else
                 "CBWFQ/LLQ unmarked (IOU fair-queue)" if r["exp"] == "CNEG" else
                 "CBWFQ/LLQ marked (IOU)" if r["policy"] in ("CBWFQ", "LLQ") and r["platform"] == "IOU" else
                 "CBWFQ/LLQ marked (c7200)" if r["platform"] == "C7200" and r["policy"] in ("CBWFQ", "LLQ") else "other")
cnt = defaultdict(lambda: [0, 0])
for r in main:
    if r["floor"] == "True" or med_loss[r["cell"]] >= 0.005:
        continue
    g = grp(r); cnt[g][0] += 1; cnt[g][1] += is_col(r)
tot_e = sum(v[0] for k, v in cnt.items() if k != "other"); tot_c = sum(v[1] for k, v in cnt.items() if k != "other")
for g, (n, k) in sorted(cnt.items()):
    if g == "other":
        continue
    exp = tot_c * n / tot_e; p = SS.binomtest(k, n, tot_c / tot_e).pvalue
    P(f"  {g:38s} eligible {n:5d} collapses {k:2d} rate {k/n:.4f} | expected if equal across groups {exp:5.2f} (binomial p {p:.3g})")
# fq_codel hash-collision expectation: voice collides with one of the b bulk flows in 1024 queues
nb = {"1": 2, "2": 3, "3": 4}
expq = sum(1 - (1 - 1 / 1024) ** nb.get(r["k"], 4) for r in main if r["policy"] == "FQC" and r["floor"] != "True" and med_loss[r["cell"]] < 0.005)
nfq = cnt["FQC (fq_codel, LXR)"]
P(f"  fq_codel (1024 queues, flows {{k=1: 2, k=2: 3, k=3: 4}} bulk UDP/TCP besides voice): expected collisions {expq:.2f} vs observed {nfq[1]} "
  f"(Poisson P(X >= {nfq[1]}) = {1 - SS.poisson.cdf(nfq[1] - 1, expq):.3g})")
P("  IOU fair-queue: number of flow queues not reported by IOU ('show policy-map interface' gives only 'per-flow queue limit 16'; "
  "'show hqf' not available). Implied by the observed rate if collisions with 4 bulk flows: N ~ 4 / rate.")
n_un = cnt["CBWFQ/LLQ unmarked (IOU fair-queue)"]
if n_un[1]:
    P(f"  -> unmarked rate {n_un[1]/n_un[0]:.4f} implies N ~ {4 / (n_un[1]/n_un[0]):.0f} queues (assumption-laden, not verified)")
P("\n3. NUMBER OF QUEUES: fq_codel 'flows 1024' (router_post.txt of every FQC run); IOU fair-queue: not available (see above).")

# ---------- 4. analysis without the collapse runs
P("\n4. CONFIRMATORY TESTS WITHOUT THE COLLAPSE RUNS (pairs containing one are dropped)")
colset = {r["run"] for r in col}
base = C.all_tests(main, boot=False)
idx = C.index(main); pf = lambda x: x[3]["run"] not in colset and x[4]["run"] not in colset
res = dict(H1=C.h1(idx, pair_filter=pf, boot=False), CNEG=C.cneg(idx, pair_filter=pf, boot=False), H2=C.h2(idx, pair_filter=pf, boot=False),
           H4=C.h4(idx, pair_filter=pf, boot=False))
for t in res:
    bm = {(r["family"], r.get("policy", ""), r["cell"]): r for r in base[t]}
    for r in res[t]:
        b = bm[(r["family"], r.get("policy", ""), r["cell"])]
        if b["decision"] != r["decision"] or r["n"] != b["n"]:
            P(f"  {t:4s} {r['family']:9s} {r.get('policy',''):4s} {r['cell']:34s} n {b['n']}->{r['n']} mean d {b.get('mean_d', b.get('mean_delta')):+.2f} -> "
              f"{r.get('mean_d', r.get('mean_delta')):+.2f}  decision {b['decision']} -> {r['decision']}")

# ---------- 5. ~8 ms of IOU
P("\n5. THE ~8 ms OF IOU AT 1-3 Mbit/s")
floor = {}
for r in main:
    if r["floor"] == "True":
        floor.setdefault((r["platform"], r["Li"]), []).append(r["p99f"])
floor = {k: float(np.median(v)) for k, v in floor.items()}
med = lambda cid: float(np.median([x["p99f"] for x in cells[cid]]))
P("  positive control: (median p99 - own floor) - T_s, ms")
for L in (500000, 1000000, 2000000, 3000000, 5000000, 10000000):
    row = [f"L={L//1000}k"]
    for pl in ("IOU", "LXR"):
        cid = f"CPOS_{pl}_FIFO_L{L//1000}k_k1_m0.2_c1_f1514_pos"
        row.append(f"{pl} {med(cid) - floor[(pl, L)] - C.Ts(L):+.2f}" if cid in cells else f"{pl} -")
    P("    " + "  ".join(row))
P("  LLQ (E1, marked): (median p99 - own floor) - (T_s + T_voz), ms")
for L in (500000, 1000000, 2000000, 3000000, 5000000):
    P("    L=%dk  " % (L // 1000) + "  ".join(f"k={k} {med(f'E1_IOU_LLQ_L{L//1000}k_k{k}_m0.2_c1_f1514') - floor[('IOU', L)] - C.Ts(L) - C.Tvoz(L):+.2f}" for k in (1, 2, 3)))
P("  c7200 (E4(b)) vs IOU at 1 Mbit/s, LLQ: (median p99 - own floor) - (T_s + T_voz), ms")
for k in ("1", "3"):
    for pl, ex in (("IOU", "E1"), ("C7200", "E4b")):
        cid = f"{ex}_{pl}_LLQ_L1000k_k{k}_m0.2_c1_f1514"
        P(f"    k={k} {pl:5s} median p99 {med(cid):6.2f} floor {floor[(pl, 1000000)]:6.2f} -> excess - (T_s+T_voz) {med(cid) - floor[(pl, 1000000)] - C.Ts(1000000) - C.Tvoz(1000000):+.2f}")
P("  c7200 vs IOU at 1 Mbit/s, CBWFQ: median p99 (ms)")
for k in ("1", "3"):
    P(f"    k={k} IOU {med(f'E1_IOU_CBWFQ_L1000k_k{k}_m0.2_c1_f1514'):.2f}  c7200 {med(f'E4b_C7200_CBWFQ_L1000k_k{k}_m0.2_c1_f1514'):.2f}")
open(os.path.join(RES, "EXPLORATORIO_COLAPSOS_8ms.txt"), "w").write("\n".join(out) + "\n"); print("\n".join(out))
