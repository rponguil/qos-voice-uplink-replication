"""One F2 run: apply policy, clear counters, launch flows, collect everything.

Flow spec (dict):
  probe : {"kind":"probe","node":"CW-VOZ","port":5001,"dscp":46,"size":160,"interval":0.02,"flow":1}
  udp   : {"kind":"udp","node":"RES-1","port":5201,"dscp":0,"size":1472,"rate":"512k"}   (iperf3 -u)
  tcp   : {"kind":"tcp","node":"CW-DAT","port":5202,"dscp":18,"streams":1}             (iperf3 TCP)
"""
import json, os, re, time
import f2lib as f

IOU_BIN = "i86bi-linux-l3"
RECORD_V2 = False   # §44.3 (session 2): LXR ip -s link + softnet_stat before/after; router counters read after TCP clients end
LXR_STATS = "ip -s link; echo SOFTNET; cat /proc/net/softnet_stat"


def _iou_cpu():
    import subprocess
    pid = subprocess.run(["pgrep", "-f", IOU_BIN], capture_output=True, text=True).stdout.split()
    if not pid:
        return None
    st = open(f"/proc/{pid[0]}/stat").read().split()
    return (int(st[13]) + int(st[14])) / os.sysconf("SC_CLK_TCK")


def run(name, policy, rate_bps, flows, duration=30, queue_limit=None, outdir=None, apply=True, voice_pct=30, platform="IOU", line_bps=None, bc_bits=None, ios_lines=None):
    out = os.path.abspath(outdir or os.path.join(f.RESULTS, name))
    os.makedirs(out, exist_ok=True)
    meta = {"name": name, "policy": policy, "rate_bps": rate_bps, "duration": duration,
            "queue_limit": queue_limit, "voice_pct": voice_pct, "platform": platform, "line_bps": line_bps, "bc_bits": bc_bits, "flows": flows, "t_start": time.strftime("%Y-%m-%dT%H:%M:%S")}
    T = {"t0": time.time()}
    f.set_line(line_bps)  # also resets the MODEM counters
    RN = f.ROUTER_OF.get(platform, "R-BORDE"); IF = f.WAN_IF.get(RN, "Ethernet0/1")
    if platform == "LXR":
        pre_if = f.lxr_apply(policy, rate_bps, queue_limit or 64) if apply else f.dx("LXR", "tc -s qdisc show dev eth1")
        if not apply:  # reset stats by re-applying the same qdisc
            pre_if = f.lxr_apply(policy, rate_bps, queue_limit or 64)
        pre_pm = ""
    else:
        if apply:
            f.configure(ios_lines if ios_lines else f.policy_lines(policy, rate_bps, queue_limit, voice_pct, bc_bits, IF), name=RN)
        f.router(RN).cmd(f"clear counters {IF}", timeout=10)
        f.router(RN).cmd("", timeout=5)  # confirm prompt
        pre_if = f.show(f"show interfaces {IF}", name=RN)
        pre_pm = f.show(f"show policy-map interface {IF}", name=RN)
        if policy != "NONE" and "Service-policy output: PARENT" not in pre_pm:
            raise RuntimeError(f"{name}: PARENT policy is NOT attached to {RN} {IF} (silent IOS rejection)")
    T["config_done"] = time.time()
    if RECORD_V2:
        lxr_pre = f.dx("LXR", LXR_STATS, check=False)
    # cleanup that cannot kill its own shell ("[u]dpprobe" does not match its own command line); then verify
    CLEAN = "pkill -f '[u]dpprobe'; pkill -x iperf3; sleep 0.3; rm -f /tmp/*.csv /tmp/*.json; true"
    for n in {"SINK"} | {fl["node"] for fl in flows}:
        f.dx(n, CLEAN, check=False)
        left = f.dx(n, "ls /tmp/*.csv /tmp/*.json 2>/dev/null; ps -eo args | grep -E '^(iperf3|python3 /usr/local/bin/udpprobe)' ; true", check=False).strip()
        if left:
            raise RuntimeError(f"{name}: leftovers from a previous run on {n}: {left[:200]}")
    # receivers
    for i, fl in enumerate(flows):
        if fl["kind"] == "probe":
            f.dbg("SINK", f"python3 /usr/local/bin/udpprobe.py recv {fl['port']} --out /tmp/recv_{i}.csv --duration {duration + 60} --idle 5 --min-duration {duration + 3}")
        else:
            # §40.6: receive timeout above the run length, so a starved TCP flow is recorded (≈ 0) instead of aborting
            f.dbg("SINK", f"iperf3 -s -1 -p {fl['port']} --rcv-timeout {int((duration + 60) * 1000)} -J > /tmp/srv_{i}.json 2>&1")
    time.sleep(1.5)
    if line_bps:
        f.start_backlog_sampler(duration + 3)
    load0, cpu0, t0 = os.getloadavg(), _iou_cpu(), time.time()
    # senders (bulk first, then probes start 0 s later; warm-up is removed in analysis)
    stagger = float(os.environ.get("QOS_STAGGER", "0"))   # s between sender starts (diagnostic; 0 = all at once)
    meta["stagger_s"] = stagger
    for i, fl in enumerate(flows):
        if stagger and fl["kind"] != "probe":
            time.sleep(stagger)
        if fl["kind"] == "udp":
            f.dbg(fl["node"], f"iperf3 -c {f.IP['SINK']} -p {fl['port']} -u -b {fl['rate']} -l {fl['size']} "
                              f"--tos {fl['dscp'] << 2} -t {duration} -J > /tmp/cli_{i}.json 2>&1")
        elif fl["kind"] == "tcp":
            f.dbg(fl["node"], f"iperf3 -c {f.IP['SINK']} -p {fl['port']} -P {fl.get('streams', 1)} " + (f"-M {fl['mss']} " if fl.get("mss") else "") + 
                              f"--tos {fl['dscp'] << 2} -t {duration} -J > /tmp/cli_{i}.json 2>&1")
    for i, fl in sorted(enumerate(flows), key=lambda x: x[1]["port"] < 5100):   # competitors before voice
        if fl["kind"] == "probe":
            if stagger:
                time.sleep(stagger)
            cnt = int(duration / fl["interval"])
            f.dbg(fl["node"], f"python3 /usr/local/bin/udpprobe.py send {f.IP['SINK']} {fl['port']} --flow {fl.get('flow', i)} "
                              f"--size {fl['size']} --interval {fl['interval']} --count {cnt} --dscp {fl['dscp']} "
                              f"--out /tmp/send_{i}.csv")
    T["flows_started"] = time.time()
    time.sleep(duration + 2)
    # wait until every probe receiver has exited (queues drained: idle 5 s, cap duration+60 s)
    t_cap = time.time() + 70
    while time.time() < t_cap and "udpprobe.py recv" in f.dx("SINK", "ps -ef", check=False):
        time.sleep(1)
    # iperf3 clients/servers finish after the control exchange, which can sit behind a full queue
    nodes = {fl["node"] for fl in flows if fl["kind"] != "probe"} | ({"SINK"} if any(fl["kind"] != "probe" for fl in flows) else set())
    t_cap = time.time() + 60
    stuck = {}
    while time.time() < t_cap:
        stuck = {n: o.strip() for n in nodes
                 if "iperf3 -" in (o := f.dx(n, "ps -eo pid,etime,args | grep -v grep | grep 'iperf3 -'", check=False))}
        if not stuck:
            break
        time.sleep(1)
    meta["iperf_stuck_at_cap"] = stuck
    if RECORD_V2 and stuck:   # §44.3: a hung TCP client must not keep sending after the router counters are read
        for n in stuck:
            if n != "SINK":
                f.dx(n, "pkill -INT -x iperf3; sleep 1; pkill -KILL -x iperf3; true", check=False)
        t_end = time.time() + 5
        while time.time() < t_end and any("iperf3 -c" in f.dx(n, "ps -eo args", check=False) for n in stuck if n != "SINK"):
            time.sleep(0.5)
        meta["iperf_clients_killed"] = sorted(n for n in stuck if n != "SINK")
    meta["iperf_wait_left_s"] = round(t_cap - time.time(), 1)
    host = {"governor": open("/sys/devices/system/cpu/cpu0/cpufreq/scaling_governor").read().strip(),
            "idle_disabled": [open(x).read().strip() for x in sorted(__import__("glob").glob("/sys/devices/system/cpu/cpu0/cpuidle/state*/disable"))],
            "ac_online": [open(x).read().strip() for x in sorted(__import__("glob").glob("/sys/class/power_supply/ADP*/online"))]}   # 14-10: record AC vs battery
    T["drained"] = time.time()
    meta.update({"host_power": host, "loadavg_start": load0, "loadavg_end": os.getloadavg(),
                 "iou_cpu_frac": (None if cpu0 is None else (_iou_cpu() - cpu0) / (time.time() - t0))})
    open(f"{out}/modem_post.txt", "w").write(f.modem_stats())
    if line_bps:
        f.fetch("MODEM", "/tmp/backlog.txt", f"{out}/modem_backlog.txt")
    if platform == "LXR":
        post_if, post_pm = f.dx("LXR", "tc -s -d qdisc show dev eth1; tc -s class show dev eth1"), ""
    else:
        post_if = f.show(f"show interfaces {IF}", name=RN)
        post_pm = f.show(f"show policy-map interface {IF}", name=RN)
    open(f"{out}/router_pre.txt", "w").write(pre_if + pre_pm)
    if RECORD_V2:
        open(f"{out}/lxr_stats_pre.txt", "w").write(lxr_pre)
        open(f"{out}/lxr_stats_post.txt", "w").write(f.dx("LXR", LXR_STATS, check=False))
    open(f"{out}/router_post.txt", "w").write(post_if + post_pm)
    if platform in ("IOU", "IOSV", "C7200"):
        open(f"{out}/running_qos.txt", "w").write(f.show(f"show running-config | section policy-map|class-map|interface {IF}", name=RN))
    for i, fl in enumerate(flows):
        if fl["kind"] == "probe":
            f.fetch("SINK", f"/tmp/recv_{i}.csv", f"{out}/recv_{i}.csv")
            f.fetch(fl["node"], f"/tmp/send_{i}.csv", f"{out}/send_{i}.csv")
        else:
            f.fetch("SINK", f"/tmp/srv_{i}.json", f"{out}/srv_{i}.json")
            f.fetch(fl["node"], f"/tmp/cli_{i}.json", f"{out}/cli_{i}.json")
    T["fetched"] = time.time()
    meta["timing_s"] = {k: round(v - T["t0"], 1) for k, v in T.items()}
    json.dump(meta, open(f"{out}/meta.json", "w"), indent=1)
    return out


