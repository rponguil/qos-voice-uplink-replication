"""Build the per-run table used by the analysis (analysis plan v2 §1), recomputed from the raw files.
Output: results/runs.csv (one row per valid run in campaign/state.json, all 4304; column 'main' = in the main analysis).
usage: python3 load_runs.py"""
import csv, json, os, sys
from concurrent.futures import ProcessPoolExecutor
HERE = os.path.dirname(os.path.abspath(__file__))
CAMP = os.path.join(HERE, "..", "..", "F4_campana", "campaign")
sys.path.insert(0, os.path.join(HERE, "..", "..", "F2_viabilidad", "scripts"))
W = 20.0


def pct(d, p):
    return d[min(len(d) - 1, int(round(p * (len(d) - 1))))] if d else None


def voice(run_dir, dur, w0=None, w1=None):
    """Flow 100 (probe index 0): delays of packets SENT in [W, W + D) from the first send of the flow
    (w0/w1 override the window, for the pilot reproduction)."""
    snd = list(csv.DictReader(open(f"{run_dir}/send_0.csv")))
    rcv = {r["seq"]: r for r in csv.DictReader(open(f"{run_dir}/recv_0.csv"))}
    t0 = min(int(r["send_ns"]) for r in snd)
    a = W if w0 is None else w0; b = dur if w1 is None else w1
    win = [r for r in snd if a * 1e9 <= int(r["send_ns"]) - t0 < b * 1e9]
    got = sorted((int(rcv[r["seq"]]["recv_ns"]) - int(rcv[r["seq"]]["send_ns"])) / 1e6 for r in win if r["seq"] in rcv)
    J, prev = 0.0, None   # RFC 3550 jitter over received packets of the window, by sequence number
    for r in sorted((rcv[r["seq"]] for r in win if r["seq"] in rcv), key=lambda x: int(x["seq"])):
        tr = (int(r["recv_ns"]) - int(r["send_ns"])) / 1e6
        if prev is not None:
            J += (abs(tr - prev) - J) / 16
        prev = tr
    return {"n_sent_w": len(win), "n_recv_w": len(got), "loss_w": (1 - len(got) / len(win)) if win else None,
            "p50": pct(got, .5), "p95": pct(got, .95), "p99": pct(got, .99), "min": got[0] if got else None,
            "max": got[-1] if got else None, "jitter": J if got else None}


def row(rid):
    d = os.path.join(CAMP, rid)
    m = json.load(open(f"{d}/meta.json")); s = json.load(open(f"{d}/summary.json")); c = m["cell"]
    r = {"run": rid, "cell": c["id"], "exp": c["exp"], "platform": c["platform"], "policy": c["policy"], "L": c["L"],
         "k": c["k"], "m": c["m"], "calls": c["calls"], "frame": c["frame"], "marked": c["marked"], "floor": c["floor"],
         "Q": c["Q"], "r_frac": c["r_frac"], "be_eq_bc": c["be_eq_bc"], "htb_burst": c.get("htb_burst"),
         "cs1_data": c["cs1_data"], "host_load": c["host_load"], "voice_over": c.get("voice_over"),
         "positive": c["positive"], "custom": (c.get("custom") or {}).get("name"), "dur": c["dur"],
         "rep": m["rep"], "ac": rid.endswith("_ac"), "t_start": m["t_start"], "R": m["R"],
         "block": (c["id"].replace(f"_{c['platform']}_{c['policy']}_", "_") if not c["floor"] else c["id"]),
         "marcada": m.get("marcada"), "tcp_hambre": ";".join(m.get("tcp_hambre") or []),
         "shaper_rate_bps": m.get("shaper_rate_bps"), "shaper_err": m.get("shaper_err"),
         "shaper_exempt": m.get("shaper_exempt"), "summary_p99": (s.get("probe0") or {}).get("p99"),
         "capture_p99": (m.get("voice_owd_capture_path") or {}).get("p99"), "load1": m.get("load1"),
         "ac_online": ";".join((m.get("host_power") or {}).get("ac_online") or [])}
    probe_is_voice = m["flows"][0].get("port", 0) < 5100   # Q004: probe 0 is video
    r["probe0_kind"] = "voice" if probe_is_voice else "video"
    r.update(voice(d, c["dur"]))
    for i, fl in enumerate(m["flows"]):   # TCP goodput by role (port)
        if fl["kind"] == "tcp":
            role = {5302: "data", 5301: "res"}.get(fl["port"], f"tcp{fl['port']}")
            v = s.get(f"tcp{i}", {})
            r[f"gp_{role}"] = v.get("rx_bps_steady"); r[f"hambre_{role}"] = bool(v.get("tcp_hambre"))
    return r


if __name__ == "__main__":
    st = json.load(open(os.path.join(CAMP, "state.json")))
    bat = set(json.load(open(os.path.join(CAMP, "battery_runs_20261014.json")))["runs"])
    with ProcessPoolExecutor(8) as ex:
        rows = list(ex.map(row, st["done"], chunksize=20))
    for r in rows:
        r["battery_original"] = r["run"] in bat
        r["main"] = not r["battery_original"]
        r["session"] = 1 if (r["rep"] <= 9 if not r["floor"] else r["rep"] <= 10) else 2
    keys = sorted({k for r in rows for k in r})
    os.makedirs(os.path.join(HERE, "..", "results"), exist_ok=True)
    with open(os.path.join(HERE, "..", "results", "runs.csv"), "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=keys); w.writeheader(); w.writerows(rows)
    print("rows", len(rows), "main", sum(r["main"] for r in rows))
