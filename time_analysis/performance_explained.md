# Performance analysis, explained

A plain-language guide to everything in `time_analysis/`: what each step does, what
each number means, and how to tell a healthy run from a struggling one.

This is a companion to the code, not a replacement — every claim here is traceable
to a specific function or source line, cited as `file.py:line`.

---

## Contents

1. [What's in this folder](#1-whats-in-this-folder)
2. [Glossary — every piece of jargon](#2-glossary--every-piece-of-jargon)
3. [Where the numbers come from](#3-where-the-numbers-come-from)
4. [Walkthrough: `realtime_decoder_timing_analysis.ipynb`](#4-walkthrough-realtime_decoder_timing_analysisipynb)
5. [Walkthrough: `decoder_efficiency_analysis.ipynb`](#5-walkthrough-decoder_efficiency_analysisipynb)
6. [How to read each figure](#6-how-to-read-each-figure)
7. [Diagnosing a run](#7-diagnosing-a-run)
8. [Known quirks and traps](#8-known-quirks-and-traps)

---

## 1. What's in this folder

| File | What it is | Reads from |
|---|---|---|
| `realtime_decoder_performance.py` | The analysis engine — 1,569 lines of loaders, aligners, metrics, and plots | **Raw** per-rank `.bin_rec` files + `.npz` timing files |
| `realtime_decoder_timing_analysis.ipynb` | A thin driver notebook that calls the engine step by step | (via the engine) |
| `decoder_efficiency_analysis.ipynb` | A standalone notebook built on the **merged** HDF5 output | `*.rec_merged.h5` + `*.timings_merged.h5` |
| `performance_explained.md` | This document | — |

**Which should you use?**

They answer the same questions from different source files, and they complement
each other:

- **The `.py` + `timing_analysis.ipynb` pair is the more rigorous one.** It
  reconstructs the decoder's internal behaviour — circular-buffer overwrites,
  timestamp de-duplication — and assigns *every single spike* one mutually
  exclusive outcome. It then **validates** that reconstruction against what the
  decoder actually recorded (`validation_table`, `realtime_decoder_performance.py:838`).
  If the reconstruction is right, you can trust the breakdown.
- **`decoder_efficiency_analysis.ipynb` is the more convenient one.** It reads the
  two merged files, so it works on any run without needing the raw per-rank files,
  and it adds two things the older pair doesn't have: a sample-clock↔wall-clock fit
  (to measure real "staleness") and a per-spike lateness histogram.

Run both. If they disagree materially, trust the one whose validation checks pass.

---

## 2. Glossary — every piece of jargon

### Recording hardware and spikes

**nTrode / electrode group / "trode"**
A named bundle of recording channels defined in the Trodes workspace
(`.trodesconf`). Historically a tetrode (4 wires); on a silicon probe it's however
many channels you grouped together. Trodes detects a spike *per group* and sends
all of that group's channels together. Referred to in code as `elec_grp_id`.

**Mark / mark vector**
The feature vector describing one spike: the voltage on each channel of the group,
sampled at the moment of the waveform's peak. With `mark_dim: 12` you get a
12-number vector per spike. This is the "clusterless" part — spikes are never
sorted into single units; the raw mark vector *is* the identity.

**Amplitude-qualified**
A spike whose largest mark value exceeded `encoder.spk_amp`. Below-threshold spikes
are discarded immediately and leave **no trace in any output file** — so the true
number of spikes the hardware detected is not knowable from these records.

**Encoding model / "mark cloud"**
The accumulated set of (mark vector, position) pairs for one trode. Literally two
parallel arrays, `marks` and `positions`, growing as the animal runs. This *is* the
model — there's no fitting step, no parameters.

### Decoding

**KDE — Kernel Density Estimation**
The method for asking "given this new spike's mark vector, where was the animal
likely to be?" It compares the new mark against **every mark already stored**,
weighting each by a Gaussian kernel of the distance in mark space, then histograms
those weights by the stored positions. Because it touches every stored mark, its
cost grows linearly with model size — this is the single most important performance
fact in the whole system.

**Joint probability / likelihood histogram**
The KDE's output: one number per position bin, i.e. "how much this spike votes for
each location." 49 numbers in hex mode. This — not the raw spike — is what the
encoder sends to the decoder.

**Posterior**
The decoder's final probability distribution over position for one time bin, formed
by combining all spike likelihoods in that bin with the previous bin's posterior
pushed through the transition matrix. Also 49 numbers in hex mode. This is the
decoder's actual output.

**Occupancy**
How many position samples the animal spent in each bin. Used to normalise the
likelihood — without it, places the animal visits often would look artificially
likely regardless of the spikes.

**Credible interval (`cred_int`)**
How many position bins are needed to accumulate a given share of the probability
mass (`cred_interval.val`, e.g. 0.5 = 50%). **Small = confident** (probability
concentrated in a few hexes); **large = diffuse**. Used here as a quality signal.
Also used as a flag: `cred_int = -1` means "no KDE result was computed."

**Position bin / hex id**
The discrete location unit. On a linear track, a bin along the linearised track; in
hex mode, a hex cell id (49 of them).

**Time bin**
The 6 ms window (`time_bin.samples: 180` at 30 kHz) over which spikes are pooled to
produce one posterior.

**`delay_samples`**
A deliberate grace period. The decoder decodes the window that ended
`delay_samples` ago rather than the one ending right now, giving spikes time to
arrive over the network. With `delay_samples: 180` that's a 6 ms head start.
**This is a designed delay, not a symptom of lag.**

### System architecture

**MPI / rank**
The parallel framework running the decoder. One OS process per **rank**, each with
a fixed job (supervisor, ripples, encoders, decoders, gui) assigned by number in
the config. Ranks pass messages rather than sharing memory.

**Circular buffer**
A fixed-size array that wraps around: slot 0, 1, 2, … n−1, then back to 0,
overwriting the oldest entry. The decoder holds incoming spike likelihoods in one
sized `decoder.bufsize` (2000). Nothing checks whether the slot being overwritten
was ever used — that's the mechanism behind "dropped" spikes.

### Time and clocks

**Sample clock (Trodes `timestamp`)**
An integer counter incremented 30,000×/second by the recording hardware. Neural
data and position share it, so it's the correct clock for aligning *data* to
*data*. It says nothing about when your computer processed anything.

**Wall clock (`time.time_ns()`)**
Real-world time in nanoseconds since 1970, read on the computer running the
decoder. This is the correct clock for measuring *how long code took*.

**Why mixing them is a trap**
A sample count and a wall-clock reading are different quantities in different
units. Subtracting one from the other is meaningless. Worse, during **playback**
the two drift apart arbitrarily — playback can run faster or slower than real time,
and can stall. To convert between them you must fit a mapping (see
"clock fit" below), and the quality of that fit bounds how much you can trust any
number derived from it.

**Epoch nanoseconds (ns)**
The raw unit of all wall-clock fields (`t_recv_data`, `t_start_kde`, …). Divide
differences by 1e6 for milliseconds.

### Statistics

**Percentile / quantile (p50, p95, p99)**
p95 = the value that 95% of observations fall below. **p50 is the median.** For
latency, the tail percentiles matter far more than the mean: p50 tells you the
typical case; **p99 tells you what your slowest 1% of spikes experienced**, which
is what actually breaks a real-time deadline. A mean would hide both.

**IQR — interquartile range**
The span from the 25th to the 75th percentile: the middle half of the data. Plotted
as a shaded band around a median line to show spread without being dragged around by
outliers.

**ECDF — Empirical Cumulative Distribution Function**
A curve where the x-axis is a value and the y-axis is "what % of observations were
at most this value." Read it by picking a height and reading across: at y=95 you
find the p95. Its advantage over a histogram is that it needs no bin-width choice
and shows every percentile at once. Steep = consistent; long flat tail to the right
= a slow minority.

**Windowed aggregation**
Chopping the session into fixed slices (5 s in the older notebook, 60 s in the
newer) and computing a statistic per slice, so you can plot how behaviour changed
over the session instead of collapsing everything to one number.

**Staircase counter**
A counter that only updates occasionally, so plotted over time it looks like steps
rather than a smooth line. `dropped_spikes` is one: it only advances when the
decoder's buffer wraps, every 2000 messages.

**Forward fill (`ffill`)**
Carrying the last known value forward through gaps. Used for model size: if a trode
recorded no spikes in a window, its model didn't shrink — it stayed where it was.

**Half-open interval `[l, r)`**
Includes the left edge, excludes the right. Time bins tile this way so that a spike
exactly on a boundary belongs to exactly one bin, never two.

**As-of join**
Joining each row to the *most recent prior* row in another table, rather than an
exact match. Used to answer "what was this trode's model size at the moment this
spike arrived?"

**`validate="one_to_one"`**
A pandas guard that raises an error if a merge would duplicate rows. Used
throughout `build_analysis_tables` because a silent many-to-many merge would
inflate every count downstream. Its presence is why you can trust the counts.

**Occurrence index**
A counter distinguishing repeated `(trode, timestamp)` pairs before joining
(`_add_occurrence_index`, `realtime_decoder_performance.py:449`). Without it, two
spikes sharing a timestamp would cross-join into four rows.

### Performance outcomes

**Latency vs throughput**
*Latency* is how long one item took (ms per spike). *Throughput* is how many items
per second. A system can have great throughput and terrible latency — that's
exactly what a backlog looks like.

**Deadline miss / late arrival**
A spike that reached the decoder **after** the posterior for its time bin had
already started computing. Its information is lost — bins only move forward, so it
can never be folded into a later one.

**Tardiness**
*How late* a late spike was, in ms. Distinguishes "missed by 1 ms" (a tuning
problem) from "missed by 2 seconds" (a collapse).

**Buffer overwrite**
A spike that arrived on time but was clobbered in the circular buffer by 2000 newer
spikes before its bin was decoded. Distinct from lateness — the spike was punctual;
the system was simply too congested to hold onto it.

**Timestamp collision / duplicate removal**
The decoder de-duplicates spikes within a bin **by timestamp alone**, ignoring which
trode they came from. Two genuinely different spikes on two different trodes that
happen to share a sample timestamp will be collapsed. Counted separately from drops.

**Utilization / busy %**
The share of wall time a rank spent inside its main computation. Encoder busy % =
(total KDE time in the window) ÷ (window length). **Approaching 100% means that
rank is saturated** and any additional load turns directly into backlog. It's a
*lower bound* on true busy-ness — it counts only the instrumented computation, not
message handling or waiting.

**Playback speed factor**
Configured bin width ÷ observed median wall time between consecutive posteriors.
`1.0×` = keeping pace with real time. `0.5×` = running at half speed (the decoder
needed 12 ms of wall time per 6 ms of neural data). Only meaningful for playback.

---

## 3. Where the numbers come from

Two independent instrumentation streams:

**Binary records** (`.bin_rec`, merged into `rec_merged.h5`) — the scientific
output. Written by each recording rank as a JSON header followed by packed rows.
The two that matter here:

| Record | One row per | Key fields |
|---|---|---|
| ID 3 — `ENCODER_OUTPUT` | amplitude-qualified spike | `timestamp`, `elec_grp_id`, `encode_spike`, `cred_int` |
| ID 4 — `DECODER_OUTPUT` | decoded 6 ms bin | `bin_timestamp_l/r`, `spike_count`, `dropped_spikes`, `duplicated_spikes` |

**Timing NPZs** (merged into `timings_merged.h5`) — the performance output.
Wall-clock stamps captured at each processing stage:

| Field | Captured when |
|---|---|
| `t_send_data` | Trodes stamped the packet (recording computer's clock) |
| `t_recv_data` | the encoder received it |
| `t_start_kde` / `t_end_kde` | KDE evaluation began / ended |
| `t_start_enc_send` / `t_end_enc_send` | the MPI send call began / ended |
| `t_decoder` | the decoder received the message |
| `t_start_post` / `t_end_post` | posterior computation began / ended (per bin) |

**Encoder model files** (`*_trode_N.encoder.npz`) — the saved mark cloud. Its
`mark_idx` field is the ground-truth final model size, used to verify the
reconstruction.

> **The critical caveat.** `ENCODER_OUTPUT`'s column *labels* are rotated relative
> to what's actually written (`encoder_process.py:333-336` vs the write call at
> `:544`). The columns named `sent_to_decoder`, `task_state`, `frozen_model`, and
> `nearby_spikes` contain the wrong values. Both notebooks work around this the same
> way: **`cred_int >= 0` is the reliable "was this sent to the decoder" indicator**
> (`realtime_decoder_performance.py:315`).

---

## 4. Walkthrough: `realtime_decoder_timing_analysis.ipynb`

### §1 Settings
Pick the output directory and optionally a run prefix. Left as `None`, `select_run`
picks the newest run that *looks complete* — meaning it has posterior timing plus at
least one encoder and one decoder timing file (`:117`). `WINDOW_SECONDS = 5` sets
the aggregation slice.

### §2 How the decoded outputs are read
Prints the JSON header of a `.bin_rec` file. This is a **schema check**, not
analysis: it shows the column labels and struct format the run actually wrote, so
you can confirm they match what the parser expects before trusting anything.

### §3 Load and align the run
The heavy lifting — `build_analysis_tables` (`:464`). In order:

1. **Read** encoder records, decoder records, and all timing NPZs.
2. **Reconstruct model growth.** Cumulatively sum `encode_spike` per trode to get
   `model_size_after` for every spike. `effective_model_size` caps this at
   `encoder.bufsize`, because that's how many marks the KDE actually evaluates.
3. **Join** each sent spike to its encoder timing row and its decoder-receipt row,
   using the occurrence index and `validate="one_to_one"` so nothing silently
   multiplies.
4. **Compute stage durations** — the differences between consecutive timestamps
   (`source_to_encoder_ms`, `kde_ms`, `encoder_to_decoder_ms`, …).
5. **Map each spike to its intended bin** — the unique half-open `[l, r)` window its
   sample timestamp belongs to.
6. **Classify.** This is the valuable part. Each spike gets exactly one `status`
   (`:792`), tested in this order:

   | `status` | Meaning |
   |---|---|
   | `transport_missing` | Sent, but no decoder receipt was recorded at all |
   | `outside_recorded_bins` | Its timestamp falls in no recorded bin (usually a gap in the bin clock) |
   | `late` | Arrived at/after its bin's posterior started — deadline miss |
   | `buffer_overwritten` | Arrived on time, but 2000 newer spikes clobbered it first |
   | `duplicate_removed` | Eligible, but removed by timestamp de-duplication |
   | `used` | Actually contributed to a posterior |

   The `buffer_overwritten` test is neat: for each on-time spike it counts how many
   messages arrived on that decoder rank between the spike and its bin's decode
   time; if that exceeds `bufsize`, the slot was necessarily recycled (`:745-766`).

### §4 Validate the reconstruction
`validation_table` (`:838`) runs nine consistency checks. Two are the real proof:

- **"Derived used count matches every posterior bin"** — the number of spikes the
  reconstruction says were used must equal the `spike_count` the decoder itself
  recorded, *for every one of the ~199,000 bins*.
- **"Derived timestamp removals match every posterior bin"** — same for duplicates.

If those pass, the simulation of the decoder's internals is faithful and the
`status` breakdown is trustworthy. **Check this table before believing anything
downstream.** It's designed to expose disagreement, not hide it.

### §5 Whole-run metrics
`headline_summary` (`:948`) — one table of counts, KDE and posterior percentiles,
and the playback speed factor. The count rows form a funnel: amplitude-qualified →
sent → received → within bins → used, with the losses at each stage named.

### §6 Aggregate through time and plot
`aggregate_windows` (`:1106`) slices everything into 5 s windows and computes
per-window counts, rates, latency percentiles, model sizes (forward-filled), and
busy percentages. `plot_time_analysis` renders the six-panel dashboard (§6 below).

### §7 Scaling with model size and spike load
`plot_scaling_analysis` (`:1467`) — the three panels that answer "does it get slower
as it learns?"

### §8 Compare the beginning and end of the run
Splits the session into its first and last 10 minutes and tabulates the same metrics
side by side. **The most direct answer to the growth question**: if late % and KDE
time are materially worse at the end, the encoder outgrew its time budget.

### §9 Per-nTrode summary
`per_trode_summary` (`:1255`) — the same funnel per trode. Use it to spot one
pathological channel: a trode with far more spikes will have a bigger model, slower
KDE, and will drag down everything sharing its encoder rank.

### §10 Optional exports
Writes the aggregate tables to CSV under `output_dir/performance_analysis/<prefix>/`.

---

## 5. Walkthrough: `decoder_efficiency_analysis.ipynb`

Same questions, merged-HDF5 source, plus two capabilities the older pair lacks.

**Cells 1–3 — config and load.** Auto-discovers the newest merged file, reads the
run's config snapshot for bin width, buffer sizes, and trode assignment, then loads
the narrow timing tables whole and slices only the needed columns out of the wide
record tables.

**Cell 4 — the clock fit.** The genuinely new piece. The `/ripples` table pairs a
sample count with a wall-clock reading 1,500×/second, so fitting a straight line
through those pairs gives a conversion from sample clock to wall clock. **The
printed residual is a health warning about the fit itself** — a large residual means
playback paced irregularly and any wall-clock-versus-sample-clock number below is
correspondingly unreliable. (On the Toby run this residual is tens of seconds, so
its staleness figures should not be read literally.)

**Cell 5 — join and classify.** Assigns each spike its bin by binary search, then
computes the seven stage latencies and flags `late`.

**§1 Latency.** Stage ECDFs plus a windowed time series of end-to-end and KDE
latency.

**§2 KDE cost vs model size.** Reconstructs model size per trode and validates it
against every `encoder.npz` `mark_idx` — an exact-match check. Then bins KDE time by
model size and fits a slope, reported as **nanoseconds per stored mark**. That slope
is the growth question's numeric answer.

**§3 Dropped spikes.** Cumulative counters, a windowed drop rate, a lateness
histogram (the substitute for the never-implemented per-spike miss record), and
sent-versus-used throughput.

**§4 Bin lag.** Asserts that `timestamp − bin_timestamp_r` is constant — proving it
measures the configured delay and nothing else — then measures the things that do
vary: bin-clock gaps, trigger-to-decode latency, and posterior staleness.

**§5 Summary** table plus CSV export.

---

## 6. How to read each figure

### The six-panel dashboard (`plot_time_analysis`)

| Panel | Shows | Healthy looks like |
|---|---|---|
| **Encoder model growth** | Cumulative marks per trode + total | Steady growth while the animal runs; flat when resting |
| **Computation latency** | KDE and posterior p50–p95 bands, with a line at the 6 ms bin width | Bands well below the bin-width line |
| **Pipeline latency (log)** | End-to-end stage latencies | Flat; log scale is used precisely so brief stalls stay visible |
| **Throughput** | Spikes/second at each funnel stage | Sent ≈ received ≈ used |
| **Deadline misses** | Late/overwritten/removed rates, plus cumulative late % | Near zero and not trending up |
| **Utilization** | Busy % per rank, with a 100% reference line | Comfortably below 100% |

Panel 2's bin-width reference line is the key one: **if median KDE time approaches
6 ms, an encoder can no longer finish one spike within one time bin**, and any
sustained spike rate above ~1 spike/bin/rank will build an unrecoverable backlog.

### The three scaling panels (`plot_scaling_analysis`)

1. **KDE scaling** — KDE time vs effective model size. Should rise **linearly**;
   the slope is your cost per stored mark. A knee upward suggests a memory effect.
2. **Posterior scaling** — posterior time vs spikes in the bin. Should be nearly
   flat: posterior cost is dominated by the 49×49 matrix multiply, not spike count.
3. **Deadline misses as models grow** — late % vs model size. **This is the punchline
   plot.** A rising curve means the encoder's growth is directly causing missed
   deadlines, and you have a real trade-off between model richness and real-time
   feasibility.

---

## 7. Diagnosing a run

Work through these in order.

**1. Did the reconstruction validate?** (§4 of the older notebook.) If the derived
used-count doesn't match recorded `spike_count`, stop — the parse is wrong and
nothing downstream means anything.

**2. Where did spikes go?** Read the funnel. Losses concentrated in:
- `late` → the pipeline is too slow for the deadline; look at KDE time and busy %.
- `buffer_overwritten` → the decoder is congested; `decoder.bufsize` is too small
  for the load, or the decoder is falling behind.
- `outside_recorded_bins` → the *bin clock* has gaps; the ripple rank isn't
  delivering LFP triggers steadily. Suspect the ripple rank or the data source, not
  the encoder.
- `duplicate_removed` → high numbers may mean genuine coincident spikes across
  trodes being wrongly collapsed by the timestamp-only rule.

**3. Is it getting worse over time?** Compare first vs last 10 minutes (§8), and
check the late-%-vs-model-size panel. Worsening ⇒ model growth is the cause.

**4. Which rank is saturated?** Utilization panel. Since encoders are one-per-trode
and busy % is dominated by KDE, the busiest encoder is usually the trode with the
most spikes.

**5. If growth is the problem**, your levers are: lower `encoder.bufsize` (caps the
KDE at a fixed cost — the model stops improving but latency stops growing); enable
`frozen_model` once the model is good enough; use fewer or better-chosen channels
per trode (`mark_dim` multiplies KDE cost); spread trodes across more encoder ranks;
or set `train_all_task_states: false` so learning stops when decoding starts.

---

## 8. Known quirks and traps

**`ENCODER_OUTPUT` column rotation.** `sent_to_decoder`, `task_state`,
`frozen_model`, `nearby_spikes` hold wrong values. Use `cred_int >= 0`.
(`encoder_process.py:333-336` vs `:544`.)

**`DECODER_MISSED_SPIKES` was never implemented.** Record ID 5 is registered with
`real_bin`/`late_bin` columns, but no code has ever written it, in any commit. There
is no per-spike record of misses; both notebooks reconstruct lateness from
wall-clock timings instead.

**`dropped_spikes` slightly overcounts.** The census runs at each buffer wrap and
counts still-in-flight spikes as dropped, never correcting them
(`decoder_process.py:636-654`). Expect it to read a bit high versus the
timing-derived count — and prefer the derived count.

**`timestamp − bin_timestamp_r` is a constant.** It equals `delay_samples` by
construction. It is the configured grace period, not backlog. Don't report it as lag.

**Sub-threshold spikes are invisible.** Everything is measured relative to
amplitude-qualified spikes; the hardware denominator is unknown.

**Spikes with no KDE result have no timing row.** Timing is only written when
`get_joint_prob` succeeds, so filtered spikes appear in `ENCODER_OUTPUT` (with
`cred_int = -1`) but contribute nothing to latency statistics.

**`t_send_data` is a different computer's clock.** It comes from Trodes'
`systemTimestamp` on the recording machine. Any latency computed against it assumes
the clocks are synchronised. Treat "source-to-X" numbers with suspicion; the
encoder-onwards stages are all same-host and safe.

**Playback ≠ real time.** All wall-clock latencies reflect playback pacing. A run
that looks slow in playback may be fine live, and vice versa. The playback speed
factor tells you which regime you're in.

**Nothing downstream of the posterior is instrumented.** There's no timestamp
anywhere in the stimulation, GUI, or supervisor receive paths, so "posterior
available" is proxied by `t_end_post`, which excludes the credible-interval
computation and the MPI send that follow it.

**Panel 5 of the dashboard uses a second y-axis** for cumulative late %. Two
different scales share one plot area, so check which axis a line belongs to before
comparing heights.

**Merged HDF5 keys are pandas *fixed* format.** No partial or column-subset reads —
each key loads whole (`rec_3` is ~850 MB in memory). Load one at a time, slice, and
delete.
