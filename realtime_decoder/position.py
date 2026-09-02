import numpy as np

from typing import List

from trodes_tracker import centroid as trodes_tracker_centroid

from realtime_decoder import base, datatypes, transitions

"""Contains objects relevant to handling position data"""

class PositionBinStruct(object):
    """Object for dealing with position bins"""

    def __init__(self, lower_bound, upper_bound, num_bins:int):

        self.pos_range = [lower_bound, upper_bound]
        self.num_bins = num_bins
        self.pos_bin_edges = np.linspace(
            lower_bound, upper_bound, num_bins + 1, endpoint=True, retstep=False
        )
        self.pos_bin_centers = (self.pos_bin_edges[:-1] + self.pos_bin_edges[1:]) / 2
        self.pos_bin_delta = self.pos_bin_centers[1] - self.pos_bin_centers[0]

    def which_bin(self, pos):
        """Find which position bin a given position belongs in.
        Legacy method that isn't used anymore"""

        return np.nonzero(np.diff(self._pos_bin_edges > pos))

    def get_bin(self, pos):

        """Find which position bin a given position belongs in."""

        return int((pos - self.pos_range[0])/self.pos_bin_delta)

class TrodesPositionMapper(base.PositionMapper):

    """Maps data obtained from a Trodes camera module into
    a position bin"""

    def __init__(self, arm_ids:List[int], arm_coords:List[List]):

        super().__init__()
        
        self._arm_ids = arm_ids
        self._arm_coords = arm_coords
        self._segment = 0
        self._segment_pos = 0
        self._seg_to_arm_map = {}
        for segment, arm in enumerate(self._arm_ids):
            self._seg_to_arm_map[segment] = arm

        self._bin_info = {}
        for arm_ind, (a, b) in enumerate(arm_coords):
            # position bin bounds are [a, b] (inclusive)
            self._bin_info[arm_ind] = {}
            self._bin_info[arm_ind]['bins'] = np.arange(a, b+1)
            self._bin_info[arm_ind]['norm_edges'] = np.linspace(0, 1, (b-a+1)+1)

    def map_position(self, datapoint:datatypes.CameraModulePoint):

        """Maps data from a Trodes camera module datapoint into a
        position bin"""

        #NOTE(DS): catch the error, if the error happens, use the previous segment value
        if (datapoint.segment != -1):
            segment = datapoint.segment
            segment_pos = datapoint.position    

            self._segment = segment
            self._segment_pos = segment_pos
        else:
            segment = self._segment
            segment_pos = self._segment_pos    

            print(f"ERROR has happened, segment: {-1}")    
            
        arm = self._seg_to_arm_map[segment]

        bins = self._bin_info[arm]['bins']
        norm_edges = self._bin_info[arm]['norm_edges']

        # in general segment positions x are assigned to a position bin
        # such that bin_edge_lower <= x < bin_edge_upper
        bin_ind = np.searchsorted(norm_edges, segment_pos, side='right') - 1

        # the exception is the last bin, where we can have
        # bin_edge_lower <= x <= bin_edge_upper 
        if bin_ind > len(bins) - 1:
            bin_ind = len(bins) - 1

        return bins[bin_ind]


class HexCentroidPositionMapper(base.PositionMapper):

    """Maps data obtained from a Trodes camera module into a hex maze
    cell, using nearest-centroid assignment (trodes_tracker.centroid).

    map_position() returns a dense array index (0..num_hexes-1), not the
    raw hex label used in the centroid/adjacency-graph CSVs -- this keeps
    it consistent with how occupancy and the transition matrix (the
    transitions.hex_*_transition_matrix functions, selected by
    clusterless_decoder.hex_transition_type) are indexed. Use
    hex_to_index()/index_to_hex() to translate between the two.

    Hexes listed in `blocked_hexes` (occupied by barriers this session)
    are never returned: they keep their dense index, but their centroids
    are excluded from the nearest-centroid search, so a position nearest
    to a barrier snaps to the nearest open hex instead.

    Returns None from map_position() when the animal is farther than
    `threshold` pixels from every open hex centroid (e.g. lost tracking).
    Callers should leave position/occupancy unchanged rather than pass
    None further down, since downstream bin lookups assume an int.
    """

    def __init__(self, centroid_file, threshold, hex_ids:List[int]=None,
                 blocked_hexes=()):

        super().__init__()

        self._centroids = trodes_tracker_centroid.load_centroids(centroid_file)
        self._threshold = threshold

        # canonical ordering: an explicit hex_ids list lets the caller
        # line this mapper up with a separately loaded adjacency graph,
        # which may not reference the exact same set of hexes
        if hex_ids is None:
            hex_ids = sorted(self._centroids.keys())
        self.hex_ids = list(hex_ids)
        self._hex_to_index = {hex_id: i for i, hex_id in enumerate(self.hex_ids)}

        # remove barriered hexes AFTER the index maps are built: blocked
        # hexes keep their dense index (the state space is fixed across
        # sessions), they just cannot win the nearest-centroid search
        for hex_id in blocked_hexes:
            self._centroids.pop(hex_id, None)

    def hex_to_index(self, hex_id):
        return self._hex_to_index.get(hex_id)

    def index_to_hex(self, index):
        return self.hex_ids[index]

    def map_position(self, datapoint:datatypes.CameraModulePoint):

        """Maps a camera-module datapoint to a dense hex-cell index, or
        None if the animal is farther than `threshold` from every hex
        centroid"""

        # two-LED midpoint -- matches trodes_tracker's own convention
        # (trodes_io.extract_xy) and this package's ripple_process.py
        # velocity computation, so all three agree on "animal position"
        xmid = (datapoint.x + datapoint.x2) / 2
        ymid = (datapoint.y + datapoint.y2) / 2

        hex_id, dist = trodes_tracker_centroid.nearest_hex(
            self._centroids, xmid, ymid
        )
        if hex_id is None or dist > self._threshold:
            return None

        return self._hex_to_index.get(hex_id)


