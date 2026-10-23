"""Pilot / campaign executor for PROTOCOLO_v3.1 (frozen P3a, SHA-256 c84b7f58...e2f8f).

Resumable run by run: state in <out>/state.json; a run that fails an automatic invalidity
criterion is moved to <out>/_invalid/ with its reason and repeated (max 2 retries).
Ends with the sentinel line CAMPAIGN_DONE.

usage: python3 -u campaign.py pilot  [--seed 20261010]
"""
import argparse, glob, hashlib, json, math, os, random, re, subprocess, sys, time, traceback
from collections import defaultdict
sys.path.insert(0, os.path.dirname(__file__))
import f2lib as f, runner

HERE = os.path.dirname(os.path.abspath(__file__))
VOICE_KBPS = 85.6                     # G.711 + RTP at L2, per call
PORT_VOICE, PORT_VIDEO, PORT_RES_UDP = 5001, 5101, 5201
PORT_RES_TCP, PORT_DATA_TCP = 5301, 5302
MAX_RETRY = 2
P3B = {"modem_queue_B": 6840, "host_load": 1.70}   # §40/§41 values from the repeated pilot
P3B_ACTIVE = False                                 # switched on in campaign modes
RETIRED = ("E4b_C7200_CBWFQ_L5000k", "E4b_C7200_LLQ_L5000k", "FLOOR_C7200_FIFO_L5000k")   # §42.2: c7200 only at 1 Mbit/s
C72_SEED = 20261015                   # §42.2: c7200 reps 1-9 as their own randomized block at the end of session 1
C72_IDLE = {"delta": None}            # Dynamips idle load, measured at the start of every session with c7200 runs (§42.2)
SHAPER_EXEMPT = tuple(f"{e}_IOU_{p}_L{L}k_k1_" for L in (2000, 3000)    # §50: option (i), IOU k = 1 at 2 and 3 Mbit/s:
                      for e, ps in (("E1", ("CBWFQ", "LLQ", "FIFO")), ("CNEG", ("CBWFQ", "LLQ"))) for p in ps)   # exempt from the shaper-rate criterion only
K1_SEED = 20261018                    # §50.3: seed of their reps 1-9 block (mode campaign1k)
RUN_SUFFIX = ""                        # "_ac" for the §47.2 repeats of the runs made on battery
BAT_SEED = 20261017                   # §47.2: seed of the randomized block of those repeats
C72_LAST_STOP = [0.0]                 # time of the last C7200 stop (see c7200_power)
PRERUN = {}         # seconds spent before the run (C7200 stop / cool-down / C7200 boot), stored in meta.json
COOL_LOAD = 0.8     # before each run, wait (max 10 min) until the 1-min load is back to pilot level (median 0.36, max 0.92)


def c7200_power(on):
    """C7200 (Dynamips without idle-PC) keeps ~1 core busy, and it was stopped in the pilot: it runs only during
    C7200 runs, so every other run keeps the pilot bench. Its base config is in NVRAM. Returns seconds spent."""
    import gns3api as g
    pid = g.project("QoS_F2_viabilidad")["project_id"]; n = g.nodes(pid)["C7200"]
    if (n["status"] == "started") == on:
        return 0.0
    t0 = time.time()
    f._con.pop("C7200", None)
    if not on:
        g.post(f"/projects/{pid}/nodes/{n['node_id']}/stop"); C72_LAST_STOP[0] = time.time()
        return time.time() - t0
    # 14-10: started right after a stop, Dynamips leaves the console unbound and the router never answers.
    # Keep >= 15 s between stop and start; if no prompt in 120 s, stop, wait and start again (3 tries).
    for attempt in range(3):
        time.sleep(max(0.0, 15 - (time.time() - C72_LAST_STOP[0])))
        g.post(f"/projects/{pid}/nodes/{n['node_id']}/start"); t1 = time.time()
        while time.time() - t1 < 120:
            try:
                c = g.Console(f.CONSOLE["C7200"]); o = c.wake(); c.close()
                if re.search(r"C7200[>#]", o):
                    return time.time() - t0
            except OSError:
                pass
            time.sleep(5)
        g.post(f"/projects/{pid}/nodes/{n['node_id']}/stop"); C72_LAST_STOP[0] = time.time()
        print(f"    C7200 gave no prompt in 120 s (try {attempt + 1}); stopped, retrying", flush=True)
    raise RuntimeError("C7200 did not boot after 3 tries")


def c7200_is_on():
    import gns3api as g
    pid = g.project("QoS_F2_viabilidad")["project_id"]
    return g.nodes(pid)["C7200"]["status"] == "started"


def measure_c72_idle(out_root, mode):
    """§42.2: load added by Dynamips at rest = 1-min load with C7200 booted and idle (240 s) minus with it stopped."""
    c7200_power(False); cool_down()
    off = os.getloadavg()[0]
    c7200_power(True); time.sleep(240)
    on = os.getloadavg()[0]
    C72_IDLE["delta"] = max(0.0, on - off)
    rec = {"t": time.strftime("%F %T"), "mode": mode, "load_off": round(off, 3), "load_on_idle_240s": round(on, 3),
           "delta": round(C72_IDLE["delta"], 3), "threshold_c7200": round(P3B["host_load"] + C72_IDLE["delta"], 3)}
    json.dump(rec, open(os.path.join(out_root, f"c7200_idle_load_{mode}_{time.strftime('%Y%m%d%H%M%S')}.json"), "w"), indent=1)
    print(f"C7200 idle load: {rec}", flush=True)


def ac_online():
    """§47.1: mains power present (no adapter file -> desktop, treated as on mains)."""
    v = [open(x).read().strip() for x in glob.glob("/sys/class/power_supply/ADP*/online")]
    return all(x == "1" for x in v)


def power_ok():
    gov = open("/sys/devices/system/cpu/cpu0/cpufreq/scaling_governor").read().strip()
    idle = [open(f"/sys/devices/system/cpu/cpu0/cpuidle/state{i}/disable").read().strip() for i in (2, 3)]
    return gov == "performance" and idle == ["1", "1"] and ac_online()


def wait_power():
    """12-10: power-profiles-daemon put the governor back to powersave mid-session and every run was invalidated.
    Now the session waits (no run burnt) and asks PPD for 'performance' (no root needed); C-states need host_perf.sh."""
    t0 = time.time(); said = False
    while not power_ok():
        if not said:
            print(f"PAUSED {time.strftime('%F %T')}: host power state not performance or no mains power (ac_online={ac_online()}); waiting", flush=True); said = True
        subprocess.run(["powerprofilesctl", "set", "performance"], capture_output=True)
        time.sleep(30)
    if said:
        print(f"RESUMED {time.strftime('%F %T')} after {time.time() - t0:.0f} s", flush=True)


def cool_down(limit=600):
    t0 = time.time()
    while os.getloadavg()[0] >= COOL_LOAD and time.time() - t0 < limit:
        time.sleep(5)
    return time.time() - t0


