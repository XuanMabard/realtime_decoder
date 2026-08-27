# content_analysis

What the decoder **decided**, per time bin — as opposed to `time_analysis/`, which covers how
fast it ran.

| File | Purpose |
|---|---|
| `decoder_output_content.ipynb` | Builds `bins`, `posterior`, and `likelihood` DataFrames from a run's merged output |

## What you get

Three objects sharing one index (one row per 6 ms time bin):

| Object | Shape | Contents |
|---|---|---|
| `bins` | n_bins × ~24 | Scalars: `decoded_hex`, `posterior_max`, `likelihood_hex`, `actual_hex`, `spike_count`, `cred_int_post`, `velocity`, `posterior_entropy`, error metrics, and all four time bases |
| `posterior` | n_bins × n_hex | P(animal in hex) after the transition model. Columns are **real hex ids** |
| `likelihood` | n_bins × n_hex | Spike evidence for that bin alone, before the transition model |
| `wide` | n_bins × (~24 + 2·n_hex) | All of the above joined into one table. Per-hex columns prefixed `post_hex01…` / `lik_hex01…`; recover a block with `wide.filter(like='post_hex')` |

The index is **unix seconds of the original recording** by default. Set `INDEX_BY` to any of
`recording_unix`, `playback_unix`, `recording_time`, `playback_time`, `trodes_sample` — all of
them remain available as columns regardless of which one indexes the frames.

## The clocks

The decoder's records carry two clocks that, during playback, refer to two different days.

| Time base | What it is | Use it for |
|---|---|---|
| `trodes_sample` | 30 kHz counter from the **original recording hardware**. Relative to that session's streaming start — encodes no date. | Ground truth; aligning with position/behaviour |
| **`recording_unix`** | **When the animal was actually there**, unix seconds. Reconstructed by anchoring the sample counter to the `.rec` header's `systemTimeAtCreation` / `timestampAtCreation`. | **Default index** — science |
| `recording_time` | The same instants as local datetimes. | Reading, plotting |
| `playback_unix` | **When your machine decoded it** (`rec_time`), unix seconds. | Performance analysis only |
| `playback_time` | The same instants as local datetimes. | Reading, plotting |

**Every unix/wall-clock field in the decoder's output is playback time, not recording time.**
Trodes stamps a *fresh* `systemTimestamp` when replaying a file — verified empirically
(`t_recv_data − t_send_data` ≈ 0.2 ms, not the 17 months separating the example run's recording
from its playback). The only route back to the original experiment's wall clock is the `.rec`
header anchor, which is what `recording_time` does.

All datetimes are reported in the machine's **local timezone**, matching the run prefix that
`runscript.py` generates.

## Quick use

```python
t0 = bins.recording_unix.iloc[0]
bins.loc[t0 + 60 : t0 + 120]                          # one minute of bins, 60 s in
posterior.loc[t0 + 60 : t0 + 120]                     # the same bins' posteriors

# wall-clock <-> unix
u = pd.Timestamp('2025-03-16 17:50', tz=LOCAL_TZ).timestamp()
bins.loc[u : u + 30]
pd.to_datetime(bins.index, unit='s', utc=True).tz_convert(LOCAL_TZ)   # index as datetimes

posterior.loc[bins.spike_count > 5]                   # bins with real spike evidence
posterior.iloc[100]                                   # full distribution for one bin
bins.decoded_hex.value_counts()                       # where the decoder spent its time
bins.groupby('actual_hex').error_hex_steps.mean()     # error by true location
```

## Gotchas

- **`mapped_pos` in the raw records is a dense 0-based index, not a hex id.** The notebook
  converts it via the run config's `hex_ids`; `actual_hex` is the converted value. Never read
  `mapped_pos` as a hex label.
- **`actual_hex = -1`** means position was unavailable for that bin. Excluded from error stats.
- **The posterior is recursive** — each bin folds in the previous bin's through the transition
  matrix, so consecutive rows are not independent. Use `likelihood` when you need independence.
- **Zero-spike bins still produce a posterior**, driven only by the transition model. Filter on
  `spike_count > 0` if that matters.
- **Decode quality depends on the run's health.** If a run dropped a large share of its spikes
  (check `time_analysis/decoder_efficiency_analysis.ipynb`), posteriors were built from partial
  evidence and understate what the model could do offline.
