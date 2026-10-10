"""Offline replay of a saved realtime-decoder run with weight-only kernel merging.

Question this answers: if every encoder had merged its stored spikes (same hex,
within TAU kernel widths, count-weighted), would the decoder have decided
differently -- and where?

Nothing here runs or modifies the live decoder. It reads one run's merged
records (``*.rec_merged.h5``), saved encoder models and config snapshot, and

1. rebuilds each trode's encoding model spike by spike, in the order the
   encoder processed them (checked against the saved ``*.encoder.npz``),
2. replays every spike through a merged copy of that model, once per TAU,
3. re-decodes every 6 ms bin with the real ``ClusterlessDecoder`` -- once with
   the unmerged votes and once per TAU -- so the only difference between the
   replays is the merging.

Merging rule (Sodkomkham et al. 2016, Hu et al. 2018, adapted to hex bins): an
encoding spike joins the nearest existing bump *in its own hex* if that bump's
center is within ``TAU * sigma`` (Euclidean distance over all mark channels),
otherwise it starts a new bump. A bump's center is the mean of its members, its
width stays ``sigma``, and its count multiplies its kernel. TAU = 0 is no
merging and reproduces today's encoder exactly.

Votes for the other models reuse the occupancy the live encoder actually used:
the logged vote ``r`` is ``(K_live + 1e-7) / occupancy``, normalized, where
``K_live`` comes from the model the live encoder ran (unmerged, or merged at the
run's own ``merge_threshold``), so another model's vote is
``(K + 1e-7) * r / (K_live + 1e-7)``, normalized. That avoids having to
reconstruct the encoder's occupancy at every spike. The merge arithmetic here is
the encoder's own, so a run recorded with merging is reproduced bit for bit.

``kernel_overlap`` measures how much each final model's kernels overlap each
other (nearest other kernel, any hex, and the area the two share).
"""

import os
import glob
import time
import multiprocessing as mp
from collections import deque
from types import SimpleNamespace

import numpy as np
import pandas as pd
import oyaml as yaml
from scipy.spatial import cKDTree
from scipy.special import ndtr

from realtime_decoder import decoder_process, position, transitions

EPS = 1e-7  # floor encoder_process.py adds to every bin before the occupancy division
CACHE_VERSION = 2   # bump whenever cached results would change; older caches are recomputed

# filled by the parent right before a pool is forked; workers only read it
_SHARED = {}


####################################################################################
# Loading
####################################################################################