# ---------------------------------------------------------------- cells
def cell(exp, platform, policy, L, k, m=0.2, calls=1, frame=1514, marked=True, floor=False, Q=64, reps=5, dur=40,
         r_frac=0.95, be_eq_bc=False, htb_burst=None, cs1_data=False, host_load=False, voice_over=None, positive=False,
         custom=None):
    d = dict(exp=exp, platform=platform, policy=policy, L=L, k=k, m=m, calls=calls, frame=frame, marked=marked,
             floor=floor, Q=Q, reps=reps, dur=dur, r_frac=r_frac, be_eq_bc=be_eq_bc, htb_burst=htb_burst,
             cs1_data=cs1_data, host_load=host_load, voice_over=voice_over, positive=positive, custom=custom)
    tag = "".join([f"_Q{Q}" if Q != 64 else "", f"_r{r_frac}" if r_frac != 0.95 else "", "_beBc" if be_eq_bc else "",
                   f"_htb{htb_burst}" if htb_burst else "", "_cs1" if cs1_data else "", "_load" if host_load else "",
                   f"_vx{voice_over}" if voice_over else "", "_pos" if positive else "",
                   f"_d{dur}" if exp == "S" and dur != CAMPAIGN_DUR else "", f"_{custom['name']}" if custom else ""])
    d["id"] = (f"{exp}_{platform}_{policy}_L{L//1000}k_k{k}_m{m}_c{calls}_f{frame}"
               f"{'' if marked else '_unmarked'}{'_floor' if floor else ''}{tag}")
    return d


def smoke_cells():
    """One short run per cell type, to test the executor end to end (not data)."""
    return [cell("E1", "IOU", "LLQ", 1000000, 3, reps=1, dur=20), cell("E1", "IOU", "CBWFQ", 500000, 1, reps=1, dur=20),
            cell("E1", "LXR", "FQC", 1000000, 3, reps=1, dur=20), cell("E1", "LXR", "CAKE", 1000000, 3, reps=1, dur=20),
            cell("CNEG", "IOU", "FIFO", 1000000, 3, marked=False, reps=1, dur=20),
            cell("FLOOR", "LXR", "FIFO", 2000000, 0, floor=True, reps=1, dur=20)]


CISCO_L = (500000, 1000000, 2000000, 3000000, 5000000)        # §34.1-2: Cisco arms up to 5 Mbit/s, 3 Mbit/s added
LINUX_L = CISCO_L + (10000000,)


def pilot_cells():
    """Repeated pilot (§32.2-3, §34): protocol §10 cells + CBWFQ/LLQ with k = 3 at every Cisco capacity.
    Competition runs 120 s (duration rule); floors 40 s, 10 runs, per platform and capacity."""
    C = []
    for L in CISCO_L:
        for pol in ("CBWFQ", "LLQ"):
            C.append(cell("E1", "IOU", pol, L, 3, dur=120))
    for L in (500000, 1000000, 5000000):
        for pol in ("CBWFQ", "LLQ"):
            C.append(cell("E1", "IOU", pol, L, 1, dur=120))
    for pol in ("FQC", "CAKE"):
        C.append(cell("E1", "LXR", pol, 1000000, 3, dur=120))
    for pol in ("CBWFQ", "LLQ"):
        C.append(cell("E1R", "IOU", pol, 1000000, 3, m=3, dur=120))
    for pol in ("CBWFQ", "LLQ", "FIFO"):
        C.append(cell("CNEG", "IOU", pol, 1000000, 3, marked=False, dur=120))
    for L in CISCO_L:
        C.append(cell("FLOOR", "IOU", "FIFO", L, 0, floor=True, reps=10, dur=40))
    for L in LINUX_L:
        C.append(cell("FLOOR", "LXR", "FIFO", L, 0, floor=True, reps=10, dur=40))
    return C


# ---------------------------------------------------------------- campaign (P3b: W = 20 s, n = 17; §§34, 36, 40, 41)
W_WARMUP = 20                          # §40.1 rule applied to the pilot (approved by Ronald, 11-10-2026)
N_REPS = 17                            # §40.3 rule applied to the pilot
CAMPAIGN_DUR = W_WARMUP + 40           # 40-s measurement after the warm-up
SESSION_REPS = {1: range(1, 10), 2: range(10, 18)}   # two sessions on different days
FLOOR_REPS = 10                        # per platform and capacity, in every session


def feasible(c):
    if c["exp"] == "E2" and c["L"] == 500000 and c["calls"] == 4:   # protocol §6: excluded for every policy
        return False
    if c["platform"] == "LXR" or c["policy"] not in ("CBWFQ", "LLQ") or c.get("custom"):
        return True
    R = c["r_frac"] * c["L"]
    return c["calls"] * VOICE_KBPS * (1 + c["m"]) + 0.45 * R / 1000 <= 0.99 * R / 1000


