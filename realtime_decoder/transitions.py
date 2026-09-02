import csv
from collections import deque

import numpy as np

from realtime_decoder import utils

"""Contains methods for generating state-space transition models"""

##########################################################################
# Clusterless decoder transitions
##########################################################################

# used for 8-arm maze
# def sungod_transition_matrix_old(pos_bins, arm_coords, bias):

#     # this for tri-diagonal matrix 
#     from scipy.sparse import diags
#     n = len(pos_bins)
#     transition_mat = np.zeros([n, n])
#     k = np.array([(1/3) * np.ones(n - 1), (1/3) *
#                   np.ones(n), (1 / 3) * np.ones(n - 1)])
#     offset = [-1, 0, 1]
#     transition_mat = diags(k, offset).toarray()
#     box_end_bin = arm_coords[0, 1]

#     for x in arm_coords[:, 0]:
#         transition_mat[int(x), int(x)] = (5/9)
#         transition_mat[box_end_bin, int(x)] = (1/9)
#         transition_mat[int(x), box_end_bin] = (1/9)

#     for y in arm_coords[:, 1]:
#         transition_mat[int(y), int(y)] = (2 / 3)

#     transition_mat[box_end_bin, 0] = 0
#     transition_mat[0, box_end_bin] = 0
#     transition_mat[box_end_bin, box_end_bin] = 0
#     transition_mat[0, 0] = (2 / 3)

#     transition_mat[box_end_bin - 1, box_end_bin - 1] = (5/9)
#     transition_mat[box_end_bin - 1, box_end_bin] = (1/9)
#     transition_mat[box_end_bin, box_end_bin - 1] = (1/9)

#     transition_mat = transition_mat + bias
#     return transition_mag


# currently flat transition matrix
def sungod_transition_matrix(pos_bins, arm_coords, bias):

    """Generate transition matrix describing transitions
    for a maze consisting of a center segment and 1 or more arms"""

    n = len(pos_bins)
    transmat = np.zeros((n, n)) + bias

    # apply no animal boundary - make gaps between arms
    transmat = utils.apply_no_anim_boundary(
        pos_bins, arm_coords, transmat
    )

    # to smooth: take transition matrix to a power
    transmat = np.linalg.matrix_power(transmat, 1)

    # row normalize transition matrix
    transmat /= np.nansum(transmat, axis=1, keepdims=True)

    transmat[np.isnan(transmat)] = 0

    return transmat


def load_hex_graph(path):
    """Load a hex maze adjacency graph from a CSV of hex_a,hex_b edges.

    The edges are undirected; each connected pair may appear once or in
    both directions in the file (both are handled identically here).
    Returns {hex_id: set of neighboring hex ids}.
    """

    adjacency = {}
    with open(path, newline='') as f:
        reader = csv.reader(f)
        next(reader, None)  # header row
        for row in reader:
            if not row:
                continue
            a, b = int(row[0]), int(row[1])
            adjacency.setdefault(a, set()).add(b)
            adjacency.setdefault(b, set()).add(a)
    return adjacency


def prune_hex_graph(adjacency, blocked):
    """Return a copy of a hex adjacency graph with the given hexes
    removed, along with every edge touching them. This derives the
    session-specific maze from the full maze graph: barriers on this
    maze always occupy whole hexes, so a list of blocked hex ids fully
    describes a session's structure.

    Distances computed on the pruned graph automatically detour around
    blocked hexes. An empty `blocked` returns an equal copy of the
    input.
    """

    blocked = set(blocked)
    return {
        hex_id: neighbors - blocked
        for hex_id, neighbors in adjacency.items()
        if hex_id not in blocked
    }


def hex_graph_components(adjacency):
    """Return the connected components of a hex adjacency graph as a
    list of sets of hex ids. Used to detect a blocked_hexes list that
    splits the open maze into disconnected pieces (usually a typo in the
    config, since barrier layouts keep the open maze connected).
    """

    seen = set()
    components = []
    for hex_id in adjacency:
        if hex_id in seen:
            continue
        component = {hex_id}
        seen.add(hex_id)
        queue = deque([hex_id])
        while queue:
            cur = queue.popleft()
            for neighbor in adjacency.get(cur, ()):
                if neighbor not in seen:
                    seen.add(neighbor)
                    component.add(neighbor)
                    queue.append(neighbor)
        components.append(component)
    return components


