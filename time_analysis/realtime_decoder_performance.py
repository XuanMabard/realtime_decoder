"""Utilities for analyzing realtime_decoder latency and throughput outputs.

This module intentionally does not import ``realtime_decoder``. Importing the
runtime package initializes MPI in some environments, which is unnecessary for
offline analysis. Binary records are read directly from their JSON header and
``struct`` formats, and large mark/posterior vectors are skipped on disk.
"""

from __future__ import annotations

import json
import math
import re
import struct
import warnings
from pathlib import Path
from typing import Iterable, Mapping, Optional

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns
import yaml

CONFIG_SUFFIX = ".config.yaml"
RECORD_HEAD = struct.Struct("=QBq")

# Only the scalar prefixes needed for performance analysis are unpacked. The
# remaining mark/histogram/posterior arrays are skipped with seek().
ENCODER_RECORD_ID = 3
ENCODER_PREFIX_FORMAT = "qidd?qqq?d?i"
ENCODER_PREFIX_LABELS = [
    "timestamp",
    "elec_grp_id",
    "position",
    "velocity",
    "encode_spike",
    "cred_int",
    "decoder_rank",
    "nearby_spikes",
    "sent_to_decoder",
    "vel_thresh",
    "frozen_model",
    "task_state",
]

DECODER_RECORD_ID = 4
DECODER_PREFIX_FORMAT = "qqqddddddddqqqqqqqd?"
DECODER_PREFIX_LABELS = [
    "timestamp",
    "bin_timestamp_l",
    "bin_timestamp_r",
    "velocity",
    "mapped_pos",
    "raw_x",
    "raw_y",
    "raw_x2",
    "raw_y2",
    "x",
    "y",
    "spike_count",
    "task_state",
    "cred_int_post",
    "cred_int_lk",
    "dec_rank",
    "dropped_spikes",
    "duplicated_spikes",
    "vel_thresh",
    "frozen_model",
]


def discover_runs(output_dir: Path | str) -> pd.DataFrame:
    """Return one row per saved run that has a copied config file."""

    output_dir = Path(output_dir).expanduser()
    rows = []
    for config_path in output_dir.glob(f"*{CONFIG_SUFFIX}"):
        prefix = config_path.name[: -len(CONFIG_SUFFIX)]
        posterior_timing_files = list(
            output_dir.glob(f"{prefix}_decoder_rank_*.timing.npz")
        )
        state_files = list(output_dir.glob(f"{prefix}.*.state.bin_rec"))
        rows.append(
            {
                "prefix": prefix,
                "config_path": config_path,
                "modified": config_path.stat().st_mtime,
                "state_files": len(state_files),
                "encoder_timing_files": len(
                    list(output_dir.glob(f"{prefix}_encoder_trode_*.timing.npz"))
                ),
                "decoder_timing_files": len(
                    list(output_dir.glob(f"{prefix}_decoder_trode_*.timing.npz"))
                ),
                "has_posterior_timing": bool(posterior_timing_files),
            }
        )

    columns = [
        "prefix",
        "config_path",
        "modified",
        "state_files",
        "encoder_timing_files",
        "decoder_timing_files",
        "has_posterior_timing",
    ]
    if not rows:
        return pd.DataFrame(columns=columns)

    result = pd.DataFrame(rows, columns=columns).sort_values("modified")
    result["modified"] = pd.to_datetime(result["modified"], unit="s")
    return result.reset_index(drop=True)


def select_run(
    output_dir: Path | str,
    run_prefix: Optional[str] = None,
) -> tuple[str, dict, pd.DataFrame]:
    """Select an explicit run or the newest completed-looking run."""

    output_dir = Path(output_dir).expanduser()
    runs = discover_runs(output_dir)
    if runs.empty:
        raise FileNotFoundError(f"No *{CONFIG_SUFFIX} files found in {output_dir}")

    if run_prefix is None:
        complete = runs[
            runs["has_posterior_timing"]
            & (runs["encoder_timing_files"] > 0)
            & (runs["decoder_timing_files"] > 0)
        ]
        chosen = complete.iloc[-1] if not complete.empty else runs.iloc[-1]
        run_prefix = str(chosen["prefix"])
    elif run_prefix not in set(runs["prefix"]):
        raise FileNotFoundError(
            f"Run prefix {run_prefix!r} was not found in {output_dir}"
        )

    config_path = output_dir / f"{run_prefix}{CONFIG_SUFFIX}"
    with config_path.open() as stream:
        config = yaml.safe_load(stream)
    return run_prefix, config, runs


def _read_json_header(stream, limit: int = 1_000_000) -> dict:
    """Read the quote-aware JSON header and leave the stream at record 0."""

    first = stream.read(1)
    if first != b"{":
        raise ValueError(f"{stream.name}: JSON binary-record header not found")

    data = bytearray(first)
    depth = 1
    in_string = False
    escaped = False
    while depth:
        char = stream.read(1)
        if not char:
            raise EOFError(f"{stream.name}: truncated JSON header")
        data.extend(char)
        if len(data) > limit:
            raise ValueError(f"{stream.name}: JSON header exceeds {limit} bytes")

        value = char[0]
        if in_string:
            if escaped:
                escaped = False
            elif value == 0x5C:  # backslash
                escaped = True
            elif value == 0x22:  # quote
                in_string = False
        elif value == 0x22:
            in_string = True
        elif value == 0x7B:  # {
            depth += 1
        elif value == 0x7D:  # }
            depth -= 1

    return json.loads(data.decode("utf-8"))


def inspect_binary_header(path: Path | str) -> dict:
    """Return a binary-record header without reading any records."""

    with Path(path).open("rb") as stream:
        return _read_json_header(stream)


def _read_record_prefix(
    path: Path | str,
    record_id: int,
    prefix_format: str,
    expected_labels: Iterable[str],
) -> pd.DataFrame:
    """Read only a record's scalar prefix and seek past its vector payload."""

    path = Path(path)
    expected_labels = list(expected_labels)
    rows = []
    with path.open("rb") as stream:
        header = _read_json_header(stream)
        formats = {int(key): value for key, value in header["rec_formats"].items()}
        labels = {int(key): value for key, value in header["rec_labels"].items()}

        if record_id not in formats:
            return pd.DataFrame(
                columns=[
                    "writer_rank",
                    "record_index",
                    "record_time_ns",
                    *expected_labels,
                ]
            )
        if labels[record_id][: len(expected_labels)] != expected_labels:
            raise ValueError(
                f"{path}: record {record_id} labels changed; update the reader"
            )
        if not formats[record_id].startswith(prefix_format):
            raise ValueError(
                f"{path}: record {record_id} format changed from {prefix_format!r}"
            )

        record_sizes = {
            rid: struct.calcsize("=" + format_string)
            for rid, format_string in formats.items()
        }
        prefix_struct = struct.Struct("=" + prefix_format)

        while True:
            raw_header = stream.read(RECORD_HEAD.size)
            if not raw_header:
                break
            if len(raw_header) != RECORD_HEAD.size:
                warnings.warn(f"Ignoring truncated record header at end of {path}")
                break

            record_index, current_id, record_time_ns = RECORD_HEAD.unpack(raw_header)
            payload_size = record_sizes.get(current_id)
            if payload_size is None:
                raise ValueError(f"{path}: unknown record id {current_id}")

            if current_id != record_id:
                stream.seek(payload_size, 1)
                continue

            raw_prefix = stream.read(prefix_struct.size)
            if len(raw_prefix) != prefix_struct.size:
                warnings.warn(f"Ignoring truncated record {record_index} in {path}")
                break
            values = prefix_struct.unpack(raw_prefix)
            stream.seek(payload_size - prefix_struct.size, 1)
            rows.append(
                (
                    int(header["mpi_rank"]),
                    record_index,
                    record_time_ns,
                    *values,
                )
            )

    return pd.DataFrame(
        rows,
        columns=[
            "writer_rank",
            "record_index",
            "record_time_ns",
            *expected_labels,
        ],
    )


