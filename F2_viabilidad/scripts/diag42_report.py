"""Report of the diag42 bench diagnostic (not data) and the option the frozen rule gives.
Rule (fixed 13-10-2026 before any diag42 run): shaper error with Bc = R x 8 ms, IOU k = 1, 2 Mbit/s;
per policy, error = |mean over the 3 repetitions of shaper_err|.
  < 1 % in CBWFQ AND in LLQ -> option (i);  > 5 % in either -> option (ii);  otherwise -> the authors decide.
Be = Bc and c7200 are reported, not part of the rule.
usage: python3 diag42_report.py > ../../F4_campana/diag42/INFORME_DIAG42.txt"""
import glob, json, os, statistics as st
D = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "F4_campana", "diag42")
runs = {}
for d in glob.glob(f"{D}/DIAG42_*_r0[1-3]") + glob.glob(f"{D}/_invalid/DIAG42_*_a0"):
    if not os.path.exists(f"{d}/meta.json"):
        continue
    m = json.load(open(f"{d}/meta.json")); c = m["cell"]
    var = "bc8" if c.get("bc_ms") == 8 else ("beBc" if c.get("be_eq_bc") else "ref")
    runs.setdefault((c["platform"], c["policy"], var), []).append((m["rep"], m.get("shaper_err"), m.get("invalid_reasons")))
print("variant                     reps  shaper error per rep (%)            mean (%)")
mean = {}
for k in sorted(runs):
    v = sorted(runs[k]); e = [x[1] for x in v if x[1] is not None]
    mean[k] = st.mean(e) if e else None
    print(f"{k[0]:5s} {k[1]:5s} {k[2]:5s}      {len(v)}   {[round(100 * x, 2) for x in e]}   {100 * mean[k]:+.2f}" if e else f"{k} no data")
    for r, _, why in v:
        other = [w for w in (why or []) if not w.startswith("shaper rate")]
        if other:
            print(f"      rep {r}: other invalidity reasons: {other}")
b = {p: mean.get(("IOU", p, "bc8")) for p in ("CBWFQ", "LLQ")}
if None in b.values():
    print("\nRULE: incomplete data for Bc = R x 8 ms -> the authors decide")
else:
    a = {p: abs(v) for p, v in b.items()}
    opt = "(i)" if all(x < 0.01 for x in a.values()) else ("(ii)" if any(x > 0.05 for x in a.values()) else "the authors decide (between 1 and 5 %)")
    print(f"\nRULE: |error| with Bc = R x 8 ms: CBWFQ {100 * a['CBWFQ']:.2f} %, LLQ {100 * a['LLQ']:.2f} % -> {opt}")
print("The authors confirm before any run of the deferred IOU k = 1 cells at 2 and 3 Mbit/s.")
