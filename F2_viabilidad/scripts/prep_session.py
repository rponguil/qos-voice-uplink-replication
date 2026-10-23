"""Prepare a campaign session: GNS3 project open, nodes started (C7200 without idle-PC, IOSV stopped),
addressing applied, the three paths checked, host power state checked. Exit code 1 if anything is wrong."""
import os, re, sys, time
sys.path.insert(0, os.path.dirname(__file__))
import gns3api as g
pid = g.project("QoS_F2_viabilidad")["project_id"]
if g.project("QoS_F2_viabilidad")["status"] != "opened":
    g.post(f"/projects/{pid}/open")
N = g.nodes(pid)
c72 = N["C7200"]
if c72["properties"].get("idlepc") not in (None, "", "0x0"):   # GNS3 stores "no idle-PC" as 0x0
    if c72["status"] == "started":
        g.post(f"/projects/{pid}/nodes/{c72['node_id']}/stop")
    g.put(f"/projects/{pid}/nodes/{c72['node_id']}", {"properties": {"idlepc": ""}})
    time.sleep(15)   # 14-10: a start right after a stop leaves the Dynamips console unbound
for n, v in g.nodes(pid).items():
    if n == "IOSV":
        if v["status"] == "started":
            g.post(f"/projects/{pid}/nodes/{v['node_id']}/stop")
    elif v["status"] != "started":
        g.post(f"/projects/{pid}/nodes/{v['node_id']}/start")
time.sleep(5)
import f2lib as f
for name in ("R-BORDE", "C7200"):
    t0 = time.time()
    while time.time() - t0 < 600:
        try:
            c = g.Console(f.CONSOLE[name]); o = c.wake(); c.close()
            if re.search(name + r"[>#]", o):
                break
        except OSError:
            pass
        time.sleep(5)
os.system(f"cd '{os.path.dirname(os.path.abspath(__file__))}' && python3 configure_all.py > /dev/null 2>&1")
ok = True
for p in ("IOU", "LXR", "C7200"):
    f.set_platform(p)
    r = [f.dx(n, "ping -c 2 -W 1 -s 1472 203.0.113.2 | grep -o '[0-9]* received'", check=False).strip() for n in ("CW-VOZ", "CW-DAT", "RES-1")]
    print(p, r); ok &= all(x.startswith("2") for x in r)
f.set_platform("IOU")
gov = open("/sys/devices/system/cpu/cpu0/cpufreq/scaling_governor").read().strip()
idle = [open(f"/sys/devices/system/cpu/cpu0/cpuidle/state{i}/disable").read().strip() for i in (2, 3)]
print("governor", gov, "C2/C3 disabled", idle); ok &= gov == "performance" and idle == ["1", "1"]
print("PREP_OK" if ok else "PREP_FAILED"); sys.exit(0 if ok else 1)