def summarize(out, warmup=5.0):
    meta = json.load(open(f"{out}/meta.json"))
    res = {"name": meta["name"], "policy": meta["policy"], "rate": meta["rate_bps"],
           "iou_cpu": meta["iou_cpu_frac"]}
    for i, fl in enumerate(meta["flows"]):
        if fl["kind"] == "probe":
            sent = sum(1 for _ in open(f"{out}/send_{i}.csv")) - 1
            st = f.owd_stats(f"{out}/recv_{i}.csv", warmup)
            nrecv = sum(1 for _ in open(f"{out}/recv_{i}.csv")) - 1
            res[f"probe{i}"] = dict(st, sent=sent, recv=nrecv, loss=1 - nrecv / sent if sent else None)
        else:
            # §40.6: tool failure (no/broken JSON, never connected) -> "error" (invalid, repeated);
            #        connected but 0 bytes received -> goodput 0 with tcp_hambre (valid, not repeated)
            key_ = f"{fl['kind']}{i}"
            try:
                txt = open(f"{out}/srv_{i}.json").read(); srv = json.loads(txt[txt.index("{"):])
            except Exception as ex:
                res[key_] = {"error": f"no server JSON: {ex!r}"}
                continue
            connected = bool((srv.get("start") or {}).get("connected"))
            s = (srv.get("end") or {}).get("sum_received")
            if s and s.get("bytes", 0) > 0:
                iv = [x["sum"] for x in srv.get("intervals", [])]
                ss = [x for x in iv if x["start"] >= warmup and x["end"] <= meta["duration"] - 1]
                secs = sum(x["seconds"] for x in ss)
                pay = sum(x["bytes"] for x in ss) * 8 / secs if secs else 0.0
                size = fl.get("size")
                res[key_] = {"rx_bps_total": s["bits_per_second"], "rx_bps_steady": pay,
                             "rx_l2_bps_steady": pay * (size + 42) / size if size else None,
                             "lost": s.get("lost_packets"), "pkts": s.get("packets"), "tcp_hambre": False}
            elif connected:
                res[key_] = {"rx_bps_total": 0.0, "rx_bps_steady": 0.0, "tcp_hambre": True,
                             "server_error": srv.get("error")}
            else:
                res[key_] = {"error": f"iperf3 never connected: {srv.get('error')!r}"}
    if os.path.exists(f"{out}/modem_post.txt"):
        res["modem"] = parse_tc(open(f"{out}/modem_post.txt").read())
    if os.path.exists(f"{out}/modem_backlog.txt"):
        lines = [l.split() for l in open(f"{out}/modem_backlog.txt") if len(l.split()) >= 2]
        b = [int(x[1]) for x in lines]
        by = [int(x[2]) for x in lines if len(x) == 3]
        res["modem"]["backlog_max_bytes"] = max(by) if by else None
        res["modem"]["backlog_frac_gt_mtu_bytes"] = sum(v > 1514 for v in by) / len(by) if by else None
        res["modem"]["backlog_samples"] = len(b)
        res["modem"]["backlog_max_pkts"] = max(b) if b else None
        res["modem"]["backlog_frac_gt1"] = sum(x > 1 for x in b) / len(b) if b else None
    txt = open(f"{out}/router_post.txt").read()
    res["router"] = parse_tc(txt) if meta.get("platform") == "LXR" else parse_pm(txt)
    return res


