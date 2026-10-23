"""Add LXR (Linux router, tc qdiscs) in parallel to R-BORDE.

  SW port 4 (dot1q trunk) -- LXR eth0 (eth0.10 192.168.10.2, eth0.20 192.168.20.2)
  LXR eth1 203.0.114.1/30 -- SINK eth1 203.0.114.2/30
The platform under test is selected by routing (set_platform): hosts' default gateway
.1 (IOU) or .2 (Linux), and SINK's return route via 203.0.113.1 or 203.0.114.1.
"""
import sys, os, subprocess, time
sys.path.insert(0, os.path.dirname(__file__))
import gns3api as g

pid = g.project("QoS_F2_viabilidad")["project_id"]
N = g.nodes(pid)
sw, sink = N["SW"], N["SINK"]

# switch: add dot1q port 4
pm = sw["properties"]["ports_mapping"]
if not any(p["port_number"] == 4 for p in pm):
    pm.append({"name": "Ethernet4", "port_number": 4, "type": "dot1q", "vlan": 1})
    # GNS3 refuses port changes on a connected switch: unlink, update, relink
    saved = []
    for l in g.get(f"/projects/{pid}/links"):
        if any(n["node_id"] == sw["node_id"] for n in l["nodes"]):
            saved.append([{k: n[k] for k in ("node_id", "adapter_number", "port_number")} for n in l["nodes"]])
            g.delete(f"/projects/{pid}/links/{l['link_id']}")
    g.put(f"/projects/{pid}/nodes/{sw['node_id']}", {"properties": {"ports_mapping": pm}})
    for ends in saved:
        g.post(f"/projects/{pid}/links", {"nodes": ends})
# SINK: second adapter (needs stop)
if sink["properties"]["adapters"] < 2:
    g.post(f"/projects/{pid}/nodes/{sink['node_id']}/stop")
    g.put(f"/projects/{pid}/nodes/{sink['node_id']}", {"properties": {"adapters": 2}})
if "LXR" not in N:
    g.post(f"/projects/{pid}/nodes", {"name": "LXR", "node_type": "docker", "compute_id": "local", "x": 0, "y": 200,
           "properties": {"image": "qos-endpoint:f2", "adapters": 2, "console_type": "none", "start_command": "sleep infinity"}})
N = g.nodes(pid)
have = {(n["node_id"], n["adapter_number"], n["port_number"]) for l in g.get(f"/projects/{pid}/links") for n in l["nodes"]}
for a, aa, ap, b, ba, bp in [(N["SW"], 0, 4, N["LXR"], 0, 0), (N["LXR"], 1, 0, N["SINK"], 1, 0)]:
    if (a["node_id"], aa, ap) not in have:
        g.post(f"/projects/{pid}/links", {"nodes": [
            {"node_id": a["node_id"], "adapter_number": aa, "port_number": ap},
            {"node_id": b["node_id"], "adapter_number": ba, "port_number": bp}]})
g.post(f"/projects/{pid}/nodes/start")
time.sleep(5)
N = g.nodes(pid)
cid = lambda n: N[n]["properties"]["container_id"]
def sh(n, c):
    subprocess.run(["docker", "exec", cid(n), "sh", "-c", c], check=True)
sh("LXR", "sysctl -qw net.ipv4.ip_forward=1; ip link set eth0 up; "
          "ip link add link eth0 name eth0.10 type vlan id 10 2>/dev/null; ip link add link eth0 name eth0.20 type vlan id 20 2>/dev/null; "
          "ip addr flush dev eth0.10; ip addr add 192.168.10.2/24 dev eth0.10; ip link set eth0.10 up; "
          "ip addr flush dev eth0.20; ip addr add 192.168.20.2/24 dev eth0.20; ip link set eth0.20 up; "
          "ip addr flush dev eth1; ip addr add 203.0.114.1/30 dev eth1; ip link set eth1 up; ip route replace default via 203.0.114.2; "
          "ethtool -K eth1 gso off gro off tso off 2>/dev/null; ethtool -K eth0 gso off gro off tso off 2>/dev/null; true")
sh("SINK", "ip addr flush dev eth0; ip addr add 203.0.113.2/30 dev eth0; ip link set eth0 up; "
           "ip addr flush dev eth1; ip addr add 203.0.114.2/30 dev eth1; ip link set eth1 up; "
           "ip route replace default via 203.0.113.1")
print({n: N[n]["status"] for n in N})
