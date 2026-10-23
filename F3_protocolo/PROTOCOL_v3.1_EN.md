# Experimental protocol — uplink QoS for voice on a home-office link (v3.1)

**English translation of the frozen protocol.**
- The original, in Spanish, was frozen on 10 October 2026 at 10:17 (UTC−5), before the pilot and the campaign.
- SHA-256 of the original: `c84b7f584a29fad92d905746494c9005860a948e52f89df8ced7853e798e2f8f`. The same hash is recorded in the `meta.json` of every pilot and campaign run. A hash identifies content, not a date.
- The original is available from the authors on request.
- This translation renders the design, hypotheses, analysis and rules in full. It omits notes on the drafting history and cross-references to the project's internal working notes. Section numbers are those of the original.

**Two-step freezing.**
- **P3a** is this document.
- **P3b** are the numerical values that the pilot obtains with the rules of §10. They were recorded, with their date, before the first campaign run (README §4).
- Anything decided later is reported as a post-freeze change or as exploratory analysis.

**Inputs:**
- the exploratory feasibility tests (phase F2, 9–10 October 2026);
- the analysis of related work;
- the standards ITU-T G.107, G.113 and G.114 and IETF RFC 2212, 3550 and 5976, checked against their official texts.

Identifiers in `code font` (cell names, file names, flags such as `tcp_hambre`) are kept as they appear in the code and data.

---

## 0. What is confirmatory and what is not

- **Exploratory:** all of F2 (9–10 October 2026), including the reservation and Bc tests of 10 October.
- The hypotheses were formulated after seeing F2 (v0, 9 October) and revised on 10 October in successive versions:
  - v1: dependence on the reservation rule;
  - v2: RFC 2212 bound, H3 only with k = 3, paired tests;
  - v3: negative control between CBWFQ and LLQ, H3 references per variable, MOS.

  No F2 data are used as confirmatory evidence.
- **Confirmatory:** only the F4 campaign, run under this frozen protocol with new data. Any analysis not foreseen here is presented as exploratory.

## 1. Research question

On a slow shared uplink (home office), in which region of **(line capacity L, number of saturated classes k, voice reservation, competing frame size, number of calls)** does CBWFQ stop protecting voice, so that LLQ is needed? How much over-reservation makes CBWFQ sufficient? What does LLQ cost the other classes? How do fq_codel and CAKE compare?

The gaps addressed are described in the related-work section of the manuscript. No claim is made to be the first CBWFQ/LLQ comparison in GNS3 (Hirchoren and Buraczewski, 2020).

## 2. Hypotheses

Notation, per run:
- `T_s = MTU_L2 · 8 / L`: transmission time of the competing frame on the line.
- `T_r = M · 8 / B_v`, with M = 214 B (layer-2 voice frame): time of one voice packet at the reserved rate `B_v`.
- `Δ = p99(CBWFQ) − p99(LLQ)` of the voice one-way delay, between paired runs of the same block.

**Reference bounds (from theory, not from the bench):**
- LLQ, **p99 bound**: non-preemptive priority argument. Voice waits at most for the competing frame in transmission: `≈ T_s + T_voz`. This does not come from Fischer et al. (2008).
- Fischer et al. (2008) give the exact mean waiting time of the priority class, with Poisson arrivals and load < 1. They are kept **only as related work**: in the campaign voice is constant-rate and the cells with competition are saturated, so there are no cells where it applies.
- CBWFQ: weighted-fair-queuing bound according to **RFC 2212**, checked against the official text: delay ≤ `(M + C)/R + D`, with "C is set to M" and "D is set to the link MTU divided by the link bandwidth". For constant-rate voice and one hop: **delay ≤ 2·T_r + T_s**.
  - Parekh and Gallager (IEEE/ACM ToN, 1993) are cited only as the origin of the discipline. Their Theorem 1 was checked against the paper; the σ/g form was not.

**Hypotheses:**
- **H1 (one competitor: equivalence).** With k = 1 and voice within its reservation, CBWFQ and LLQ are equivalent in voice p99.
  - Test: TOST with margin δ = minimum effect of interest (EMI), fixed before the campaign (§10).
  - The p99 of both stays close to the LLQ bound, `T_s + T_voz + floor(L)`.
