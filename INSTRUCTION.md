# Running the Realtime Decoder on a Hex Maze

A practical, step-by-step guide for running this decoder with **hex-cell position
bins** instead of Trodes linearization, plus a full explanation of every config
parameter.

Companion config: [`config/Vinnie_nTrode12_test_config.yml`](config/Vinnie_nTrode12_test_config.yml)

---

## 1. What the hex-maze mode changes

Normally this decoder asks Trodes to linearize position onto line segments, then
maps `(segment, position-along-segment)` to a 1-D position bin. A hex maze has
graph topology, not a line, so that mapping does not apply.

In hex mode:

| Concept | Linear-track mode | Hex mode |
|---|---|---|
| Position bin | 1-D bin along linearized track | Hex cell id |
| How it is assigned | Trodes line-segment linearization | Nearest hex centroid to the animal's position |
| Number of bins | `num_bins` in the YAML | Derived automatically from the hex CSVs (49) |
| Transition model | Arms with gaps (`arm_coords`) | Adjacency graph — a hex connects only to its true physical neighbours |
| GUI | Likelihood/posterior vs. time | Same, **plus** a spatial scatter of the posterior drawn at the real hex coordinates |

Everything downstream (spike marks, KDE encoding model, decoding, MPI messages)
is unchanged — a hex id is simply used wherever a position bin used to be.

**Two data files define the maze**, both in `config/`:

- `20260609_Nova_hex_coordinates.csv` — `hex,x,y`, one row per hex cell, in **raw
  camera pixels**. Used to decide which hex the animal is in.
- `Hex_maze_graph.csv` — `hex_a,hex_b` undirected edges. Used to build the
  decoder's transition matrix.

Both currently describe 49 hexes with 63 connections. Adjacent hex centroids are
68–82 px apart (median 77), so the half-spacing is about 37 px — which is why
`hex_threshold` is set to 40 px.

---

## 2. One-time setup

Already done on this machine, listed here for reproducing elsewhere.

```bash
conda activate realtime_decoder
cd ~/realtime_decoder
pip install -e .                 # the decoder itself
pip install -e ~/trodes-tracker  # supplies the hex-assignment code
```

`trodes-tracker` is a real dependency now: `position.py` imports its
`load_centroids` / `nearest_hex` so the hex geometry logic lives in exactly one
place.

Confirm it works:

```bash
python -c "import realtime_decoder, trodes_tracker; print('ok')"
```

---

## 3. Before every run — the checklist

1. **`trodes.config_file` must be the workspace that matches the `.rec` you are
   playing back.** Electrode-group ids and channel counts come from it; a
   mismatch means wrong or missing spikes.
2. **All `trode_selection.decoding` groups must have exactly `mark_dim`
   channels.** This is the single easiest way to crash the encoder. See §7.
3. **Set the starting task state** (see §5):
   ```bash
   echo "1" >> ~/realtime_decoder/config/taskstate.txt
   ```
4. **Check `files.output_dir` exists and is writable.**
5. **`mpiexec -np N` must match the rank count** in the config
   (currently `N = 11`).

---

## 4. Step-by-step: first playback test (encoding **and** decoding)

### Step 0 — Understand what you are about to see

**Decoding runs continuously from the first spike. It is never gated by task
state.** The decoder produces a posterior every 6 ms bin the whole time.

What task state actually controls is *learning*:

| | Task state 1 | Task state 2 |
|---|---|---|
| Encoder adds spikes to the model | yes | **only if `train_all_task_states: true`** |
| Occupancy updates | yes | same as above |
| Decoder computes/sends posterior | yes | yes |
| Stimulation may fire shortcut messages | no | yes (not functional on hex — see §8) |
| Encoding model saved to disk | — | once, at the transition |

So early in the run the posterior will look like noise simply because the model
has almost no spikes in it yet. It sharpens as the model fills.

Because the config sets `train_all_task_states: true`, **the model keeps growing
after you switch to state 2**, which is what you asked for.

### Step 1 — Set the starting task state to 1

```bash
echo "1" >> ~/realtime_decoder/config/taskstate.txt
tail -1 ~/realtime_decoder/config/taskstate.txt   # should print 1
```

### Step 2 — Open Trodes and load the playback file

Open Trodes with the **same workspace** referenced in the config:

