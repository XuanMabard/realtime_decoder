# compression_analysis

Would **kernel merging** (compressing each encoder's stored spikes) change what the decoder
decides? Offline replays of a saved run, merged vs unmerged — as opposed to `content_analysis/`
(what the live decoder decided) and `time_analysis/` (how fast it ran).

| File | Purpose |
|---|---|
| `merging_replay.ipynb` | Replays one run at several merge thresholds, summarizes the trade-off (kernels kept, KDE time, decoding changes), and shows where and when the merged decoder disagrees with the unmerged one |
| `kernel_merging.py` | The replay itself: run loading, model rebuild, merging, per-spike votes, decoder replay with the real `ClusterlessDecoder`, caching |

Design decisions and open questions for the encoder change live in
`docs/kernel_compression_plan.md`.

## The merging rule being tested

Weight-only merging (Hu et al. 2018, Cell Reports, with the merge rule of Sodkomkham et al.
2016, Knowledge-Based Systems), adapted to hex bins:

- An encoding spike joins the **nearest existing bump in its own hex** if that bump's center is
  within **TAU × σ** of the spike's mark (Euclidean distance over all mark channels; σ =
  `encoder.mark_kernel.std`). Otherwise it starts a new bump.
- A bump's center is the mean of its members; its width stays σ; its **count multiplies its
  kernel** in the vote. The per-hex totals are therefore exactly the per-hex spike counts.
- The "enough nearby marks" rule (`n_marks_min` inside the `±n_std·σ` box) adds up bump counts.
- TAU = 0 is no merging and reproduces today's encoder exactly.

## How the replay stays faithful

| Step | Check |
|---|---|
| Rebuild each trode's model from `rec_3` in processing order (`rec_ind`) | Must equal the saved `*.encoder.npz` exactly (section 1) |
| Recompute which spikes the unmerged model sends | Must equal the logged `cred_int >= 0` exactly (section 2) |
| Merged votes reuse the encoder's own occupancy | Logged vote = `(K + 1e-7) / occupancy`, normalized, so merged vote = `(K_merged + 1e-7) × logged / (K + 1e-7)`, normalized |
| Decode with the real `ClusterlessDecoder` | Occupancy per bin = the decoder's own `rec_7` record just before that bin's `rec_4` record (they share one `rec_ind` counter) |

## Gotchas

- **Both replays use every spike the encoders sent.** The live run dropped late spikes, so the
  live decoded hex differs from the unmerged replay far more than merging does. Never compare
  the merged replay to the live output.
- **First run is slow, later runs are fast.** The unmerged per-spike replay dominates (~150k
  marks per big trode). Results are cached as one `.npz` per threshold in
  `<run dir>/compression_analysis/`; set `FORCE = True` to recompute.
- **Memory:** a full run holds a few GB (per-spike kernel sums and votes for every threshold).
  Fine on the decoder machine; reduce `TAUS` elsewhere.
- **Preloaded-model runs** fail the section 1 check (the saved model also contains the preloaded
  spikes). The replay needs a run that built its model from scratch.
- **KDE times are offline**: a single-process benchmark (`time_kde`) on the largest trode's final
  model, run after the parallel replay has finished. Compare thresholds with each other and with
  the 6 ms bin, not with live latencies (the live encoder shares the machine with other ranks).
