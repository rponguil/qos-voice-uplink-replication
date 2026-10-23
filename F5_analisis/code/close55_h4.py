"""Closure of sensitivity 5.5 (confirmatory decisions with the 12 failed shaper attempts instead of their replacements) and
H4 reporting (mean difference with 90 % CI next to each TOST decision + direction table, raw and floor-corrected; the
direction table is exploratory). Output: results/CIERRE_55_H4.txt, results/H4_direccion.csv"""
import csv, glob, json, os, sys
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import core as C, stats_lib as S, load_runs as LR
SHAPER_EXEMPT = C.shaper_exempt()
RES = os.path.join(HERE, "..", "results"); CAMP = LR.CAMP
out = []; P = out.append
allrows = C.prep(list(csv.DictReader(open(os.path.join(RES, "runs.csv")))))
main = [r for r in allrows if r["main"] == "True"]
base = C.all_tests(main, boot=False)

# ---------- 5.5 closure
if not os.path.isdir(os.path.join(CAMP, "_invalid")):
    sys.exit("close55_h4.py needs the raw archive (F4_campana/campaign/_invalid/)")
st = json.load(open(os.path.join(CAMP, "state.json"))); subs = {}
for rid, lst in st["invalid"].items():
    if any(p in rid for p in SHAPER_EXEMPT):
        continue
    for d in sorted(glob.glob(os.path.join(CAMP, "_invalid", f"{rid}_a*"))):
        if any(x.startswith("shaper rate") for x in open(d + "/reason.txt").read().splitlines()) and os.path.exists(d + "/send_0.csv"):
            subs[rid] = os.path.relpath(d, CAMP)
P(f"5.5 CLOSURE: {len(subs)} failed shaper attempts substituted for their accepted runs")
alt = []
for r in main:
    if r["run"] in subs:
        f = LR.row(subs[r["run"]]); f.update(run=r["run"], block=r["block"], rep=r["rep"], main="True", session=r["session"], ac=r["ac"])
        alt.append(f)
    else:
        alt.append(r)
C.prep(alt)
res = C.all_tests(alt, boot=False)
ch = 0
for t in ("H1", "CNEG", "H2", "H4", "H5"):
    bm = {(r["family"], r.get("policy", ""), r.get("cell", r.get("flow"))): r["decision"] for r in base[t]}
    for r in res[t]:
        k = (r["family"], r.get("policy", ""), r.get("cell", r.get("flow")))
        if bm.get(k) != r["decision"]:
            ch += 1; P(f"  CHANGE {t} {k}: {bm.get(k)} -> {r['decision']}")
for m in ("p99_CBWFQ", "Delta"):
    if res["H3"][m]["decision"] != base["H3"][m]["decision"]:
        ch += 1; P(f"  CHANGE H3 {m}")
    P(f"  H3 {m}: a {res['H3'][m]['a']:.4f} (base {base['H3'][m]['a']:.4f}), b {res['H3'][m]['b']:.4f} (base {base['H3'][m]['b']:.4f})")
P(f"  decisions changed: {ch}")

# ---------- H4 with mean d and 90 % CI + direction table (raw and floor-corrected)
floor = {}
for r in main:
    if r["floor"] == "True":
        floor.setdefault((r["platform"], r["Li"]), []).append(r["p99f"])
floor = {k: float(np.median(v)) for k, v in floor.items()}
idx = C.index(main); recs = []
P("\nH4 with mean difference (X - LLQ) and 90 % CI; direction (exploratory): 'equivalent' if TOST comparable (Holm); else 'better' if the 90 % CI"
  " is entirely below 0, 'worse' if entirely above 0, 'inconclusive' otherwise. Floor-corrected: d - (floor_LXR - floor_IOU) at that L.")
dec = {(r["family"], r["policy"], r["cell"]): r for r in base["H4"]}
for fam, filt in [(f"H4 E1 k={k}", (lambda r, k=k: r["exp"] == "E1" and r["k"] == k and r["Li"] <= 5000000)) for k in ("1", "2", "3")] + \
                 [("H4 E2 k=3", lambda r: r["exp"] == "E2")]:
    fam_recs = []
    for X in ("FQC", "CAKE"):
        g = C.paired(idx, filt, ("LXR", X), C.IOU("LLQ"))
        for blk, v in g.items():
            d = np.array([x[1] - x[2] for x in v]); L = v[0][3]["Li"]; corr = floor[("LXR", L)] - floor[("IOU", L)]; dc = d - corr
            t = S.tost_paired(d, -C.EMI(L), C.EMI(L)); tc = S.tost_paired(dc, -C.EMI(L), C.EMI(L))
            fam_recs.append(dict(family=fam, policy=X, cell=C.lab(v[0][3]), L=L, n=len(d), mean_d=t["mean"], ci90=t["ci90"], margin=C.EMI(L),
                                 floor_LXR=floor[("LXR", L)], floor_IOU=floor[("IOU", L)], mean_d_floorcorr=tc["mean"], ci90_floorcorr=tc["ci90"],
                                 p_tost=t["p"], p_tost_floorcorr=tc["p"]))
    for key, pk in (("decision", "p_tost"), ("decision_floorcorr", "p_tost_floorcorr")):
        for r, a in zip(fam_recs, S.holm([r[pk] for r in fam_recs])):
            ci = r["ci90"] if key == "decision" else r["ci90_floorcorr"]
            r[key] = "equivalent" if a < 0.05 else ("better" if ci[1] < 0 else ("worse" if ci[0] > 0 else "inconclusive"))
    for r in fam_recs:
        assert (r["decision"] == "equivalent") == (dec[(r["family"], r["policy"], r["cell"])]["decision"] == "comparable")
    recs += sorted(fam_recs, key=lambda r: (r["policy"], r["L"], r["cell"]))
for r in recs:
    P(f"  {r['family']:9s} {r['policy']:4s} {r['cell']:34s} mean d {r['mean_d']:+8.2f} [90% {r['ci90'][0]:+.2f},{r['ci90'][1]:+.2f}] (margin {r['margin']}) -> {r['decision']:12s} | "
      f"floor-corrected {r['mean_d_floorcorr']:+8.2f} [{r['ci90_floorcorr'][0]:+.2f},{r['ci90_floorcorr'][1]:+.2f}] -> {r['decision_floorcorr']}")
from collections import Counter
P("  counts raw: " + str(dict(Counter((r["policy"], r["decision"]) for r in recs))))
P("  counts floor-corrected: " + str(dict(Counter((r["policy"], r["decision_floorcorr"]) for r in recs))))
with open(os.path.join(RES, "H4_direccion.csv"), "w", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=list(recs[0].keys())); w.writeheader(); w.writerows(recs)
open(os.path.join(RES, "CIERRE_55_H4.txt"), "w").write("\n".join(out) + "\n"); print("\n".join(out))
