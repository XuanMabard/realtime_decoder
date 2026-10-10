# compression_analysis

Would **kernel merging** (compressing each encoder's stored spikes) change what the decoder
decides? Offline replays of a saved run, merged vs unmerged — as opposed to `content_analysis/`
(what the live decoder decided) and `time_analysis/` (how fast it ran).

| File | Purpose |
|---|---|
| `merging_replay.ipynb` | Replays one run at several merge thresholds, summarizes the trade-off (kernels kept, KDE time, decoding changes), shows where and when the merged decoder disagrees with the unmerged one, and how much the merged kernels overlap each other |
| `kernel_merging.py` | The replay itself: run loading, model rebuild, merging, per-spike votes, decoder replay with the real `ClusterlessDecoder`, caching; `kernel_overlap` for the overlap section |

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
- TAU = 0 is no merging and reproduces the unmerged encoder exactly.
- This is the rule the encoder itself runs since 2026-10-08 (`encoder.mark_kernel.merge_threshold`),
  with the same arithmetic (a merged center moves by `(mark − center) / count`), so a run recorded
  with merging is reproduced bit for bit.

## How the replay stays faithful

| Step | Check |
|---|---|
| Rebuild each trode's model from `rec_3` in processing order (`rec_ind`) | Must equal the saved `*.encoder.npz` exactly (section 1). For runs recorded with merging: the file's unmerged copy must equal the records, and its merged model must equal this rule at the run's threshold |
| Recompute which spikes the live run's own model sends | Must equal the logged `cred_int >= 0` exactly (section 2) |
| Other models' votes reuse the encoder's own occupancy | Logged vote = `(K_live + 1e-7) / occupancy`, normalized (`K_live` from the model the run used), so another model's vote = `(K + 1e-7) × logged / (K_live + 1e-7)`, normalized |
| Decode with the real `ClusterlessDecoder` | Occupancy per bin = the decoder's own `rec_7` record just before that bin's `rec_4` record (they share one `rec_ind` counter) |

## Gotchas

- **Both replays use every spike the encoders sent.** The live run dropped late spikes, so the
  live decoded hex differs from the unmerged replay far more than merging does. Never compare
  the merged replay to the live output.
- **First run is slow, later runs are fast.** The unmerged per-spike replay dominates (~150k
  marks per big trode). Results are cached as one `.npz` per threshold in
  `<run dir>/compression_analysis/`; set `FORCE = True` to recompute. Caches carry a version
  (`CACHE_VERSION` in `kernel_merging.py`) and the run's own threshold; older ones are recomputed
  automatically.
- **Memory:** a full run holds a few GB (per-spike kernel sums and votes for every threshold).
  Fine on the decoder machine; reduce `THRESHOLDS` elsewhere.
- **Preloaded-model runs** fail the section 1 check (the saved model also contains the preloaded
  spikes). The replay needs a run that built its model from scratch.
- **KDE times are offline**: a single-process benchmark (`time_kde`) on the largest trode's final
  model, run after the parallel replay has finished. Compare thresholds with each other and with
  the 6 ms bin, not with live latencies (the live encoder shares the machine with other ranks).
- **Kernel overlap** (section 5): for every kernel of each final model, the area it shares with
  its nearest other kernel in any hex. Kernels all have width σ, so this is 2Φ(−d/2σ) of the
  distance d between centers, in any number of dimensions; spike counts are ignored. Not cached
  (a few seconds).