- **H2 (several classes: LLQ advantage).** With k ≥ 2 and the base reservation (m = 0.2), Δ > 0 at every L (paired test, §11).
- **H3 (what the advantage depends on; k = 3 only).** Two regressions on T_s and T_r, **only with k = 3**, which is where the design varies T_r (E1-R). With k = 2, T_r is constant and b is not identifiable; this is stated. Each regression is compared with its theoretical reference:

  | Variable | Model | Reference for a (T_s) | Reference for b (T_r) |
  |---|---|---|---|
  | CBWFQ p99 | `p99 ≈ a·T_s + b·T_r + c` | 1 | 2 |
  | Δ = CBWFQ p99 − LLQ p99 | `Δ ≈ a·T_s + b·T_r + c` | 0 (T_s cancels: the LLQ bound contains it too) | 2 |

  - IOS does not implement the ideal discipline (Masi et al., 2007): how far it departs is reported.
  - An a > 0 in Δ would mean that IOS CBWFQ makes voice wait for more than one competing frame, which the ideal discipline does not do. In F2 (exploratory) Δ/T_s was about 2.
  - Practical result: **minimum over-reservation** m*(L) at which the CBWFQ p99 falls below each budget (§9), with CI. It is estimated with four levels of m (0.2, 0.5, 1, 3). Between levels it is interpolated in log(1 + m), and the resolution is stated.
- **H4 (fq_codel and CAKE).**
  - fq_codel gives voice a p99 comparable to LLQ's as long as its rate is below its flow's share (≈ R / number of active flows, recorded per run).
  - CAKE `diffserv4` does the same as long as voice does not exceed the threshold of the Voice tin (25 % of R; above it voice loses priority, it is not dropped; `tc-cake(8)`).
  - Above those thresholds, both degrade.
  - Because the burst reaching the modem differs between platforms (§3), each policy is also compared with the floor of **its own** platform (§7.8, §11).
- **H5 (cost of LLQ).** With voice within the priority rate, the TCP goodput of data and residential traffic under LLQ is not lower than under CBWFQ by more than **δ_c = 5 % of the CBWFQ goodput** (TOST). With voice above it (1.5 × B_v) it is measured without a directional hypothesis.

## 3. Testbed

- GNS3 3.0.6. Reduced topology:
  - endpoints CW-VOZ and CW-DAT (VLAN 10) and RES-1 (VLAN 20);
  - GNS3 built-in switch (802.1Q trunk);
  - **R-BORDE** (IOU L3 15.5(2)T) and **LXR** (Linux `tc`) in parallel;
  - **MODEM** (Linux, `netem rate` = L, 64-packet queue) and SINK.
  - IOSv is added for E4(b) if it passes tests 2.3 and 2.4. **If it does not, E4(b) is withdrawn, this is stated in the paper, and fidelity rests on E4(a), (c) and (d).**
- Docker endpoints `qos-endpoint:f2` (Debian 12, iperf 3.12); the image digest is stored in every `meta.json`.
- Host: Ubuntu, kernel 7.0.0-34, AMD Ryzen 5 7535HS, on mains power. CPU governor `performance` and C2/C3 disabled (mandatory).
- **R-BORDE:**
  - `ip cef`, `no cdp run`, `no keepalive`;
  - PARENT `shape average R Bc 0` with R = 0.95·L, **Bc = R × 4 ms** (the minimum IOS accepts) and **Be = 0**. This replaces condition 2 of the previous phase, which cannot be realized; it is stated in the paper.
  - Burst reaching the modem ≈ Bc + 1 frame: ≈ 4 frames at 10 Mbit/s and ≈ 2 at ≤ 2 Mbit/s (F2, exploratory).
  - The executor **aborts** the run if `show policy-map interface` does not show PARENT applied (IOS can accept the configuration and silently not apply it).
