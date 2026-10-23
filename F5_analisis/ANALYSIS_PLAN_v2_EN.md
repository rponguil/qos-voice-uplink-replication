# Consolidated analysis plan (F5), v2 — uplink QoS for voice on a home-office link

**English translation of the frozen analysis plan.**
- The original, in Spanish, was frozen on 17 October 2026 at 21:14 (UTC−5), before any test was computed.
- SHA-256 of the original: `335da89f68ecd628a9fd3d6b313d8fc9e30b16516c7477103cec24d1be1182c3`. A hash identifies content, not a date.
- The original is available from the authors on request.
- This translation renders every test, rule, seed and output in full. It omits notes on the drafting and review history and cross-references to the project's internal working notes. Section numbers are those of the original.

**Sources it consolidates:**
- the frozen protocol (P3a; `F3_protocolo/PROTOCOL_v3.1_EN.md`, original SHA-256 `c84b7f58…98e2f8f`): §§2, 6, 7, 9 and 11;
- the P3b values;
- decisions taken after the protocol was frozen.

**Markers:**
- **[P3a]**: taken literally from the frozen protocol.
- **[P3b]**: value obtained by the pilot with the frozen rules (README §4).
- **[D]**: decision taken after the protocol was frozen and before any test was computed.
- **[OP]**: operationalization, fixed in this plan, of something the protocol left unspecified.

No test had been computed when this plan was written. The only campaign data inspected were descriptive and did not compare policies: completeness, checksums, invalidity reasons, floors at 1 Mbit/s and the LXR ingress log.

Identifiers in `code font` (cell names, file names, flags such as `tcp_hambre` and `marcada`) are kept as they appear in the code and data.

---

## 1. Data and inclusion rules

### 1.1 Runs

- **Directory:** `F4_campana/campaign/`, one folder per valid run. The list is `state.json["done"]` (4304 runs).
- **Runs in the main analysis:**
  - the 233 cells × repetitions 1–17 and the 12 floors × repetitions 1–20;
  - **the 103 runs listed in `battery_runs_20261014.json` are replaced by their `_ac` repeat** [D]. The original is kept only for sensitivity §5.4;
  - **the 10 IOU cells with k = 1 at 2 and 3 Mbit/s** (`SHAPER_EXEMPT`) enter with their measured shaper rate (`shaper_rate_bps`, `shaper_err`) [D];
  - **runs flagged for input losses** (`marcada` = true) enter [D]; the sensitivity analysis excludes them (§5.1);
  - **the c7200 enters only in E4(b)** and in its floor [D].
- **Not included:** the attempts in `_invalid/` (except in sensitivity §5.5), the runs in `pilot/`, `csmoke*/`, `diag42/` and `fix_tests/`, and the withdrawn cells (c7200 at 5 Mbit/s).

### 1.2 Blocks and pairing

- **Block:** the cell identifier without platform or policy, plus the repetition. For example, `E1_L2000k_k3_m0.2_c1_f1514` r05 contains the six E1 policies with L = 2 Mbit/s and k = 3 in repetition 5.
- **CBWFQ–LLQ pair:** the two runs of the same block and repetition.
  - If a run was replaced by its `_ac` repeat, the pair uses the `_ac` run.
  - Checked: no CBWFQ–LLQ pair was split by the power cut of 14 October. Either both members of each pair are in the battery list or neither is. The only split block is E2 5 Mbit/s k = 3 r09, and only in CAKE.
  - The same pairing is used for LLQ versus FQC and CAKE (H4), whose blocks include both platforms.
- **The 10 exempt cells:** their repetitions 1–9 were run as a block of their own (`campaign1k`) and 10–17 in session 2. The pair is formed in the same way, by repetition.

### 1.3 Variables per run (recomputed from the raw files)

