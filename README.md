# CBWFQ vs LLQ for voice on slow shared home-office uplinks — reproducibility package

Code, frozen protocol, analysis plan, per-run results and figures of the measurement campaign behind the manuscript
*When Is Strict Priority Needed for Voice on Slow Home-Office Uplinks? A Replicated Emulation Study of CBWFQ, LLQ, fq_codel and CAKE*.

**Authors:** Ronald Ponguillo-Intriago, Derian S. Barros Palma, Jonathan A. Rodríguez Borbor.
Facultad de Ciencias Matemáticas y Físicas, Universidad de Guayaquil, Guayaquil 090510, Ecuador.

Repository: https://github.com/rponguil/qos-voice-uplink-replication. Data DOI: [10.5281/zenodo.23604110](https://doi.org/10.5281/zenodo.23604110). Code DOI (this version, v1.0.0): [10.5281/zenodo.23630217](https://doi.org/10.5281/zenodo.23630217).

The folder layout mirrors the working project (`F2_…`, `F3_…`, `F4_…`, `F5_…`), so every script runs unchanged with its relative paths.

The protocol and the analysis plan were written and frozen in Spanish. The repository holds their English translations; each one gives the SHA-256 of its original, and the originals are available from the authors on request.

Folder names, result file names and some identifiers in the data keep their Spanish names: *viabilidad* = feasibility, *protocolo* = protocol, *campana* = campaign, *analisis* = analysis, *AUDITORIA* = audit, *VALIDACION* = validation, *CONFIRMATORIO* = confirmatory, *SENSIBILIDAD* = sensitivity, *EXPLORATORIO* = exploratory, *CIERRE* = closure, *suelo* = floor, *celdas* = cells, *corridas* = runs, *colapso* = collapse, *MUESTRA_VERIFICACION* = re-computation sample, `marcada` = flagged run, `tcp_hambre` = TCP starvation. Section numbers (§n) in the comments of `campaign.py`, `runner.py` and `f2lib.py` refer to the project's internal lab notebook; those three files are left unchanged because their hashes are recorded in every run's `meta.json`.

## 1. What is in this repository