- **LXR:** HTB root at R (`burst`/`cburst` 1600 B) with a pfifo leaf (`limit` Q) or fq_codel (defaults); CAKE `bandwidth R diffserv4`; GSO/TSO/GRO disabled (Beshay et al., 2015).
- **Burst asymmetry between platforms** (IOU ≈ Bc; HTB 1600 B; CAKE no burst):
  - positive control on both platforms (§6, C);
  - each policy is compared with the floor of its platform;
  - FIFO-C versus FIFO-L is reported as a difference between benches;
  - sensitivity cells with the HTB burst set equal to Bc (§6, S).

## 4. Policies

| Code | Platform | Configuration |
|---|---|---|
| FIFO-C | IOU | PARENT only; FIFO with `queue-limit` Q |
| CBWFQ | IOU | CHILD: voice `bandwidth B_v`; video `bandwidth B_vid`; data `bandwidth B_dat`; class-default `fair-queue` |
| LLQ | IOU | Same, with voice in `priority B_v` |
| FIFO-L | Linux | HTB at R + pfifo `limit` Q |
| FQC | Linux | HTB at R + fq_codel |
| CAKE | Linux | `cake bandwidth R diffserv4` |

- **Reservations in kbit/s:**
  - `B_v = calls × 85.6 × (1 + m)`;
  - `B_vid = 0.25 × R`;
  - `B_dat = 0.20 × R`.
- **The policy-map is identical for every k:** the video and data classes exist even when they carry no traffic (k = 1 or 2). Feasibility and weights therefore do not change with k.
- **Feasibility.** IOU applies the policy up to a total reservation of 99 % of R and silently rejects it from 100 % (`F2_viabilidad/results/t_c12_reservations.jsonl` and `t_c2_limit.jsonl`).
  - Rule: a cell is feasible if `B_v + B_vid + B_dat ≤ 0.99·R`.
  - Infeasible cells are excluded and listed by script in `cells_excluded.csv`.
- **CAKE and marking.** The same DSCP on all platforms. In `diffserv4`, AF41 (video) and AF21 (data) share the Video tin; this is stated. In CAKE, k = 3 means two tins (Video and Best Effort) plus voice.
  - Sensitivity: 2 cells with data re-marked to CS1 (CAKE Bulk tin), to have three distinct tins (§6, S).

## 5. Traffic

Nested design in k:

| Class | Present when | Generator | DSCP | Profile |
|---|---|---|---|---|
| Voice | always | `udpprobe.py` | EF | G.711 at 20 ms: 172 B of UDP (214 B at layer 2, 85.6 kbit/s) per call |
| Residential | k ≥ 1 | iperf3 TCP (1 flow) + `udpprobe.py` UDP of 1472 B at 0.8·L | 0 | Bulk |
| Video | k ≥ 2 | `udpprobe.py` UDP of 1000 B at 0.6·L | AF41 | Fixed fraction of L |
| Data | k = 3 | iperf3 TCP (1 flow) | AF21 (CS1 in the 2 CAKE sensitivity cells) | Bulk, reactive |

- Opus and the video-call profile of MacMillan et al. (2021) are outside the confirmatory campaign.
- Offered load is measured at the sender and goodput at the receiver; utilization is reported as measured.

## 6. Experiments

- **Unit of analysis:** the run.
- **Duration:** 40 s of measurement plus warm-up (fixed by the pilot; initial proposal 5 s).
- **Base:** 1 call, m = 0.2, competing frame of 1514 B, Q = 64.

