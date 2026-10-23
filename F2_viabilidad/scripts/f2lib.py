"""Helpers for the F2 viability tests: run tools inside the endpoint containers,
apply QoS policies on R-BORDE and read its counters."""
import os, re, subprocess, sys, time
sys.path.insert(0, os.path.dirname(__file__))
import gns3api as g

PID = g.project("QoS_F2_viabilidad")["project_id"]
_N = g.nodes(PID)
CID = {n: v["properties"]["container_id"] for n, v in _N.items() if v["node_type"] == "docker"}
CONSOLE = {n: v["console"] for n, v in _N.items() if v["node_type"] in ("iou", "qemu", "dynamips")}
WAN_IF = {"R-BORDE": "Ethernet0/1", "IOSV": "GigabitEthernet0/1", "C7200": "FastEthernet1/0"}
ROUTER_OF = {"IOU": "R-BORDE", "IOSV": "IOSV", "C7200": "C7200"}
IP = {"CW-VOZ": "192.168.10.11", "CW-DAT": "192.168.10.12", "RES-1": "192.168.20.11", "SINK": "203.0.113.2"}
RESULTS = os.path.join(os.path.dirname(__file__), "..", "results")


def dx(node, cmd, check=True):
    r = subprocess.run(["docker", "exec", CID[node], "sh", "-c", cmd], capture_output=True, text=True)
    if check and r.returncode != 0:
        raise RuntimeError(f"{node}: {cmd}\n{r.stdout}\n{r.stderr}")
    return r.stdout + r.stderr


def dbg(node, cmd):
    """Start cmd detached inside the container."""
    subprocess.run(["docker", "exec", "-d", CID[node], "sh", "-c", cmd], check=True)


def fetch(node, path, dest):
    subprocess.run(["docker", "cp", f"{CID[node]}:{path}", dest], check=True)


_con = {}


def router(name="R-BORDE"):
    if name not in _con:
        c = g.Console(CONSOLE[name])
        c.wake(); c.cmd("end", timeout=5); c.cmd("enable"); c.cmd("terminal length 0")
        _con[name] = c
    return _con[name]


def configure(lines, name="R-BORDE", fast=True):
    """fast: lines sent back to back (50 ms apart) and the console read once at the end (overhead reduction, §32.5);
    errors are still detected in the echoed output, and callers verify the applied policy."""
    c = router(name)
    out = c.cmd("configure terminal")
    if fast:
        for l in lines:
            c.s.sendall(l.encode() + b"\r"); time.sleep(0.05)
        out += c.cmd("end", timeout=30)
    else:
        for l in lines:
            out += c.cmd(l, timeout=20)
        out += c.cmd("end")
    if re.search(r"% ?(Invalid|Incomplete|Ambiguous)|%.*[Ee]rror|out of range|should be at least|[Nn]ot (allowed|supported)|exceed", out):
        raise RuntimeError("IOS rejected config:\n" + out)
    return out


def show(cmd, name="R-BORDE"):
    return router(name).cmd(cmd, timeout=60)


def policy_lines(policy, rate_bps, queue_limit=None, voice_pct=30, bc_bits=None, iface="Ethernet0/1"):
    """Hierarchical policy on Ethernet0/1 output. policy in {FIFO, CBWFQ, LLQ}."""
    L = [f"interface {iface}", "no service-policy output PARENT", "exit",
         "no policy-map PARENT", "no policy-map CHILD"]
    L += ["class-map match-any CM-VOZ", "match ip dscp ef",
          "class-map match-any CM-VIDEO", "match ip dscp af41",
          "class-map match-any CM-DATOS", "match ip dscp af21"]
    if policy == "NONE":
        return L[:3]
    if policy != "FIFO":
        L += ["policy-map CHILD"]
        L += ["class CM-VOZ", f"priority percent {voice_pct}" if policy == "LLQ" else f"bandwidth percent {voice_pct}"]
        L += ["class CM-VIDEO", "bandwidth percent 25", "class CM-DATOS", "bandwidth percent 20",
              "class class-default", "fair-queue"]
        if queue_limit:
            L += [f"queue-limit {queue_limit} packets"]
        L += ["exit"]
    L += ["policy-map PARENT", "class class-default", f"shape average {rate_bps}" + (f" {bc_bits} 0" if bc_bits else "")]
    if policy != "FIFO":
        L += ["service-policy CHILD"]
    elif queue_limit:
        L += [f"queue-limit {queue_limit} packets"]
    L += ["exit", "exit", f"interface {iface}", "service-policy output PARENT"]
    return L


