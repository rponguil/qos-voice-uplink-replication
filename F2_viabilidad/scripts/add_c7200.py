"""Diagnostic: Cisco c7200 (Dynamips) in parallel.
  SW port 7 (dot1q) -- C7200 Fa0/0 (Fa0/0.10 192.168.10.4, Fa0/0.20 192.168.20.4)
  C7200 Fa1/0 10.0.4.1/30 -- MODEM eth4 10.0.4.2/30
Stops all nodes; rebuilds every MODEM link with the lab stopped (adapter count changes); starts."""
import sys, os, time
sys.path.insert(0, os.path.dirname(__file__))
import gns3api as g
IMG = "c7200-adventerprisek9-mz.153-3.XB12.image"
pid = g.project("QoS_F2_viabilidad")["project_id"]
g.post(f"/projects/{pid}/nodes/stop"); time.sleep(3)
N = g.nodes(pid)
if "C7200" not in N:
    g.post(f"/projects/{pid}/nodes", {"name": "C7200", "node_type": "dynamips", "compute_id": "local", "x": 0, "y": -350,
           "symbol": ":/symbols/classic/router.svg",
           "properties": {"platform": "c7200", "image": IMG, "ram": 512, "npe": "npe-400", "midplane": "vxr",
                          "slot0": "C7200-IO-FE", "slot1": "PA-2FE-TX", "idlepc": "0x60630d08"}})
    N = g.nodes(pid)
sw = N["SW"]; pm = sw["properties"]["ports_mapping"]
if not any(p["port_number"] == 7 for p in pm):
    pm.append({"name": "Ethernet7", "port_number": 7, "type": "dot1q", "vlan": 1})
    saved = []
    for l in g.get(f"/projects/{pid}/links"):
        if any(x["node_id"] == sw["node_id"] for x in l["nodes"]):
            saved.append([{k: x[k] for k in ("node_id", "adapter_number", "port_number")} for x in l["nodes"]])
            g.delete(f"/projects/{pid}/links/{l['link_id']}")
    g.put(f"/projects/{pid}/nodes/{sw['node_id']}", {"properties": {"ports_mapping": pm}})
    for ends in saved:
        g.post(f"/projects/{pid}/links", {"nodes": ends})
M = N["MODEM"]
msaved = []
for l in g.get(f"/projects/{pid}/links"):
    if any(x["node_id"] == M["node_id"] for x in l["nodes"]):
        msaved.append([{k: x[k] for k in ("node_id", "adapter_number", "port_number")} for x in l["nodes"]])
        g.delete(f"/projects/{pid}/links/{l['link_id']}")
if M["properties"]["adapters"] < 5:
    g.put(f"/projects/{pid}/nodes/{M['node_id']}", {"properties": {"adapters": 5}})
for ends in msaved:
    g.post(f"/projects/{pid}/links", {"nodes": ends})
N = g.nodes(pid)
g.post(f"/projects/{pid}/links", {"nodes": [{"node_id": sw["node_id"], "adapter_number": 0, "port_number": 7},
                                            {"node_id": N["C7200"]["node_id"], "adapter_number": 0, "port_number": 0}]})
g.post(f"/projects/{pid}/links", {"nodes": [{"node_id": N["C7200"]["node_id"], "adapter_number": 1, "port_number": 0},
                                            {"node_id": N["MODEM"]["node_id"], "adapter_number": 4, "port_number": 0}]})
g.post(f"/projects/{pid}/nodes/start"); time.sleep(5)
N = g.nodes(pid)
print({n: v["status"] for n, v in N.items()}, len(g.get(f"/projects/{pid}/links")), "links; C7200 console", N["C7200"]["console"])