def hex_transition_matrix(hex_ids, adjacency, bias):

    """Generate a transition matrix for a hex maze from its adjacency
    graph. Unlike hex_uniform_transition_matrix (uniform over every bin),
    this restricts each hex's transition probability to itself and its
    physically adjacent neighbors, since the animal cannot jump to a
    non-adjacent hex within one decoder time bin.

    `hex_ids` is the canonical, ordered list of hex ids; row/column i of
    the returned matrix corresponds to hex_ids[i]. A hex with no entry in
    `adjacency` (e.g. not yet visited this session, but still a real,
    physically valid maze location) gets self-transition probability 1 --
    it's a valid isolated state rather than an error.
    """

    n = len(hex_ids)
    index = {hex_id: i for i, hex_id in enumerate(hex_ids)}
    transmat = np.zeros((n, n)) + bias * np.identity(n)

    for hex_id in hex_ids:
        i = index[hex_id]
        for neighbor in adjacency.get(hex_id, ()):
            j = index.get(neighbor)
            if j is not None:
                transmat[i, j] = bias

    return _normalize_row_probability(transmat)


def hex_random_walk_transition_matrix(hex_ids, adjacency, movement_var):

    """Generate a random-walk transition matrix for a hex maze: a
    Gaussian over graph hop distance, following the RandomWalk model in
    LorenFrankLab/non_local_detector (which evaluates a Gaussian at
    track-graph shortest-path distance). Sits between
    hex_transition_matrix (hard 1-hop cutoff) and
    hex_uniform_transition_matrix (no spatial structure): transition
    probability decays smoothly with the number of hexes traveled.

    `movement_var` is the Gaussian's variance in hops^2 per decoding
    time bin. Hop count is used instead of physical distance because
    neighboring hex centroids are evenly spaced, so hops are
    proportional to travel distance along the maze. The Gaussian's
    normalization constant is omitted -- it is identical for every
    entry and cancels in the row normalization.

    Hexes in different graph components get transition probability 0
    between them; a hex with no entry in `adjacency` degenerates to a
    self-loop, matching hex_transition_matrix.

    `hex_ids` is the canonical, ordered list of hex ids; row/column i of
    the returned matrix corresponds to hex_ids[i].
    """

    if movement_var <= 0:
        raise ValueError(
            f"movement_var must be positive, got {movement_var}"
        )

    index = {hex_id: i for i, hex_id in enumerate(hex_ids)}
    n = len(hex_ids)

    # all-pairs hop distances, BFS from each hex. unreachable pairs stay
    # at inf, which the gaussian kernel below maps to probability 0
    dist = np.full((n, n), np.inf)
    for hex_id in hex_ids:
        i = index[hex_id]
        dist[i, i] = 0
        queue = deque([(hex_id, 0)])
        seen = {hex_id}
        while queue:
            cur, d = queue.popleft()
            for neighbor in adjacency.get(cur, ()):
                if neighbor not in seen:
                    seen.add(neighbor)
                    j = index.get(neighbor)
                    if j is not None:
                        dist[i, j] = d + 1
                    queue.append((neighbor, d + 1))

    transmat = np.exp(-dist**2 / (2 * movement_var))

    return _normalize_row_probability(transmat)


def hex_uniform_transition_matrix(num_bins):

    """Generate a uniform transition matrix for a hex maze: every hex is
    reachable, with equal probability, from every hex -- i.e. no
    spatial-continuity assumption is imposed. This mirrors what
    sungod_transition_matrix already does for the linear track, so the two
    maze types are decoded under the same (flat) prior.

    Depends only on the maze size, so it is built once at startup and
    never rebuilt. An earlier version gated this on which hexes the animal
    had visited so far, which made the matrix the identity until the
    second hex was visited -- turning the update into a running product of
    likelihoods that saturated within a few bins and, after ~200 bins,
    underflowed to a posterior that could no longer recover.

    Note this deliberately says nothing about which hexes have enough data
    to decode. That is the encoder's job and it already handles it: a hex
    with zero occupancy divides by zero in get_joint_prob() and is zeroed
    by the ~isfinite guard, so observed spikes contribute no likelihood
    there.

    Row/column i corresponds to dense position-bin index i, indexed the
    same way as occupancy (not raw hex id).
    """

    return np.full((num_bins, num_bins), 1 / num_bins)


def zero_blocked_hexes(transmat, blocked_idx):
    """Remove blocked (barriered) hexes from a row-normalized transition
    matrix: their rows and columns are zeroed, so any posterior mass
    there is annihilated within one time bin and can never return. This
    is deliberately different from the self-loop given to an *isolated*
    hex -- an isolated hex is a real location the animal could occupy,
    while a blocked hex is physically absent this session.

    `blocked_idx` holds dense position-bin indices (not raw hex ids).
    Rows of open hexes are re-normalized in case the matrix was built
    without knowledge of the blocked set (e.g. the uniform matrix);
    matrices built from a pruned graph already have zero mass there, so
    for them this is a no-op. Returns the input unchanged (same object,
    bit-identical) when blocked_idx is empty.
    """

    blocked_idx = list(blocked_idx)
    if not blocked_idx:
        return transmat

    transmat[blocked_idx, :] = 0
    transmat[:, blocked_idx] = 0
    # blocked rows are all-zero, so 0/0 happens inside the normalization;
    # _normalize_row_probability already maps the resulting nan's to 0,
    # only the warning needs suppressing
    with np.errstate(invalid='ignore'):
        return _normalize_row_probability(transmat)