| Exp. | Question | Factors | Cells |
|---|---|---|---|
| **E1** | H1, H2, H4 | k = 1 and k = 3: the 6 policies × L {0.5; 1; 2; 5; 10} (60). k = 2: CBWFQ, LLQ, FQC, CAKE × 5 L (20) | 80 |
| **E1-R** Reservation | H3, over-reservation | CBWFQ, LLQ × 5 L × m {0.5; 1; 3}; k = 3. Excluded as infeasible: L = 0.5 with m = 3. (m = 0.2 is in E1) | 28 |
| **E2** Frame and calls | Does the boundary move? | CBWFQ, LLQ, FQC, CAKE × L {0.5; 1; 5} × frame {590; 1514} B × calls {1; 4}; k = 3. Excluded: L = 0.5 with 4 calls | 40 |
| **E3** Cost | H5 | CBWFQ, LLQ × L {1; 5} × voice {within the reservation; 1.5 × B_v}; k = 3 | 8 |
| **E4** Fidelity | Bench versus theory, another emulator and hardware | (a) no new runs: LLQ of E1 versus the non-preemptive priority bound and **CBWFQ of E1/E1-R versus 2·T_r + T_s (RFC 2212)**; (b) IOSv versus IOU: L {1; 5} × k {1; 3} × {CBWFQ, LLQ}; (c) repetition of 4 E1 cells on another day; (d) the scenarios of Hirchoren et al. (2017; 384 kbit/s, cells labelled `Q004`) and Luca et al. (2016; 480 kbit/s, cells labelled `Q034`) versus their hardware figures (without c7200) | ≈ 18 |
| **S** Sensitivity | Does the result survive our choices? | On L {1; 5} × k 3 × {CBWFQ, LLQ}: Q {16; 256}, shaper fraction 0.90, Be = Bc (IOS default) and a 120-s duration (20). HTB burst = Bc with FQC at L {5; 10}, k 3 (2). CAKE with data in CS1, L {1; 5}, k 3 (2) | 24 |
| **S-H** Loaded host | Robustness to the state of the machine | CBWFQ, LLQ × L {1; 5}; k = 3; 10 of 12 cores busy; without the host-load invalidity criterion | 4 |
| **C** Controls | §7 | Negative: CBWFQ and LLQ with all traffic unmarked, k {1; 3} × 5 L (20). Positive, on both platforms: FIFO-C and FIFO-L at 0.5·R × 5 L (10) | 30 |

**Total ≈ 232 cells** (80 + 28 + 40 + 8 + 18 + 24 + 4 + 30). The cost is computed with the time per run measured in the pilot. Unmeasured estimate at ~75 s per run: about 145 h with n = 30 and about 97 h with n = 20.

## 7. Mandatory controls

1. **Negative.** With all traffic unmarked, everything falls into `class-default`, which is identical in both policies.
   - Criterion: **unmarked CBWFQ ≡ unmarked LLQ** (TOST, δ = EMI), at k = 1 and k = 3. This shows that the difference between them comes from classification and priority.
   - FIFO-C is reported as a reference, without a pass criterion. It is not expected to match, because `fair-queue` shares per flow and protects voice even when it is unmarked. What it measures (how much `fair-queue` protects on its own) is a result for the paper.
   - The pilot includes this control (§10) to confirm the behaviour before the campaign.
2. **Positive**, on IOU and on Linux: without congestion (0.5·R), FIFO-C and FIFO-L stay at the floor of their platform and L.
3. **Packet accounting:** per class on R-BORDE (UDP), aggregated on LXR, and for TCP from captures at the sender and at SINK.
4. **Offered load and received goodput**, measured.
5. **Randomized order** with a seed, in blocks (each block contains all policies of one factor combination), in at least two sessions on different days.
6. **Warm-up** discarded.
7. **`meta.json` per run:**
   - effective configuration and `tc -s` before and after;
   - modem queue in bytes every 20 ms;
   - for FQC, active flows (`new_flows_len` and `old_flows_len`, sampled);
   - CPU power state, host load and IOU CPU;
   - seed, script hashes, image digest and versions.
8. **Floor per L and per platform** (voice alone, through IOU and through Linux): 10 runs per L, platform and session.

## 8. Invalidity criteria (automatic; the run is stored separately with its reason and repeated)

- The PARENT policy is not applied.
- Accounting mismatch > 1 %.
- Shaper rate outside R ± 5 % under saturation.
- Modem queue > Bc + 2 frames + 3 voice packets (in bytes), or any drop at the modem. Threshold derived from F2; the pilot revises it.
- Governor other than `performance`, or deep C-states enabled.
- **Host load** above **the maximum 1-min load average observed in the pilot × 1.5**. The pilot is run **with no other use of the machine**. Not applied in S-H.
- Input "ignored" counters or buffer failures on R-BORDE that grow during the run.
- Incomplete receiver or iperf3 output, or a probe count that does not add up.
- **A failure is never recorded as 0 or filled in with a value.**

## 9. Metrics