def _state_files_by_rank(output_dir: Path, prefix: str) -> dict[int, Path]:
    result = {}
    for path in output_dir.glob(f"{prefix}.*.state.bin_rec"):
        header = inspect_binary_header(path)
        result[int(header["mpi_rank"])] = path
    return result


def read_encoder_records(
    output_dir: Path | str,
    prefix: str,
    encoder_ranks: Iterable[int],
) -> pd.DataFrame:
    """Read amplitude-qualified encoder records from all encoder ranks.

    ``kde_sent`` is inferred from ``cred_int >= 0``. This deliberately avoids
    the legacy ID-3 field-order bug, which makes the stored column named
    ``sent_to_decoder`` unreliable in current files.
    """

    output_dir = Path(output_dir)
    paths = _state_files_by_rank(output_dir, prefix)
    frames = []
    for rank in encoder_ranks:
        rank = int(rank)
        if rank not in paths:
            warnings.warn(f"Encoder rank {rank} has no binary record file")
            continue
        frame = _read_record_prefix(
            paths[rank],
            ENCODER_RECORD_ID,
            ENCODER_PREFIX_FORMAT,
            ENCODER_PREFIX_LABELS,
        )
        print(f"Read {len(frame):,} encoder records from rank {rank}")
        frames.append(frame)

    if not frames:
        raise FileNotFoundError("No encoder ID-3 records were found")
    result = pd.concat(frames, ignore_index=True)
    result["encode_spike"] = result["encode_spike"].astype(bool)
    result["kde_sent"] = result["cred_int"] >= 0
    result = result.rename(columns={"writer_rank": "encoder_rank"})
    return result


def read_decoder_records(
    output_dir: Path | str,
    prefix: str,
    decoder_ranks: Iterable[int],
) -> pd.DataFrame:
    """Read decoder-bin metadata while skipping all posterior vectors."""

    output_dir = Path(output_dir)
    paths = _state_files_by_rank(output_dir, prefix)
    frames = []
    for rank in decoder_ranks:
        rank = int(rank)
        if rank not in paths:
            warnings.warn(f"Decoder rank {rank} has no binary record file")
            continue
        frame = _read_record_prefix(
            paths[rank],
            DECODER_RECORD_ID,
            DECODER_PREFIX_FORMAT,
            DECODER_PREFIX_LABELS,
        )
        print(f"Read {len(frame):,} decoder-bin records from rank {rank}")
        frames.append(frame)

    if not frames:
        raise FileNotFoundError("No decoder ID-4 records were found")
    result = pd.concat(frames, ignore_index=True)
    result = result.rename(
        columns={
            "writer_rank": "record_writer_rank",
            "dec_rank": "record_decoder_rank",
        }
    )
    return result


def _npz_timing_frame(path: Path) -> pd.DataFrame:
    with np.load(path, allow_pickle=False) as data:
        return pd.DataFrame(data["timings"])


def _trode_from_path(path: Path) -> int:
    match = re.search(r"_trode_(\d+)\.timing\.npz$", path.name)
    if not match:
        raise ValueError(f"Could not extract nTrode id from {path}")
    return int(match.group(1))