```
/media/ssd1/Vinnie/20260814_Vinnie_07_r4/20260814_Vinnie_07_r4.trodesconf
```

Load the `.rec` file for playback:

```
/media/ssd1/Vinnie/20260814_Vinnie_07_r4/20260814_Vinnie_07_r4.rec
```

Open the **Camera Module** and make sure position is being tracked/published —
the decoder needs the `source.position` stream, not just neural data. Do **not**
press Play yet.

### Step 3 — Start the decoder (before pressing Play)

```bash
conda activate realtime_decoder
cd ~/realtime_decoder
mpiexec -np 14 -bind-to hwthread python -u runscript.py config/Vinnie_nTrode12_test_config.yml
```

Startup is triggered by Trodes' own `play`/`record` network command, so the
decoder must already be listening.

### Step 4 — Wait for the GUI "READY" popup

Two windows appear: the plot window and a Parameters/Control dialog. Wait for the
popup saying all processes finished setup.

If it never appears but there are no errors, raise `num_setup_messages` (the
first setup messages are sometimes dropped).

### Step 5 — Press Play in Trodes

You should now see, in the terminal:

- `Received N pos points` — position is flowing
- `Added N spikes to encoding model of nTrode X` — **encoding is working**
- `Number of encoder occupancy points: N` — occupancy is filling

And in the GUI:

- Likelihood and posterior panels start filling left-to-right
- The **hex posterior scatter** lights up — 49 dots at the real maze coordinates,
  brightening where the decoder thinks the animal is

> If you see position points but **no** spikes being added, the animal is
> probably below `encoder.vel_thresh` (10 cm/s). Encoding only happens while the
> animal is *running*. See §7.

### Step 6 — Let the model build

Watch the "Added N spikes" counters. Wait until the trodes have accumulated a
meaningful number of spikes (a few thousand each is a reasonable starting point)
and the posterior visibly tracks the animal.

### Step 7 — Switch to task state 2 **while streaming**

This is the key step. In a **second terminal**, simply append a new line:

```bash
echo "2" >> ~/realtime_decoder/config/taskstate.txt
```

That is the entire mechanism. Every process re-reads the **last line** of that
file every `num_pos_points` position samples — 150 samples at 30 Hz, so the
change takes effect **within about 5 seconds**.

You can switch back and forth as many times as you like:

```bash
echo "1" >> ~/realtime_decoder/config/taskstate.txt   # back to state 1
echo "2" >> ~/realtime_decoder/config/taskstate.txt   # state 2 again
```

Watch the current state live:

```bash
watch -n 1 'tail -1 ~/realtime_decoder/config/taskstate.txt'
```

**What you should observe at the transition:**

- A one-time save: `n_spikes_current_in_buffer in encoder <trode>: N`, and
  `.encoder.npz` / `.occupancy.npz` files appear in `output_dir`
- Because `train_all_task_states: true`, the "Added N spikes" counters **keep
  climbing** — the model is still learning
- The posterior keeps updating throughout

### Step 8 — Stop the run

Press **Stop** in Trodes. That sends the termination command, all ranks shut
down, and rank 0 merges the per-rank binary records automatically.

Output lands in `/media/ssd1/decoder_output`, prefixed with a timestamp and
`Vinnie_hex_realtime_decoding`:

| File | Contents |
|---|---|
| `*.bin_rec` (merged) | All recorded events: decoded spikes, posteriors, occupancy, position |
| `*_trode_<n>.encoder.npz` | Encoding model per trode (marks, positions, occupancy) |
| `*_decoder_rank_1.occupancy.npz` | Decoder occupancy |
| `*.timing.npz` | Latency measurements |
| `*.config.yaml` | Exact config used for the run — snapshot for reproducibility |

---

## 5. Task state, in detail

The task state is read from the **last line** of `trodes.taskstate_file`. It is a
plain text file with one integer per line:

```
1
1
2
```

**Nothing updates this file automatically during playback.** In a live experiment
a StateScript program appends to it; during playback *you* are that program. This
is why the switch in Step 7 is a manual `echo`.

Reading is done with a non-blocking read of the final line, so appending while
the decoder is running is safe.

- **State 1** — training/encoding phase.
- **State 2** — decode/stimulation phase. Stim shortcut messages are only ever
  allowed in state 2 (`task_state == 2 and <other conditions>`).