def campaign_cells():
    D = CAMPAIGN_DUR; n = N_REPS; C = []
    add = lambda *a, **k: C.append(cell(*a, reps=n, dur=k.pop("dur", D), **k))
    # E1 (H1, H2, H4): k = 1 and 3, all policies; k = 2 for CBWFQ, LLQ, FQC, CAKE
    for k in (1, 3):
        for L in CISCO_L:
            for pol in ("FIFO", "CBWFQ", "LLQ"):
                add("E1", "IOU", pol, L, k)
        for L in LINUX_L:
            for pol in ("FIFO", "FQC", "CAKE"):
                add("E1", "LXR", pol, L, k)
    for L in CISCO_L:
        for pol in ("CBWFQ", "LLQ"):
            add("E1", "IOU", pol, L, 2)
    for L in LINUX_L:
        for pol in ("FQC", "CAKE"):
            add("E1", "LXR", pol, L, 2)
    # E1-R (H3): m in {0.5, 1, 3}, k = 3
    for L in CISCO_L:
        for m_ in (0.5, 1, 3):
            for pol in ("CBWFQ", "LLQ"):
                add("E1R", "IOU", pol, L, 3, m=m_)
    # E2: frame {590, 1514} x calls {1, 4} x L {0.5, 1, 5}, k = 3
    for L in (500000, 1000000, 5000000):
        for fr in (590, 1514):
            for ca in (1, 4):
                for pol, plat in (("CBWFQ", "IOU"), ("LLQ", "IOU"), ("FQC", "LXR"), ("CAKE", "LXR")):
                    add("E2", plat, pol, L, 3, frame=fr, calls=ca)
    # E3 (H5): voice inside the reservation / at 1.5 x B_v, k = 3
    for L in (1000000, 5000000):
        for vo in (None, 1.5):
            for pol in ("CBWFQ", "LLQ"):
                add("E3", "IOU", pol, L, 3, voice_over=vo)
    # E4(b) with c7200 (§40.7): L {1, 5} x k {1, 3} x {CBWFQ, LLQ}
    for L in (1000000, 5000000):
        for k in (1, 3):
            for pol in ("CBWFQ", "LLQ"):
                add("E4b", "C7200", pol, L, k)
    # E4(d): published hardware scenarios (Q004: 384 kbit/s, video + FTP; Q034: shaper 480 kbit/s, voice 190 + FTP 150)
    for pol in ("FIFO", "CBWFQ", "LLQ"):
        add("E4d", "IOU", pol, 384000, 0, custom={"name": "Q004"})
        add("E4d", "IOU", pol, 500000, 0, custom={"name": "Q034"})
    # S (sensitivity): L {1, 5}, k = 3, CBWFQ/LLQ: Q {16, 256}, shaper 0.90, Be = Bc, 120-s measurement
    for L in (1000000, 5000000):
        for pol in ("CBWFQ", "LLQ"):
            add("S", "IOU", pol, L, 3, Q=16); add("S", "IOU", pol, L, 3, Q=256)
            add("S", "IOU", pol, L, 3, r_frac=0.90); add("S", "IOU", pol, L, 3, be_eq_bc=True)
            add("S", "IOU", pol, L, 3, dur=W_WARMUP + 120)
    for L in (5000000, 10000000):
        add("S", "LXR", "FQC", L, 3, htb_burst="Bc")
    for L in (1000000, 5000000):
        add("S", "LXR", "CAKE", L, 3, cs1_data=True)
    # S-H: host loaded (10 of 12 cores), no load criterion
    for L in (1000000, 5000000):
        for pol in ("CBWFQ", "LLQ"):
            add("SH", "IOU", pol, L, 3, host_load=True)
    # C: negative control (unmarked) CBWFQ/LLQ, k {1, 3}; positive control (0.5 R offered) FIFO-C and FIFO-L
    for L in CISCO_L:
        for k in (1, 3):
            for pol in ("CBWFQ", "LLQ"):
                add("CNEG", "IOU", pol, L, k, marked=False)
        add("CPOS", "IOU", "FIFO", L, 1, positive=True)
    for L in LINUX_L:
        add("CPOS", "LXR", "FIFO", L, 1, positive=True)
    for c in C:
        c["warmup"] = W_WARMUP
    excluded = [c for c in C if not feasible(c)]
    C = [c for c in C if feasible(c)]
    return C, excluded


def campaign_floor_cells():
    D = CAMPAIGN_DUR
    F = [cell("FLOOR", "IOU", "FIFO", L, 0, floor=True, reps=FLOOR_REPS, dur=D) for L in CISCO_L]
    F += [cell("FLOOR", "LXR", "FIFO", L, 0, floor=True, reps=FLOOR_REPS, dur=D) for L in LINUX_L]
    F += [cell("FLOOR", "C7200", "FIFO", L, 0, floor=True, reps=FLOOR_REPS, dur=D) for L in (1000000, 5000000)]
    for c in F:
        c["warmup"] = W_WARMUP
    return F


# ---------------------------------------------------------------- traffic and policies
def flows_for(c):
    L = c["L"]; dscp = (lambda d: d if c["marked"] else 0)
    if c.get("custom"):
        return custom_flows(c)
    if c.get("positive"):          # positive control: no congestion, offered load 0.5 R (voice + residential UDP)
        R = c["r_frac"] * L
        return [{"kind": "probe", "node": "CW-VOZ", "port": PORT_VOICE, "dscp": dscp(46), "size": 172, "interval": 0.02, "flow": 100},
                {"kind": "probe", "node": "RES-1", "port": PORT_RES_UDP, "dscp": 0, "size": 1472,
                 "interval": round(1472 * 8 / (0.5 * R - VOICE_KBPS * 1000), 6), "flow": 4}]
    payload_res = c["frame"] - 42
    pr = lambda node, port, ds, size, bps, fl: {"kind": "probe", "node": node, "port": port, "dscp": ds, "size": size,
                                               "interval": round(size * 8 / bps, 6), "flow": fl}
    F = [{"kind": "probe", "node": "CW-VOZ", "port": PORT_VOICE + i, "dscp": dscp(46), "size": 172, "interval": 0.02,
          "flow": 100 + i} for i in range(c["calls"])]
    if c.get("voice_over"):        # E3: EF load at voice_over x B_v (measured call + EF filler of 172-B packets)
        Bv = c["calls"] * VOICE_KBPS * (1 + c["m"]) * 1000
        extra = c["voice_over"] * Bv - c["calls"] * VOICE_KBPS * 1000
        F.append({"kind": "probe", "node": "CW-VOZ", "port": PORT_VOICE + 9, "dscp": dscp(46), "size": 172,
                  "interval": round(214 * 8 / extra, 6), "flow": 109})
    if c["k"] >= 1:
        F.append(pr("RES-1", PORT_RES_UDP, 0, payload_res, 0.8 * L, 4))
        F.append({"kind": "tcp", "node": "RES-1", "port": PORT_RES_TCP, "dscp": 0, "streams": 1,
                  "mss": (payload_res - 12 if c["frame"] != 1514 else None)})
    if c["k"] >= 2:
        F.append(pr("CW-DAT", PORT_VIDEO, dscp(34), 1000, 0.6 * L, 2))
    if c["k"] >= 3:
        F.append({"kind": "tcp", "node": "CW-DAT", "port": PORT_DATA_TCP, "dscp": dscp(8 if c.get("cs1_data") else 18), "streams": 1,
                  "mss": (payload_res - 12 if c["frame"] != 1514 else None)})
    return F


def custom_flows(c):
    """E4(d) published hardware scenarios (reproduced in the bank; declared as approximations)."""
    name = c["custom"]["name"]
    if name == "Q004":     # 384 kbit/s, RTP video (mean 408 kbit/s) + FTP; video is the prioritised class
        return [{"kind": "probe", "node": "CW-DAT", "port": PORT_VIDEO, "dscp": 34, "size": 1000,
                 "interval": round(1042 * 8 / 408000, 6), "flow": 2},
                {"kind": "tcp", "node": "RES-1", "port": PORT_RES_TCP, "dscp": 0, "streams": 1, "mss": None}]
    if name == "Q034":     # shaper 480 kbit/s, voice priority 190 kbit/s (2 G.711 calls), FTP class 150 kbit/s
        return [{"kind": "probe", "node": "CW-VOZ", "port": PORT_VOICE + i, "dscp": 46, "size": 172, "interval": 0.02, "flow": 100 + i}
                for i in range(2)] + [{"kind": "tcp", "node": "CW-DAT", "port": PORT_DATA_TCP, "dscp": 18, "streams": 1, "mss": None}]
    raise ValueError(name)


def bc_bits(R, ms=4):
    """Bc = R x 4 ms, rounded up: IOS needs Tc >= 4 ms (int() gave 1459 < 1459.2 at R = 364.8 kbit/s, Q004)."""
    return math.ceil(round(R * ms / 1000, 6))


def custom_R(c):
    return {"Q004": int(0.95 * 384000), "Q034": 480000}[c["custom"]["name"]]