def load_timing_tables(
    output_dir: Path | str,
    prefix: str,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Load encoder, decoder-arrival, and posterior timing NPZ files."""

    output_dir = Path(output_dir)
    encoder_frames = []
    for path in sorted(output_dir.glob(f"{prefix}_encoder_trode_*.timing.npz")):
        frame = _npz_timing_frame(path)
        if "elec_grp_id" not in frame:
            frame["elec_grp_id"] = _trode_from_path(path)
        encoder_frames.append(frame)

    decoder_frames = []
    for path in sorted(output_dir.glob(f"{prefix}_decoder_trode_*.timing.npz")):
        frame = _npz_timing_frame(path)
        if "elec_grp_id" not in frame:
            frame["elec_grp_id"] = _trode_from_path(path)
        decoder_frames.append(frame)

    posterior_frames = [
        _npz_timing_frame(path)
        for path in sorted(output_dir.glob(f"{prefix}_decoder_rank_*.timing.npz"))
    ]
    if not encoder_frames or not decoder_frames or not posterior_frames:
        raise FileNotFoundError(
            "The run is missing encoder, decoder-arrival, or posterior timing files"
        )

    return (
        pd.concat(encoder_frames, ignore_index=True),
        pd.concat(decoder_frames, ignore_index=True),
        pd.concat(posterior_frames, ignore_index=True),
    )


def _model_counts_from_files(paths: Iterable[Path]) -> dict[int, int]:
    counts = {}
    for path in paths:
        match = re.search(r"_trode_(\d+)\.encoder\.npz$", path.name)
        if not match:
            continue
        with np.load(path, allow_pickle=False) as data:
            counts[int(match.group(1))] = int(np.asarray(data["mark_idx"]).flat[0])
    return counts


def load_final_model_sizes(output_dir: Path | str, prefix: str) -> dict[int, int]:
    output_dir = Path(output_dir)
    return _model_counts_from_files(output_dir.glob(f"{prefix}_trode_*.encoder.npz"))


def load_initial_model_sizes(config: Mapping, trodes: Iterable[int]) -> dict[int, int]:
    """Read preloaded-model offsets without loading the large marks arrays."""

    trodes = [int(trode) for trode in trodes]
    if not config.get("preloaded_model", False):
        return {trode: 0 for trode in trodes}

    model_dir = Path(config["files"]["saved_model_dir"]).expanduser()
    saved_prefix = config["files"]["saved_model_prefix"]
    counts = {}
    for trode in trodes:
        candidates = list(model_dir.glob(f"{saved_prefix}*trode_{trode}.encoder.npz"))
        if len(candidates) != 1:
            warnings.warn(
                f"Expected one initial model for nTrode {trode}; found {len(candidates)}"
            )
            counts[trode] = 0
        else:
            saved = _model_counts_from_files(candidates).get(trode, 0)
            # Match Encoder._load_model(): the runtime deliberately starts one
            # slot below the saved mark_idx (or one below the buffer ceiling).
            counts[trode] = max(
                min(saved, int(config["encoder"]["bufsize"])) - 1,
                0,
            )
    return counts


def _add_occurrence_index(
    frame: pd.DataFrame,
    order_column: str,
) -> pd.DataFrame:
    """Disambiguate repeated (nTrode, timestamp) pairs before merging."""

    result = frame.sort_values(
        ["elec_grp_id", "timestamp", order_column], kind="stable"
    ).copy()
    result["occurrence"] = result.groupby(
        ["elec_grp_id", "timestamp"], sort=False
    ).cumcount()
    return result


def build_analysis_tables(
    output_dir: Path | str,
    prefix: str,
    config: Mapping,
) -> dict[str, object]:
    """Read a run and construct aligned encoder, spike, and bin tables.

    Repeated ``(nTrode, timestamp)`` pairs receive an occurrence number before
    joins. This prevents a many-to-many merge from silently multiplying rows.
    A sent spike is considered on time only when the decoder received it before
    the intended bin's posterior computation began.
    """

    output_dir = Path(output_dir).expanduser()
    encoder_events = read_encoder_records(
        output_dir, prefix, config["rank"]["encoders"]
    )
    decoder_metadata = read_decoder_records(
        output_dir, prefix, config["rank"]["decoders"]
    )
    encoder_timing, decoder_timing, posterior_timing = load_timing_tables(
        output_dir, prefix
    )

    trodes = sorted(int(value) for value in encoder_events["elec_grp_id"].unique())
    initial_sizes = load_initial_model_sizes(config, trodes)
    final_sizes = load_final_model_sizes(output_dir, prefix)

    encoder_events = encoder_events.sort_values(
        ["elec_grp_id", "record_time_ns", "record_index"], kind="stable"
    ).copy()
    additions = encoder_events["encode_spike"].astype(np.int64)
    encoder_events["model_additions"] = additions.groupby(
        encoder_events["elec_grp_id"]
    ).cumsum()
    initial = (
        encoder_events["elec_grp_id"].map(initial_sizes).fillna(0).astype(np.int64)
    )
    encoder_events["model_size_after"] = initial + encoder_events["model_additions"]
    encoder_events["model_size_before"] = encoder_events["model_size_after"] - additions
    encoder_events["effective_model_size"] = np.minimum(
        encoder_events["model_size_before"], int(config["encoder"]["bufsize"])
    )

    decoder_rank_for = {
        int(trode): int(rank)
        for rank, assigned_trodes in config["decoder_assignment"].items()
        for trode in assigned_trodes
    }
    decoder_timing["decoder_rank"] = decoder_timing["elec_grp_id"].map(decoder_rank_for)
    if decoder_timing["decoder_rank"].isna().any():
        missing = sorted(
            int(value)
            for value in decoder_timing.loc[
                decoder_timing["decoder_rank"].isna(), "elec_grp_id"
            ].unique()
        )
        raise ValueError(f"No decoder_assignment entry for nTrodes {missing}")
    decoder_timing["decoder_rank"] = decoder_timing["decoder_rank"].astype(int)

    # Timing NPZs exist only for successful joint-probability queries.
    encoder_sent_metadata = _add_occurrence_index(
        encoder_events[encoder_events["kde_sent"]].copy(), "record_time_ns"
    )
    encoder_timing = _add_occurrence_index(encoder_timing, "t_recv_data")
    decoder_timing = _add_occurrence_index(decoder_timing, "t_decoder")
    decoder_timing = decoder_timing.sort_values(
        ["decoder_rank", "t_decoder", "elec_grp_id"], kind="stable"
    ).copy()
    decoder_timing["recv_seq"] = decoder_timing.groupby(
        "decoder_rank", sort=False
    ).cumcount()
    decoder_timing["buffer_slot"] = decoder_timing["recv_seq"] % int(
        config["decoder"]["bufsize"]
    )
    join_keys = ["elec_grp_id", "timestamp", "occurrence"]

    sent_spikes = encoder_sent_metadata[
        join_keys
        + [
            "encoder_rank",
            "decoder_rank",
            "record_time_ns",
            "encode_spike",
            "position",
            "velocity",
            "model_size_before",
            "model_size_after",
            "effective_model_size",
        ]
    ].merge(
        encoder_timing,
        on=join_keys,
        how="left",
        validate="one_to_one",
        indicator="encoder_record_join",
    )
    sent_spikes["decoder_rank"] = sent_spikes["decoder_rank"].astype(int)
    sent_spikes = sent_spikes.merge(
        decoder_timing[
            join_keys + ["decoder_rank", "t_decoder", "recv_seq", "buffer_slot"]
        ],
        on=join_keys + ["decoder_rank"],
        how="left",
        validate="one_to_one",
        indicator="decoder_timing_join",
    )

    decoder_metadata_for_join = decoder_metadata.rename(
        columns={"record_decoder_rank": "decoder_rank"}
    )
    posterior_bins = posterior_timing.merge(
        decoder_metadata_for_join[
            [
                "decoder_rank",
                "bin_timestamp_l",
                "bin_timestamp_r",
                "record_time_ns",
                "timestamp",
                "spike_count",
                "task_state",
                "dropped_spikes",
                "duplicated_spikes",
            ]
        ],
        on=["decoder_rank", "bin_timestamp_l", "bin_timestamp_r"],
        how="left",
        validate="one_to_one",
        indicator="decoder_record_join",
    ).sort_values(["decoder_rank", "bin_timestamp_l"], kind="stable")
    posterior_bins = posterior_bins.reset_index(drop=True)
    posterior_bins["bin_index"] = np.arange(len(posterior_bins), dtype=np.int64)

    # Use a shared wall-clock origin for performance plots. Trodes sample time
    # is retained separately because playback and wall time can diverge.
    wall_t0_ns = min(
        int(encoder_events["record_time_ns"].min()),
        int(encoder_timing["t_recv_data"].min()),
        int(posterior_bins["t_start_post"].min()),
    )
    sample_t0 = min(
        int(encoder_events["timestamp"].min()),
        int(posterior_bins["bin_timestamp_l"].min()),
    )
    spike_rate = float(config["sampling_rate"]["spikes"])

    encoder_events["elapsed_s"] = (encoder_events["record_time_ns"] - wall_t0_ns) / 1e9
    encoder_events["source_elapsed_s"] = (
        encoder_events["timestamp"] - sample_t0
    ) / spike_rate
    sent_spikes["elapsed_s"] = (
        sent_spikes["t_recv_data"].fillna(sent_spikes["record_time_ns"]) - wall_t0_ns
    ) / 1e9
    sent_spikes["source_elapsed_s"] = (
        sent_spikes["timestamp"] - sample_t0
    ) / spike_rate
    posterior_bins["elapsed_s"] = (posterior_bins["t_start_post"] - wall_t0_ns) / 1e9
    posterior_bins["source_elapsed_s"] = (
        posterior_bins["bin_timestamp_l"] - sample_t0
    ) / spike_rate

    # Stage durations. These are wall-clock measurements on the same host.
    sent_spikes["source_to_encoder_ms"] = (
        sent_spikes["t_recv_data"] - sent_spikes["t_send_data"]
    ) / 1e6
    sent_spikes["encoder_schedule_ms"] = (
        sent_spikes["t_start_kde"] - sent_spikes["t_recv_data"]
    ) / 1e6
    sent_spikes["kde_ms"] = (
        sent_spikes["t_end_kde"] - sent_spikes["t_start_kde"]
    ) / 1e6
    sent_spikes["post_kde_ms"] = (
        sent_spikes["t_start_enc_send"] - sent_spikes["t_end_kde"]
    ) / 1e6
    sent_spikes["encoder_send_call_ms"] = (
        sent_spikes["t_end_enc_send"] - sent_spikes["t_start_enc_send"]
    ) / 1e6
    sent_spikes["encoder_total_ms"] = (
        sent_spikes["t_end_enc_send"] - sent_spikes["t_recv_data"]
    ) / 1e6
    sent_spikes["decoder_received"] = sent_spikes["t_decoder"].notna()
    sent_spikes["encoder_to_decoder_ms"] = (
        sent_spikes["t_decoder"] - sent_spikes["t_start_enc_send"]
    ) / 1e6
    sent_spikes["source_to_decoder_ms"] = (
        sent_spikes["t_decoder"] - sent_spikes["t_send_data"]
    ) / 1e6

    posterior_bins["posterior_ms"] = (
        posterior_bins["t_end_post"] - posterior_bins["t_start_post"]
    ) / 1e6
    posterior_bins["wall_bin_interval_ms"] = (
        posterior_bins.groupby("decoder_rank")["t_start_post"].diff() / 1e6
    )

    def counter_increment(series: pd.Series) -> pd.Series:
        numeric = pd.to_numeric(series, errors="coerce").fillna(0)
        delta = numeric.diff()
        if len(delta):
            delta.iloc[0] = max(float(numeric.iloc[0]), 0)
        reset = delta < 0
        delta.loc[reset] = numeric.loc[reset]
        return delta.fillna(0).clip(lower=0)

    posterior_bins["reported_drop_increment"] = posterior_bins.groupby(
        "decoder_rank", group_keys=False
    )["dropped_spikes"].apply(counter_increment)
    posterior_bins["duplicate_increment"] = posterior_bins.groupby(
        "decoder_rank", group_keys=False
    )["duplicated_spikes"].apply(counter_increment)

    # Map each sent spike to the unique intended half-open decoder bin [l, r).
    sent_spikes["intended_bin_index"] = -1
    for rank, row_indices in sent_spikes.groupby("decoder_rank").groups.items():
        bins_for_rank = posterior_bins[
            posterior_bins["decoder_rank"] == rank
        ].sort_values("bin_timestamp_l", kind="stable")
        left = bins_for_rank["bin_timestamp_l"].to_numpy(dtype=np.int64)
        right = bins_for_rank["bin_timestamp_r"].to_numpy(dtype=np.int64)
        timestamps = sent_spikes.loc[row_indices, "timestamp"].to_numpy(dtype=np.int64)
        candidate = np.searchsorted(left, timestamps, side="right") - 1
        valid = candidate >= 0
        safe = np.clip(candidate, 0, max(len(left) - 1, 0))
        if len(left):
            valid &= (timestamps >= left[safe]) & (timestamps < right[safe])
        else:
            valid[:] = False
        mapped = np.full(len(timestamps), -1, dtype=np.int64)
        mapped[valid] = bins_for_rank["bin_index"].to_numpy(dtype=np.int64)[safe[valid]]
        sent_spikes.loc[row_indices, "intended_bin_index"] = mapped

    sent_spikes["intended_bin_index"] = sent_spikes["intended_bin_index"].astype(
        np.int64
    )
    sent_spikes["in_bin_coverage"] = sent_spikes["intended_bin_index"] >= 0
    bin_columns = posterior_bins.set_index("bin_index")[
        ["t_start_post", "t_end_post", "bin_timestamp_l", "bin_timestamp_r"]
    ].rename(
        columns={
            "t_start_post": "intended_t_start_post",
            "t_end_post": "intended_t_end_post",
            "bin_timestamp_l": "intended_bin_l",
            "bin_timestamp_r": "intended_bin_r",
        }
    )
    sent_spikes = sent_spikes.join(
        bin_columns, on="intended_bin_index", validate="many_to_one"
    )

    received = sent_spikes["decoder_received"]
    in_coverage = sent_spikes["in_bin_coverage"]
    # The decoder inserts messages and computes the posterior in one thread.
    # At/after t_start_post is too late to enter that bin.
    sent_spikes["on_time"] = (
        received
        & in_coverage
        & (sent_spikes["t_decoder"] < sent_spikes["intended_t_start_post"])
    )
    sent_spikes["late"] = received & in_coverage & ~sent_spikes["on_time"]
    sent_spikes["unmatched_receive"] = ~received
    sent_spikes["deadline_slack_ms"] = (
        sent_spikes["intended_t_start_post"] - sent_spikes["t_decoder"]
    ) / 1e6
    sent_spikes["late_tardiness_ms"] = np.where(
        sent_spikes["late"], -sent_spikes["deadline_slack_ms"], np.nan
    )
    sent_spikes["decoder_to_posterior_ms"] = np.where(
        sent_spikes["on_time"],
        (sent_spikes["intended_t_end_post"] - sent_spikes["t_decoder"]) / 1e6,
        np.nan,
    )
    sent_spikes["source_to_posterior_ms"] = np.where(
        sent_spikes["on_time"],
        (sent_spikes["intended_t_end_post"] - sent_spikes["t_send_data"]) / 1e6,
        np.nan,
    )

    # Reproduce the decoder's circular-buffer and timestamp-dedup behavior so
    # every sent spike receives one auditable outcome.
    sent_spikes["buffer_overwritten"] = False
    decoder_buffer_size = int(config["decoder"]["bufsize"])
    for rank, row_indices in (
        sent_spikes[sent_spikes["on_time"]].groupby("decoder_rank").groups.items()
    ):
        receive_walls = np.sort(
            decoder_timing.loc[
                decoder_timing["decoder_rank"] == rank, "t_decoder"
            ].to_numpy(dtype=np.int64)
        )
        newer = (
            np.searchsorted(
                receive_walls,
                sent_spikes.loc[row_indices, "intended_t_start_post"].to_numpy(
                    dtype=np.int64
                ),
                side="left",
            )
            - sent_spikes.loc[row_indices, "recv_seq"].to_numpy(dtype=np.int64)
            - 1
        )
        sent_spikes.loc[row_indices, "buffer_overwritten"] = (
            newer >= decoder_buffer_size
        )

    sent_spikes["eligible_for_posterior"] = (
        sent_spikes["on_time"] & ~sent_spikes["buffer_overwritten"]
    )
    sent_spikes["duplicate_group_size"] = 0
    eligible = sent_spikes["eligible_for_posterior"]
    duplicate_keys = ["decoder_rank", "intended_bin_index", "timestamp"]
    sent_spikes.loc[eligible, "duplicate_group_size"] = (
        sent_spikes.loc[eligible].groupby(duplicate_keys)["timestamp"].transform("size")
    )
    minimum_slot = (
        sent_spikes.loc[eligible]
        .groupby(duplicate_keys)["buffer_slot"]
        .transform("min")
    )
    sent_spikes["used_in_posterior"] = False
    sent_spikes.loc[eligible, "used_in_posterior"] = sent_spikes.loc[
        eligible, "duplicate_group_size"
    ].eq(1) | (
        sent_spikes.loc[eligible, "duplicate_group_size"].eq(2)
        & sent_spikes.loc[eligible, "buffer_slot"].eq(minimum_slot)
    )
    sent_spikes["duplicate_removed"] = (
        sent_spikes["eligible_for_posterior"] & ~sent_spikes["used_in_posterior"]
    )
    sent_spikes["status"] = np.select(
        [
            sent_spikes["unmatched_receive"],
            ~sent_spikes["in_bin_coverage"],
            sent_spikes["late"],
            sent_spikes["buffer_overwritten"],
            sent_spikes["duplicate_removed"],
            sent_spikes["used_in_posterior"],
        ],
        [
            "transport_missing",
            "outside_recorded_bins",
            "late",
            "buffer_overwritten",
            "duplicate_removed",
            "used",
        ],
        default="unclassified",
    )

    used_by_bin = sent_spikes.groupby("intended_bin_index")["used_in_posterior"].sum()
    removed_by_bin = sent_spikes.groupby("intended_bin_index")[
        "duplicate_removed"
    ].sum()
    posterior_bins["derived_used_spikes"] = (
        posterior_bins["bin_index"].map(used_by_bin).fillna(0).astype(np.int64)
    )
    posterior_bins["derived_duplicate_removals"] = (
        posterior_bins["bin_index"].map(removed_by_bin).fillna(0).astype(np.int64)
    )

    return {
        "encoder_events": encoder_events,
        "sent_spikes": sent_spikes,
        "posterior_bins": posterior_bins,
        "decoder_metadata": decoder_metadata,
        "encoder_timing": encoder_timing,
        "decoder_timing": decoder_timing,
        "initial_model_sizes": initial_sizes,
        "final_model_sizes": final_sizes,
        "wall_t0_ns": wall_t0_ns,
        "sample_t0": sample_t0,
        "spike_rate": spike_rate,
    }


def validation_table(tables: Mapping[str, object]) -> pd.DataFrame:
    """Return consistency checks without hiding known legacy discrepancies."""

    encoder_events = tables["encoder_events"]
    sent_spikes = tables["sent_spikes"]
    posterior_bins = tables["posterior_bins"]
    encoder_timing = tables["encoder_timing"]
    decoder_timing = tables["decoder_timing"]
    final_sizes = tables["final_model_sizes"]
    initial_sizes = tables["initial_model_sizes"]

    additions_by_trode = (
        encoder_events.groupby("elec_grp_id")["encode_spike"].sum().astype(int)
    )
    expected_by_trode = pd.Series(
        {
            int(trode): max(
                final_sizes.get(int(trode), 0) - initial_sizes.get(int(trode), 0),
                0,
            )
            for trode in additions_by_trode.index
        }
    )
    sent_records = int(encoder_events["kde_sent"].sum())
    encoder_timing_matches = int((sent_spikes["encoder_record_join"] == "both").sum())
    received_rows = int(sent_spikes["decoder_received"].sum())
    decoder_timing_rows = len(decoder_timing)
    posterior_record_matches = int(
        (posterior_bins["decoder_record_join"] == "both").sum()
    )

    checks = [
        (
            "Encoder additions match saved growth for every nTrode",
            int((additions_by_trode == expected_by_trode).sum()),
            len(expected_by_trode),
            bool((additions_by_trode == expected_by_trode).all()),
        ),
        (
            "KDE-sent ID-3 records retained",
            sent_records,
            len(sent_spikes),
            sent_records == len(sent_spikes),
        ),
        (
            "KDE-sent records matched encoder timing rows",
            encoder_timing_matches,
            len(encoder_timing),
            encoder_timing_matches == len(encoder_timing) == sent_records,
        ),
        (
            "Received flags equal decoder timing rows",
            received_rows,
            decoder_timing_rows,
            received_rows == decoder_timing_rows,
        ),
        (
            "Posterior timing rows matched decoder records",
            posterior_record_matches,
            len(posterior_bins),
            posterior_record_matches == len(posterior_bins),
        ),
        (
            "Posterior durations are nonnegative",
            int((posterior_bins["posterior_ms"] >= 0).sum()),
            len(posterior_bins),
            bool((posterior_bins["posterior_ms"] >= 0).all()),
        ),
        (
            "KDE durations are nonnegative",
            int((sent_spikes["kde_ms"] >= 0).sum()),
            encoder_timing_matches,
            bool(sent_spikes.loc[sent_spikes["kde_ms"].notna(), "kde_ms"].ge(0).all()),
        ),
        (
            "Derived used count matches every posterior bin",
            int(
                (
                    posterior_bins["derived_used_spikes"]
                    == posterior_bins["spike_count"]
                ).sum()
            ),
            len(posterior_bins),
            bool(
                (
                    posterior_bins["derived_used_spikes"]
                    == posterior_bins["spike_count"]
                ).all()
            ),
        ),
        (
            "Derived timestamp removals match every posterior bin",
            int(
                (
                    posterior_bins["derived_duplicate_removals"]
                    == posterior_bins["duplicate_increment"]
                ).sum()
            ),
            len(posterior_bins),
            bool(
                (
                    posterior_bins["derived_duplicate_removals"]
                    == posterior_bins["duplicate_increment"]
                ).all()
            ),
        ),
    ]
    return pd.DataFrame(checks, columns=["check", "observed", "expected", "passes"])


def headline_summary(
    tables: Mapping[str, object],
    config: Mapping,
) -> pd.DataFrame:
    """Create a compact summary of counts, latency, and decoder headroom."""

    encoder_events = tables["encoder_events"]
    sent_spikes = tables["sent_spikes"]
    posterior_bins = tables["posterior_bins"]
    duration_min = (
        max(
            float(encoder_events["elapsed_s"].max()),
            float(posterior_bins["elapsed_s"].max()),
        )
        / 60
    )
    received = sent_spikes["decoder_received"]
    valid_received = received & sent_spikes["in_bin_coverage"]
    late_count = int(sent_spikes["late"].sum())
    late_denominator = int(valid_received.sum())
    bin_ms = (
        float(config["decoder"]["time_bin"]["samples"])
        / float(config["sampling_rate"]["spikes"])
        * 1000
    )

    def percentile(series: pd.Series, value: float) -> float:
        clean = pd.to_numeric(series, errors="coerce").dropna()
        return float(clean.quantile(value)) if len(clean) else math.nan

    rows = [
        ("Run duration", duration_min, "min"),
        ("Amplitude-qualified spikes", len(encoder_events), "count"),
        (
            "Spikes added to encoder models",
            int(encoder_events["encode_spike"].sum()),
            "count",
        ),
        (
            "Joint-probability messages sent",
            int(encoder_events["kde_sent"].sum()),
            "count",
        ),
        ("Messages received by decoder", int(received.sum()), "count"),
        ("Messages received within recorded bins", late_denominator, "count"),
        (
            "Spikes used in posterior bins",
            int(sent_spikes["used_in_posterior"].sum()),
            "count",
        ),
        ("Derived late arrivals", late_count, "count"),
        (
            "Derived late-arrival fraction",
            100 * late_count / late_denominator if late_denominator else math.nan,
            "%",
        ),
        (
            "Unmatched sent messages",
            int(sent_spikes["unmatched_receive"].sum()),
            "count",
        ),
        (
            "Received outside recorded bin coverage",
            int((received & ~sent_spikes["in_bin_coverage"]).sum()),
            "count",
        ),
        (
            "Circular-buffer overwrites (derived)",
            int(sent_spikes["buffer_overwritten"].sum()),
            "count",
        ),
        (
            "Timestamp-collision removals (derived)",
            int(sent_spikes["duplicate_removed"].sum()),
            "count",
        ),
        (
            "Reported circular-buffer drops",
            int(posterior_bins["reported_drop_increment"].sum()),
            "count (approx.)",
        ),
        ("KDE time median", percentile(sent_spikes["kde_ms"], 0.5), "ms"),
        ("KDE time p95", percentile(sent_spikes["kde_ms"], 0.95), "ms"),
        ("KDE time p99", percentile(sent_spikes["kde_ms"], 0.99), "ms"),
        (
            "Posterior time median",
            percentile(posterior_bins["posterior_ms"], 0.5),
            "ms",
        ),
        ("Posterior time p95", percentile(posterior_bins["posterior_ms"], 0.95), "ms"),
        ("Posterior time p99", percentile(posterior_bins["posterior_ms"], 0.99), "ms"),
        ("Configured source-bin width", bin_ms, "ms"),
        (
            "Observed wall interval between posterior bins (median)",
            percentile(posterior_bins["wall_bin_interval_ms"], 0.5),
            "ms",
        ),
        (
            "Playback speed factor (median estimate)",
            bin_ms / percentile(posterior_bins["wall_bin_interval_ms"], 0.5),
            "x realtime",
        ),
        (
            "On-time decoder-receive-to-posterior median",
            percentile(
                sent_spikes.loc[sent_spikes["on_time"], "decoder_to_posterior_ms"],
                0.5,
            ),
            "ms",
        ),
        (
            "On-time decoder-receive-to-posterior p99",
            percentile(
                sent_spikes.loc[sent_spikes["on_time"], "decoder_to_posterior_ms"],
                0.99,
            ),
            "ms",
        ),
        (
            "On-time source-to-posterior median",
            percentile(
                sent_spikes.loc[sent_spikes["on_time"], "source_to_posterior_ms"], 0.5
            ),
            "ms",
        ),
        (
            "On-time source-to-posterior p99",
            percentile(
                sent_spikes.loc[sent_spikes["on_time"], "source_to_posterior_ms"], 0.99
            ),
            "ms",
        ),
        (
            "Late-arrival tardiness p95",
            percentile(
                sent_spikes.loc[sent_spikes["late"], "late_tardiness_ms"],
                0.95,
            ),
            "ms",
        ),
    ]
    return pd.DataFrame(rows, columns=["metric", "value", "unit"])


def _window_quantiles(
    frame: pd.DataFrame,
    value_column: str,
    prefix: str,
    quantiles: Iterable[float] = (0.5, 0.95, 0.99),
) -> pd.DataFrame:
    clean = frame[["window", value_column]].replace([np.inf, -np.inf], np.nan).dropna()
    if clean.empty:
        return pd.DataFrame()
    values = clean.groupby("window")[value_column].quantile(list(quantiles)).unstack()
    values.columns = [f"{prefix}_p{int(round(q * 100)):02d}" for q in values.columns]
    return values


def aggregate_windows(
    tables: Mapping[str, object],
    window_seconds: float = 5.0,
) -> dict[str, pd.DataFrame]:
    """Aggregate event tables into aligned wall-time windows."""

    if window_seconds <= 0:
        raise ValueError("window_seconds must be positive")

    encoder_events = tables["encoder_events"].copy()
    sent_spikes = tables["sent_spikes"].copy()
    posterior_bins = tables["posterior_bins"].copy()
    maximum_s = max(
        float(encoder_events["elapsed_s"].max()),
        float(sent_spikes["elapsed_s"].max()),
        float(posterior_bins["elapsed_s"].max()),
    )
    n_windows = int(math.floor(maximum_s / window_seconds)) + 1
    index = pd.Index(range(n_windows), name="window")
    windows = pd.DataFrame(index=index)
    windows["elapsed_s"] = (windows.index.to_numpy() + 0.5) * window_seconds
    windows["elapsed_min"] = windows["elapsed_s"] / 60

    for frame in (encoder_events, sent_spikes, posterior_bins):
        frame["window"] = np.floor(frame["elapsed_s"] / window_seconds).astype(int)
    sent_spikes["covered_received"] = (
        sent_spikes["decoder_received"] & sent_spikes["in_bin_coverage"]
    )

    encoder_counts = encoder_events.groupby("window").agg(
        amplitude_qualified=("timestamp", "size"),
        model_added=("encode_spike", "sum"),
        kde_sent=("kde_sent", "sum"),
        kde_rejected=("kde_sent", lambda values: (~values.astype(bool)).sum()),
    )
    spike_counts = sent_spikes.groupby("window").agg(
        decoder_received=("decoder_received", "sum"),
        covered_received=("covered_received", "sum"),
        late=("late", "sum"),
        on_time=("on_time", "sum"),
        unmatched_receive=("unmatched_receive", "sum"),
        outside_recorded_bins=(
            "status",
            lambda values: values.eq("outside_recorded_bins").sum(),
        ),
        buffer_overwritten=("buffer_overwritten", "sum"),
        timestamp_collisions=("duplicate_removed", "sum"),
        used_spikes=("used_in_posterior", "sum"),
    )
    decoder_counts = posterior_bins.groupby("window").agg(
        recorded_used_spikes=("spike_count", "sum"),
        recorded_timestamp_collisions=("duplicate_increment", "sum"),
        reported_drops=("reported_drop_increment", "sum"),
    )
    windows = windows.join(encoder_counts).join(spike_counts).join(decoder_counts)
    count_columns = [
        "amplitude_qualified",
        "model_added",
        "kde_sent",
        "kde_rejected",
        "decoder_received",
        "covered_received",
        "late",
        "on_time",
        "unmatched_receive",
        "outside_recorded_bins",
        "buffer_overwritten",
        "used_spikes",
        "timestamp_collisions",
        "recorded_used_spikes",
        "recorded_timestamp_collisions",
        "reported_drops",
    ]
    windows[count_columns] = windows[count_columns].fillna(0)
    for column in count_columns:
        windows[f"{column}_rate"] = windows[column] / window_seconds

    for quantile_frame in [
        _window_quantiles(sent_spikes, "kde_ms", "kde"),
        _window_quantiles(sent_spikes, "source_to_encoder_ms", "source_to_encoder"),
        _window_quantiles(sent_spikes, "encoder_to_decoder_ms", "encoder_to_decoder"),
        _window_quantiles(
            sent_spikes[sent_spikes["on_time"]],
            "decoder_to_posterior_ms",
            "decoder_to_posterior",
        ),
        _window_quantiles(
            sent_spikes[sent_spikes["on_time"]], "source_to_posterior_ms", "end_to_end"
        ),
        _window_quantiles(
            sent_spikes, "deadline_slack_ms", "deadline_slack", (0.05, 0.5)
        ),
        _window_quantiles(
            sent_spikes[sent_spikes["late"]],
            "late_tardiness_ms",
            "late_tardiness",
            (0.5, 0.95),
        ),
        _window_quantiles(posterior_bins, "posterior_ms", "posterior"),
    ]:
        windows = windows.join(quantile_frame)

    windows["late_cumulative"] = windows["late"].cumsum()
    windows["unmatched_cumulative"] = windows["unmatched_receive"].cumsum()
    windows["received_cumulative"] = windows["covered_received"].cumsum()
    windows["late_percent_cumulative"] = (
        100
        * windows["late_cumulative"]
        / windows["received_cumulative"].replace(0, np.nan)
    )

    # Reconstruct end-of-window model size per nTrode, forward-filled through
    # windows without an amplitude-qualified event.
    growth = pd.DataFrame(index=index)
    initial_sizes = tables["initial_model_sizes"]
    for trode, group in encoder_events.groupby("elec_grp_id"):
        series = group.groupby("window")["model_size_after"].last().reindex(index)
        growth[int(trode)] = series.ffill().fillna(initial_sizes.get(int(trode), 0))
    growth["total"] = growth.sum(axis=1)
    growth["elapsed_min"] = windows["elapsed_min"]

    encoder_busy = (
        sent_spikes.groupby(["window", "encoder_rank"])["kde_ms"].sum()
        / (window_seconds * 1000)
        * 100
    ).unstack()
    busy = pd.DataFrame(index=index)
    busy["encoder_busy_max_pct"] = encoder_busy.max(axis=1).reindex(index)
    busy["encoder_busy_median_pct"] = encoder_busy.median(axis=1).reindex(index)
    decoder_busy = (
        posterior_bins.groupby(["window", "decoder_rank"])["posterior_ms"].sum()
        / (window_seconds * 1000)
        * 100
    ).unstack()
    busy["decoder_busy_max_pct"] = decoder_busy.max(axis=1).reindex(index)
    busy["decoder_busy_median_pct"] = decoder_busy.median(axis=1).reindex(index)
    windows = windows.join(busy)

    return {
        "windows": windows.reset_index(),
        "growth": growth.reset_index(),
        "encoder_busy_by_rank": encoder_busy.reindex(index).reset_index(),
        "decoder_busy_by_rank": decoder_busy.reindex(index).reset_index(),
        "encoder_events_windowed": encoder_events,
        "sent_spikes_windowed": sent_spikes,
        "posterior_bins_windowed": posterior_bins,
    }


def per_trode_summary(tables: Mapping[str, object]) -> pd.DataFrame:
    encoder_events = tables["encoder_events"]
    sent_spikes = tables["sent_spikes"]
    final_sizes = tables["final_model_sizes"]

    rows = []
    for trode in sorted(int(value) for value in encoder_events["elec_grp_id"].unique()):
        events = encoder_events[encoder_events["elec_grp_id"] == trode]
        spikes = sent_spikes[sent_spikes["elec_grp_id"] == trode]
        received = int(spikes["decoder_received"].sum())
        covered_received = int(
            (spikes["decoder_received"] & spikes["in_bin_coverage"]).sum()
        )
        late = int(spikes["late"].sum())
        rows.append(
            {
                "elec_grp_id": trode,
                "amplitude_qualified": len(events),
                "model_added": int(events["encode_spike"].sum()),
                "final_model_size": final_sizes.get(trode, np.nan),
                "kde_sent": int(events["kde_sent"].sum()),
                "decoder_received": received,
                "covered_received": covered_received,
                "unmatched": int(spikes["unmatched_receive"].sum()),
                "late": late,
                "late_percent": (
                    100 * late / covered_received if covered_received else np.nan
                ),
                "buffer_overwritten": int(spikes["buffer_overwritten"].sum()),
                "timestamp_collision_removed": int(spikes["duplicate_removed"].sum()),
                "used_in_posterior": int(spikes["used_in_posterior"].sum()),
                "kde_median_ms": spikes["kde_ms"].median(),
                "kde_p95_ms": spikes["kde_ms"].quantile(0.95),
                "kde_p99_ms": spikes["kde_ms"].quantile(0.99),
            }
        )
    return pd.DataFrame(rows)


def _plot_band(axis, x, frame, median_column, high_column, label, color=None):
    if median_column not in frame or high_column not in frame:
        return None
    median = frame[median_column].to_numpy(dtype=float)
    high = frame[high_column].to_numpy(dtype=float)
    line = axis.plot(x, median, label=label, color=color)[0]
    axis.fill_between(x, median, high, color=line.get_color(), alpha=0.18)
    return line


def plot_time_analysis(
    aggregates: Mapping[str, pd.DataFrame],
    config: Mapping,
    prefix: str,
):
    """Plot the aligned model-growth, latency, throughput, and loss panels."""

    sns.set_theme(style="whitegrid", context="notebook")
    windows = aggregates["windows"]
    growth = aggregates["growth"]
    x = windows["elapsed_min"].to_numpy(dtype=float)
    source_bin_ms = (
        float(config["decoder"]["time_bin"]["samples"])
        / float(config["sampling_rate"]["spikes"])
        * 1000
    )

    figure, axes = plt.subplots(6, 1, figsize=(15, 23), sharex=True)

    for column in growth.columns:
        if isinstance(column, (int, np.integer)):
            axes[0].plot(
                x, growth[column], alpha=0.5, linewidth=1, label=f"nTrode {column}"
            )
    axes[0].plot(x, growth["total"], color="black", linewidth=2.2, label="Total")
    axes[0].set_ylabel("Encoder marks")
    axes[0].set_title("Encoder model growth")
    axes[0].legend(ncol=4, fontsize=8)

    _plot_band(axes[1], x, windows, "kde_p50", "kde_p95", "Successful KDE p50–p95")
    _plot_band(
        axes[1], x, windows, "posterior_p50", "posterior_p95", "Posterior p50–p95"
    )
    if "kde_p99" in windows:
        axes[1].plot(x, windows["kde_p99"], linewidth=0.8, alpha=0.8, label="KDE p99")
    axes[1].axhline(
        source_bin_ms,
        color="red",
        linestyle="--",
        label=f"{source_bin_ms:g} ms configured source-bin width",
    )
    axes[1].set_ylabel("Compute time (ms)")
    axes[1].set_title("Computation latency")
    axes[1].legend()

    _plot_band(
        axes[2],
        x,
        windows,
        "source_to_encoder_p50",
        "source_to_encoder_p95",
        "Source→encoder p50–p95",
    )
    _plot_band(
        axes[2],
        x,
        windows,
        "decoder_to_posterior_p50",
        "decoder_to_posterior_p95",
        "On-time decoder receive→posterior p50–p95",
    )
    _plot_band(
        axes[2],
        x,
        windows,
        "end_to_end_p50",
        "end_to_end_p95",
        "On-time source→posterior p50–p95",
    )
    axes[2].plot(
        x, windows["encoder_to_decoder_p95"], label="Encoder→decoder p95", linewidth=1
    )
    axes[2].set_yscale("log")
    axes[2].set_ylabel("Latency (ms, log scale)")
    axes[2].set_title("Pipeline latency (log scale preserves transient stalls)")
    axes[2].legend()

    for column, label in [
        ("amplitude_qualified_rate", "Amplitude-qualified"),
        ("model_added_rate", "Added to model"),
        ("kde_sent_rate", "Sent"),
        ("decoder_received_rate", "Received"),
        ("used_spikes_rate", "Used in posterior"),
    ]:
        axes[3].plot(x, windows[column], label=label)
    axes[3].set_ylabel("Spikes / second")
    axes[3].set_title("Throughput")
    axes[3].legend(ncol=3)

    for column, label in [
        ("kde_rejected_rate", "KDE rejected / s"),
        ("unmatched_receive_rate", "Transport unmatched / s"),
        ("outside_recorded_bins_rate", "Outside recorded bins / s"),
        ("late_rate", "Late / s"),
        ("buffer_overwritten_rate", "Buffer overwritten / s"),
        ("timestamp_collisions_rate", "Timestamp collisions / s"),
    ]:
        axes[4].plot(x, windows[column], label=label)
    axes[4].plot(
        x,
        windows["reported_drops_rate"],
        color="0.35",
        linestyle=":",
        label="Runtime drop counter / s (approx.)",
    )
    axes[4].set_ylabel("Events / second")
    late_axis = axes[4].twinx()
    late_axis.plot(
        x,
        windows["late_percent_cumulative"],
        color="black",
        linewidth=1.5,
        label="Cumulative late %",
    )
    late_axis.set_ylabel("Cumulative late (%)")
    axes[4].set_title("Deadline misses and exclusions")
    lines, labels = axes[4].get_legend_handles_labels()
    lines2, labels2 = late_axis.get_legend_handles_labels()
    axes[4].legend(lines + lines2, labels + labels2, loc="upper left")

    axes[5].plot(x, windows["encoder_busy_max_pct"], label="Busiest encoder: KDE-only")
    axes[5].plot(
        x, windows["encoder_busy_median_pct"], label="Median encoder: KDE-only"
    )
    axes[5].plot(
        x, windows["decoder_busy_max_pct"], label="Busiest decoder: posterior-only"
    )
    axes[5].plot(
        x, windows["decoder_busy_median_pct"], label="Median decoder: posterior-only"
    )
    axes[5].axhline(100, color="red", linestyle="--", linewidth=1, label="100%")
    axes[5].set_ylabel("Measured busy time (%)")
    axes[5].set_xlabel("Elapsed wall time (minutes)")
    axes[5].set_title(
        "Lower-bound process utilization (successful KDE/core posterior only)"
    )
    axes[5].legend()

    figure.suptitle(f"Realtime decoder performance\n{prefix}", fontsize=15, y=0.995)
    figure.tight_layout()
    return figure, axes


def _binned_scaling(
    frame: pd.DataFrame,
    x_column: str,
    y_column: str,
    bins: int,
) -> pd.DataFrame:
    clean = frame[[x_column, y_column]].replace([np.inf, -np.inf], np.nan).dropna()
    if clean.empty or clean[x_column].nunique() < 2:
        return pd.DataFrame()
    q = min(bins, int(clean[x_column].nunique()))
    clean = clean.assign(model_bin=pd.qcut(clean[x_column], q=q, duplicates="drop"))
    grouped = clean.groupby("model_bin", observed=True)
    return grouped.agg(
        x=(x_column, "median"),
        median=(y_column, "median"),
        p95=(y_column, lambda values: values.quantile(0.95)),
        count=(y_column, "size"),
    ).reset_index(drop=True)


def plot_scaling_analysis(
    tables: Mapping[str, object],
    prefix: str,
    model_bins: int = 30,
):
    """Plot KDE scaling, posterior scaling, and deadline misses."""

    sent_spikes = tables["sent_spikes"]
    posterior_bins = tables["posterior_bins"]
    figure, axes = plt.subplots(1, 3, figsize=(19, 5.5))
    palette = sns.color_palette(
        "tab10", n_colors=max(sent_spikes["elec_grp_id"].nunique(), 1)
    )

    for color, (trode, group) in zip(palette, sent_spikes.groupby("elec_grp_id")):
        scaling = _binned_scaling(group, "effective_model_size", "kde_ms", model_bins)
        if scaling.empty:
            continue
        axes[0].plot(
            scaling["x"], scaling["median"], color=color, label=f"{int(trode)} median"
        )
        axes[0].plot(
            scaling["x"], scaling["p95"], color=color, linestyle="--", alpha=0.65
        )
    axes[0].set_xlabel("Effective per-trode model size")
    axes[0].set_ylabel("Successful KDE time (ms)")
    axes[0].set_title("KDE scaling (solid median, dashed p95)")
    axes[0].legend(ncol=2, fontsize=7)

    posterior_scaling = (
        posterior_bins.groupby("spike_count")["posterior_ms"]
        .agg(
            median="median",
            p95=lambda values: values.quantile(0.95),
            count="size",
        )
        .reset_index()
    )
    axes[1].plot(
        posterior_scaling["spike_count"],
        posterior_scaling["median"],
        marker="o",
        label="Median",
    )
    axes[1].plot(
        posterior_scaling["spike_count"],
        posterior_scaling["p95"],
        marker="o",
        label="p95",
    )
    axes[1].set_xlabel("Spikes used in posterior bin")
    axes[1].set_ylabel("Posterior compute time (ms)")
    axes[1].set_title("Posterior scaling")
    axes[1].legend()

    late_source = sent_spikes[
        sent_spikes["decoder_received"] & sent_spikes["in_bin_coverage"]
    ].copy()
    q = min(model_bins, int(late_source["effective_model_size"].nunique()))
    if q >= 2:
        late_source["model_bin"] = pd.qcut(
            late_source["effective_model_size"], q=q, duplicates="drop"
        )
        late_scaling = (
            late_source.groupby("model_bin", observed=True)
            .agg(
                x=("effective_model_size", "median"),
                late_percent=("late", lambda values: 100 * values.mean()),
                count=("late", "size"),
            )
            .reset_index(drop=True)
        )
    else:
        late_scaling = pd.DataFrame()
    if not late_scaling.empty:
        axes[2].plot(late_scaling["x"], late_scaling["late_percent"], marker="o")
    axes[2].set_xlabel("Effective per-trode model size")
    axes[2].set_ylabel("Late arrivals in bin (%)")
    axes[2].set_title("Deadline misses as models grow")

    figure.suptitle(f"Scaling analysis — {prefix}", y=1.03)
    figure.tight_layout()
    return figure, axes


def export_aggregates(
    output_dir: Path | str,
    prefix: str,
    aggregates: Mapping[str, pd.DataFrame],
    summary: pd.DataFrame,
    validation: pd.DataFrame,
    per_trode: pd.DataFrame,
) -> Path:
    """Export only compact aggregate tables, never the multi-GB raw events."""

    destination = Path(output_dir).expanduser() / "performance_analysis" / prefix
    destination.mkdir(parents=True, exist_ok=True)
    aggregates["windows"].to_csv(destination / "performance_windows.csv", index=False)
    aggregates["growth"].to_csv(destination / "model_growth.csv", index=False)
    summary.to_csv(destination / "summary.csv", index=False)
    validation.to_csv(destination / "validation.csv", index=False)
    per_trode.to_csv(destination / "per_trode_summary.csv", index=False)
    return destination