class Run:
    """Everything the replay needs from one decoder run."""

    def __init__(self, run_dir, run_prefix=None):
        if run_prefix is None:
            cands = sorted(glob.glob(os.path.join(run_dir, '*.rec_merged.h5')))
            assert cands, f'no *.rec_merged.h5 in {run_dir}'
            run_prefix = os.path.basename(cands[-1]).replace('.rec_merged.h5', '')
        self.run_dir = run_dir
        self.prefix = run_prefix
        self.base = os.path.join(run_dir, run_prefix)
        self.rec_path = self.base + '.rec_merged.h5'
        self.cfg = yaml.safe_load(open(glob.glob(self.base + '*.config.yaml')[0]))

        enc = self.cfg['encoder']
        pos = enc['position']
        mk = enc['mark_kernel']
        self.num_bins = pos['num_bins']
        self.is_hex = pos.get('type') == 'hex'
        self.hex_ids = list(pos['hex_ids']) if self.is_hex else list(range(self.num_bins))
        self.pos_bin_struct = position.PositionBinStruct(
            pos['lower'], pos['upper'], pos['num_bins'])
        self.sigma = float(mk['std'])
        self.live_tau = float(mk.get('merge_threshold', 0))   # what the live encoder ran with
        self.use_filter = bool(mk['use_filter'])
        self.box = mk['n_std'] * mk['std']        # same expression as get_joint_prob
        self.n_marks_min = mk['n_marks_min']
        self.mark_dim = enc['mark_dim']
        self.cred_interval = self.cfg['cred_interval']['val']
        self.preloaded = bool(self.cfg['preloaded_model'])
        self.states = self.cfg[self.cfg['algorithm']]['state_labels']
        self._dig = len(str(self.num_bins))

        self._load_spikes()
        self._load_decoder_records()

    def _load_spikes(self):
        """Per-trode arrays in the exact order the encoder processed them
        (each encoder rank writes its records with an increasing rec_ind)."""

        mcols = [f'mark_dim_{i}' for i in range(self.mark_dim)]
        hcols = [f'x{v:0{self._dig}d}' for v in range(self.num_bins)]
        r3 = pd.read_hdf(self.rec_path, 'rec_3')
        self.spikes = {}
        for trode, d in r3.groupby('elec_grp_id', sort=True):
            d = d.sort_values('rec_ind', kind='stable')
            enc = d.encode_spike.to_numpy(bool)
            self.spikes[int(trode)] = SimpleNamespace(
                ts=d.timestamp.to_numpy(np.int64),
                rec_time=d.rec_time.to_numpy(np.int64),
                pos=d.position.to_numpy().astype(np.int64),   # hex index stored with the spike
                enc=enc,
                sent=d.cred_int.to_numpy() >= 0,                # cred_int = -1 -> not sent
                marks=np.ascontiguousarray(d[mcols].to_numpy(np.float64)),
                votes=np.ascontiguousarray(d[hcols].to_numpy(np.float64)),
                enc_rank=np.concatenate([[0], np.cumsum(enc)[:-1]]).astype(np.int64),
            )
        del r3
        self.trodes = sorted(self.spikes)

    def _load_decoder_records(self):
        r4 = pd.read_hdf(self.rec_path, 'rec_4').sort_values('rec_ind', kind='stable')
        post_cols = [f'x{v:0{self._dig}d}_{s}' for s in self.states for v in range(self.num_bins)]
        post = r4[post_cols].to_numpy(np.float64)
        if len(self.states) > 1:
            post = post.reshape(len(r4), len(self.states), self.num_bins).sum(axis=1)
        self.logged_posterior = post.astype(np.float32)
        self.bins = r4[['rec_ind', 'timestamp', 'bin_timestamp_l', 'bin_timestamp_r',
                        'spike_count', 'task_state', 'velocity', 'mapped_pos',
                        'dec_rank']].reset_index(drop=True)
        del r4

        r7 = pd.read_hdf(self.rec_path, 'rec_7').sort_values('rec_ind', kind='stable')
        occ_cols = [f'x{v:0{self._dig}d}' for v in range(self.num_bins)]
        self.occ = SimpleNamespace(
            rec_ind=r7.rec_ind.to_numpy(np.int64),
            timestamp=r7.timestamp.to_numpy(np.int64),
            rec_time=r7.rec_time.to_numpy(np.int64),
            dec_rank=r7.dec_rank.to_numpy(np.int64),
            mapped_pos=r7.mapped_pos.to_numpy(np.int64),
            values=r7[occ_cols].to_numpy(np.float64),
        )
        del r7

    def check_models(self):
        """Rebuild each trode's final model from the per-spike records and compare
        it with the saved encoder.npz. Exact equality means the replay order and
        the stored positions are right. Files from the merging encoder are checked
        twice: their unmerged copy against the records, and their merged model
        against this module's merge rule at the run's own threshold."""

        rows = []
        for trode, s in self.spikes.items():
            em, ep = s.marks[s.enc], s.pos[s.enc]
            with np.load(f'{self.base}_trode_{trode}.encoder.npz') as z:
                if 'raw_marks' in z.files:
                    n = int(z['n_spikes'][0])
                    n_rows = int(z['mark_idx'][0])
                    marks_ok = np.array_equal(em, z['raw_marks'][:n])
                    pos_ok = np.array_equal(ep.astype('<f4'), z['raw_positions'][:n])
                    bump_of, bump_pos = merge_assignments(em, ep, self.live_tau, self.sigma, self.num_bins)
                    C, W = bump_state(bump_of, em, len(bump_pos))
                    merged_ok = (len(bump_pos) == n_rows
                                 and np.array_equal(C, z['marks'][:n_rows])
                                 and np.array_equal(bump_pos.astype('<f4'), z['positions'][:n_rows])
                                 and np.array_equal(W, z['counts'][:n_rows]))
                else:
                    n = n_rows = int(z['mark_idx'][0])
                    marks_ok = np.array_equal(em, z['marks'][:n])
                    pos_ok = np.array_equal(ep.astype('<f4'), z['positions'][:n])
                    merged_ok = True                       # older files: nothing merged
            rows.append(dict(trode=trode, spikes=len(s.ts), encoding=int(s.enc.sum()),
                             saved_spikes=n, saved_rows=n_rows, marks_match=marks_ok,
                             positions_match=pos_ok, merged_model_match=merged_ok))
        return pd.DataFrame(rows).set_index('trode')