def resolve_hex_position_config(config):
    """If config['encoder']['position']['type'] == 'hex', load the
    centroid and adjacency-graph CSVs it points to and inject 'hex_ids'
    and 'num_bins' into config['encoder']['position'] in place, so every
    site that reads config['encoder']['position']['num_bins'] gets a
    value consistent with the actual maze data rather than a
    hand-maintained YAML number. hex_ids is the sorted union of both
    files, so a hex present in only one of them is still a valid state.

    Also validates and normalizes 'blocked_hexes' (session barriers):
    unknown ids raise, and the cleaned list is injected back so
    downstream consumers (transition matrix, position mapper) all see
    the same value.

    No-op when position type is 'linear' (the default) -- existing
    configs are unaffected.
    """

    pos_config = config['encoder']['position']
    if pos_config.get('type') != 'hex':
        return

    centroids = trodes_tracker_centroid.load_centroids(
        pos_config['hex_centroid_file']
    )
    adjacency = transitions.load_hex_graph(pos_config['hex_graph_file'])
    hex_ids = sorted(set(centroids.keys()) | set(adjacency.keys()))

    pos_config['hex_ids'] = hex_ids
    pos_config['num_bins'] = len(hex_ids)

    # validate blocked_hexes (hexes made unavailable by barriers this
    # session) here, at config-resolution time, so a typo kills startup on
    # every rank with a clear message instead of silently decoding the
    # wrong maze. normalized (sorted, deduplicated, missing -> []) so
    # downstream consumers can rely on the injected value.
    blocked = pos_config.get('blocked_hexes', []) or []
    unknown = sorted(set(blocked) - set(hex_ids))
    if unknown:
        raise ValueError(
            f"blocked_hexes contains unknown hex ids {unknown} -- valid "
            f"ids are defined by {pos_config['hex_centroid_file']} and "
            f"{pos_config['hex_graph_file']}"
        )
    pos_config['blocked_hexes'] = sorted(set(blocked))


def build_position_mapper(config):
    """Construct the position mapper indicated by
    config['encoder']['position']['type'] ('linear', the default, or
    'hex'). Centralizing this avoids the mapper-construction call sites
    (encoder rank, decoder rank, ripple rank) drifting out of sync, which
    they previously did (each built its own TrodesPositionMapper).
    """

    pos_config = config['encoder']['position']

    if pos_config.get('type') == 'hex':
        return HexCentroidPositionMapper(
            pos_config['hex_centroid_file'],
            pos_config['hex_threshold'],
            hex_ids=pos_config['hex_ids'],
            blocked_hexes=pos_config.get('blocked_hexes', ())
        )

    return TrodesPositionMapper(
        pos_config['arm_ids'],
        pos_config['arm_coords']
    )


class KinematicsEstimator(object):

    """Object used to estimate position and speed, can also
    smooth the estimates using an FIR filter"""

    def __init__(
        self, *, scale_factor=1, dt=1,
        xfilter=None, yfilter=None,
        speedfilter=None
    ):
        self._sf = scale_factor
        self._dt = dt

        self._b_x = np.array(xfilter)
        self._b_y = np.array(yfilter)
        self._b_speed = np.array(speedfilter)

        self._buf_x = np.zeros(self._b_x.shape[0])
        self._buf_y = np.zeros(self._b_y.shape[0])
        self._buf_speed = np.zeros(self._b_speed.shape[0])

        self._last_x = -1
        self._last_y = -1
        self._last_speed = -1

    def compute_kinematics(
        self, x, y, *, smooth_x=False,
        smooth_y=False, smooth_speed=False
    ):

        """Estimate x position, y position, and the speed"""

        # very first datapoint
        if self._last_speed == -1:
            self._last_x = x
            self._last_y = y
            self._last_speed = 0
            return x, y, 0

        if smooth_x:
            xv = self._smooth(x * self._sf, self._b_x, self._buf_x)
        else:
            xv = x

        if smooth_y:
            yv = self._smooth(y * self._sf, self._b_y, self._buf_y)
        else:
            yv = y

        sv = np.sqrt((yv - self._last_y)**2 + (xv - self._last_x)**2) / self._dt
        if smooth_speed:
            sv = self._smooth(sv, self._b_speed, self._buf_speed)

        # now that the speed has been estimated, the current x and y values
        # become the most recent (last) x and y values
        self._last_x = xv
        self._last_y = yv
        self._last_speed = sv

        return xv, yv, sv

    def _smooth(self, newval, coefs, buf):

        """Smooths data using an FIR filter"""

        # mutates data!
        buf[1:] = buf[:-1]
        buf[0] = newval
        rv = np.sum(coefs * buf, axis=0)

        return rv