- **Voice:**
  - one-way delay p50, p95 and p99 per run, and loss;
  - RFC 3550 §6.4.1 jitter: `J(i) = J(i−1) + (|D(i−1,i)| − J(i−1))/16`, with `D(i,j) = (Rj − Ri) − (Sj − Si)`.
- **R factor and MOS (secondary, estimated metric).** Computed after the campaign from the per-packet traces, without extra runs. Equations of ITU-T G.107 (06/2015), transcribed from the PDF:
  - (7-1) `R = Ro − Is − Id − Ie-eff + A`;
  - (7-18) `Id = Idte + Idle + Idd`;
  - (7-27) `Idd = 25·{(1 + X^(6·sT))^(1/(6·sT)) − 3·(1 + [X/3]^(6·sT))^(1/(6·sT)) + 2}` if `Ta > mT` (`Idd = 0` if `Ta ≤ mT`);
  - (7-28) `X = log(Ta/mT)/log 2`;
  - (7-29) `Ie-eff = Ie + (95 − Ie)·Ppl/(Ppl/BurstR + Bpl)`;
  - (B-4) `MOS = 1 + 0.035·R + R·(R − 60)·(100 − R)·7·10⁻⁶` for 0 < R < 100 (1 if R < 0; 4.5 if R > 100).

  **Computation per run** (voice, without the warm-up):
  1. `d_i` = one-way delay of packet i; `d_min` = the minimum of the run.
  2. Static playout buffer of size `B`: packet i is late if `d_i > d_min + B`.
  3. `Ppl` = (lost in the network + late) / sent, in %. G.113 states that the loss that counts is the loss at the buffer output.
  4. `Ta = d_min + B + T_resto`.
  5. `R = 93.2 − Idd − Ie-eff` (other parameters at their defaults, R = 93.2); MOS with (B-4).

  **Parameters (fixed before the campaign):**

  | Parameter | Main case | Sensitivity | Origin |
  |---|---|---|---|
  | Buffer `B` | 60 ms | 40 and 100 ms | Project choice; not from a standard |
  | Delay of the rest of the path `T_resto` | 100 ms | 50 and 150 ms | Project choice; not from a standard |
  | `Bpl` of G.711 | 4.3 (no concealment) | 25.1 (with concealment) | G.113 (09/2024), Table I.4 |
  | `Ie` of G.711 | 0 | — | G.113, Tables I.1 and I.4 |
  | `BurstR` | 1 | — | G.113: the burst adjustment is only recommended with Bpl ≥ 16 |
  | `sT`, `mT` | 1 and 100 ms | — | G.107, Table 1, default class |

  **Simplifications stated in the paper:**
  - only `Idd` is used; `Idte` and `Idle` (echo) stay at their defaults;
  - the Bpl values of Table I.4 are for 10-ms packets, and the probe uses 20 ms;
  - the buffer is static (G.113 refers to G.1020 for emulating one; G.1020 was not consulted);
  - the MOS is estimated by a planning model, not measured; quality on real audio (PESQ, POLQA) is out of scope and stated as a limitation.

  **Presentation:** figure of MOS versus `T_resto` per policy, with the main case marked. The conclusion is called robust only if it does not change over the sensitivity range. Sanity check (computed with equation 7-27): Idd = 0 up to Ta = 100 ms, 0.16 at 150 ms, 3.0 at 200 ms and 14.8 at 300 ms; with Bpl = 4.3, 1 % loss gives Ie-eff ≈ 17.9.
- **Cost:** TCP goodput of data and residential traffic, and their RTT.
- **Secondary:** maximum delay (mandatory at L ≤ 1 Mbit/s; Gao and Qian, 2016), loss bursts, drops per class.
- **Delay budgets:**
  - the main result is the **continuous curves**;
  - 20, 50 and 100 ms are presented as **illustrative**. What can be defended: 100 ms is the whole mean-delay budget and 50 ms the whole delay-variation budget of Y.1541 class 0, end to end (according to RFC 5976, which cites the 2006 edition; Y.1541 itself was not consulted). 20 ms is an arbitrary fraction and is stated as such. No standard allocates the budget to the access segment;
  - G.114 (checked): 150 ms one way as the end-to-end target and 400 ms as the maximum; it gives no jitter limit;
  - the 30 ms of jitter and 1 % of loss are Cisco design recommendations and are not attributed to the ITU.