| Path | Content |
|---|---|
| `F3_protocolo/PROTOCOL_v3.1_EN.md` | English translation of the experimental protocol, frozen before the pilot and the campaign. SHA-256 of the frozen original (Spanish; recorded in every run's `meta.json`): `c84b7f584a29fad92d905746494c9005860a948e52f89df8ced7853e798e2f8f` |
| `F5_analisis/ANALYSIS_PLAN_v2_EN.md` | English translation of the consolidated analysis plan v2, frozen before any test was computed. SHA-256 of the frozen original (Spanish): `335da89f68ecd628a9fd3d6b313d8fc9e30b16516c7477103cec24d1be1182c3` |
| `F5_analisis/MUESTRA_VERIFICACION.json` | Sample fixed by seed for the independent re-computation (fixed before the confirmatory run) |
| `F2_viabilidad/scripts/` | Campaign executor and bench tooling: `campaign.py` (cells, randomized order, validity criteria), `runner.py` (one run), `f2lib.py` (bench control), `gns3api.py`, `prep_session.py`, `configure_all.py`, `modem_backlog.sh`, `host_perf.sh`, pilot analysis (`analyze_pilot.py`, `analyze_p3b.py`) and the shaper diagnostic (`diag_shaper_k1.py`, `diag42_report.py`) |
| `F2_viabilidad/docker/` | Endpoint image (`Dockerfile`) and the UDP probe `udpprobe.py` (send time in the payload; kernel receive timestamp `SO_TIMESTAMPNS`) |
| `F2_viabilidad/ops/qos_guard.sh` | Unattended watchdog used during the campaign (cron) |
| `F2_viabilidad/topology/QoS_F2_viabilidad.gns3` | GNS3 3.0.6 project file (topology only; **no router images**) |
| `F4_campana/campaign/<run>/` | For each of the 4304 valid runs: `meta.json` (cell, configuration, validity checks, host state, seeds and script hashes), `summary.json` (per-flow statistics), `CHECKSUMS.sha256` of the run's raw files, and `fqc_flows.txt` for fq_codel runs |
| `F4_campana/campaign/*.json` | Campaign state, randomized orders per session block (with seeds), deferral history, list of runs measured on battery |
| `F4_campana/pilot/<run>/` | Same metadata (`meta.json`, `summary.json`, `CHECKSUMS.sha256`) for the 225 pilot runs that fixed the P3b parameters |
| `F5_analisis/code/` | Analysis code (Section 3) |
| `F5_analisis/results/` | `runs.csv` (one row per run, recomputed from the raw files), all tables (`*.txt`, `*.csv`), `numbers.json`, figures (`paper_fig*.png`, `paper_fig0_topologia.pdf`) and draft captions (`FIGURAS_PIES.md`) |

## 2. What is not in this repository, and where it is

| Item | Size | Where |
|---|---|---|
| Packet captures of every run (`sink.pcap`, `src_*.pcap`) | 14 GB | Zenodo data record [10.5281/zenodo.23604110](https://doi.org/10.5281/zenodo.23604110) |
| Per-packet probe traces (`send_*.csv`, `recv_*.csv`), iperf3 JSON, router/modem text logs of every run | ≈ 6.2 GB (CSV 5.3 GB; JSON 0.47 GB; text 0.40 GB) | same Zenodo record |
| Invalid attempts kept with their reason (`F4_campana/campaign/_invalid/`) | 1.2 GB | same Zenodo record |
| Cisco IOS images (IOU L3 15.5(2)T, c7200 15.3(3)XB12) | — | **Not distributed** (licensed). The project file references them by name only |

Every raw file is covered by the `CHECKSUMS.sha256` of its run folder, so the archive can be verified against this repository
(`sha256sum -c CHECKSUMS.sha256` inside each run folder). Campaign checksums were written, and flushed to disk, when each run closed.
Pilot checksums were generated on 23 October 2026: two pilot captures (`sink.pcap` of the CBWFQ and LLQ runs `E1_IOU_*_L1000k_k3_m0.2_c1_f1514_r05`)
had been damaged on the local disk after the pilot and were restored from the synchronized cloud copy; the restored files match the damaged ones outside
the zeroed blocks, and the pilot analysis reproduces exactly with them.

## 3. How to reproduce each result

Environment used: Python 3.12.3 with the versions in `requirements.txt`. Bench: Ubuntu 24.04 (kernel 7.0.0-38 for the campaign; the pilot ran on 7.0.0-34),
GNS3 3.0.6, Docker 29.8.1, Dynamips 0.2.25, endpoints Debian 12.15 with iperf 3.12 and tcpdump 4.99.3, AMD Ryzen 5 7535HS,
CPU governor `performance` with C2/C3 disabled.

Scripts marked **raw** need the Zenodo archive unpacked into `F4_campana/` (same folder names). The rest run from this repository alone.

| Output in `F5_analisis/results/` | Script (`F5_analisis/code/`) | Needs |
|---|---|---|
| `runs.csv` | `load_runs.py` | raw |
| `AUDITORIA.txt`, `inclusion_por_celda.csv` | `audit.py` | `runs.csv` |
| `VALIDACION.txt` (pilot reproduction, shuffled labels, synthetic H3) | `validate.py`, then `validate_extra.py` | raw (pilot) for part 1 |
| `CONFIRMATORIO.txt`, `H1.csv`, `CNEG.csv`, `H2.csv`, `H3.json`, `H3_residuos.csv`, `H4.csv`, `H4_suelo.csv`, `H5.csv`, `CPOS.csv`, `E4a.csv`, `celdas.csv`, `numbers.json`, `VERIFICACION_MUESTRA.json` | `confirm.py` | `runs.csv`, run metadata |
| `SENSIBILIDAD.txt`, `sens_5*.csv` | `sens.py` (uses `core.py`, which reproduces `confirm.py`) | `runs.csv`; raw `_invalid/` for 5.5 |
| `CIERRE_55_H4.txt`, `H4_direccion.csv` | `close55_h4.py` | raw `_invalid/` |
| `EXPLORATORIO_COLAPSOS_8ms.txt`, `expl_colapso_correlacion.csv`, `corridas_atipicas_voz.csv` | `explore_collapse.py` | raw |
| `EXPLORATORIO_SEC6.txt`, `expl_mos_celdas.csv`, `expl_mos_sens.csv` | `explore_sec6.py` | raw (MOS) |
| `EXPLORATORIO_TCP_SHAPER.txt`, `expl_colapso_tcp.csv` | `explore2.py` | raw (pcaps). The IOU tx-ring value was read on the live bench (`show controllers`) and is not reproducible from files |
| `REIMPLEMENTACION_CAPTURAS.txt` | `reimpl_capture.py` (own pcap reader) | raw (pcaps) |
| `paper_fig1`–`paper_fig5` | `figures_paper.py` | `runs.csv` and the CSV/JSON outputs above |
| `paper_fig6_colapso.png` | `figures_paper.py` | raw (two runs) |
| `paper_fig0_topologia.pdf/.png` | `fig_topologia.py` | — |
| `EXPLORATORIO_E4B_COTA.txt`, `E4b_cota.csv`, `numbers_e4b.json` (c7200 CBWFQ against the RFC 2212 bound, exploratory) | `explore_e4b_bound.py` (`python3 explore_e4b_bound.py > ../results/EXPLORATORIO_E4B_COTA.txt`) | `runs.csv`, `E4a.csv` |

Example from a clean clone (no raw data needed):

```
python3 -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt
cd F5_analisis/code
python3 audit.py && python3 confirm.py && python3 sens.py
```

Without the raw archive, `sens.py` reports sensitivity 5.5 as not computed (it needs `_invalid/`) and leaves its stored table unchanged.

To re-run the campaign itself you need GNS3 3.0.6 with the two IOS images (not provided), the endpoint image built from `F2_viabilidad/docker/`,
and `F2_viabilidad/scripts/prep_session.py` followed by `campaign.py campaign1` / `campaign2` (and the blocks `campaign1c`, `campaign1b`, `campaign1k`).
`campaign.py --dry-run` prints the cells and the randomized order without running anything.

## 4. Parameters fixed before the campaign (P3b)

Warm-up W = 20 s; 40-s measurement window (60-s runs); n = 17 runs per cell (two sessions on different days); minimum effect of interest
3.02 ms at 0.5 Mbit/s and 2.00 ms elsewhere; modem-queue threshold 6840 B; host-load threshold 1.70 (c7200 runs: 1.70 plus the idle load of
Dynamips measured at the start of each session). Changes made after the protocol was frozen are listed in the manuscript (Table [DEV]) and marked [D] in the analysis plan. One rule was added after the analysis plan was frozen and before H5 was computed: any zero goodput in the measurement window counts as starvation in H5 (see `confirm.py`).

## 5. Licence and citation

- Code: MIT (`LICENSE`).
- Data and results (`F4_campana/`, `F5_analisis/results/`): CC BY 4.0 (`LICENSE-data`).
- Cite with `CITATION.cff`.
