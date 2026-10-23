"""Analysis plan v2 §3: data audit (no policy contrasts). Output: results/AUDITORIA.txt + results/inclusion_por_celda.csv"""
import csv, os, statistics as st
from collections import defaultdict
HERE = os.path.dirname(os.path.abspath(__file__)); RES = os.path.join(HERE, "..", "results")
rows = list(csv.DictReader(open(os.path.join(RES, "runs.csv"))))
B = lambda x: x == "True"
F = lambda x: float(x) if x not in ("", "None") else None
main = [r for r in rows if B(r["main"])]
out = []; P = out.append; stop = []
P(f"runs total {len(rows)}; main {len(main)}; battery originals {sum(B(r['battery_original']) for r in rows)}; _ac {sum(B(r['ac']) for r in rows)}")
# 1. inclusion per cell
cells = defaultdict(list)
for r in main:
    cells[r["cell"]].append(r)
with open(os.path.join(RES, "inclusion_por_celda.csv"), "w", newline="") as fh:
    w = csv.writer(fh); w.writerow(["cell", "n", "reps", "marcadas", "exentas", "ac", "tcp_hambre_runs"])
    for c, v in sorted(cells.items()):
        reps = sorted(int(r["rep"]) for r in v)
        w.writerow([c, len(v), f"{reps[0]}-{reps[-1]}", sum(B(r["marcada"]) for r in v), sum(B(r["shaper_exempt"]) for r in v),
                    sum(B(r["ac"]) for r in v), sum(1 for r in v if r["tcp_hambre"])])
        exp_n = 20 if B(v[0]["floor"]) else 17
        if len(v) != exp_n or len(set(reps)) != exp_n:
            stop.append(f"cell {c}: n={len(v)} reps={reps}")
P(f"cells {len(cells)} (floors {sum(B(v[0]['floor']) for v in cells.values())}); all complete: {not stop}")
P(f"marcadas (main) {sum(B(r['marcada']) for r in main)}; exentas {sum(B(r['shaper_exempt']) for r in main)}; runs with tcp_hambre {sum(1 for r in main if r['tcp_hambre'])}")
# 2. non-null / min / max per variable
P("\nvariable            non-null/total     min          max")
for var in ("p99", "p95", "p50", "min", "max", "loss_w", "jitter", "n_sent_w", "n_recv_w", "gp_data", "gp_res",
            "shaper_rate_bps", "shaper_err", "summary_p99", "capture_p99", "load1"):
    vals = [F(r.get(var, "")) for r in main]; nn = [x for x in vals if x is not None]
    zeros = sum(1 for x in nn if x == 0)
    P(f"{var:18s} {len(nn):5d}/{len(main):5d}   {min(nn) if nn else None!s:>12.12} {max(nn) if nn else None!s:>12.12}   zeros {zeros}")
    if nn and zeros == len(nn):
        stop.append(f"variable {var}: all zero")
# expected nulls
P("  expected: gp_data only k=3/E4d-Q034; gp_res k>=1 & Q004; shaper_* only saturated cells (k>=1, not CPOS/E4d); capture_p99 not for Q004")
nulls = defaultdict(int)
for r in main:
    if F(r["p99"]) is None: nulls["p99"] += 1
    if not B(r["floor"]) and int(r["k"]) >= 1 and not B(r["positive"]) and not r["custom"] and F(r["shaper_err"]) is None: nulls["shaper_err(expected present)"] += 1
    if int(r["k"]) == 3 and not r["custom"] and F(r.get("gp_data", "")) is None: nulls["gp_data(k=3)"] += 1
    if int(r["k"]) >= 1 and not r["custom"] and not B(r["positive"]) and F(r.get("gp_res", "")) is None: nulls["gp_res(k>=1)"] += 1
    if r["probe0_kind"] == "voice" and F(r["capture_p99"]) is None: nulls["capture_p99(voice runs)"] += 1
P(f"  unexpected nulls: {dict(nulls) or 'none'}")
if nulls: stop.append(f"unexpected nulls {dict(nulls)}")
# 3. physical checks
floor_med = {}
for c, v in cells.items():
    if B(v[0]["floor"]):
        p = sorted(F(r["p99"]) for r in v); floor_med[(v[0]["platform"], v[0]["L"])] = (st.median(p), p[-1] - p[0])
bad = defaultdict(list)
for r in main:
    p99 = F(r["p99"]); L = r["L"]
    if r["policy"] == "LLQ" and r["platform"] == "IOU" and r["probe0_kind"] == "voice" and not r["custom"]:
        fm, amp = floor_med[("IOU", L)]
        if p99 < fm - amp: bad["LLQ p99 below IOU floor-median minus amplitude"].append((r["run"], p99, round(fm, 3)))
        if r["voice_over"] in ("", "None") and B(r["marked"]) and F(r["loss_w"]) > 0.001: bad["LLQ voice loss > 0.1 % (voice within reservation, marked)"].append((r["run"], r["loss_w"]))
    if F(r["shaper_rate_bps"]) is not None and F(r["shaper_rate_bps"]) > 1.05 * F(r["R"]): bad["shaper rate > 1.05 R"].append((r["run"], r["shaper_rate_bps"]))
    if F(r["min"]) is not None and F(r["min"]) < 0: bad["negative delay"].append(r["run"])
    if int(r["n_recv_w"]) > int(r["n_sent_w"]): bad["received > sent"].append(r["run"])
P("\nphysical checks:")
for k_, v in bad.items():
    P(f"  {k_}: {len(v)}  e.g. {v[:4]}")
if not bad: P("  all pass")
# 4. p99 recomputed vs summary and vs capture path
d_sum = [(abs(F(r["p99"]) - F(r["summary_p99"])), r["run"]) for r in main if F(r["summary_p99"]) is not None and F(r["p99"]) is not None]
d_cap = [(abs(F(r["p99"]) - F(r["capture_p99"])), r["run"]) for r in main if F(r["capture_p99"]) is not None]
over_s = [x for x in d_sum if x[0] > 0.001]; over_c = [x for x in d_cap if x[0] > 0.1]
P(f"\np99 recomputed vs summary: n {len(d_sum)}, max diff {max(d_sum)[0]:.6f} ms, > 1 us: {len(over_s)} {sorted(over_s, reverse=True)[:5]}")
P(f"p99 recomputed vs capture path: n {len(d_cap)}, max diff {max(d_cap)[0]:.4f} ms, > 0.1 ms: {len(over_c)} {sorted(over_c, reverse=True)[:5]}")
P(f"floors (median p99, amplitude) ms: " + "; ".join(f"{p} {L/1e6 if False else int(L)//1000}k {m:.2f} ({a:.2f})" for (p, L), (m, a) in sorted(floor_med.items(), key=lambda x: (x[0][0], int(x[0][1])))))
P("\nSTOP REASONS: " + ("; ".join(stop) if stop else "none"))
open(os.path.join(RES, "AUDITORIA.txt"), "w").write("\n".join(out) + "\n")
print("\n".join(out))