- Any other value behaves like "not 1".

### Keeping the encoder growing while decoding

By default this decoder is *train-then-decode*: the moment task state leaves 1,
the encoding model freezes. To train and decode simultaneously, the config sets:

```yaml
encoder:
  train_all_task_states: true
```

With this on, the only remaining gates on learning are the velocity threshold and
`frozen_model`. Setting it to `false` (or deleting the key) restores the original
train-then-decode behaviour exactly.

> **Important limitation:** the KDE only ever uses the **first `bufsize` spikes**
> per trode. Spikes beyond that are stored but do not influence decoding, so the
> model effectively stops improving once `bufsize` (30000) spikes are collected
> for a trode. If you want a genuinely ever-growing model, raise `bufsize` —
> at the cost of more memory and slower per-spike KDE evaluation.

You can also freeze/unfreeze the model at any time from the GUI's
Parameters/Control dialog, which is independent of the task state.

---

## 6. Complete parameter reference

### `rank` / `rank_settings`
- **`supervisor`** — the orchestrator rank; also runs the stimulation decider. Exactly one.
- **`ripples`** — ranks doing LFP ripple detection.
- **`encoders`** — ranks building encoding models. Decoding trodes are handed out **round-robin**, so with 7 trodes and 7 encoder ranks each rank handles exactly one trode.
- **`decoders`** — ranks computing the posterior.
- **`gui`** — the display rank. Exactly one.
- **`rank_settings.enable_rec`** — which ranks write binary records to disk.

> Every integer `0 .. N-1` must appear in exactly **one** of these lists, and
> `mpiexec -np N` must equal the total. Otherwise startup raises `ValueError`.

### `trode_selection` / `decoder_assignment`
- **`ripples`** — electrode groups supplying LFP for ripple detection. Channel counts may differ between these groups; only one LFP channel per group is used.
- **`decoding`** — electrode groups supplying spikes for the encoding model. **Every group here must have exactly `mark_dim` channels.**
- **`decoder_assignment`** — maps each decoder rank to the trodes it decodes. Must collectively cover `trode_selection.decoding`.

### Top-level
- **`algorithm`** — `clusterless_decoder` (the one in real use).
- **`datasource`** — `trodes`. Selects which config block supplies acquisition settings.
- **`num_setup_messages`** — how many "setup complete" pings the supervisor sends the GUI. Raise it if the READY popup never appears.
- **`preloaded_model`** — `true` loads a saved encoding model from `saved_model_dir` instead of building one live.
- **`frozen_model`** — `true` prevents any new spikes entering the model. Toggleable in the GUI.

### `files`
- **`output_dir`** — where all output goes. Must exist and be writable.
- **`backup_dir`** — optional copy of critical files.
- **`saved_model_dir` / `saved_model_prefix`** — only used when `preloaded_model: true`; the prefix must match exactly one saved model set.
- **`prefix`** — output filename prefix (a timestamp is prepended automatically).
- **`rec_postfix` / `timing_postfix`** — filename suffixes for record and timing files.

### `trodes`
- **`config_file`** — the `.trodesconf` workspace. Defines electrode groups and the network address. **Must match the `.rec` being played back.**
- **`taskstate_file`** — file whose last line is the current task state. See §5.
- **`instructive_file`** — only read when `stimulation.instructive: true`.
- **`voltage_scaling_factor`** — raw Trodes units → microvolts. `0.195` for Intan headstages. Affects `spk_amp` and ripple thresholds.

### `sampling_rate`
- **`spikes`** (30000), **`lfp`** (1500), **`position`** (30) — in Hz. Used to convert sample counts to real time everywhere, including the decoding bin width and the task-state re-read interval.

### `ripples`
- **`max_ripple_samples`** — hard cap on ripple event length, in LFP samples.
- **`vel_thresh`** — cm/s. Ripples are only detected while the animal is **slower** than this (ripples happen at rest). Note this is the opposite sense to `encoder.vel_thresh`.
- **`freeze_stats`** — stop adapting the envelope mean/std.
- **`filter`** — the ripple band-pass. `iir` / order 2 / 150–250 Hz Butterworth by default.
- **`smoothing_filter`** — FIR smoothing applied to the ripple envelope.
- **`threshold`** — detection thresholds in **standard deviations above the mean** envelope: `standard`, `conditioning`, `content` (progressively stricter), and `end` (the level a ripple must fall back below to be considered over).
- **`custom_mean` / `custom_std`** — optional fixed statistics instead of adaptive estimates.