def hex_hop_distance(run):
    """All-pairs hop distance between position bins (dense indices) on the
    session's open maze, by BFS. Linear runs fall back to |i - j|."""

    n = run.num_bins
    if not run.is_hex:
        idx = np.arange(n)
        return np.abs(idx[:, None] - idx[None, :]).astype(float)
    pos_cfg = run.cfg['encoder']['position']
    adjacency = transitions.prune_hex_graph(
        transitions.load_hex_graph(pos_cfg['hex_graph_file']),
        pos_cfg.get('blocked_hexes', []) or [])
    index = {h: i for i, h in enumerate(run.hex_ids)}
    dist = np.full((n, n), np.inf)
    for h in run.hex_ids:
        i = index[h]
        dist[i, i] = 0
        queue, seen = deque([(h, 0)]), {h}
        while queue:
            cur, d = queue.popleft()
            for nb in adjacency.get(cur, ()):
                if nb not in seen:
                    seen.add(nb)
                    j = index.get(nb)
                    if j is not None:
                        dist[i, j] = d + 1
                    queue.append((nb, d + 1))
    return dist


####################################################################################
# Merging and per-spike replay
####################################################################################

def merge_assignments(marks, pos, tau, sigma, num_bins):
    """Weight-only merging of one trode's encoding spikes, in arrival order, with
    exactly the arithmetic of Encoder.add_new_mark (so a run recorded with merging
    is reproduced bit for bit).

    Each spike joins the nearest bump in its own hex if that bump's center is
    within tau * sigma, otherwise it starts a new bump; a joined bump's center
    moves by (mark - center) / count. Returns bump_of (the bump index of every
    encoding spike) and bump_pos (the hex of every bump). tau <= 0 means no
    merging: every spike is its own bump."""

    n, d = marks.shape
    if tau <= 0:
        return np.arange(n, dtype=np.int64), pos.astype(np.int64).copy()

    lim = (tau * sigma) ** 2
    cap = np.bincount(pos, minlength=num_bins)
    centers = [np.empty((c, d)) for c in cap]
    counts = [np.empty(c) for c in cap]
    ids = [np.empty(c, np.int64) for c in cap]
    in_hex = np.zeros(num_bins, np.int64)
    bump_of = np.empty(n, np.int64)
    bump_pos = np.empty(n, np.int64)
    n_bumps = 0
    for i in range(n):
        a, h = marks[i], pos[i]
        c = in_hex[h]
        if c:
            diff = centers[h][:c] - a
            d2 = np.einsum('ij,ij->i', diff, diff)
            j = int(np.argmin(d2))
            if d2[j] <= lim:
                counts[h][j] += 1
                centers[h][j] += (a - centers[h][j]) / counts[h][j]
                bump_of[i] = ids[h][j]
                continue
        centers[h][c] = a
        counts[h][c] = 1
        ids[h][c] = n_bumps
        bump_of[i] = n_bumps
        bump_pos[n_bumps] = h
        n_bumps += 1
        in_hex[h] = c + 1
    return bump_of, bump_pos[:n_bumps]


def bump_state(bump_of, marks_enc, n_bumps, n_members=None):
    """Centers and counts of every bump after its first n_members encoding
    spikes, with exactly the arithmetic of Encoder.add_new_mark: a bump starts
    at its first spike's mark, and its k-th spike moves it by (mark - center) / k.
    Bumps are independent, so the k-th spike of every bump is applied at once."""

    n = len(bump_of) if n_members is None else int(n_members)
    centers = np.zeros((n_bumps, marks_enc.shape[1]))
    counts = np.zeros(n_bumps)
    if n == 0:
        return centers, counts
    b = bump_of[:n]
    order = np.argsort(b, kind='stable')                 # each bump's spikes, in arrival order
    sb = b[order]
    first = np.r_[0, np.flatnonzero(np.diff(sb)) + 1]
    rank = np.arange(n) - np.repeat(first, np.diff(np.r_[first, n]))
    by_rank = np.argsort(rank, kind='stable')
    spikes, ranks = order[by_rank], rank[by_rank]
    bounds = np.searchsorted(ranks, np.arange(ranks.max() + 2))
    for k in range(ranks.max() + 1):
        sel = spikes[bounds[k]:bounds[k + 1]]             # the (k+1)-th spike of every bump that has one
        bb = b[sel]
        if k == 0:
            centers[bb] = marks_enc[sel]
            counts[bb] = 1.0
        else:
            counts[bb] += 1.0
            centers[bb] += (marks_enc[sel] - centers[bb]) / counts[bb][:, None]
    return centers, counts