- **Double path:** the delay is recomputed from `tcpdump` captures at the sender and at SINK in 10 % of the runs, stratified (at least one per cell), and in all pilot runs. p99 discrepancy ≤ 0.1 ms.

## 10. Pilot and sample size

- **Pilot cells:**
  - E1 with L {0.5; 1; 5}, k {1; 3}, CBWFQ and LLQ;
  - **FQC and CAKE with L = 1 and k = 3** (time per run and host load on Linux);
  - E1-R with L 1 and m 3;
  - **negative control with L = 1 and k = 3** (unmarked CBWFQ and LLQ, plus FIFO-C), to confirm the behaviour of `class-default`;
  - floor per L and platform;
  - 5 runs per cell. Not part of the confirmatory analysis.
- **The pilot is run with no other use of the machine** (it sets the load threshold).
- **Double path in every pilot run.**
- **Rules frozen in P3a; the pilot only applies the rules, it does not choose the values:**

  | Value | Rule |
  |---|---|
  | **EMI** (= δ of H1 and of the negative control; basis of the computation of n) | The larger of **2 ms** and **10 % of the LLQ p99 at that L**, measured in the pilot. It is a threshold of practical relevance: the pilot only checks that it is detectable with n ≤ 30 (at 0.5 Mbit/s the range of the floor with the line is about 1.7–2.4 ms). If it is not, this is reported and the lead author decides |
  | **n per cell** | The smallest n between 10 and 30 that gives power 0.80 (α = 0.05 with Holm) for the EMI, with the between-run deviation of the pilot in the **noisiest cell**. If more than 30 are needed, this is reported and the lead author decides |
  | **Warm-up** | The smallest multiple of 5 s after which the median delay in 5-s windows stops changing by more than the range of the floor, in all pilot cells |
  | **Duration** | 40 s, unless the 40-s and 120-s p99 differ by more than the EMI in the pilot; then 120 s |
  | **Modem queue** (§8) | The maximum observed in the pilot in valid runs, plus one frame |
  | **Host load** (§8) | Maximum 1-min load average of the pilot × 1.5 |
  | Time per run | Measured (actual machine hours) |

- The resulting values are recorded with their date (**P3b**) before the first campaign run.

## 11. Analysis plan (F5)

- **Per cell:** median across runs and 95 % CI by bootstrap (10 000 resamples, fixed seed); Cliff's delta with CI.
- **H1 and negative control:** TOST of the CBWFQ − LLQ p99 difference, paired by block, with margin δ = EMI.
- **H2:** **paired** test per cell on Δ (sign permutation; Wilcoxon signed-rank as a check); Holm per family (experiment × k).
- **H3** (k = 3): two regressions on E1 + E1-R (m {0.2; 0.5; 1; 3}), with bootstrap 95 % CIs for a and b: CBWFQ p99 (reference a = 1, b = 2) and Δ paired by block (reference a = 0, b = 2). Practical result: m*(L) for each budget, interpolating in log(1 + m).
- **H4:**
  - LLQ versus FQC and CAKE per cell, Holm per family (experiment × k);
  - each policy is also reported as excess over the floor of its platform;
  - region where FQC and CAKE stop meeting the hypothesis, with the number of active flows as a covariate.
- **H5:** TOST of the TCP goodput with δ_c = 5 %.
- **Boundary:** L* where the CBWFQ p99 crosses each budget, interpolated in log L, with bootstrap CI.
- **E4(a):** LLQ p99 versus `T_s + T_voz` (non-preemption) and CBWFQ p99 versus `2·T_r + T_s` (RFC 2212), in each E1/E1-R cell (ratio measured / bound, with CI).
- **Re-implementation by another path:** percentiles and jitter recomputed from the captures, with different code.
- **Comparison with the literature:** E4(d) versus Hirchoren et al. (2017) and Luca et al. (2016).
- Each figure is opened and checked visually. Every number in the manuscript comes from `results/numbers.json`.

## 12. Threats to validity