def ios_lines(c, R, iface):
    """Kbps reservations (§4); identical policy-map for every k; Bc = R x 4 ms, Be = 0 (§3)."""
    Bv = round(c["calls"] * VOICE_KBPS * (1 + c["m"])); Bvid = round(0.25 * R / 1000); Bdat = round(0.20 * R / 1000)
    if c.get("custom"):
        if c["custom"]["name"] == "Q004":   # Q004: priority 73 % of the line for video; FTP in class-default
            Bv, Bvid, Bdat = 1, round(0.73 * R / 1000), 1
        else:                              # Q034: voice 190, FTP 150, video class unused
            Bv, Bvid, Bdat = 190, 1, 150
    if Bv + Bvid + Bdat > 0.99 * R / 1000:
        raise ValueError(f"infeasible cell {c['id']}: reservation {Bv + Bvid + Bdat} kbps > 0.99 R")
    L = [f"interface {iface}", "no service-policy output PARENT", "exit", "no policy-map PARENT", "no policy-map CHILD",
         "class-map match-any CM-VOZ", "match ip dscp ef", "class-map match-any CM-VIDEO", "match ip dscp af41",
         "class-map match-any CM-DATOS", "match ip dscp af21"]
    pol = c["policy"]
    q004 = bool(c.get("custom")) and c["custom"]["name"] == "Q004"
    if pol in ("CBWFQ", "LLQ") and q004:   # the prioritised class is video (AF41)
        L += ["policy-map CHILD", "class CM-VIDEO", (f"priority {Bvid}" if pol == "LLQ" else f"bandwidth {Bvid}")]
        if pol == "CBWFQ":
            L += [f"queue-limit {c['Q']} packets"]
        L += ["class class-default", "fair-queue", f"queue-limit {c['Q']} packets", "exit"]
    elif pol in ("CBWFQ", "LLQ"):
        L += ["policy-map CHILD", "class CM-VOZ", (f"priority {Bv}" if pol == "LLQ" else f"bandwidth {Bv}")]
        if pol == "CBWFQ":
            L += [f"queue-limit {c['Q']} packets"]
        L += ["class CM-VIDEO", f"bandwidth {Bvid}", f"queue-limit {c['Q']} packets",
              "class CM-DATOS", f"bandwidth {Bdat}", f"queue-limit {c['Q']} packets",
              "class class-default", "fair-queue", f"queue-limit {c['Q']} packets", "exit"]
    L += ["policy-map PARENT", "class class-default",
          f"shape average {R} {bc_bits(R, c.get('bc_ms', 4))}" + ("" if c.get("be_eq_bc") else " 0")]   # S: Be = Bc (IOS default)
    L += ["service-policy CHILD"] if pol in ("CBWFQ", "LLQ") else [f"queue-limit {c['Q']} packets"]
    L += ["exit", "exit", f"interface {iface}", "service-policy output PARENT"]
    return L, {"B_v_kbps": Bv, "B_vid_kbps": Bvid, "B_dat_kbps": Bdat}


# ---------------------------------------------------------------- captures (second computation path)
def start_captures(c):
    f.dx("SINK", "pkill tcpdump; rm -f /tmp/sink.pcap", check=False)
    f.dx("CW-VOZ", "pkill tcpdump; rm -f /tmp/src.pcap", check=False)
    f.dbg("SINK", "tcpdump -i eth0 -s 96 -U -w /tmp/sink.pcap ip and not icmp 2>/dev/null")
    f.dbg("CW-VOZ", f"tcpdump -i eth0 -s 96 -U -w /tmp/src.pcap udp dst portrange {PORT_VOICE}-{PORT_VOICE + 9} 2>/dev/null")
    for n, port in (("RES-1", PORT_RES_TCP), ("CW-DAT", PORT_DATA_TCP)):
        f.dx(n, "pkill tcpdump; rm -f /tmp/tcp.pcap", check=False)
        f.dbg(n, f"tcpdump -i eth0 -s 96 -U -w /tmp/tcp.pcap tcp dst port {port} 2>/dev/null")
    time.sleep(1.0)


def stop_captures(out):
    for n in ("SINK", "CW-VOZ", "RES-1", "CW-DAT"):
        f.dx(n, "pkill -INT tcpdump", check=False)
    time.sleep(1.5)
    f.fetch("SINK", "/tmp/sink.pcap", f"{out}/sink.pcap")
    f.fetch("CW-VOZ", "/tmp/src.pcap", f"{out}/src_voice.pcap")
    for n in ("RES-1", "CW-DAT"):
        try:
            f.fetch(n, "/tmp/tcp.pcap", f"{out}/src_tcp_{n}.pcap")
        except subprocess.CalledProcessError:
            pass


def pcap_lines(path, flt=""):
    r = subprocess.run(["tcpdump", "-tt", "-nn", "-x", "-r", path] + ([flt] if flt else []),
                       capture_output=True, text=True)
    return r.stdout


def voice_owd_from_pcaps(out, warmup):
    """Independent path: parse seq/flow from the UDP payload hex dump at sender and SINK; OWD = t_sink - t_src."""
    def parse(path):
        res, cur_t, hexb = {}, None, []
        def flush():
            if cur_t is None or not hexb:
                return
            b = bytes.fromhex("".join(hexb))
            ihl = (b[0] & 0x0F) * 4
            pl = b[ihl + 8: ihl + 8 + 14]
            if len(pl) == 14:
                flow = int.from_bytes(pl[0:2], "big"); seq = int.from_bytes(pl[2:6], "big")
                res[(flow, seq)] = cur_t
        for line in pcap_lines(path, f"udp dst portrange {PORT_VOICE}-{PORT_VOICE + 9}").splitlines():
            if line and not line.startswith("\t"):
                flush(); hexb = []
                cur_t = float(line.split()[0])
            else:
                hexb += line.split(":", 1)[1].split()
        flush()
        return res
    s, r = parse(f"{out}/src_voice.pcap"), parse(f"{out}/sink.pcap")
    s = {k: v for k, v in s.items() if k[0] == 100}   # the measured call (probe0); E3 filler and extra calls share the port range
    if not s:
        return None
    t0 = min(s.values())
    d = sorted((r[k] - s[k]) * 1000 for k in s if k in r and s[k] - t0 >= warmup)
    if not d:
        return None
    q = lambda p: d[min(len(d) - 1, int(round(p * (len(d) - 1))))]
    return {"n": len(d), "p50": q(.5), "p99": q(.99), "sent_cap": len(s), "recv_cap": len(r)}


def count_pcap(path, flt=""):
    if not os.path.exists(path):
        return None
    return sum(1 for l in pcap_lines(path, flt).splitlines() if l and not l.startswith("\t"))


