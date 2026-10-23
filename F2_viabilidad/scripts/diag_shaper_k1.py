"""Offline (no bench): IOU k = 1 shaper deficit at 2 and 3 Mbit/s.
For the invalid attempts (campaign/_invalid) and comparable valid runs (campaign/): per-second L2 rate at SINK,
router output (policy-map bytes) vs SINK, inter-arrival gaps of 1514-B frames, 1514-B frame size / Bc.
usage: python3 diag_shaper_k1.py > ../../F4_campana/DIAG_SHAPER_K1.txt"""
import glob, json, os, re, subprocess, statistics as st
from collections import Counter
D = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "F4_campana", "campaign")


def sink_events(d):
    out = subprocess.run(["tcpdump", "-tt", "-nn", "-e", "-r", f"{d}/sink.pcap", "dst host 203.0.113.2"],
                         capture_output=True, text=True).stdout
    ev = []
    for l in out.splitlines():
        m = re.match(r"(\d+\.\d+) .*?length (\d+):", l)
        if m:
            ev.append((float(m.group(1)), int(m.group(2))))
    return ev


def router_out(d):
    t = open(f"{d}/router_post.txt").read()
    m = re.search(r"Service-policy output: PARENT.*?\(pkts output/bytes output\) (\d+)/(\d+)", t, re.S)
    return (int(m.group(1)), int(m.group(2))) if m else (None, None)


def analyse(d):
    m = json.load(open(f"{d}/meta.json")); c = m["cell"]; R = m["R"]; L = c["L"]
    ev = sink_events(d)
    t0 = ev[0][0]; dur = c["dur"]
    secs = Counter()
    for t, b in ev:
        if 10 <= t - t0 < dur - 2:
            secs[int(t - t0)] += b * 8
    rates = [secs[s] for s in range(10, int(dur - 2))]
    big = [t for t, b in ev if b >= 1514 and 10 <= t - t0 < dur - 2]
    gaps = [(b - a) * 1000 for a, b in zip(big, big[1:])]
    ser = 1514 * 8 / L * 1000            # serialisation of a 1514-B frame on the line (ms)
    rp, rb = router_out(d)
    sink_l3 = sum(b - 14 for t, b in ev)   # L2 length minus Ethernet header ~ router IP bytes
    bc = R * 0.004
    return dict(id=os.path.basename(d), pol=c["policy"], L=L, k=c["k"], marked=c["marked"], R=R,
                frame_over_bc=round(1514 * 8 / bc, 2), err=m.get("shaper_err") if m.get("shaper_err") is not None else None,
                mean=st.mean(rates) / R - 1, cv=st.pstdev(rates) / st.mean(rates), lo=min(rates) / R - 1, hi=max(rates) / R - 1,
                frac_lt95=sum(r < 0.95 * R for r in rates) / len(rates),
                router_vs_sink=(rb / sink_l3 - 1) if rb and sink_l3 else None,
                share1514=sum(b >= 1514 for t, b in ev) * 1514 / max(1, sum(b for t, b in ev)),
                gap_med=st.median(gaps) if gaps else None, ser=ser,
                gap_hist=Counter(round(g / 4) * 4 for g in gaps).most_common(4))


rows = []
for d in sorted(glob.glob(f"{D}/_invalid/*_IOU_*_k1_*_a[0-9]")) + sorted(glob.glob(f"{D}/*_IOU_*_k[13]_*_r0[1-2]")):
    if not os.path.exists(f"{d}/meta.json"):
        continue
    c = json.load(open(f"{d}/meta.json"))["cell"]
    if c["exp"] not in ("E1", "CNEG") or c["policy"] not in ("CBWFQ", "LLQ", "FIFO"):
        continue
    if c["k"] == 3 and c["L"] not in (2000000, 3000000):
        continue
    try:
        rows.append(analyse(d))
    except Exception as e:
        print("skip", d, e)
print(f"{'run':62s} {'L':>4} k {'F/Bc':>5} {'mean':>6} {'CV':>5} {'min':>6} {'max':>6} {'<95%':>5} {'rt/snk':>6} {'B1514':>5} gaps 1514-B (ms, mode)")
for r in sorted(rows, key=lambda r: (r["k"], r["L"], r["pol"], r["id"])):
    print(f"{r['id'][:62]:62s} {r['L']/1e6:4.1f} {r['k']} {r['frame_over_bc']:5.2f} {100*r['mean']:+6.1f} {r['cv']:5.3f} {100*r['lo']:+6.1f} "
          f"{100*r['hi']:+6.1f} {r['frac_lt95']:5.2f} {100*(r['router_vs_sink'] or 0):+6.2f} {r['share1514']:5.2f} ser {r['ser']:.2f} {r['gap_hist']}")
print("\nSummary by (k, L, policy): mean deficit % [min, max] over runs")
g = {}
for r in rows:
    g.setdefault((r["k"], r["L"], r["pol"], r["marked"]), []).append(100 * r["mean"])
for k_ in sorted(g):
    v = g[k_]
    print(f"  k={k_[0]} L={k_[1]/1e6:.1f} {k_[2]:5s} {'marked' if k_[3] else 'unmarked'}: n={len(v):2d} mean {st.mean(v):+.1f} [{min(v):+.1f}, {max(v):+.1f}]")