- IOU is not hardware: mitigated with E4; absolute figures are stated as properties of the bench.
- The policy acts on the uplink only.
- The line is `netem rate`, without a real physical layer. The IOS minimum Bc (Tc ≥ 4 ms, Be = 0) and the 0.95 fraction determine where the queue forms; the burst differs between platforms (§3).
- Synthetic traffic; one TCP flow per class.
- In CAKE, video and data share a tin under standard marking (§4); sensitivity with CS1.
- A single host: CPU power state and load change the magnitude → invalidity criterion and S-H.

## 13. Before freezing

1. Pending decisions of the lead author: resolved.
2. Standards: G.113 checked; Y.1541 only through RFC 5976; budgets illustrative.
3. IOU reservation threshold: done (≤ 0.99·R).
4. Validate IOSv (2.3 and 2.4) and repeat 2.3 with minimum Bc and Be = 0 at 1 and 10 Mbit/s.
5. Implement in the executor:
   - reservations in kbit/s with feasibility;
   - TCP with accounting from captures;
   - fq_codel flow sampling;
   - configurable HTB burst;
   - re-marking to CS1;
   - MOS computation (§9) in the analysis, from the traces;
   - randomization in blocks with a seed;
   - invalidity criteria and per-run resumption.

## 14–16. Version history

**v1 → v2.**
- Minimum Bc and Be = 0, stated (§3).
- CAKE: marking limitation stated, and 2 cells with data re-marked to CS1 (Bulk) (§4, §6 S).
- Host-load threshold derived from the pilot (§8, §10).
- Continuous curves; budgets illustrative (§9).
- Double path in 10 % of runs, stratified, plus the whole pilot (§9, §10).
- EMI from the pilot (§10); δ of H1 = EMI, fixed beforehand (§2, §11); δ_c = 5 % (§2, §11).
- Burst asymmetry: positive control on both platforms, floor per platform, FIFO-C versus FIFO-L, HTB burst = Bc (§3, §6).
- H3 only with k = 3 (§2, §11). TOST margin not taken from the data.
- Identical policy-map for every k (§4).
- RFC 2212 for the CBWFQ bound, checked against the official text; E4(a) with CBWFQ versus 2·T_r + T_s (§6, §11).
- Paired test in H2 (§11).
- G.107 transcribed from the PDF: equations 7-1, 7-18, 7-27, 7-28, 7-29 and B-4 and Table 1.
- Control count corrected: v1 stated 15 control cells, but its own description added up to 25.

**v2 → v3.**
- Negative control "unmarked CBWFQ ≡ unmarked LLQ" with both policies, FIFO-C as a reference, and a cell in the pilot (§6 C: 20 negative-control cells; §7.1; §10; §11). An LLQ-only negative control considered in v2 was dropped: without marks, `fair-queue` also protects voice.
- H3 with two regressions and their references (§2, table; §11).
- Host-load threshold = pilot maximum × 1.5, pilot with no other use of the machine (§8, §10).
- m = 0.5 added to E1-R (+10 cells; L = 0.5 with m = 0.5 reserves 72 % of R, feasible).
- MOS specified (§9).
- FQC and CAKE in the pilot (§10).
- Fischer et al. (2008) separated from the p99 bound (§2, §11).
- G.113 and Y.1541 resolved (§9). Sanity check of the MOS equations by script: Idd (7-27) = 0 / 0.16 / 3.04 / 14.76 / 24.07 at 100 / 150 / 200 / 300 / 400 ms; Ie-eff (7-29) with 1 % loss = 17.92 (Bpl 4.3) and 3.64 (Bpl 25.1).
- Count: 232 cells (80 + 28 + 40 + 8 + 18 + 24 + 4 + 30).

**v3 → v3.1 (frozen, P3a).**
- Two-step freezing (header; §10).
- EMI rule (§10, rules table).
- Rules for n, warm-up, duration, modem queue and host load (§10, rules table).
- Exit if IOSv fails tests 2.3/2.4 (§3).
- Fischer et al. (2008) removed from E4(a) and §11; kept as related work (§2, §6, §11).

Nothing else changed: design, hypotheses, analysis and cell count (232) are those of v3.