def per_class_counts(c, out, s, m):
    """§36.3: per class, sent / classified (router) / received (SINK capture). TCP split by DSCP (iperf3 control is unmarked)."""
    tos = {"voz": 0xb8, "video": 0x88, "datos": 0x48}
    if not c["marked"]:
        tos = {k: 0 for k in tos}
    sent = defaultdict(int); recv = defaultdict(int)
    for i, fl in enumerate(m["flows"]):
        if fl["kind"] != "probe":
            continue
        k_ = "voz" if PORT_VOICE <= fl["port"] < PORT_VOICE + 10 else ("video" if fl["port"] == PORT_VIDEO else "default")
        sent[k_] += s[f"probe{i}"]["sent"]
        recv[k_] += count_pcap(f"{out}/sink.pcap", f"udp dst port {fl['port']}") or 0
    sp = f"{out}/src_tcp_CW-DAT.pcap"
    if os.path.exists(sp):
        if c["marked"]:
            sent["datos"] += count_pcap(sp, "ip[1] & 0xfc == 0x48") or 0
            sent["default"] += count_pcap(sp, "ip[1] & 0xfc != 0x48") or 0
            recv["datos"] += count_pcap(f"{out}/sink.pcap", f"tcp dst port {PORT_DATA_TCP} and ip[1] & 0xfc == 0x48") or 0
            recv["default"] += count_pcap(f"{out}/sink.pcap", f"tcp dst port {PORT_DATA_TCP} and ip[1] & 0xfc != 0x48") or 0
        else:
            sent["default"] += count_pcap(sp) or 0
            recv["default"] += count_pcap(f"{out}/sink.pcap", f"tcp dst port {PORT_DATA_TCP}") or 0
    sr = f"{out}/src_tcp_RES-1.pcap"
    if os.path.exists(sr):
        sent["default"] += count_pcap(sr) or 0
        recv["default"] += count_pcap(f"{out}/sink.pcap", f"tcp dst port {PORT_RES_TCP}") or 0
    rt = s["router"]
    if c["platform"] == "LXR":
        cls = {"total": (rt.get("sent_pkts") or 0) + (rt.get("drops") or 0)}
    elif c["policy"] in ("CBWFQ", "LLQ"):
        g_ = lambda key: (rt.get(key) or {}).get("pkts")
        cls = {"voz": g_("CM-VOZ"), "video": g_("CM-VIDEO"), "datos": g_("CM-DATOS"), "default": g_("class-default#2")}
    else:
        cls = {"total": (rt.get("class-default") or {}).get("pkts")}
    return {"sent": dict(sent), "classified": cls, "received_at_sink": dict(recv)}


# ---------------------------------------------------------------- one run + validity
def lxr_ingress_delta(out):
    """§44.3: LXR interface RX drops/missed (ip -s link) and softnet dropped/time_squeeze, post - pre. None if not recorded."""
    if not os.path.exists(f"{out}/lxr_stats_pre.txt"):
        return None
    def parse(t):
        link, soft = t.split("SOFTNET")
        d, cur, lines = {}, None, link.splitlines()
        for i, l in enumerate(lines):
            mm = re.match(r"\d+: ([^:@]+)", l)
            if mm:
                cur = mm.group(1)
            if cur and l.strip().startswith("RX:") and i + 1 < len(lines):
                v = lines[i + 1].split()
                d[f"{cur}_rx_errors"], d[f"{cur}_rx_dropped"], d[f"{cur}_rx_missed"] = int(v[2]), int(v[3]), int(v[4])
        rows = [l.split() for l in soft.strip().splitlines() if l.strip()]
        d["softnet_dropped"] = sum(int(r[1], 16) for r in rows); d["softnet_time_squeeze"] = sum(int(r[2], 16) for r in rows)
        return d
    a, b = parse(open(f"{out}/lxr_stats_pre.txt").read()), parse(open(f"{out}/lxr_stats_post.txt").read())
    return {k: b[k] - a.get(k, 0) for k in b}


def host_state():
    gov = open("/sys/devices/system/cpu/cpu0/cpufreq/scaling_governor").read().strip()
    idle = [open(x).read().strip() for x in sorted(glob.glob("/sys/devices/system/cpu/cpu0/cpuidle/state*/disable"))]
    return gov, idle


INGRESS = {"R-BORDE": ("Ethernet0/0", "Ethernet0/2"), "C7200": ("FastEthernet0/0",), "IOSV": ("GigabitEthernet0/0",)}


def router_health(rn, ifaces_in=None):
    """Input 'ignored' (plus overruns and input errors) summed over the ingress interfaces that are up, plus buffer failures."""
    ifaces_in = ifaces_in or INGRESS.get(rn)
    if not ifaces_in:
        return None
    ign, per = 0, {}
    for itf in ifaces_in:
        t = f.show(f"show interfaces {itf} | include ignored|line protocol", name=rn)
        ov = re.search(r"(\d+) overrun", t); ie = re.search(r"(\d+) input errors", t)
        per[itf + "_overrun"] = int(ov.group(1)) if ov else None
        per[itf + "_input_errors"] = int(ie.group(1)) if ie else None
        if "line protocol is up" not in t:
            continue
        m_ = re.search(r"(\d+) ignored", t)
        per[itf] = int(m_.group(1)) if m_ else None
        ign += per[itf] or 0
    fails = [int(x) for x in re.findall(r"(\d+) failures", f.show("show buffers | include failures", name=rn))]
    return {"ignored": ign, "per_interface": per, "buffer_failures": sum(fails)}