##########################################################################
# Clusterless classifier transitions
##########################################################################

# Adapted from Eric's code at 
# https://github.com/Eden-Kramer-Lab/replay_trajectory_classification.
# Compatible with arm_coords specified in config file.
# Note that arm_coords[0] is assumed to be the center well.
# It is also assumed that arm_coords[0][0] is 0.

def _normalize_row_probability(x):
    '''Ensure the state transition matrix rows sum to 1
    '''
    x /= x.sum(axis=1, keepdims=True)
    x[~np.isfinite(x)] = 0
    return x

def _gaussian(x, mu, sigma):
    '''Normalized gaussian
    '''
    return np.exp(-0.5*((x - mu)/sigma)**2) / (sigma*np.sqrt(2*np.pi))


def random_walk(arm_coords, cm_per_bin, sigma):
    """Generate transition matrix describing transitions
    for a maze consisting of a center segment and 1 or more arms.
    A Gaussian kernel is used for smoothing"""

    base_offset = arm_coords[0][1]*cm_per_bin
    arm_labels = np.zeros(arm_coords[-1][-1] + 1) * np.nan
    bin_centers = np.arange(arm_labels.shape[0], dtype=np.float) * np.nan
    for arm_ind, (a, b) in enumerate(arm_coords):
        arm_labels[a:b+1] = arm_ind

        dist_vec = np.arange(b - a + 1, dtype=np.float) * cm_per_bin
        if arm_ind != 0:
            dist_vec += base_offset + cm_per_bin
        bin_centers[a:b+1] = dist_vec

    n_states = bin_centers.shape[0]
    transmat = np.zeros((n_states, n_states))
    for ii, (arm_label, center) in enumerate(zip(arm_labels, bin_centers)):
        if np.isnan(arm_label):
            transmat_row = 0
        else:
            transmat_row = _gaussian(bin_centers, center, sigma)
            if arm_label == 0:
                mask = ~np.isnan(arm_labels)
            else:
                # transitions within a specific arm ok. transitions to arm 0
                # (center well) also ok.
                mask = np.logical_or(arm_labels==0, arm_labels==arm_label)
            transmat_row[~mask] = 0
        transmat[ii] = transmat_row

    return _normalize_row_probability(transmat)


def uniform(arm_coords, cm_per_bin, sigma):

    """Generate transition matrix describing transitions
    for a maze consisting of a center segment and 1 or more arms.
    Transitions are uniform"""

    n_states = arm_coords[-1][-1]- arm_coords[0][0] + 1
    is_track_interior = np.zeros(n_states, dtype=bool)
    for ii, (a, b) in enumerate(arm_coords):
        is_track_interior[a:b+1] = True

    transmat = np.ones((n_states, n_states))
    transmat[~is_track_interior] = 0
    transmat[:, ~is_track_interior] = 0

    return _normalize_row_probability(transmat)


def identity(arm_coords, cm_per_bin, sigma):
    """Generate transition matrix describing transitions
    for a maze consisting of a center segment and 1 or more arms.
    There is zero transition probability on the off-diagonal elements"""
    
    n_states = arm_coords[-1][-1]- arm_coords[0][0] + 1
    is_track_interior = np.zeros(n_states, dtype=bool)
    for ii, (a, b) in enumerate(arm_coords):
        is_track_interior[a:b+1] = True

    transmat = np.identity(n_states)
    transmat[~is_track_interior] = 0
    transmat[:, ~is_track_interior] = 0

    return _normalize_row_probability(transmat)


def strong_diagonal_discrete(n_states, diag):
    """Generate transition matrix describing transitions
    for a maze consisting of a center segment and 1 or more arms.
    Unlike identity(), this method puts some transition probability
    on the off-diagonals"""

    strong_diagonal = np.identity(n_states) * diag
    is_off_diag = ~np.identity(n_states, dtype=bool)
    strong_diagonal[is_off_diag] = (
        (1 - diag) / (n_states - 1))
    return strong_diagonal


CONTINUOUS_TRANSITIONS = {
    'random_walk': random_walk,
    'uniform': uniform,
    'identity': identity,
}


DISCRETE_TRANSITIONS = {
    'strong_diagonal': strong_diagonal_discrete,
}