### `encoder`
- **`spk_amp`** — microvolts. A spike's peak mark value must exceed this to be used at all. Interacts with the threshold set in Trodes.
- **`use_channel_dist_from_max_amp`** — keeps only channels within ±N of the peak-amplitude channel, zeroing the rest of the mark vector. `2` keeps a 5-channel window. Only takes effect when the group has more than `2N+1` channels — with 12-channel groups it is active.
- **`mark_dim`** — length of the mark vector = **number of channels in each decoding trode**. One global value; all decoding trodes must match it.
- **`bufsize`** — spikes stored per trode. **Also caps how many spikes the KDE uses** (see §5).
- **`timings_bufsize`** — capacity of the latency-measurement array.
- **`vel_thresh`** — cm/s. Spikes are only added to the model while the animal is **faster** than this, so place fields are built from running data only.
- **`num_pos_points`** — re-read the task-state file every N position samples. 150 at 30 Hz ≈ every 5 s.
- **`train_all_task_states`** — keep learning after task state leaves 1. See §5.

#### `encoder.position` (hex mode)
- **`type`** — `"hex"` enables hex mode. `"linear"` (or omitting it) uses the original Trodes-linearization path.
- **`hex_centroid_file`** — `hex,x,y` CSV in raw camera pixels.
- **`hex_graph_file`** — `hex_a,hex_b` undirected adjacency CSV.
- **`hex_threshold`** — pixels. If the animal is farther than this from *every* centroid, tracking is treated as lost and position **holds at the last known hex** rather than jumping. 40 px ≈ the half-spacing between adjacent hexes.
- `num_bins` is **derived** from the CSVs at startup — do not set it manually.
- Linear-mode-only keys (`lower`, `upper`, `num_bins`, `arm_ids`, `arm_coords`) are ignored in hex mode.

#### `encoder.mark_kernel`
- **`mean`** — unused.
- **`std`** — microvolts. Width of the Gaussian kernel used to compare a new spike's mark against stored marks.
- **`use_filter`** — if true, only decode a spike when enough similar marks already exist.
- **`n_std`** — the search box is `mark ± n_std × std` in every dimension.
- **`n_marks_min`** — minimum stored marks inside that box for the spike to be decoded. Too high and few spikes decode; too low and estimates get noisy.

#### `encoder.dead_channels`
Map of trode id → list of **zero-indexed** channels to zero out before computing
the mark. Use for broken or noisy channels.

### `decoder`
- **`decoder_to_message`** — which decoder drives stimulation (`0` = all must agree).
- **`bufsize`** — circular buffer of incoming spike messages.
- **`cred_int_bufsize`** — how many recent credible intervals are kept.
- **`num_pos_points`** — task-state re-read cadence, as above.
- **`time_bin.samples`** — decoding bin width in spike samples. `180 / 30000 = 6 ms`.
- **`time_bin.delay_samples`** — how far the bin's right edge lags the live LFP clock. Larger = more tolerant of jitter, but adds latency.

### `clusterless_decoder`
- **`state_labels`** — names of the decoder states (one state here).
- **`transmat_bias`** — weight given to a hex itself and each adjacent hex before row-normalising the transition matrix. With the hex graph, non-adjacent hexes get zero probability, so the decoder cannot "teleport" across the maze in one 6 ms bin.

### `gui`
- **`colormap`** — any seaborn colormap name.
- **`send_interval`** — seconds between automatic parameter re-sends; `0` disables.
- **`refresh_rate`** — plot refresh rate in Hz.
- **`trace_length`** — seconds of history shown in the scrolling panels.
- **`state_colors` / `num_xticks`** — cosmetic.

### `mua`
Multiunit-activity burst detector. **`threshold.trigger` / `end`** are in SDs above the mean rate; **`moving_avg_window`** is the smoothing window in decoding bins. Informational unless used by stimulation.

