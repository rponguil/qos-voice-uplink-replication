"""Extra smoke (not data): cell types the csmoke did not cover, same pre-run steps and checks as the campaign."""
import os, sys, time, json
sys.path.insert(0, os.path.dirname(__file__))
import campaign as C, f2lib as f
C.P3B_ACTIVE = True
cc, _ = C.campaign_cells(); fl = C.campaign_floor_cells()
want = ["E4b_C7200_LLQ_L1000k_k3", "E4b_C7200_CBWFQ_L1000k_k3", "FLOOR_C7200_FIFO_L5000k"]
cells = [c for w in want for c in cc + fl if c["id"].startswith(w)]
print([c["id"] for c in cells], flush=True)
out_root = os.path.join(f.RESULTS, "..", "..", "F4_campana", "csmoke_extra"); os.makedirs(out_root, exist_ok=True)
seed_info = {"seed": None, "note": "smoke"}
for c in cells:
    c72 = c["platform"] == "C7200"
    t_off = 0.0 if c72 else C.c7200_power(False)
    t_cool = 0.0 if (c72 and C.c7200_is_on()) else C.cool_down()
    t_on = C.c7200_power(True) if c72 else 0.0
    C.PRERUN.update(c7200_stop=round(t_off, 1), cool_down=round(t_cool, 1), c7200_boot=round(t_on, 1))
    rid, out, reasons = C.do_run(dict(c), 1, out_root, seed_info)
    print(time.strftime("%T"), rid, dict(C.PRERUN), reasons, flush=True)
f.set_platform("IOU"); C.c7200_power(False)
print("EXTRA_DONE", flush=True)