- **Measurement window:** voice packets with send time in [W, W + D) s, with W = 20 s [P3b] and D = 40 s (D = 120 s in the 4 S cells with 120 s of measurement). Time counts from the first send of that flow.
- **One-way delay:** `recv_ns − send_ns` per packet (`recv_0.csv`, flow 100 = the measured call).
- **Percentile p of the window:** the sorted value at index `round(p · (n − 1))` over the received packets (the same method as `f2lib.owd_stats`).
  - Primary: **p99**. Secondary: p50 and p95.
  - [OP] It is recomputed from the CSV and compared with `summary.json["probe0"]["p99"]`. If any difference exceeds 1 µs, the analysis stops (audit, §3).
- **Voice loss in the window:** 1 − received / sent among the packets sent in the window. [OP] `summary.json` stores the loss of the whole run; the analysis uses the loss in the window.
- **RFC 3550 jitter** over the packets of the window, ordered by sequence number [P3a §9].
- **TCP goodput:** `rx_bps_steady` of the iperf3 server (intervals starting ≥ W and ending ≤ duration − 1 s). The flow is identified by its port in `meta.json["flows"]`: 5302 = data (AF21) and 5301 = residential.
  - With `tcp_hambre` the goodput is 0 and it is counted per cell [D].
- **Shaper rate:** `shaper_rate_bps` and `shaper_err` (window [10, D − 2] s at SINK).
- **Maximum delay** (mandatory at L ≤ 1 Mbit/s [P3a §9]) and, for FQC, active flows (`fqc_flows.txt`, every 100 ms).

### 1.4 Constants

- R = 0.95·L (Q004 scenario: 364.8 kbit/s; Q034 scenario: 480 kbit/s).
- T_s = 1514·8 / L (590·8 / L in the E2 cells with 590-B frames).
- T_voz = 214·8 / L.
- T_r = 214·8 / B_v, with B_v = calls × 85.6 × (1 + m) kbit/s.
- EMI(L) = 3.02 ms at 0.5 Mbit/s and 2.00 ms from 1 to 10 Mbit/s [P3b].

---

## 2. Confirmatory analysis

**Common rules:**
- α = 0.05 per family, with Holm within each family (experiment × k) [P3a §11].
- [OP] Tests of equivalence use the paired TOST with exact t: p_TOST = max(p_lower, p_upper) of the two one-sided t tests on the mean of the paired differences. This is the form with which n was computed.
- "Met" and "not met" are decided with the Holm-adjusted p. Everything is reported as it comes out, including what is not met [D].

### 2.1 H1 — one competitor: equivalence CBWFQ ≡ LLQ

- **Cells:** E1, IOU, k = 1, L ∈ {0.5; 1; 2; 3; 5}. The 2 and 3 Mbit/s cells are exempt, with measured shaper rate [D].
- **Variable:** d_r = p99(CBWFQ) − p99(LLQ) per pair, n = 17.
- **Test:** TOST with margin ±EMI(L). **Family:** H1 (5 L).
- **Met at L** if the adjusted p_TOST < 0.05.
- **Also reported:** mean and median of d with bootstrap 95 % CI, and the p99 of each policy against `T_s + T_voz + floor(L)` (median of the IOU floor at that L) [P3a §2].

### 2.2 H2 — several classes: LLQ advantage (Δ > 0)

- **Cells:** those with m = 0.2 and k ≥ 2 [P3a §2], in three families:
  - E1 × k = 2 (5 L);
  - E1 × k = 3 (5 L);
  - E2 × k = 3: 10 cells, L {0.5; 1; 5} × frame {590; 1514} × calls {1; 4}, without L = 0.5 with 4 calls.
- **Variable:** Δ_r = p99(CBWFQ) − p99(LLQ) per pair.
- **Main test:** **exact** sign permutation (all 2¹⁷ assignments) on the mean of Δ, one-sided (Δ > 0) [P3a §11].
  - Check: Wilcoxon signed-rank, one-sided.
- **Met in the cell** if the adjusted p of the main test < 0.05.
- [OP] The median of Δ with bootstrap 95 % CI and Cliff's delta are also reported.

### 2.3 H3 — what the advantage depends on (k = 3 only)