def do_run(c, rep, out_root, seed_info):
    run_id = f"{c['id']}_r{rep:02d}{RUN_SUFFIX}"
    out = os.path.join(out_root, run_id)
    os.makedirs(out, exist_ok=True)
    gov, idle = host_state()
    reasons = []
    if gov != "performance" or idle[2:] != ["1", "1"]:
        reasons.append(f"host power state governor={gov} idle_disabled={idle}")
    if not ac_online():                 # §47.1: no run on battery
        reasons.append("no mains power at start (ac_online = 0)")
    L = c["L"]; R = custom_R(c) if c.get("custom") else int(c["r_frac"] * L)
    plat = c["platform"]
    f.set_platform(plat)
    flows = flows_for(c)          # k = 0 (floor): voice only
    ios = None; resv = {}
    if plat in ("IOU", "IOSV", "C7200"):
        rn = f.ROUTER_OF[plat]
        ios, resv = ios_lines(c, R, f.WAN_IF[rn])
        h0 = router_health(rn)
    pol_runner = c["policy"] if plat != "LXR" else {"FIFO": "FIFO", "FQC": "FQ_CODEL", "CAKE": "CAKE"}[c["policy"]]
    start_captures(c)
    if plat == "LXR" and c["policy"] == "FQC":   # active flows in fq_codel, every 100 ms (§7.7)
        f.dx("LXR", "pkill -f '[f]qc_sample'; rm -f /tmp/fqc.txt", check=False)
        f.dbg("LXR", f"timeout {c['dur'] + 15} sh -c 'while :; do echo $(date +%s.%N) $(tc -s qdisc show dev eth1 | "
                     "grep -o \"new_flows_len [0-9]* old_flows_len [0-9]*\" | head -1); sleep 0.1; done' > /tmp/fqc.txt # fqc_sample")
    if c.get("host_load"):              # S-H: 10 of 12 cores busy during the run
        subprocess.run(["docker", "rm", "-f", "f2load"], capture_output=True)
        subprocess.run(["docker", "run", "--rm", "-d", "--name", "f2load", "alpine", "sh", "-c",
                        "for i in $(seq 10); do yes > /dev/null & done; wait"], capture_output=True)
    if plat == "LXR" and c.get("htb_burst") == "Bc":
        os.environ["QOS_HTB_BURST"] = str(max(1600, int(R * 0.004 / 8)))
    else:
        os.environ.pop("QOS_HTB_BURST", None)
    t_wall = time.time()
    meta_extra = {"cell": c, "rep": rep, "seed_info": seed_info, "reservations": resv, "R": R,
                  "htb_burst_B": os.environ.get("QOS_HTB_BURST")}
    try:
        runner.run(run_id, pol_runner, R, flows, duration=c["dur"], queue_limit=c["Q"], outdir=out,
                   platform=plat, line_bps=L, bc_bits=bc_bits(R, c.get("bc_ms", 4)), ios_lines=ios)
    finally:
        stop_captures(out)
        if c.get("host_load"):
            subprocess.run(["docker", "rm", "-f", "f2load"], capture_output=True)
        if plat == "LXR" and c["policy"] == "FQC":
            try:
                f.fetch("LXR", "/tmp/fqc.txt", f"{out}/fqc_flows.txt")
            except subprocess.CalledProcessError:
                pass
    m = json.load(open(f"{out}/meta.json")); m.update(meta_extra); m["wall_s"] = round(time.time() - t_wall, 1)
    s = runner.summarize(out, warmup=float(c.get("warmup", 5.0)))
    # --- applied reservations must be the configured ones (guards the fast console configuration)
    if plat != "LXR" and c["policy"] in ("CBWFQ", "LLQ") and not c.get("custom"):
        pm_txt = open(f"{out}/router_pre.txt").read()
        want = f"Priority: {resv['B_v_kbps']} kbps" if c["policy"] == "LLQ" else f"bandwidth {resv['B_v_kbps']} kbps"
        if want not in pm_txt or f"bandwidth {resv['B_vid_kbps']} kbps" not in pm_txt:
            reasons.append(f"applied reservations differ from configured ({want}, video {resv['B_vid_kbps']} kbps)")
    # --- automatic invalidity criteria (§8)
    if plat in ("IOU", "IOSV", "C7200"):
        h1 = router_health(f.ROUTER_OF[plat])
        m["router_health"] = {"pre": h0, "post": h1}
        # §36: router input losses no longer invalidate; the run is flagged ("marcada") and analysed with and without
        dl = {}
        if h0 and h1:
            for kk, vv in (h1.get("per_interface") or {}).items():
                if vv is not None and (h0.get("per_interface") or {}).get(kk) is not None:
                    dl[kk] = vv - h0["per_interface"][kk]
            dl["ignored_total"] = h1["ignored"] - h0["ignored"]
            dl["buffer_failures"] = h1["buffer_failures"] - h0["buffer_failures"]
        m["ingress_loss_delta"] = dl
        m["marcada"] = bool(dl) and (dl.get("ignored_total", 0) > 0 or dl.get("buffer_failures", 0) > 0
                                     or any(v > 0 for k_, v in dl.items() if k_.endswith("_input_errors")))
    mod = s.get("modem", {})
    if mod.get("drops"):
        reasons.append(f"modem drops {mod['drops']}")
    m["lxr_ingress_delta"] = lxr_ingress_delta(out)   # recorded only (session 2, §44.3); not an invalidity criterion
    hp = m.get("host_power") or {}     # power state at the END of the run (the start is checked above); 13-10: one run spanned the 11:48 switch
    if hp.get("governor") != "performance" or (hp.get("idle_disabled") or [])[2:] != ["1", "1"]:
        reasons.append(f"host power state at end governor={hp.get('governor')} idle_disabled={hp.get('idle_disabled')}")
    if any(x != "1" for x in hp.get("ac_online") or []):   # §47.1
        reasons.append("no mains power at end (ac_online = 0)")
    if P3B_ACTIVE:                     # P3b thresholds (§41): modem queue and host load
        if (mod.get("backlog_max_bytes") or 0) > P3B["modem_queue_B"]:
            reasons.append(f"modem queue {mod.get('backlog_max_bytes')} B > {P3B['modem_queue_B']} B")
        ld = max(m.get("loadavg_end", [0])[0], m.get("loadavg_start", [0])[0])
        thr = P3B["host_load"] + ((C72_IDLE["delta"] or 0.0) if plat == "C7200" else 0.0)
        m["host_load_threshold"] = round(thr, 3)
        if not c.get("host_load") and ld > thr:
            reasons.append(f"host load {ld:.2f} > {thr:.2f}")
    for key, v in s.items():
        if key.startswith("probe") and (v.get("n", 0) == 0 or v.get("sent", 0) == 0):
            reasons.append(f"{key}: empty probe data")
        if key.startswith("tcp") and "error" in v:
            reasons.append(f"{key}: iperf3 error {v['error']}")
    m["tcp_hambre"] = sorted(k_ for k_, v in s.items() if k_.startswith("tcp") and v.get("tcp_hambre"))
    # accounting: sender-side counts vs router classified (IOU) or tc sent+drops (LXR)
    sent_udp = sum(v["sent"] for k_, v in s.items() if k_.startswith("probe"))
    sent_tcp = sum(c_ for c_ in (count_pcap(f"{out}/src_tcp_RES-1.pcap"), count_pcap(f"{out}/src_tcp_CW-DAT.pcap")) if c_)
    rt = s["router"]
    if plat == "LXR":
        router_total = (rt.get("sent_pkts") or 0) + (rt.get("drops") or 0)
    else:
        router_total = (rt.get("class-default") or {}).get("pkts")
    sent_total = sent_udp + sent_tcp
    m["accounting"] = {"sent_udp": sent_udp, "sent_tcp_cap": sent_tcp, "router_total": router_total}
    m["per_class"] = per_class_counts(c, out, s, m)
    if router_total is None or sent_total == 0 or abs(router_total - sent_total) / sent_total > 0.01:
        reasons.append(f"accounting sent {sent_total} vs router {router_total}")
    # shaper exactness under saturation (§8): aggregate L2 rate at SINK, steady window [10 s, dur - 2 s]
    if c["k"] >= 1 and not c.get("positive"):   # positive control: 0.5 R offered, no saturation by design
        ev = []
        for l in subprocess.run(["tcpdump", "-tt", "-nn", "-e", "-r", f"{out}/sink.pcap", "dst host 203.0.113.2"], capture_output=True, text=True).stdout.splitlines():
            mm = re.match(r"(\d+\.\d+) .*?length (\d+):", l)
            if mm:
                ev.append((float(mm.group(1)), int(mm.group(2))))
        if ev:
            t0 = ev[0][0]; win = (10.0, c["dur"] - 2.0)
            rate = sum(b for t, b in ev if win[0] <= t - t0 < win[1]) * 8 / (win[1] - win[0])
            m["shaper_rate_bps"] = round(rate); m["shaper_err"] = round(rate / R - 1, 4)
            m["shaper_exempt"] = any(x in c["id"] for x in SHAPER_EXEMPT)   # §50: recorded, not an invalidity reason
            if abs(rate / R - 1) > 0.05 and not m["shaper_exempt"]:
                reasons.append(f"shaper rate {rate:.0f} bps vs R {R} ({100 * (rate / R - 1):+.1f} %)")
        else:
            reasons.append("no SINK capture for shaper check")
    # second path for voice OWD
    v2 = voice_owd_from_pcaps(out, float(c.get("warmup", 5.0)))   # same window as the summary
    m["voice_owd_capture_path"] = v2
    if v2 and "probe0" in s and abs(v2["p99"] - s["probe0"]["p99"]) > 0.1:
        reasons.append(f"double path p99 mismatch {s['probe0']['p99']:.3f} vs {v2['p99']:.3f} ms")
    m["load1"] = os.getloadavg()[0]
    m["prerun_s"] = dict(PRERUN)
    m["invalid_reasons"] = reasons
    json.dump(m, open(f"{out}/meta.json", "w"), indent=1)
    json.dump(s, open(f"{out}/summary.json", "w"), indent=1)
    # integrity: checksums of every file of the run, then force the write-back to disk (pilot pcaps were lost
    # to zero-filled blocks after a forced power-off)
    with open(f"{out}/CHECKSUMS.sha256", "w") as ck:
        for fn in sorted(os.listdir(out)):
            if fn != "CHECKSUMS.sha256":
                ck.write(hashlib.sha256(open(os.path.join(out, fn), "rb").read()).hexdigest() + "  " + fn + "\n")
    os.sync()
    return run_id, out, reasons