def _merge_job(job):
    trode, tau = job
    s = _SHARED['spikes'][trode]
    bump_of, bump_pos = merge_assignments(
        s['marks_enc'], s['pos'][s['enc']], tau, _SHARED['sigma'], _SHARED['num_bins'])
    return trode, tau, bump_of, bump_pos


def _in_box_rows(C, m, box):
    """Rows of C inside the box m +/- box on every channel. Same comparisons as
    get_joint_prob's filter loop; testing the most selective channel first and
    only the surviving rows afterwards gives the identical row set."""

    order = np.argsort(-np.abs(m), kind='stable')
    j = order[0]
    idx = np.flatnonzero((C[:, j] > m[j] - box) & (C[:, j] < m[j] + box))
    for j in order[1:]:
        if idx.size == 0:
            break
        col = C[idx, j]
        idx = idx[(col > m[j] - box) & (col < m[j] + box)]
    return idx


def _eval_job(job):
    """Kernel sums per hex (K) and the weighted 'nearby marks' count for spikes
    [start, stop) of one trode, against the merged model as it stood when each
    spike arrived. Encoding spikes join the model after their own evaluation,
    as in EncoderManager._process_spike."""

    trode, tau, start, stop = job
    s = _SHARED['spikes'][trode]
    bump_of, bump_pos = _SHARED['assign'][(trode, tau)]
    marks, enc, enc_rank, marks_enc = s['marks'], s['enc'], s['enc_rank'], s['marks_enc']
    nbins, box = _SHARED['num_bins'], _SHARED['box']
    k1 = 1 / (np.sqrt(2 * np.pi) * _SHARED['sigma'])
    k2 = -0.5 / (_SHARED['sigma'] ** 2)

    n_b = len(bump_pos)
    n_before = enc_rank[start]
    centers, counts = bump_state(bump_of, marks_enc, n_b, n_before)
    n_active = int(bump_of[:n_before].max()) + 1 if n_before else 0

    K = np.zeros((stop - start, nbins))
    near = np.zeros(stop - start)
    t_eval = np.zeros(stop - start, np.float32)
    for i in range(start, stop):
        m = marks[i]
        t0 = time.perf_counter()
        if n_active:
            C = centers[:n_active]
            diff = C - m
            kv = counts[:n_active] * (k1 * np.exp(np.einsum('ij,ij->i', diff, diff) * k2))
            K[i - start] = np.bincount(bump_pos[:n_active], weights=kv, minlength=nbins)
            near[i - start] = counts[_in_box_rows(C, m, box)].sum()
        t_eval[i - start] = time.perf_counter() - t0
        if enc[i]:
            g = bump_of[enc_rank[i]]
            if g >= n_active:                                   # a new bump
                centers[g] = m
                counts[g] = 1.0
                n_active = g + 1
            else:
                counts[g] += 1.0
                centers[g] += (m - centers[g]) / counts[g]
    return trode, tau, start, K, near, t_eval


def _cred_int(votes, val):
    """encoder_process.py's per-spike credible interval, row-wise"""
    cs = np.cumsum(-np.sort(-votes, axis=1), axis=1)
    return (cs < val).sum(axis=1) + 1


####################################################################################
# Decoder replay
####################################################################################

def _replay_job(variant):
    """Decode every bin of one decoder rank with the real ClusterlessDecoder,
    feeding it this variant's sent spikes and the occupancy the live decoder
    had when it decoded that bin."""

    cfg, pbs = _SHARED['cfg'], _SHARED['pos_bin_struct']
    out = {}
    for rank, R in _SHARED['ranks'].items():
        V = _SHARED['variants'][variant][rank]
        dec = decoder_process.ClusterlessDecoder(rank, cfg, pbs)
        init_occ = dec._occupancy.copy()
        n_bins = len(R['bin_lb'])
        post = np.zeros((n_bins, cfg['encoder']['position']['num_bins']), np.float32)
        n_used = np.zeros(n_bins, np.int16)
        bounds = V['bounds']
        arr = V['arr']
        for b in range(n_bins):
            k = R['occ_idx'][b]
            dec._occupancy = R['occ_values'][k] if k >= 0 else init_occ
            lo, hi = bounds[b], bounds[b + 1]
            p, _ = dec.compute_posterior(arr[lo:hi])
            post[b] = p.sum(axis=0)
            n_used[b] = hi - lo
        out[rank] = (post, n_used)
    return variant, out