- **Data:** E1 (m = 0.2) + E1-R (m ∈ {0.5; 1; 3}), IOU, k = 3, the 5 L; 19 cells per policy.
- **Models:**
  - p99(CBWFQ) ≈ a·T_s + b·T_r + c. Reference: a = 1, b = 2.
  - Δ ≈ a·T_s + b·T_r + c. Reference: a = 0, b = 2.
- [OP] **Fit:** ordinary least squares on the per-run observations (CBWFQ p99) and per-pair observations (Δ), with T_s and T_r in ms.
- **Two 95 % CIs for a, b and c**, by percentile bootstrap with 10 000 resamples (seed in §7):
  - (a) [OP] resampling runs or pairs **within each cell** (stratified): measurement uncertainty;
  - (b) [OP] **cluster** bootstrap, resampling the 19 cells whole with all their runs: includes the lack of fit between cells.
- **Compatibility with the reference** (a = 1 and b = 2 for CBWFQ p99; a = 0 and b = 2 for Δ) **is judged with CI (b)** [OP].
- Reported:
  - a, b and c with both CIs and R²;
  - the residuals per cell (cell mean minus the fitted value);
  - [OP] the **lack-of-fit F test**: the linear model against the cell-means model (19 means).
  - With k = 2, T_r is constant and b is not identifiable; this is stated [P3a §2].
- **Practical result (exploratory, §6):** m*(L) per budget.

### 2.4 H4 — fq_codel and CAKE versus LLQ

- **Cells:** E1 with k ∈ {1; 2; 3} and L ∈ {0.5; 1; 2; 3; 5} (the capacities common to both platforms), plus E2 × k = 3.
- **Variable:** p99(X) − p99(LLQ) per block, with X ∈ {FQC, CAKE}.
- **Test that decides "comparable":** [OP] the **TOST** with margin ±EMI(L), which is what H4 states.
  - Holm families: E1 × k (2 comparisons × 5 L = 10 tests per k) and E2 × k = 3 (20 tests).
- **The exact two-sided sign permutation is descriptive** [OP]: it reports the direction and size of the difference, with its unadjusted p, and decides nothing.
- **Also reported** [P3a §11]:
  - the excess of each policy over the median floor of its platform and L;
  - the region where FQC and CAKE stop being comparable, with the number of active FQC flows (median of `new_flows_len + old_flows_len`) as a descriptive covariate;
  - the 25 %-of-R threshold of the CAKE Voice tin against the voice rate of each cell (E2 with 4 calls).
- The cells at 10 Mbit/s only have Linux policies: they are reported descriptively.

### 2.5 H5 — cost of LLQ in TCP goodput

- **Cells:** E3, IOU, k = 3, L ∈ {1; 5}, with voice within the reservation.
- **Variable:** goodput of data and of residential traffic separately; [OP] per pair, **ln(goodput LLQ / goodput CBWFQ)**.
- **Test:** TOST on the mean of that logarithm with margin **[ln 0.95; ln 1.05]** [OP]. This is the P3a question (δ_c = 5 % of the CBWFQ goodput) with the margin fixed beforehand and not estimated from the data.
  - [OP] Family: E3 (2 L × 2 classes = 4 tests).
- **Pairs with `tcp_hambre`** in either member (goodput 0, undefined ratio) [OP]:
  - they are counted and reported separately, and the TOST is computed without them;
  - if a cell and class has **more than 2**, it is reported as **"not evaluable"**.
- **With voice at 1.5 × B_v:** the same ratio, descriptive and without a directional hypothesis [P3a §2].
- `tcp_hambre` is counted per cell.

### 2.6 Controls

- **Negative** [P3a §7.1]:
  - TOST of p99(unmarked CBWFQ) − p99(unmarked LLQ) with margin ±EMI(L);
  - families CNEG × k = 1 and CNEG × k = 3, 5 L each;
  - reported as it comes out [D].
  - Descriptive complement: §6.3.
