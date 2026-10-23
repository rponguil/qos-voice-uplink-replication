"""Insert MODEM (Linux, netem rate = upstream line rate) between both routers and SINK.

  R-BORDE e0/1 10.0.1.1/30 -- MODEM eth0 10.0.1.2/30
  LXR eth1     10.0.2.1/30 -- MODEM eth1 10.0.2.2/30
  MODEM eth2 203.0.113.1/30 -- SINK eth0 203.0.113.2/30
Run once with the project stopped-or-running; it stops all nodes, rewires and starts them.
Afterwards run configure_all.py (also after any restart of the lab).
"""
import sys, os, time
sys.path.insert(0, os.path.dirname(__file__))
import gns3api as g

pid = g.project("QoS_F2_viabilidad")["project_id"]
g.post(f"/projects/{pid}/nodes/stop")
N = g.nodes(pid)
if "MODEM" not in N:
    g.post(f"/projects/{pid}/nodes", {"name": "MODEM", "node_type": "docker", "compute_id": "local", "x": 250, "y": 100,
           "symbol": ":/symbols/classic/router.svg",
           "properties": {"image": "qos-endpoint:f2", "adapters": 3, "console_type": "none", "start_command": "sleep infinity"}})
    N = g.nodes(pid)
idn = {v["node_id"]: k for k, v in N.items()}
for l in g.get(f"/projects/{pid}/links"):
    names = {idn[n["node_id"]] for n in l["nodes"]}
    if "SINK" in names and names & {"R-BORDE", "LXR"}:
        g.delete(f"/projects/{pid}/links/{l['link_id']}")
have = {(idn[n["node_id"]], n["adapter_number"], n["port_number"]) for l in g.get(f"/projects/{pid}/links") for n in l["nodes"]}
for a, aa, ap, b, ba, bp in [("R-BORDE", 0, 1, "MODEM", 0, 0), ("LXR", 1, 0, "MODEM", 1, 0), ("MODEM", 2, 0, "SINK", 0, 0)]:
    if (a, aa, ap) not in have:
        g.post(f"/projects/{pid}/links", {"nodes": [
            {"node_id": N[a]["node_id"], "adapter_number": aa, "port_number": ap},
            {"node_id": N[b]["node_id"], "adapter_number": ba, "port_number": bp}]})
g.post(f"/projects/{pid}/nodes/start")
time.sleep(5)
print({n: v["status"] for n, v in g.nodes(pid).items()}, len(g.get(f"/projects/{pid}/links")), "links")