def _bin_spikes(R, ts, trode, pos, votes):
    """Assign sent spikes to the rank's bins and apply the decoder's duplicate
    rule (decoder_process._get_unique: keep the first spike of each timestamp
    seen fewer than 3 times in the bin). Returns the spike rows the decoder would
    receive, grouped by bin, and the row bounds of each bin."""

    lb, ub = R['bin_lb'], R['bin_ub']
    b = np.searchsorted(lb, ts, side='right') - 1
    ok = (b >= 0)
    ok[ok] = ts[ok] < ub[b[ok]]
    b, ts, trode, pos, votes = b[ok], ts[ok], trode[ok], pos[ok], votes[ok]
    order = np.lexsort((trode, ts, b))
    b, ts, trode, pos, votes = b[order], ts[order], trode[order], pos[order], votes[order]
    # duplicate rule, vectorized: runs of equal (bin, timestamp)
    key_new = np.ones(len(ts), bool)
    key_new[1:] = (b[1:] != b[:-1]) | (ts[1:] != ts[:-1])
    run_id = np.cumsum(key_new) - 1
    run_len = np.bincount(run_id)
    keep = key_new & (run_len[run_id] < 3)
    b, ts, trode, pos, votes = b[keep], ts[keep], trode[keep], pos[keep], votes[keep]
    arr = np.zeros((len(ts), 5 + votes.shape[1]))
    arr[:, 0] = ts
    arr[:, 1] = trode
    arr[:, 2] = pos
    arr[:, 5:] = votes
    bounds = np.searchsorted(b, np.arange(len(lb) + 1))
    return arr, bounds


####################################################################################
# Timing
####################################################################################

def time_kde(run, taus, trode=None, n_queries=300, seed=0):
    """Per-spike KDE time at the end of the session, single process, for one
    trode (default: the one with the most training spikes). Queries are spikes
    from the last 10% of the session, evaluated against the final model.

    Two evaluation styles, so merging and code speed-ups can be read separately:
    - 'today's code': get_joint_prob's structure (per-channel filter loop,
      np.sum(np.square(...)), np.histogram with explicit edges), with counts as
      histogram weights when merged
    - 'faster evaluation': the replay's evaluation (einsum, bincount, most
      selective channel first in the box test)"""

    trode = trode or max(run.trodes, key=lambda t: run.spikes[t].enc.sum())
    s = run.spikes[trode]
    marks_enc = np.ascontiguousarray(s.marks[s.enc])
    pos_enc = s.pos[s.enc]
    rng = np.random.default_rng(seed)
    tail = np.arange(int(0.9 * len(s.ts)), len(s.ts))
    Q = s.marks[rng.choice(tail, size=min(n_queries, len(tail)), replace=False)]
    k1 = 1 / (np.sqrt(2 * np.pi) * run.sigma)
    k2 = -0.5 / run.sigma ** 2
    edges = run.pos_bin_struct.pos_bin_edges
    nbins, box, d = run.num_bins, run.box, marks_enc.shape[1]

    def todays_code(C, w, P, q):
        in_range = np.ones(len(C), dtype=bool)
        for ii in range(d):
            in_range = np.logical_and(
                np.logical_and(C[:, ii] > q[ii] - box, C[:, ii] < q[ii] + box), in_range)
        near = w[in_range].sum()
        kv = w * (k1 * np.exp(np.sum(np.square(C - q), axis=1) * k2))
        return near, np.histogram(a=P, bins=edges, weights=kv)[0]

    def faster(C, w, P, q):
        diff = C - q
        kv = w * (k1 * np.exp(np.einsum('ij,ij->i', diff, diff) * k2))
        return w[_in_box_rows(C, q, box)].sum(), np.bincount(P, weights=kv, minlength=nbins)

    rows = []
    for tau in [0.0] + [float(t) for t in taus if t > 0]:
        bump_of, bump_pos = merge_assignments(marks_enc, pos_enc, tau, run.sigma, nbins)
        C, counts = bump_state(bump_of, marks_enc, len(bump_pos))
        C = np.ascontiguousarray(C)
        Pf = bump_pos.astype('<f4')        # the encoder stores positions as float32
        row = {'threshold': tau, 'kernels': len(bump_pos)}
        for name, f, P in (("today's code ms", todays_code, Pf), ('faster evaluation ms', faster, bump_pos)):
            f(C, counts, P, Q[0])          # warm-up
            t0 = time.perf_counter()
            for q in Q:
                f(C, counts, P, q)
            row[name] = (time.perf_counter() - t0) / len(Q) * 1e3
        rows.append(row)
    return trode, pd.DataFrame(rows).set_index('threshold')


####################################################################################
# Kernel overlap
####################################################################################