- **Positive** [P3a §7.2]: FIFO-C and FIFO-L at 0.5·R.
  - [OP] The literal criterion is "they stay at the floor of their platform and L": the median p99(CPOS) − median p99(floor) is reported against EMI(L).
  - Pass or fail is reported with the literal criterion.
  - [OP] **Secondary physical criterion, fixed now:** excess over the floor ≤ T_s + EMI(L). With a 1514-B frame competing, voice can wait up to T_s (24 ms at 0.5 Mbit/s) even without a queue. The literal criterion therefore cannot be met at low L, and the paper explains this if it fails.
  - The excess in units of T_s is also reported.
- **Accounting, offered load and received goodput:** tables per cell [P3a §7.3–4].

### 2.7 E4(a) — bench versus theory

In each E1 and E1-R cell, IOU, the ratio measured / bound is computed, with bootstrap 95 % CI of the median [P3a §11]:
- **LLQ:** the **main** ratio is p99 / (T_s + T_voz + floor(L)) [OP], because the theoretical bound does not include the bench's own delay; p99 / (T_s + T_voz) is also reported;
- **CBWFQ:** p99 / (2·T_r + T_s) (RFC 2212).

---

## 3. Data audit (before any test) [D]

1. **Inclusion table per cell:** runs, flagged, exempt, `_ac`, `tcp_hambre` and invalid attempts.
2. **For each variable of §1.3:** non-null values over the total, minimum and maximum, per cell and overall.
   - A column that is entirely zero or empty stops the analysis.
3. **Physical checks.** If any comes out impossible, the analysis stops:
   - LLQ p99 ≥ median floor at its L minus the range of the floor;
   - shaper rate ≤ R × 1.05;
   - voice loss with LLQ ≈ 0 with voice within the reservation;
   - minimum delay ≥ 0;
   - received ≤ sent.
4. **The recomputed p99 matches `summary.json`** (§1.3) and the capture path (`voice_owd_capture_path`, ≤ 0.1 ms) in every run that has it.
   - The 3 Q004 cells have no voice in the port range of the capture (the probe there is video); this is stated.

---

## 4. Code validation (before using it on the campaign) [D]

1. **Pilot reproduction:** with the analysis code, the per-cell p99, the EMI and the deviations of `F4_campana/pilot/ANALISIS_PILOTO.txt` and `ANALISIS_P3b.txt` must come out the same (up to rounding).
2. **Shuffled labels:**
   - in E1 with k = 3 the CBWFQ/LLQ labels are permuted at random within each block (seed in §7), and H2 and the TOST are run;
   - [OP] 200 shuffles.
   - **H2:** the fraction of p < 0.05 is reported; it should be around 0.05.
   - **TOST** [OP]: with shuffled labels the true difference is 0, so the TOST should often declare equivalence (depending on its power). It is checked that:
     - the mean of d over the 200 shuffles is around 0;
     - the 95 % CI of the mean contains 0 in ~95 % of them;
     - and the fraction of equivalences is reported; it is expected to be high.
   - If a systematic effect appears, the code is wrong and the analysis stops.
3. **Synthetic H3 case:**
   - simulated data with a = 1, b = 2, c = 1 ms, with the real T_s and T_r of the 19 cells, 17 replicates and normal noise with SD = 1.3 ms (the largest between-run SD of the pilot for CBWFQ with k = 3);
   - the code must recover a and b with CIs that contain them.
   - It is repeated with Δ and the reference a = 0, b = 2.

---

## 5. Sensitivity analyses (fixed before seeing the data they affect)

1. **Without the flagged runs** [D]: H1, H2 and negative control.
2. **Without the IOU capacities of 2 and 3 Mbit/s** [D]: H1, H2 and negative control.
3. **By session (E4(c))** [D]:
   - Δ_ses = median p99 in session 2 minus that in session 1, per tested cell (E1 CBWFQ and LLQ, E1-R and negative control), against the EMI, with bootstrap CI (seed 20261016);
   - the number and list of cells with |Δ_ses| > EMI are reported;
   - the tests of H1–H5 and of the negative control are repeated within each session, and whether any conclusion changes is reported.
   - **Session 1:** repetitions 1–9; includes the `_ac` runs and the `campaign1k` block.
   - **Session 2:** repetitions 10–17.
   - [OP] It is stated that repetitions 1–9 of the 10 exempt cells (`campaign1k`, 15 October from 01:30 to 04:04) were run on the same day on which session 2 started.