### `stimulation`
Arm-based closed-loop logic. **Not functional on a hex maze** (see §8). Keys must still be present and well-formed for startup — notably `head_direction.well_loc` must have exactly two entries. `replay.enabled` and `ripples.enabled` are set `false` here.

### `kinematics`
- **`smooth_x` / `smooth_y` / `smooth_speed`** — which signals get FIR smoothing.
- **`smoothing_filter`** — the FIR coefficients.
- **`scale_factor`** — **centimetres per pixel.** Converts tracked pixel motion into cm/s. Every `vel_thresh` in the config depends on this being right. **Currently inherited from another rig — measure it for this camera.**

### `cred_interval`
- **`val`** — probability mass defining the credible interval (0.5 = 50%).
- **`max_num`** — how many bins may hold that mass before a spike is considered too uncertain.

### `display`
Console print cadence only (print every N events). Purely cosmetic; no effect on computation.

### `process_monitor`
- **`interval`** — seconds between liveness checks (`<= 0` disables).
- **`timeout`** — seconds to wait for replies. Too short and healthy ranks get falsely reported as dead.

---

## 7. Troubleshooting

**`ValueError: Could not find rank N listed in the config file!`**
`mpiexec -np N` does not match the rank lists. Count them again.

**Encoder crashes with a shape/broadcast error on the first spike**
A decoding trode's channel count does not equal `mark_dim`. Check the workspace:
```bash
python - <<'EOF'
import xml.etree.ElementTree as ET
root = ET.parse('/media/ssd1/Vinnie/20260814_Vinnie_07_r4/20260814_Vinnie_07_r4.trodesconf').getroot()
for t in root.find('SpikeConfiguration').findall('SpikeNTrode'):
    print(t.attrib['id'], len(t.findall('SpikeChannel')))
EOF
```
Every id in `trode_selection.decoding` must show the same count as `mark_dim`.

**Position arrives but no spikes are ever added to the model**
Most likely the velocity gate. Either the animal is genuinely below
`encoder.vel_thresh`, or `kinematics.scale_factor` is wrong so the computed speed
is wrong. Confirm the task state is 1 (or that `train_all_task_states: true`).

**Hex ids never change / always the same hex**
`hex_centroid_file` coordinates and the incoming camera coordinates are not in
the same space. The CSV must be in **raw camera pixels** for this camera
(1292×964 for this session).

**Position frequently "lost"**
Raise `hex_threshold`. At 40 px it covers roughly to the midpoint between
adjacent hexes; larger values assign the animal to the nearest hex more
aggressively.

**GUI never shows the "setup complete" popup**
Raise `num_setup_messages`.

**Nothing happens after pressing Play**
The decoder was probably started *after* Play. Stop everything, start the decoder
first, wait for READY, then press Play.

---

## 8. Known limitations on the hex maze

1. **Closed-loop stimulation does not work.** `stimulation.py` implements a
   two-arm task: it detects replay by summing posterior probability over *arms*
   using hard-coded bin ranges, and triggers per-arm rewards. None of that has a
   hex-graph equivalent. Ripple detection, encoding, decoding and the GUI all
   work; only the reward/stim decision logic is inapplicable. It is disabled in
   the config and left intact only so the supervisor rank starts.

2. **The model stops improving at `bufsize` spikes per trode** — see §5.

3. **`kinematics.scale_factor` is not calibrated for this rig.** Until measured,
   every velocity threshold is off by an unknown factor.

4. **Spike/position pairing is "most recent position wins."** Each spike is
   tagged with whatever hex was last reported, not a timestamp-interpolated
   position. This is the decoder's original behaviour, inherited unchanged. Hex
   ids change abruptly at boundaries, so a spike right at a hex boundary may be
   attributed to either side.

---

## 9. Quick reference

```bash
# start
conda activate realtime_decoder && cd ~/realtime_decoder
mpiexec -np 14 -bind-to hwthread python -u runscript.py config/Vinnie_nTrode12_test_config.yml

# switch task state while streaming
echo "2" >> ~/realtime_decoder/config/taskstate.txt   # decode phase
echo "1" >> ~/realtime_decoder/config/taskstate.txt   # back to training

# watch current task state
watch -n 1 'tail -1 ~/realtime_decoder/config/taskstate.txt'

# inspect results
ls -lt /media/ssd1/decoder_output | head
```