def _overlap_job(job):
    trode, tau = job
    s = _SHARED['spikes'][trode]
    marks_enc = s['marks_enc']
    bump_of, bump_pos = merge_assignments(
        marks_enc, s['pos'][s['enc']], tau, _SHARED['sigma'], _SHARED['num_bins'])
    centers, counts = bump_state(bump_of, marks_enc, len(bump_pos))
    n = len(counts)
    dist, nearest = np.full(n, np.inf), np.full(n, -1)
    if n > 1:
        d, i = cKDTree(centers).query(centers, k=2)       # exact nearest neighbours
        dist = d[:, 1]                                     # closest other kernel (0 for duplicates)
        nearest = np.where(i[:, 0] == np.arange(n), i[:, 1], i[:, 0])
    return trode, tau, counts, bump_pos, dist, nearest


def kernel_overlap(run, taus, n_workers=None):
    """Every kernel of each trode's final model, per threshold (0 = unmerged),
    with the distance to its nearest other kernel (in any hex) and the area the
    two share. One row per kernel.

    All kernels have the same width sigma, so the area two of them share (the
    integral of min(f, g)) depends only on the distance d between their centers:
    2 * Phi(-d / (2 sigma)), in any number of dimensions (the two bumps cross on
    the plane halfway between the centers). Distance is the KDE's own (Euclidean
    over all mark channels); the spike counts are ignored. Marks are quantized,
    so a few kernels have two neighbours at exactly the same distance; which one
    counts as nearest then only affects nearest_same_hex."""

    variants = [0.0] + [float(t) for t in taus if t > 0]
    n_workers = n_workers or max(1, min(64, (os.cpu_count() or 2) - 4))
    _SHARED.clear()
    _SHARED.update(sigma=run.sigma, num_bins=run.num_bins,
                   spikes={t: dict(marks_enc=np.ascontiguousarray(s.marks[s.enc]), pos=s.pos, enc=s.enc)
                           for t, s in run.spikes.items()})
    jobs = [(t, v) for v in variants for t in run.trodes]
    with mp.get_context('fork').Pool(min(n_workers, len(jobs))) as pool:
        out = pool.map(_overlap_job, jobs)
    _SHARED.clear()

    frames = []
    for trode, tau, counts, bump_pos, dist, nearest in out:
        widths = dist / run.sigma
        frames.append(pd.DataFrame({
            'threshold': tau,
            'trode': trode,
            'hex_idx': bump_pos,                     # dense index into run.hex_ids
            'spikes': counts.astype(np.int64),       # training spikes the kernel holds
            'nearest_widths': widths,                # distance to the nearest other kernel, in sigmas
            'shared': 2 * ndtr(-widths / 2),         # area shared with that kernel (0..1)
            'nearest_same_hex': (nearest >= 0) & (bump_pos[np.maximum(nearest, 0)] == bump_pos),
        }))
    return pd.concat(frames, ignore_index=True)


####################################################################################
# Orchestration
####################################################################################

def _chunks(n, size):
    return [(s, min(s + size, n)) for s in range(0, n, size)]