4. **With the battery runs** [D]: the analysis is repeated with the 103 originals instead of their `_ac` repeats.
   - Per cell, paired difference original − `_ac` of the p99, and sign test.
   - [OP] Eight of the 103 started between 06:30 and 06:43:30, before the discharge began (upower). They were repeated anyway, and this is stated.
5. **The 12 sporadic shaper failures** [D]: voice p99 of each failed attempt (`_invalid/`) against its valid replacement, compared with the EMI.
6. **The run that coincided with the automatic update of 15 October** (E2 IOU LLQ 5 Mbit/s r10, 06:42:45; systemd re-executed at 06:42:48) [OP]: H2 of that cell with and without it.
7. **Table of S and S-H** against their E1 base cell: difference of medians with CI, and whether the H1 and H2 conclusion in that cell changes [P3a §6].
8. **MOS:** buffer of 40/60/100 ms, T_resto of 50/100/150 ms and Bpl of 4.3/25.1 [P3a §9].

---

## 6. Exploratory (labelled as such)

1. **Boundary L\*** where the CBWFQ p99 crosses each budget (20, 50 and 100 ms, illustrative), interpolating in log L, with bootstrap CI [P3a §11].
2. **m\*(L)** per budget, interpolating in log(1 + m). Reported as censored ("> 3") if it falls outside the range [D].
3. **Negative-control ratio** [D]:
   - ρ = D_sin / D_con per (L, k), with D_sin = mean of the paired CBWFQ − LLQ differences without marks and D_con = the same mean in the marked E1 cell (IOU, same L and k, m = 0.2);
   - **D_sin in ms as well**;
   - percentile bootstrap 95 % CI with 10 000 resamples (seed 20261014), with the repetitions resampled separately in each cell.
4. **FIFO-C versus FIFO-L**, as a difference between benches [P3a §3].
5. **E4(b):** c7200 versus IOU at 1 Mbit/s (k {1; 3} × {CBWFQ, LLQ}).
   - Difference of median p99 with CI and excess of each over the floor of its platform (median floor at 1 Mbit/s: IOU 2.07 ms; c7200 12.02 ms).
6. **E4(d):** the Q004 scenario (Hirchoren et al., 2017) and the Q034 scenario (Luca et al., 2016) against the published hardware figures, descriptively.
7. **MOS** (G.107/G.113) according to P3a §9, with the figure of MOS against T_resto per policy.
8. **Re-implementation by another path:** percentiles and jitter from the captures, with different code [P3a §11].

---

## 7. Seeds and re-computation sample

- **Seeds fixed here** [OP]:
  - per-cell bootstrap: 20261020;
  - H3 bootstrap: 20261021;
  - shuffled labels: 20261022;
  - synthetic case: 20261023;
  - sessions: 20261016;
  - negative-control ratio: 20261014.
- **Sample for a re-computation with separately written code** [D], with seed 20261024 and fixed before the confirmatory run:
  - 30 runs drawn at random from those in the main analysis;
  - Δ and its test in E1 IOU k = 3 at 1 and 5 Mbit/s (H2);
  - the H1 TOST at 1 Mbit/s;
  - the H3 regression (CBWFQ p99).
  - The list is stored in `F5_analisis/MUESTRA_VERIFICACION.json` before computing.

## 8. Outputs

- `F5_analisis/results/numbers.json`: every number in the manuscript [P3a §11].
- CSV tables per test, with cell, n, statistic, p, adjusted p and CI.
- Figures: each one is opened and checked visually.
- The analysis code outputs tables and numbers **without interpretation** [D].