# ---------------------------------------------------------------- driver
def main():
    global P3B_ACTIVE, RUN_SUFFIX
    ap = argparse.ArgumentParser(); ap.add_argument("mode", choices=["pilot", "smoke", "campaign1", "campaign2", "campaign1c", "csmoke", "diag42", "campaign1b", "campaign1k"])
    ap.add_argument("--seed", type=int, default=None)
    ap.add_argument("--dry-run", action="store_true", help="build cells and order through main, print them and exit (no runs, no files)")
    a = ap.parse_args()
    campaign = a.mode.startswith("campaign") or a.mode in ("csmoke", "diag42")
    P3B_ACTIVE = campaign
    runner.RECORD_V2 = a.mode == "campaign2"   # §44.3: recording changes from session 2 on
    a.seed = a.seed or {"campaign1": 20261012, "campaign2": 20261013, "campaign1c": C72_SEED, "campaign1b": BAT_SEED, "campaign1k": K1_SEED}.get(a.mode, 20261010)
    out_root = os.path.join(f.RESULTS, "..", "..", "F4_campana", "campaign" if a.mode.startswith("campaign") else a.mode)
    os.makedirs(os.path.join(out_root, "_invalid"), exist_ok=True)
    state_p = os.path.join(out_root, "state.json")
    state = json.load(open(state_p)) if os.path.exists(state_p) else {"done": [], "invalid": {}}
    if a.mode == "campaign1c":   # §42.2: c7200 at 1 Mbit/s, reps 1-9 (floors 1-10), own randomized block, end of session 1
        cells = [c for c in campaign_cells()[0] + campaign_floor_cells()
                 if c["platform"] == "C7200" and not any(x in c["id"] for x in RETIRED)]
        rep_list = {c["id"]: (list(SESSION_REPS[1]) if not c["floor"] else list(range(1, FLOOR_REPS + 1))) for c in cells}
    elif a.mode in ("campaign1", "campaign2"):
        sess = int(a.mode[-1]); reps_ = list(SESSION_REPS[sess])
        cc, _ = campaign_cells(); fl = campaign_floor_cells()
        off = (sess - 1) * FLOOR_REPS
        cells = cc + fl
        rep_list = {c["id"]: (reps_ if not c["floor"] else list(range(off + 1, off + FLOOR_REPS + 1))) for c in cells}
    elif a.mode == "campaign1k":   # §50.3: IOU k = 1 at 2 and 3 Mbit/s, reps 1-9, own randomized block after campaign1b
        cells = [c for c in campaign_cells()[0] if any(x in c["id"] for x in SHAPER_EXEMPT)]
        rep_list = {c["id"]: list(SESSION_REPS[1]) for c in cells}
    elif a.mode == "campaign1b":   # §47.2: repeat on mains the 103 valid runs of 14-10 made on battery (own randomized block)
        RUN_SUFFIX = "_ac"
        bat = json.load(open(os.path.join(out_root, "battery_runs_20261014.json")))["runs"]
        byid = {c["id"]: c for c in campaign_cells()[0] + campaign_floor_cells()}
        rep_list = {}
        for r in bat:
            cid, rr = r.rsplit("_r", 1)
            rep_list.setdefault(cid, []).append(int(rr))
        cells = [byid[cid] for cid in rep_list]
    elif a.mode == "diag42":     # §42.1 step 3 (not data): IOU k = 1, 2 Mbit/s, Bc = R x 4 ms / R x 8 ms / Be = Bc
        cells = []
        for pol in ("CBWFQ", "LLQ"):
            for var in ("ref", "bc8", "beBc"):
                c = cell("DIAG42", "IOU", pol, 2000000, 1, dur=CAMPAIGN_DUR, be_eq_bc=(var == "beBc"))
                c["warmup"] = W_WARMUP
                if var == "bc8":
                    c["bc_ms"] = 8; c["id"] += "_bc8ms"
                cells.append(c)
        c = cell("DIAG42", "C7200", "CBWFQ", 2000000, 1, dur=CAMPAIGN_DUR)   # §44.2: c7200 reference, Bc = R x 4 ms
        c["warmup"] = W_WARMUP; cells.append(c)
        rep_list = {c["id"]: [1, 2, 3] for c in cells}
    elif a.mode == "csmoke":     # one short run of each campaign cell type (not data)
        cc, _ = campaign_cells(); seen = set(); cells = []
        for c in cc:
            k_ = (c["exp"], c["platform"], c["policy"], bool(c.get("custom")), c.get("host_load"), c.get("voice_over"),
                  c.get("cs1_data"), c.get("htb_burst"), c.get("be_eq_bc"), c.get("positive"), c["marked"])
            if k_ not in seen:
                seen.add(k_); cells.append(dict(c, dur=30))
        rep_list = {c["id"]: [1] for c in cells}
    else:
        cells = pilot_cells() if a.mode == "pilot" else smoke_cells()
        rep_list = {c["id"]: list(range(1, c["reps"] + 1)) for c in cells}
    # randomized block order: a block = cells sharing (exp, platform group, L, k, m); policies shuffled inside
    rnd = random.Random(a.seed)
    blocks = {}
    for c in cells:   # a block = every policy/platform of one factor combination
        bk = c["id"].replace(f"_{c['platform']}_{c['policy']}_", "_") if not c["floor"] else c["id"]
        blocks.setdefault(bk, []).append(c)
    order = []
    all_reps = sorted({r for v in rep_list.values() for r in v})
    for rep in all_reps:
        bl = list(blocks.values()); rnd.shuffle(bl)
        for b in bl:
            b2 = b[:]; rnd.shuffle(b2)
            order += [(c, rep) for c in b2 if rep in rep_list[c["id"]]]
    hashes = {fn: hashlib.sha256(open(os.path.join(HERE, fn), "rb").read()).hexdigest()[:16]
              for fn in ("campaign.py", "runner.py", "f2lib.py", "modem_backlog.sh")}
    hashes["udpprobe.py"] = hashlib.sha256(open(os.path.join(HERE, "..", "docker", "udpprobe.py"), "rb").read()).hexdigest()[:16]
    img = subprocess.run(["docker", "image", "inspect", "qos-endpoint:f2", "--format", "{{.Id}}"], capture_output=True, text=True).stdout.strip()
    seed_info = {"seed": a.seed, "script_sha256_16": hashes, "image": img, "protocol_sha256": "c84b7f584a29fad92d905746494c9005860a948e52f89df8ced7853e798e2f8f"}
    if a.dry_run:
        dp = os.path.join(out_root, "deferred.json")
        pats = json.load(open(dp))["patterns"] if os.path.exists(dp) and a.mode != "campaign1c" else []
        skip = sum(1 for c, r in order if any(x in c["id"] for x in RETIRED + tuple(pats)))
        done_ = sum(1 for c, r in order if f"{c['id']}_r{r:02d}{RUN_SUFFIX}" in state["done"])
        print(f"DRY-RUN mode={a.mode} seed={a.seed} out={os.path.abspath(out_root)} runs={len(order)} "
              f"deferred/retired={skip} already_done={done_} to_run={len(order) - skip - done_}")
        for c, r in order[:4]:
            print(f"  {c['id']}_r{r:02d}{RUN_SUFFIX}  shaper_exempt={any(x in c['id'] for x in SHAPER_EXEMPT)}")
        sys.exit(0)
    order_p = os.path.join(out_root, f"order_{a.mode}.json")
    new_order = [[c["id"], r] for c, r in order]
    if os.path.exists(order_p) and json.load(open(order_p))["order"] != new_order:
        sys.exit(f"ABORT: {order_p} exists with a different order (cell list or seed changed)")
    if not os.path.exists(order_p):
        json.dump({"order": new_order, "seed_info": seed_info}, open(order_p, "w"), indent=1)
    f.router().cmd("clear counters", timeout=10); f.router().cmd("", timeout=5)   # §32.6: ignored at zero each session
    defer_p = os.path.join(out_root, "deferred.json")   # cells set aside pending a decision (not done, not data)
    deferred = lambda cid: (any(x in cid for x in RETIRED) or (a.mode != "campaign1c" and os.path.exists(defer_p)
                                                               and any(x in cid for x in json.load(open(defer_p))["patterns"])))
    if P3B_ACTIVE and any(c["platform"] == "C7200" and not deferred(c["id"]) and f"{c['id']}_r{r:02d}" not in state["done"] for c, r in order):
        wait_power(); measure_c72_idle(out_root, a.mode)
    print(f"START {time.strftime('%F %T')} runs={len(order)} done={len(state['done'])} (R-BORDE counters cleared)", flush=True)
    for i, (c, rep) in enumerate(order):
        run_id = f"{c['id']}_r{rep:02d}{RUN_SUFFIX}"
        if run_id in state["done"]:
            continue
        if deferred(c["id"]):
            print(f"[{i+1}/{len(order)}] {'RETIRED' if any(x in c['id'] for x in RETIRED) else 'DEFERRED'} {run_id}", flush=True)
            continue
        stale = os.path.join(out_root, run_id)
        if os.path.exists(stale):   # left by an interrupted run (power cut, kill): set aside, never reused as data
            os.rename(stale, os.path.join(out_root, "_invalid", f"{run_id}_interrupted_{time.strftime('%Y%m%d%H%M%S')}"))
        for attempt in range(1 if a.mode == "diag42" else MAX_RETRY + 1):   # diagnostic: every attempt kept, no retry
            try:
                wait_power()
                c72 = c["platform"] == "C7200"
                t_off = 0.0 if c72 else c7200_power(False)
                t_cool = 0.0 if (c72 and c7200_is_on()) else cool_down()   # C7200 running keeps ~1 core busy: no cool-down target
                t_on = c7200_power(True) if c72 else 0.0
                PRERUN.update(c7200_stop=round(t_off, 1), cool_down=round(t_cool, 1), c7200_boot=round(t_on, 1))
                if t_off + t_cool + t_on > 5:
                    print(f"    pre-run: C7200 stop {t_off:.0f} s, cool-down {t_cool:.0f} s (load {os.getloadavg()[0]:.2f}), C7200 boot {t_on:.0f} s", flush=True)
                rid, out, reasons = do_run(c, rep, out_root, seed_info)
            except Exception as e:
                rid, out, reasons = run_id, os.path.join(out_root, run_id), [f"exception: {e!r}"]
                traceback.print_exc()
            if not reasons:
                state["done"].append(run_id)
                print(f"[{i+1}/{len(order)}] OK {run_id} {time.strftime('%T')}", flush=True)
                break
            dest = os.path.join(out_root, "_invalid", f"{run_id}_a{attempt}")
            if os.path.exists(out):
                os.rename(out, dest)
            else:
                os.makedirs(dest, exist_ok=True)
            open(os.path.join(dest, "reason.txt"), "w").write("\n".join(reasons))
            state["invalid"].setdefault(run_id, []).append(reasons)
            print(f"[{i+1}/{len(order)}] INVALID {run_id} a{attempt}: {reasons}", flush=True)
        json.dump(state, open(state_p, "w"), indent=1)
    f.set_platform("IOU")
    if a.mode == "diag42":   # §44.1: report with the rule fixed before the data; then everything stops for Ronald
        rep_txt = subprocess.run([sys.executable, os.path.join(HERE, "diag42_report.py")], capture_output=True, text=True)
        open(os.path.join(out_root, "INFORME_DIAG42.txt"), "w").write(rep_txt.stdout + rep_txt.stderr)
        print(rep_txt.stdout, flush=True)
    print(f"CAMPAIGN_DONE {time.strftime('%F %T')} done={len(state['done'])} invalid_runs={len(state['invalid'])}", flush=True)


if __name__ == "__main__":
    main()