def replay(run, taus, n_workers=None, chunk_size=4000, cache_dir=None, force=False, log=print):
    """Run the whole comparison. Returns a SimpleNamespace with, per variant
    (0 = unmerged, then each tau): per-spike results, model growth, timing,
    and the replayed posterior for every bin.

    Results are cached in cache_dir (one npz per variant); set force=True to
    recompute."""

    taus = [float(t) for t in taus]
    variants = [0.0] + [t for t in taus if t > 0]
    n_workers = n_workers or max(1, min(64, (os.cpu_count() or 2) - 4))
    live = run.live_tau
    cache = {}
    if cache_dir and not force:
        for v in variants:
            f = os.path.join(cache_dir, f'{run.prefix}.merge_tau{v:g}.npz')
            if os.path.exists(f):
                with np.load(f) as z:
                    current = ('cache_version' in z.files
                               and int(z['cache_version'][0]) == CACHE_VERSION
                               and float(z['live_tau'][0]) == live)
                if current:
                    cache[v] = f
                else:
                    log(f'threshold {v:g}: cached results in {f} are from an older version; recomputing')
    todo = [v for v in variants if v not in cache]
    ctx = mp.get_context('fork')

    _SHARED.clear()
    _SHARED.update(
        sigma=run.sigma, box=run.box, num_bins=run.num_bins, cfg=run.cfg,
        pos_bin_struct=run.pos_bin_struct,
        spikes={t: dict(marks=s.marks, marks_enc=np.ascontiguousarray(s.marks[s.enc]),
                        pos=s.pos, enc=s.enc, enc_rank=s.enc_rank)
                for t, s in run.spikes.items()},
    )

    results = {}
    if todo:
        # the unmerged model is the reference for every comparison, and the live
        # run's own model is needed for the vote ratio
        need = sorted(set(todo) | {0.0, live})
        # 1. merge assignments (cheap, one sequential pass per trode and tau)
        t0 = time.time()
        with ctx.Pool(n_workers) as pool:
            assign = {(t, v): (bo, bp) for t, v, bo, bp in
                      pool.map(_merge_job, [(t, v) for v in need for t in run.trodes])}
        _SHARED['assign'] = assign
        log(f'merge passes: {time.time() - t0:.0f} s')

        # 2. replay every spike through each variant's model
        t0 = time.time()
        jobs = [(t, v, a, b) for v in need for t in run.trodes
                for a, b in _chunks(len(run.spikes[t].ts), chunk_size)]
        jobs.sort(key=lambda j: -run.spikes[j[0]].enc_rank[j[2]])   # biggest models first
        K = {(t, v): np.zeros((len(run.spikes[t].ts), run.num_bins)) for v in need for t in run.trodes}
        near = {(t, v): np.zeros(len(run.spikes[t].ts)) for v in need for t in run.trodes}
        teval = {(t, v): np.zeros(len(run.spikes[t].ts), np.float32) for v in need for t in run.trodes}
        with ctx.Pool(n_workers) as pool:
            for t, v, a, Kc, nc, tc in pool.imap_unordered(_eval_job, jobs, chunksize=1):
                K[(t, v)][a:a + len(nc)] = Kc
                near[(t, v)][a:a + len(nc)] = nc
                teval[(t, v)][a:a + len(nc)] = tc
        log(f'spike replay ({len(jobs)} chunks, {n_workers} workers): {time.time() - t0:.0f} s')

        # 3. votes per model, then per-spike comparison against the unmerged model
        vote_models = sorted(set(todo) | {0.0})
        per_spike = {v: {} for v in todo}
        variant_spikes = {v: [] for v in todo}
        n_fallback = {v: 0 for v in vote_models}
        for t in run.trodes:
            s = run.spikes[t]
            nonempty = s.enc_rank > 0
            occ_fb = None
            sent_of, votes_of = {}, {}
            for v in vote_models:
                if v == live:
                    sent, votes = s.sent, s.votes      # the live run, as logged
                else:
                    sent = nonempty & ((near[(t, v)] >= run.n_marks_min) if run.use_filter else True)
                    Kr, Km = K[(t, live)], K[(t, v)]
                    with np.errstate(divide='ignore', invalid='ignore'):
                        votes = (Km + EPS) * s.votes / (Kr + EPS)
                    # spikes the live model did not send have no logged vote:
                    # fall back to the decoder's occupancy at that wall-clock time
                    # (the encoder starts from zeros, the decoder from ones)
                    fb = sent & ~s.sent
                    if fb.any():
                        if occ_fb is None:
                            k = np.searchsorted(run.occ.rec_time, s.rec_time, side='right') - 1
                            occ_fb = run.occ.values[np.clip(k, 0, None)] - (0.0 if run.preloaded else 1.0)
                        with np.errstate(divide='ignore', invalid='ignore'):
                            o = occ_fb[fb] / np.nansum(occ_fb[fb], axis=1, keepdims=True)
                            votes[fb] = (Km[fb] + EPS) / o
                        n_fallback[v] += int(fb.sum())
                    votes[~np.isfinite(votes)] = 0.0
                    tot = votes.sum(axis=1, keepdims=True) * run.pos_bin_struct.pos_bin_delta
                    with np.errstate(divide='ignore', invalid='ignore'):
                        votes = np.where(tot > 0, votes / tot, 0.0)
                sent_of[v], votes_of[v] = sent, votes
            ref_sent, ref_votes = sent_of[0.0], votes_of[0.0]
            for v in todo:
                sent, votes = sent_of[v], votes_of[v]
                both = sent & ref_sent
                tv = np.full(len(s.ts), np.nan, np.float32)
                tv[both] = 0.5 * np.abs(votes[both] - ref_votes[both]).sum(axis=1)
                same_top = np.zeros(len(s.ts), bool)
                same_top[both] = votes[both].argmax(1) == ref_votes[both].argmax(1)
                ci = np.full(len(s.ts), -1, np.int16)
                ci[sent] = _cred_int(votes[sent], run.cred_interval)
                bump_of = assign[(t, v)][0]
                per_spike[v][t] = dict(
                    sent=sent, tv=tv, same_top=same_top, cred_int=ci,
                    t_eval=teval[(t, v)],
                    n_bumps_after=np.maximum.accumulate(bump_of) + 1 if len(bump_of) else bump_of,
                )
                variant_spikes[v].append((s.ts[sent], np.full(sent.sum(), t), s.pos[sent], votes[sent]))
        # the replay of the live run's own model must send exactly the spikes it sent
        ref_gate_ok = {t: bool(np.array_equal(
            run.spikes[t].enc_rank.astype(bool) & (near[(t, live)] >= run.n_marks_min), run.spikes[t].sent))
            for t in run.trodes}
        del K, near

        # 4. decode every bin, all variants in parallel
        t0 = time.time()
        ranks = {}
        for rank in sorted(run.bins.dec_rank.unique()):
            sel = (run.bins.dec_rank == rank).to_numpy()
            bins_r = run.bins[sel]
            occ_sel = run.occ.dec_rank == rank
            occ_ri = run.occ.rec_ind[occ_sel]
            ranks[int(rank)] = dict(
                rows=np.flatnonzero(sel),
                bin_lb=bins_r.bin_timestamp_l.to_numpy(np.int64),
                bin_ub=bins_r.bin_timestamp_r.to_numpy(np.int64),
                occ_idx=np.searchsorted(occ_ri, bins_r.rec_ind.to_numpy(), side='left') - 1,
                occ_values=run.occ.values[occ_sel],
                trodes=set(run.cfg['decoder_assignment'][int(rank)]),
            )
        _SHARED['ranks'] = ranks
        _SHARED['variants'] = {}
        for v in todo:
            ts = np.concatenate([x[0] for x in variant_spikes[v]])
            tr = np.concatenate([x[1] for x in variant_spikes[v]])
            ps = np.concatenate([x[2] for x in variant_spikes[v]])
            vo = np.concatenate([x[3] for x in variant_spikes[v]])
            _SHARED['variants'][v] = {}
            for rank, R in ranks.items():
                m = np.isin(tr, list(R['trodes']))
                arr, bounds = _bin_spikes(R, ts[m], tr[m], ps[m], vo[m])
                _SHARED['variants'][v][rank] = dict(arr=arr, bounds=bounds)
        del variant_spikes
        n_bins = len(run.bins)
        with ctx.Pool(min(n_workers, len(todo))) as pool:
            for v, out in pool.imap_unordered(_replay_job, todo):
                post = np.zeros((n_bins, run.num_bins), np.float32)
                n_used = np.zeros(n_bins, np.int16)
                for rank, (p, n) in out.items():
                    post[ranks[rank]['rows']] = p
                    n_used[ranks[rank]['rows']] = n
                results[v] = dict(posterior=post, n_used=n_used,
                                  per_spike=per_spike[v], n_fallback=n_fallback[v],
                                  ref_gate_ok=ref_gate_ok, live_tau=live)
        log(f'decoder replay ({len(todo)} variants): {time.time() - t0:.0f} s')
        _SHARED.pop('variants', None)
        _SHARED.pop('assign', None)

        if cache_dir:
            os.makedirs(cache_dir, exist_ok=True)
            for v, r in results.items():
                flat = dict(posterior=r['posterior'], n_used=r['n_used'],
                            n_fallback=np.atleast_1d(r['n_fallback']),
                            cache_version=np.atleast_1d(CACHE_VERSION),
                            live_tau=np.atleast_1d(live),
                            ref_gate_ok=np.array([[t, r['ref_gate_ok'][t]] for t in run.trodes]))
                for t, d in r['per_spike'].items():
                    for key, val in d.items():
                        flat[f'{key}__{t}'] = val
                np.savez(os.path.join(cache_dir, f'{run.prefix}.merge_tau{v:g}.npz'), **flat)

    for v, f in cache.items():
        with np.load(f) as z:
            per_spike = {t: {} for t in run.trodes}
            for key in z.files:
                if '__' in key:
                    name, t = key.split('__')
                    per_spike[int(t)][name] = z[key]
            results[v] = dict(posterior=z['posterior'], n_used=z['n_used'],
                              per_spike=per_spike, n_fallback=int(z['n_fallback'][0]),
                              ref_gate_ok={int(a): bool(b) for a, b in z['ref_gate_ok']},
                              live_tau=float(z['live_tau'][0]))
        log(f'threshold {v:g}: loaded from cache {f}')

    return SimpleNamespace(variants=variants, results=results)