def owd_stats(csv_path, warmup_s=0.0):
    import csv, statistics
    rows = list(csv.DictReader(open(csv_path)))
    if not rows:
        return {"n": 0}
    t0 = min(int(r["send_ns"]) for r in rows)
    d = [(int(r["recv_ns"]) - int(r["send_ns"])) / 1e6 for r in rows
         if int(r["send_ns"]) - t0 >= warmup_s * 1e9]
    d.sort()
    q = lambda p: d[min(len(d) - 1, int(round(p * (len(d) - 1))))]
    # RFC 3550 interarrival jitter
    J, prev = 0.0, None
    for r in sorted(rows, key=lambda r: int(r["seq"])):
        transit = (int(r["recv_ns"]) - int(r["send_ns"])) / 1e6
        if prev is not None:
            J += (abs(transit - prev) - J) / 16
        prev = transit
    return {"n": len(d), "min": d[0], "p50": q(.5), "p95": q(.95), "p99": q(.99),
            "max": d[-1], "mean": statistics.fmean(d), "jitter3550": J}


def set_platform(p):
    """Route the endpoints through R-BORDE (IOU) or LXR (Linux tc); MODEM return route follows."""
    last = {"IOU": "1", "LXR": "2", "IOSV": "3", "C7200": "4"}[p]
    for n, net in (("CW-VOZ", "10"), ("CW-DAT", "10"), ("RES-1", "20")):
        dx(n, f"ip route replace default via 192.168.{net}.{last}")
    dx("MODEM", f"ip route replace 192.168.0.0/16 via {dict(IOU='10.0.1.1', LXR='10.0.2.1', IOSV='10.0.3.1', C7200='10.0.4.1')[p]}")


def set_line(line_bps, limit=64):
    """Upstream line model on MODEM eth2 (towards SINK): netem rate = line rate (serialisation).
    None removes it (infinitely fast line, as in the first F2 runs)."""
    c = "tc qdisc del dev eth2 root 2>/dev/null;"
    if line_bps:
        c += f" tc qdisc add dev eth2 root netem rate {int(line_bps)}bit limit {limit}"
    dx("MODEM", c + " true" if not line_bps else c)


def modem_stats():
    return dx("MODEM", "tc -s qdisc show dev eth2")


def lxr_apply(policy, rate_bps, limit=64):
    """Linux qdiscs on LXR eth1 (egress to WAN). policy in {FIFO, FQ_CODEL, CAKE}."""
    r = f"{rate_bps}bit"
    c = "tc qdisc del dev eth1 root 2>/dev/null; "
    if policy == "CAKE":
        c += f"tc qdisc add dev eth1 root cake bandwidth {r} diffserv4"
    else:
        c += (f"tc qdisc add dev eth1 root handle 1: htb default 10 && "
              f"tc class add dev eth1 parent 1: classid 1:10 htb rate {r} ceil {r} quantum 1514 "
              f"burst {os.environ.get('QOS_HTB_BURST', '1600')} cburst {os.environ.get('QOS_HTB_BURST', '1600')} && ")
        c += (f"tc qdisc add dev eth1 parent 1:10 handle 10: pfifo limit {limit}" if policy == "FIFO"
              else "tc qdisc add dev eth1 parent 1:10 handle 10: fq_codel")
    dx("LXR", c)
    return dx("LXR", "tc -s -d qdisc show dev eth1; tc -s class show dev eth1")


def start_backlog_sampler(seconds):
    subprocess.run(["docker", "cp", os.path.join(os.path.dirname(__file__), "modem_backlog.sh"),
                    f"{CID['MODEM']}:/tmp/modem_backlog.sh"], check=True)
    dbg("MODEM", f"sh /tmp/modem_backlog.sh {int(seconds)} > /tmp/backlog.txt")