def parse_pm(txt):
    """Per-class counters from 'show policy-map interface' (+ interface output drops).
    Keys: classified pkts/bytes, queued-output pkts, queue drops; priority: exceed drops."""
    d = {}
    m = re.search(r"Total output drops: (\d+)", txt)
    d["if_out_drops"] = int(m.group(1)) if m else None
    m = re.search(r"(\d+) packets output, (\d+) bytes", txt)
    d["if_out_pkts"] = int(m.group(1)) if m else None
    seen = {}
    for blk in re.split(r"\n\s*Class-map: ", txt)[1:]:
        cname = blk.split()[0]
        seen[cname] = seen.get(cname, 0) + 1
        key = cname if seen[cname] == 1 else f"{cname}#{seen[cname]}"
        m = re.search(r"(\d+) packets, (\d+) bytes", blk)
        q = re.search(r"\(queue depth/total drops/no-buffer drops[^)]*\) (\d+)/(\d+)/(\d+)", blk)
        o = re.search(r"\(pkts output/bytes output\) (\d+)/(\d+)", blk)
        e = re.search(r"b/w exceed drops: (\d+)", blk)
        d[key] = {"pkts": int(m.group(1)) if m else None, "bytes": int(m.group(2)) if m else None,
                  "out_pkts": int(o.group(1)) if o else None,
                  "drops": int(q.group(2)) if q else None,
                  "exceed_drops": int(e.group(1)) if e else None}
    m = re.search(r"queue stats for all priority classes:.*?\(queue depth/total drops/no-buffer drops\) (\d+)/(\d+)/(\d+).*?\(pkts output/bytes output\) (\d+)/(\d+)", txt, re.S)
    if m:
        d["PRIORITY_Q"] = {"drops": int(m.group(2)), "out_pkts": int(m.group(4))}
    return d


def parse_tc(txt):
    """Root qdisc stats from 'tc -s qdisc show': sent pkts, dropped, overlimits."""
    m = re.search(r"Sent (\d+) bytes (\d+) pkt \(dropped (\d+), overlimits (\d+)", txt)
    return {"sent_bytes": int(m.group(1)), "sent_pkts": int(m.group(2)), "drops": int(m.group(3)),
            "overlimits": int(m.group(4))} if m else {"error": "no tc stats"}
