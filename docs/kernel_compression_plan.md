# Kernel Compression (Merging) Plan

Working notes for adding kernel merging to the encoder's KDE. This file is the source of truth
for design decisions on this feature — updated as we go.

## Background

- **Method:** Hu et al. 2018, *Real-Time Readout of Large-Scale Unsorted Neural Ensemble Place
  Codes*, Cell Reports 25:2635 (PMC6314684). Its compression step is the online merge rule of
  Sodkomkham et al. 2016, *Kernel density compression for real-time Bayesian encoding/decoding of
  unsorted hippocampal spikes*, Knowledge-Based Systems 94:1.
- **Problem it solves:** `Encoder.get_joint_prob` touches every stored mark for every spike, so
  its cost grows linearly over a session. In the 2026-09-17 Vinnie run the five busiest trodes
  (117k–147k stored spikes) took a median 27–33 ms per spike by the end, against 6 ms bins.
- **Why it fits this decoder's math:** the vote for a spike is a sum over stored spikes of
  (Gaussian mark kernel) × (indicator of the stored spike's hex), then ÷ occupancy and
  normalized. Merging spikes that share a hex leaves the position side exactly unchanged; the
  only approximation is in mark space, controlled by the threshold.

## Decisions

1. **"Thinning" means merging** — every spike stays counted through its bump's count; spikes
   are never dropped. (Random dropping was tested on saved models: ~20× larger change to each
   spike's vote than merging at a smaller model size.) *(2026-10-07)*
2. **Merge only within the same hex.** Positions are hex labels, not coordinates, so the paper's
   joint mark+position merge does not transfer. A new encoding spike joins the nearest bump in
   its own hex if the bump's center is within TAU × σ, else it starts a new bump. No time
   condition: spikes from different laps can merge. *(2026-10-07)*
3. **Weight-only bumps** (Hu et al. eqs. 2–5): center = mean of members, width stays σ, count
   multiplies the kernel. Width-matched bumps (Sodkomkham's bandwidth match) were considered —
   ~3× smaller vote change at the same TAU and the same per-spike speed — but not chosen, for
   simplicity. *(2026-10-07)*
4. **Online only for now:** merge inside `add_new_mark` as spikes arrive. An offline tool to
   compress saved models for `preloaded_model` runs may come later; write the merge step as a
   standalone function so that tool is just a loop. *(2026-10-07)*
5. **Choose TAU from the replay notebook** (`compression_analysis/merging_replay.ipynb`), which
   compares decoded hexes bin by bin, merged vs unmerged. *(2026-10-07)*
6. **The send rule counts bump weights:** the "≥ n_marks_min marks inside the ±n_std·σ box" test
   adds up the counts of bumps whose centers are inside the box. *(2026-10-07)*
7. **KDE speed-up without merging — implemented, fastest version** (`Encoder.get_joint_prob`):
   the box test checks this spike's largest channel first and only re-checks survivors (same
   comparisons, same count); the distance uses `einsum`; the per-hex sum uses `bincount` when
   bins have width 1 starting at 0 (all 50 configs), else `np.histogram`. Trode 5's final model:
   8.0 → 2.8 ms per spike; 4.2× at 0.9–1.75M marks. Checked on 12 trodes × 2 model sizes ×
   500 spikes: identical send decisions, nearby counts, top hex and `cred_int`; votes differ by
   ≤ 2e-13. Chosen over the bit-identical rewrite, which measured only 1.5×. *(2026-10-07)*
8. **Pair each spike with the position at its own timestamp** (fixes the encoder-lag
   mislabeling in Findings). `EncoderManager` keeps a history of position samples
   (timestamp, hex, speed, task state); `_process_spike` looks up the latest sample at or before
   the spike's timestamp and uses it for the stored hex, the add-to-model decision, the logged
   position/speed/task state, and the position sent to the decoder. Occupancy still uses
   real-time positions. History length: optional `encoder.position_history_s`, default 120 s;
   a spike older than the history (or fired before tracking started) is never trained on, and
   the too-old case logs a warning every 1,000 spikes. `add_new_mark` now grows a buffer
   compacted to zero rows at the task-state switch (reachable now that a pre-switch spike can
   be added after the switch). Checked by driving the real `EncoderManager` offline with the
   recorded Vinnie position stream and spikes: no delay → identical to the original code; every
   spike 30 s late → identical model to no delay (original: 95–97% wrong hex). *(2026-10-07)*

## Order of work

1. KDE speed-up independent of merging — implemented 2026-10-07 (decision 7); needs a Trodes
   playback check.
2. Offline replay notebook + disagreement visualizations — `compression_analysis/` (2026-10-07).
3. Encoder change, then Trodes playback — after the notebook has been reviewed.

## Open Questions

- **Which TAU** — from the notebook.
- **`_mark_idx` changes meaning** once spikes merge (rows ≠ spikes). It feeds the first-spike
  check, the progress log, the bufsize cap, the saved model size, and the time_analysis
  model-size validation. Plan: keep it as rows-in-use, add a spike counter, record the bump
  count in the timing records.

## Replay results (2026-10-07, Vinnie 2026-09-17 run, weight-only, same-hex)

From `compression_analysis/merging_replay.ipynb`. Both replays decode every sent spike; "differs"
= decoded hex (posterior argmax) changes vs the unmerged replay. Timing = single process, trode
5's final model (146,618 training spikes), spikes from the last 10% of the session.

| TAU | kernels kept (all trodes) | KDE ms, today's code / faster | bins that differ | … when unmerged peak ≥ 0.5 | … ≥ 2 hex steps apart |
|---|---|---|---|---|---|
| 0 | 100% | 7.6 / 2.5 | — | — | — |
| 0.5 | 51% | 4.0 / 1.3 | 3.6% | 0.3% | 2.7% |
| 1.0 | 17% | 1.3 / 0.43 | 9.0% | 1.9% | 6.4% |
| 1.5 | 8% | 0.76 / 0.27 | 13.1% | 3.4% | 8.5% |
| 2.0 | 5% | 0.39 / 0.16 | 20.4% | 6.4% | 12.9% |

- Disagreements concentrate where the unmerged decoder was unsure (45% of bins have a posterior
  peak < 0.2 over 49 hexes; at TAU 1.0, 17% of bins with peak < 0.1 differ vs ~1.5% above 0.6),
  are brief (median 1 bin = 6 ms; 90% ≤ 2 bins), and are more common at rest (10.5%) than while
  moving (7.4%) and early in the session (small models).
- For scale: the live run's own decoded hex differs from its unmerged replay in 55.8% of bins —
  it used 746k of the 1.47M sent spikes (the rest arrived too late).
- Checks: replayed models equal the saved `encoder.npz` for all 10 trodes; recomputed send
  decisions equal the logged ones exactly; a near-zero threshold (0.01) gives 0.0000% of bins
  different (largest per-spike vote change 3e-16).

## Findings

- **Encoder lag mislabels training spikes (2026-09-17 Vinnie run).** Trodes 2, 5, 12, 15 and
  18 were more than 1 s behind real time for 20–32% of their spikes (up to 38 s). During those
  stretches ~94% of their training spikes were stored with a later hex than the one at spike
  time; 26–35% of their training spikes overall, vs 3–4% for trodes that kept up. Cause: the
  encoder loop handles one spike and one position message per iteration, so when the KDE is
  slower than real time, spikes queue while the position stays current. The add-to-model
  decision used the current speed too (~50% of delayed spikes decided wrongly). 9 of the 10
  saved runs show it (worst trode per run: 24–49% of spikes > 1 s late, waits up to 44 s).
  **Fixed by decision 8** for new runs; runs recorded before 2026-10-07 keep the mislabeled
  models and records.
- **Crash risk to avoid:** `nearby_spikes` is written into an int32 record field. A summed
  bump count is a float; `struct.pack` would raise and the encoder's main loop would exit for
  the rest of the session. Cast to int.

## Codebase Anchors

- `encoder_process.py` (line numbers as of 2026-10-07): `add_new_mark` (142), `get_joint_prob`
  (202), `save` / `_load_model`, the position history (`_init_position_history` 499,
  `_record_position` 516, `_position_at` 539), the spike-time lookup in `_process_spike` (608),
  the save-early reindex block in `_process_pos` (~789; its random choice is a no-op), progress
  log using `_mark_idx` (706), `nearby_spikes` written at 680.
- `decoder_process.py`: the no-spike term (296–316) uses the decoder's own spike counts per hex,
  not the encoder's stored marks — merging does not touch it.
- `position.py`: stored positions are integer bins in both hex (164) and linear (92) modes.

## Change Log

- **2026-10-06** — Read Hu et al. 2018 and Sodkomkham et al. 2016; offline tests on saved
  models (same-hex merging at TAU 1.0 keeps ~20% of kernels on the big Vinnie trodes, median
  vote change ~0.2–0.3%).
- **2026-10-07** — Decisions 1–6. Added `compression_analysis/` (replay notebook + module).
  Found the encoder-lag mislabeling. Corrected the earlier "identical output, 1.6×" claim: the
  bit-identical rewrite measured 1.5× end to end; the faster one is near-identical.
- **2026-10-07** — Implemented the fastest KDE rewrite in `get_joint_prob` (decision 7);
  merging not started.
- **2026-10-07** — Implemented spike-time position pairing in the encoder (decision 8).
