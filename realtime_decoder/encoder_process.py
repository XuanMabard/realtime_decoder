import os
import glob
import time
import fcntl
import numpy as np
import copy
from mpi4py import MPI
from typing import Sequence, List

from realtime_decoder import (
    base, utils, position, datatypes, messages, binary_record, taskstate
)

####################################################################################
# Data classes
####################################################################################

class EncoderJointProbEstimate(object):
    """Data object containing infomration about joint probability
    over marks and position"""

    def __init__(self, nearby_spikes, weights, positions, hist):
        self.nearby_spikes = nearby_spikes
        self.weights = weights
        self.positions = positions
        self.hist = hist

####################################################################################
# Interfaces
####################################################################################

class EncoderMPISendInterface(base.StandardMPISendInterface):
    """Sending interface object for encoder_process"""

    def __init__(self, comm, rank, config):
        super().__init__(comm, rank, config)

    def send_joint_prob(self, dest, msg):
        """Send mark-position joint probability data"""

        self.comm.Send(
            buf=msg.tobytes(),
            dest=dest,
            tag=messages.MPIMessageTag.SPIKE_DECODE_DATA
        )

####################################################################################
# Data handlers/managers
####################################################################################

class Encoder(base.LoggingClass):
    """Represents an encoding model. Note: this class only handles
    1D position currently"""

    def __init__(self, config, trode, pos_bin_struct):

        super().__init__()
        self._config = config
        self._trode = trode
        self._pos_bin_struct = pos_bin_struct

        sigma = self._config['encoder']['mark_kernel']['std']
        self._k1 = 1 / (np.sqrt(2*np.pi) * sigma)
        self._k2 = -0.5 / (sigma**2)

        self._position = 0

        # be aware that this starts from zero. in order to be correct,
        # we must have self._config['encoder']['position']['lower'] be 0
        self._pos_bins = np.arange(
            self._config['encoder']['position']['num_bins']
        )

        pos_config = self._config['encoder']['position']
        self._is_hex = pos_config.get('type') == 'hex'
        self._arm_coords = (
            None if self._is_hex else np.array(pos_config['arm_coords'])
        )

        if config['preloaded_model']:
            self._load_model()
        else:
            N = self._config['encoder']['bufsize']
            dim = self._config['encoder']['mark_dim']
            self._marks = np.zeros((N, dim), dtype='<f8')
            self._chosen_indices = 0
            self._positions = np.zeros(N, dtype='<f4')
            # how many spikes each stored row stands for (1 unless spikes were
            # merged into it); multiplies the row's kernel in get_joint_prob
            self._counts = np.zeros(N, dtype='<f8')
            self._mark_idx = 0
            # every training spike as it came in, before merging. saved next
            # to the (merged) model so the unmerged model is always available
            self._raw_marks = np.zeros((N, dim), dtype='<f8')
            self._raw_positions = np.zeros(N, dtype='<f4')
            self._n_spikes = 0
            self._occupancy = np.zeros(self._config['encoder']['position']['num_bins'])
            self._occupancy_ct = 0
            self._temp_idx = 0 # NOTE(DS): so that mark_idx does not increase but still write down in the mark vec

        self._init_params()
    def _load_model(self):

        fname = os.path.join(
                self._config['files']['saved_model_dir'],
                f"{self._config['files']['saved_model_prefix']}*trode_{self._trode}.encoder.npz"
            )
        print(f"encoder model fname: {fname}")
        
        files = glob.glob(fname)

        if files == []:
            raise ValueError(
                f"Could not load encoding model successfully!")

        elif len(files) != 1:
            raise ValueError(
                "Found multiple encoders in directory "
                f"{self._config['files']['saved_model_dir']}. "
                "Make sure there is only one."
            )
        else:
            with np.load(files[0]) as f:
                self._positions = f['positions']
                self._marks = f['marks']
                print(f['mark_idx'])
                if 'counts' in f.files:
                    # saved by the merging code: the arrays hold exactly the
                    # rows in use, and the unmerged spikes are saved too
                    self._mark_idx = int(f['mark_idx'][0])
                    self._counts = f['counts']
                    self._raw_marks = f['raw_marks']
                    self._raw_positions = f['raw_positions']
                    self._n_spikes = int(f['n_spikes'][0])
                else:
                    if f['mark_idx'][0] < self._config['encoder']['bufsize']: #NOTE(DS): it seem to be a offset of 1.
                        self._mark_idx = f['mark_idx'][0]-1
                    else:
                        self._mark_idx = self._config['encoder']['bufsize']-1
                    # older files: every row is one spike, so the model is
                    # also its own unmerged copy
                    self._counts = np.ones(self._marks.shape[0])
                    self._raw_marks = self._marks[:self._mark_idx].copy()
                    self._raw_positions = self._positions[:self._mark_idx].copy()
                    self._n_spikes = int(self._mark_idx)

                self._occupancy = f['occupancy']
                self._occupancy_ct = f['occupancy_ct'][0]
            self.class_log.info(f"Loaded encoding model from {files[0]}")

        # save() writes this; it was only set for new (not loaded) models
        self._chosen_indices = 0
        self._temp_idx = 0 

    def _init_params(self):
        """Initialize parameters used for the encoding model"""

        self.p = {}
        self.p['mark_dim'] = self._config['encoder']['mark_dim']
        self.p['use_channel_dist_from_max_amp'] = self._config['encoder']['use_channel_dist_from_max_amp']
        self.p['use_filter'] = self._config['encoder']['mark_kernel']['use_filter']
        self.p['filter_std'] = self._config['encoder']['mark_kernel']['std']
        self.p['filter_n_std'] = self._config['encoder']['mark_kernel']['n_std']
        self.p['n_marks_min'] = self._config['encoder']['mark_kernel']['n_marks_min']
        self.p['num_occupancy_points'] = self._config['display']['encoder']['occupancy']
        # merge a training spike into the nearest stored row of the same hex
        # if it is within merge_threshold kernel widths (std) of it. 0 = never
        # merge: every spike gets its own row, as before
        self.p['merge_threshold'] = self._config['encoder']['mark_kernel'].get(
            'merge_threshold', 0
        )
        if (isinstance(self.p['merge_threshold'], bool) or
                not isinstance(self.p['merge_threshold'], (int, float)) or
                not np.isfinite(self.p['merge_threshold']) or
                self.p['merge_threshold'] < 0):
            raise ValueError(
                "encoder.mark_kernel.merge_threshold must be a number >= 0, "
                f"got {self.p['merge_threshold']!r}"
            )
        self.p['merge_dist2'] = (
            self.p['merge_threshold'] * self._config['encoder']['mark_kernel']['std']
        ) ** 2

    def add_new_mark(self, mark, position=None):
        """Add a training spike to the encoding model. `position` is where
        the animal was when the spike fired; defaults to the current position.
        Returns True if the spike got its own row, False if it was merged
        into an existing row"""

        '''
        # NOTE(DS): Having only the most recent spikes bias the encoding 
        if self._mark_idx < self._marks.shape[0]:
            self._marks[self._mark_idx%self._marks.shape[0]] = mark
            self._positions[self._mark_idx%self._marks.shape[0]] = self._position
            self._mark_idx += 1
        else:
            if self._mark_idx%2 == 0:
                self._marks[self._mark_idx%self._marks.shape[0]] = mark
                self._positions[self._mark_idx%self._marks.shape[0]] = self._position
            self._mark_idx += 3
        '''

        '''
        if self._mark_idx < self._marks.shape[0]:
            self._marks[self._mark_idx] = mark
            self._positions[self._mark_idx] = self._position
            self._mark_idx += 1

        else:
            self._marks[self._temp_idx%self._marks.shape[0]] = mark
            self._positions[self._temp_idx%self._marks.shape[0]] = self._position
            self._temp_idx += 2
            if self._temp_idx%2000 == 0:
                self.class_log.info(
                f"mark buffer is full. substitutes every other markvec {self._temp_idx/2}"
                )
        '''

        if position is None:
            position = self._position

        # the unmerged copy keeps every training spike as it came in.
        # same growth rule as the model buffer below
        if self._n_spikes == self._raw_marks.shape[0]:
            n_new = max(self._raw_marks.shape[0], 1)
            self._raw_marks = np.vstack((
                self._raw_marks,
                np.zeros((n_new, self._raw_marks.shape[1]), dtype=self._raw_marks.dtype)
            ))
            self._raw_positions = np.hstack((
                self._raw_positions,
                np.zeros(n_new, dtype=self._raw_positions.dtype)
            ))
        self._raw_marks[self._n_spikes] = mark
        self._raw_positions[self._n_spikes] = position
        self._n_spikes += 1

        # merge into the nearest stored row recorded in the same hex, if it is
        # within merge_threshold kernel widths: that row then stands for one
        # more spike, and its center moves to the average of its spikes. only
        # rows of the same hex are candidates, so every hex keeps exactly its
        # own spike count
        if self.p['merge_threshold'] > 0 and self._mark_idx > 0:
            same_hex = np.flatnonzero(self._positions[:self._mark_idx] == position)
            if same_hex.size:
                diff = self._marks[same_hex] - mark
                squared_distance = np.einsum('ij,ij->i', diff, diff)
                nearest = np.argmin(squared_distance)
                if squared_distance[nearest] <= self.p['merge_dist2']:
                    row = same_hex[nearest]
                    self._counts[row] += 1
                    self._marks[row] += (mark - self._marks[row]) / self._counts[row]
                    return False

        if self._mark_idx == self._marks.shape[0]:
            # NOTE(DS): This make buf_size meaningless
            # double the buffer, by at least one row: a buffer compacted to
            # zero rows at the task state switch must still be able to grow,
            # since a spike that fired before the switch can arrive after it
            n_new = max(self._marks.shape[0], 1)
            self._marks = np.vstack((
                self._marks,
                np.zeros((n_new, self._marks.shape[1]), dtype=self._marks.dtype)
            ))
            self._positions = np.hstack((
                self._positions,
                np.zeros(n_new, dtype=self._positions.dtype)
            ))
            self._counts = np.hstack((
                self._counts,
                np.zeros(n_new, dtype=self._counts.dtype)
            ))
            
        # this is where the mark_size increases over time 
        self._marks[self._mark_idx] = mark
        self._positions[self._mark_idx] = position
        self._counts[self._mark_idx] = 1
        self._mark_idx += 1
        return True





    def get_joint_prob(self, mark):
        """Get a estimate of the joint mark-position probability,
        given an observed mark"""

        # on the very first spike, there are no marks with which to evaluate
        # the kernel. therefore, return immediately
        if self._mark_idx == 0:
            return None


        #NOTE(DS): if number of mark exceeds 
        if self._mark_idx >= self._config['encoder']['bufsize']:#self._marks.shape[0]:
            mark_idx = self._config['encoder']['bufsize']

        else:
            mark_idx = self._mark_idx

        marks = self._marks[:mark_idx]
        counts = self._counts[:mark_idx]
        nearby_spikes = int(counts.sum())
        if self.p['use_filter']:
            std = self.p['filter_std']
            n_std = self.p['filter_n_std']
            # count stored marks within +/- n_std*std of this mark on every
            # channel. same comparisons as checking each channel over all
            # stored marks, but channels are checked from this mark's largest
            # value down, and each channel only re-checks the marks that passed
            # the channels before it: the peak channel rules out most marks at
            # once, so later channels see a few thousand instead of all of
            # them. the order cannot change the count, since a mark has to
            # pass every channel
            order = np.argsort(-np.abs(mark), kind='stable')
            ch = order[0]
            rows = np.flatnonzero(
                (marks[:, ch] > mark[ch] - n_std * std) &
                (marks[:, ch] < mark[ch] + n_std * std)
            )
            for ch in order[1:]:
                col = marks[rows, ch]
                rows = rows[
                    (col > mark[ch] - n_std * std) &
                    (col < mark[ch] + n_std * std)
                ]
            # spikes represented by the stored rows inside the box (int: it
            # goes into an int32 record field)
            nearby_spikes = int(counts[rows].sum())

            # not enough spikes within n-cube
            if nearby_spikes < self.p['n_marks_min']:
                return None

        # evaluate Gaussian kernel on distance in mark space. einsum squares
        # and sums each row in one pass, without a temporary array of squares
        diff = marks - mark
        squared_distance = np.einsum('ij,ij->i', diff, diff)
        # each row's kernel counts once for every spike the row stands for
        weights = counts * (self._k1 * np.exp(squared_distance * self._k2))
        positions = self._positions[:mark_idx]

        # print(positions.shape)
        # print("")
        # print(self._pos_bin_struct.pos_bin_edges)
        # print("")
        # print(weights)

        pbs = self._pos_bin_struct
        if pbs.pos_range[0] == 0 and pbs.pos_bin_delta == 1:
            # bins of width 1 starting at 0 (every config so far): the stored
            # positions are the bin indices themselves, so add each weight
            # straight into its bin. np.histogram sorts all positions to get
            # the same sums (equal up to rounding in the last digit)
            hist = np.bincount(
                positions.astype(np.intp),
                weights=weights,
                minlength=pbs.num_bins
            )
        else:
            hist, hist_edges = np.histogram(
                a=positions,
                bins=pbs.pos_bin_edges,
                weights=weights
            )

        hist += 0.0000001

        # normalize by occupancy
        hist /= (self._occupancy/np.nansum(self._occupancy))
        hist[~np.isfinite(hist)] = 0.0

        # note: if pos_bin_delta is not one, this will not sum to 1
        hist /= (np.sum(hist) * self._pos_bin_struct.pos_bin_delta)

        # print("")
        # print(hist)
        # print("")

        return EncoderJointProbEstimate(
            nearby_spikes, weights, positions, hist
        )

    def update_position(self, position, update_occupancy:bool):
        """Update the current position of the encoding model"""

        self._position = position

        if update_occupancy:

            bin_idx = self._pos_bin_struct.get_bin(self._position)
            self._occupancy[bin_idx] += 1
            if not self._is_hex:
                # no "gap between arms" concept for a hex maze -- every
                # hex is a physically valid location
                utils.apply_no_anim_boundary(
                    self._pos_bins, self._arm_coords, self._occupancy, np.nan)

            self._occupancy_ct += 1

            if self._occupancy_ct % self.p['num_occupancy_points'] == 0:
                print(f"Number of encoder occupancy points: {self._occupancy_ct}")

    def save(self):
        """Save the encoding model to disk"""

        filename = os.path.join(
            self._config['files']['output_dir'],
            f"{self._config['files']['prefix']}_" +
            f"trode_{self._trode}.encoder.npz"
        )
        # only the rows in use (the buffers are preallocated far larger).
        # marks/positions/counts: the model the decoder uses, merged rows
        # included; raw_marks/raw_positions: every training spike, unmerged
        n_rows = self._mark_idx
        np.savez(
            filename,
            marks=self._marks[:n_rows],
            marks_indices = self._chosen_indices,
            bufsize = self._config['encoder']['bufsize'],
            positions=self._positions[:n_rows],
            counts=self._counts[:n_rows],
            mark_idx=np.atleast_1d(self._mark_idx),
            raw_marks=self._raw_marks[:self._n_spikes],
            raw_positions=self._raw_positions[:self._n_spikes],
            n_spikes=np.atleast_1d(self._n_spikes),
            merge_threshold=np.atleast_1d(self.p['merge_threshold']),
            occupancy=self._occupancy,
            occupancy_ct=np.atleast_1d(self._occupancy_ct)
        )
        self.class_log.info(f"Saved encoding model to {filename}")

class EncoderManager(base.BinaryRecordBase, base.MessageHandler):
    """Manager class that handles MPI messsages and delegates training
    of the encoding model, among other functions"""

    def __init__(self, rank, config, send_interface, spikes_interface,
        pos_interface, pos_mapper
    ):

        n_bins = config['encoder']['position']['num_bins']
        dig = len(str(n_bins))

        n_mark_dims = config['encoder']['mark_dim']

        super().__init__(
            rank=rank,
            rec_ids=[
                binary_record.RecordIDs.ENCODER_QUERY,
                binary_record.RecordIDs.ENCODER_OUTPUT,
                #############################################################################################################################
                # Only for testing, remove when finalized
                binary_record.RecordIDs.POS_INFO
                #############################################################################################################################
            ],
            rec_labels=[
                ['timestamp',
                'elec_grp_id',
                'weight',
                'position'],
                ['timestamp', 'elec_grp_id','position', 'velocity',
                'encode_spike', 'cred_int', 'decoder_rank',
                'nearby_spikes', 'sent_to_decoder',
                'vel_thresh', 'frozen_model', 'task_state'] +
                [f'mark_dim_{dim}' for dim in range(n_mark_dims)] +
                [f'x{v:0{dig}d}' for v in range(n_bins)],
                ['timestamp', 'x', 'y', 'x2', 'y2', 'segment', 'position', 'smooth_x', 'smooth_y', 'vel', 'mapped_pos']
            ],
            rec_formats=[
                'qidd',
                'qidd?qqq?d?i'+'d'*n_mark_dims+'d'*n_bins,
                'qddddiddddd'
            ],
            send_interface=send_interface,
            manager_label='state'
        )

        self._config = config

        self._spikes_interface = spikes_interface
        self._pos_interface = pos_interface

        if not isinstance(pos_mapper, base.PositionMapper):
            raise TypeError(f"Invalid 'pos_mapper' type {type(pos_mapper)}")
        self._pos_mapper = pos_mapper

        self._kinestimator = position.KinematicsEstimator(
            scale_factor=config['kinematics']['scale_factor'],
            dt=1/config['sampling_rate']['position'],
            xfilter=config['kinematics']['smoothing_filter'],
            yfilter=config['kinematics']['smoothing_filter'],
            speedfilter=config['kinematics']['smoothing_filter'],
        )

        self._spike_msg = np.zeros(
            (1, ),
            dtype=messages.get_dtype(
                "SpikePosJointProb", config=config
            )
        )

        # key for these dictionaries is elec_grp_id
        self._spk_counters = {}
        self._encoders = {}
        self._dead_channels = {}
        self._decoder_map = {} # map elec grp id to decoder rank
        self._times = {}
        self._times_ind = {}

        self._task_state = 1
        self._task_state_handler = taskstate.TaskStateHandler(self._config)
        self._save_early = True

        self._pos_counter = 0
        self._current_pos = 0
        self._current_vel = 0
        self._pos_timestamp = -1

        self._init_params()
        self._init_position_history()

    def handle_message(self, msg, mpi_status):
        """Process a (non neural data) received MPI message"""

        if isinstance(msg, messages.TrodeSelection):
            self._set_up_trodes(msg.trodes)
        elif isinstance(msg, messages.BinaryRecordCreate):
            self.set_record_writer_from_message(msg)
        elif isinstance(msg, messages.StartRecordMessage):
            self.class_log.info("Starting records")
            self.start_record_writing()
        elif isinstance(msg, messages.ActivateDataStreams):
            self.class_log.info("Activating datastreams")
            self._spikes_interface.activate()
            self._pos_interface.activate()
        elif isinstance(msg, messages.TerminateSignal):
            rank = mpi_status.source
            self.class_log.info(f"Got terminate signal from rank {rank}")
            raise StopIteration()
        elif isinstance(msg, messages.VerifyStillAlive):
            self.send_interface.send_alive_message()
        elif isinstance(msg, messages.GuiEncodingModelParameters):
            self._update_gui_params(msg)
        else:
            self._class_log.warning(
                f"Received message of type {type(msg)} "
                f"from source: {mpi_status.source}, "
                f" tag: {mpi_status.tag}, ignoring"
            )

    def next_iter(self):
        """Run one iteration processing any available neural data"""

        spike_msg = self._spikes_interface.__next__()
        if spike_msg is not None:
            self._process_spike(spike_msg)

        pos_msg = self._pos_interface.__next__()
        if pos_msg is not None:
            self._process_pos(pos_msg)

    def _init_params(self):
        """Initialize parameters used by this object"""

        self.p = {}
        self.p['num_bins'] = self._config['encoder']['position']['num_bins']
        self.p['spk_amp'] = self._config['encoder']['spk_amp']
        self.p['preloaded_model'] = self._config['preloaded_model']
        self.p['frozen_model'] = self._config['frozen_model']
        # if true, the encoding model keeps growing after the task state
        # switches away from 1 (i.e. train and decode simultaneously).
        # default false preserves the original train-then-decode behavior
        self.p['train_all_task_states'] = self._config['encoder'].get(
            'train_all_task_states', False
        )
        self.p['smooth_x'] = self._config['kinematics']['smooth_x']
        self.p['smooth_y'] = self._config['kinematics']['smooth_y']
        self.p['smooth_speed'] = self._config['kinematics']['smooth_speed']
        self.p['vel_thresh'] = self._config['encoder']['vel_thresh']
        self.p['cred_interval'] = self._config['cred_interval']['val']
        self.p['timings_bufsize'] = self._config['encoder']['timings_bufsize']
        self.p['num_encoding_disp'] = self._config['display']['encoder']['encoding_spikes']
        self.p['num_total_disp'] = self._config['display']['encoder']['total_spikes']
        self.p['num_pos_disp'] = self._config['display']['encoder']['position']
        self.p['num_pos_points'] = self._config['encoder']['num_pos_points']
        self.p['use_channel_dist_from_max_amp'] = self._config['encoder']['use_channel_dist_from_max_amp']
        # seconds of position samples kept for pairing each spike with where
        # the animal was when it fired (spikes have waited up to ~45 s when
        # the KDE fell behind). older spikes are not added to the model
        self.p['pos_history_s'] = self._config['encoder'].get(
            'position_history_s', 120
        )

    def _init_position_history(self):
        """Set up the history of recent position samples used to pair each
        spike with the position, speed and task state at its own timestamp"""

        n = int(np.ceil(
            self.p['pos_history_s'] * self._config['sampling_rate']['position']
        ))
        # twice the size: when full, the newest half is kept, so at least
        # pos_history_s seconds are always available
        self._pos_hist_ts = np.zeros(2 * n, dtype=np.int64)
        self._pos_hist_pos = np.zeros(2 * n, dtype=np.float64)
        self._pos_hist_vel = np.zeros(2 * n, dtype=np.float64)
        self._pos_hist_task_state = np.zeros(2 * n, dtype=np.int64)
        self._pos_hist_n = 0
        self._first_pos_timestamp = None
        self._n_spikes_too_old = 0

    def _record_position(self, timestamp):
        """Append the current position, speed and task state to the
        position history"""

        if self._pos_hist_n == len(self._pos_hist_ts):
            keep = len(self._pos_hist_ts) // 2
            for arr in (
                self._pos_hist_ts, self._pos_hist_pos,
                self._pos_hist_vel, self._pos_hist_task_state
            ):
                arr[:keep] = arr[-keep:]
            self._pos_hist_n = keep

        if self._first_pos_timestamp is None:
            self._first_pos_timestamp = timestamp

        ind = self._pos_hist_n
        self._pos_hist_ts[ind] = timestamp
        self._pos_hist_pos[ind] = self._current_pos
        self._pos_hist_vel[ind] = self._current_vel
        self._pos_hist_task_state[ind] = self._task_state
        self._pos_hist_n += 1

    def _position_at(self, timestamp):
        """Position, speed and task state of the latest position sample at
        or before `timestamp`. None if the history doesn't reach back that
        far (or no position sample has arrived yet)"""

        ind = np.searchsorted(
            self._pos_hist_ts[:self._pos_hist_n], timestamp, side='right'
        ) - 1
        if ind < 0:
            return None

        return (
            self._pos_hist_pos[ind],
            self._pos_hist_vel[ind],
            int(self._pos_hist_task_state[ind])
        )

    def _update_gui_params(self, gui_msg):
        """Update parameters that can be changed by the GUI"""

        self.class_log.info("Updating GUI encoder parameters")
        self.p['vel_thresh'] = gui_msg.encoding_velocity_threshold
        self.p['frozen_model'] = gui_msg.freeze_model

    def _init_timings(self, trode):
        """Initialize objects that are used for keeping track of
        timing information"""

        dt = np.dtype([
            ('elec_grp_id', '=i4'),
            ('timestamp', '=i8'),
            ('t_send_data', '=i8'),
            ('t_recv_data', '=i8'),
            ('t_start_kde', '=i8'),
            ('t_end_kde', '=i8'),
            ('t_start_enc_send', '=i8'),
            ('t_end_enc_send', '=i8'),
            # stored rows the KDE evaluated for this spike (= spikes in the
            # model when nothing is merged)
            ('kde_rows', '=i8')
        ])
        self._times[trode] = np.zeros(
            self.p['timings_bufsize'],
            dtype=dt
        )
        self._times_ind[trode] = 0

    def _process_spike(self, spike_msg):
        """Process a spike event"""

        spike_timestamp = spike_msg.timestamp
        elec_grp_id = spike_msg.elec_grp_id

        # zero out dead channels
        if elec_grp_id in self._dead_channels:
            dch  = self._dead_channels[elec_grp_id]
            spike_msg.data[dch] = 0 # mutates data

        mark_vec = self._compute_mark(spike_msg)


        #print('this is mark vec')
        #print(mark_vec)
        #print(mark_vec.shape) # NOTE(DS): for debug

        
        if max(mark_vec) > self.p['spk_amp']:

            # pair the spike with where the animal was when it fired. when
            # the KDE falls behind, spikes wait in the Trodes stream (tens of
            # seconds at worst) while position messages keep being processed,
            # so the current position can be far from the spike's own
            spike_state = self._position_at(spike_timestamp)
            if spike_state is None:
                # no position sample at or before this spike: it fired before
                # position tracking started, or it is older than the history.
                # its position is unknown, so it is never trained on; the
                # current values only go to the record and the decoder message
                spike_pos = self._current_pos
                spike_vel = self._current_vel
                spike_task_state = self._task_state
                if (self._first_pos_timestamp is not None and
                        spike_timestamp >= self._first_pos_timestamp):
                    self._n_spikes_too_old += 1
                    if self._n_spikes_too_old % 1000 == 1:
                        self.class_log.warning(
                            f"{self._n_spikes_too_old} spike(s) so far were "
                            f"older than the {self.p['pos_history_s']} s "
                            "position history when processed, so they were "
                            "not added to the encoding model"
                        )
            else:
                spike_pos, spike_vel, spike_task_state = spike_state

            t_start_kde = time.time_ns()
            joint_prob_obj = self._encoders[elec_grp_id].get_joint_prob(
                mark_vec
            )
            t_end_kde = time.time_ns()

            # determine if encoding spike, from the speed and task state at
            # the spike's own time. never train on a spike whose position is
            # unknown
            encoding_spike = (
                spike_state is not None and
                self._is_training_epoch(spike_vel, spike_task_state)
            )

            # determine decoder
            decoder_rank = self._decoder_map[elec_grp_id]

            if joint_prob_obj is not None:

                # compute credible interval
                spxx = np.sort(joint_prob_obj.hist)[::-1]
                cred_int = np.searchsorted(np.cumsum(spxx), self.p['cred_interval']) + 1

                # send decoded spike message
                self._spike_msg[0]['timestamp'] = spike_timestamp
                self._spike_msg[0]['elec_grp_id'] = elec_grp_id
                self._spike_msg[0]['current_pos'] = spike_pos
                self._spike_msg[0]['cred_int'] = cred_int
                self._spike_msg[0]['hist'] = joint_prob_obj.hist
                t_start_enc_send = time.time_ns()
                self._spike_msg[0]['send_time'] = t_start_enc_send
                self.send_interface.send_joint_prob(decoder_rank, self._spike_msg)
                t_end_enc_send = time.time_ns()

                self._record_timings(
                    elec_grp_id, spike_timestamp,
                    spike_msg.t_send_data, spike_msg.t_recv_data,
                    t_start_kde, t_end_kde,
                    t_start_enc_send, t_end_enc_send,
                    min(
                        self._encoders[elec_grp_id]._mark_idx,
                        self._config['encoder']['bufsize']
                    )
                )
                # record result

                self.write_record(
                    binary_record.RecordIDs.ENCODER_OUTPUT,
                    spike_timestamp, elec_grp_id,
                    spike_pos, spike_vel,
                    encoding_spike, cred_int,
                    decoder_rank, True,
                    self.p['vel_thresh'], self.p['frozen_model'],
                    spike_task_state,
                    joint_prob_obj.nearby_spikes,
                    *mark_vec, *joint_prob_obj.hist
                )

            # either first spike or not enough neighboring spikes
            # (assuming filter is on). still record result
            else:
                if len(mark_vec) != 8:
                   print(f"******************mark_vec: {len(mark_vec)}*******************")
                self.write_record(
                    binary_record.RecordIDs.ENCODER_OUTPUT,
                    spike_timestamp, elec_grp_id,
                    spike_pos, spike_vel,
                    encoding_spike, -1, # since didn't compute credible interval
                    decoder_rank, False,
                    self.p['vel_thresh'], self.p['frozen_model'],
                    spike_task_state,
                    -1,
                    *mark_vec, *np.zeros(self.p['num_bins'])
                )

            # now that we've estimated the spike/pos joint probability,
            # we need to decide whether to add it to the encoding model
            # or not
            if encoding_spike:
                encoder = self._encoders[elec_grp_id]
                new_row = encoder.add_new_mark(mark_vec, spike_pos)
                # only on a new row: while spikes merge, the row count can sit
                # at a multiple of 1000 and would log on every merge
                if new_row and encoder._mark_idx % 1000 == 0:
                    self.class_log.info(
                        f"num spikes in {elec_grp_id} is {encoder._n_spikes} "
                        f"({encoder._mark_idx} stored rows)"
                        )
                self._spk_counters[elec_grp_id]['encoding'] += 1
                if self._spk_counters[elec_grp_id]['encoding'] % self.p['num_encoding_disp'] == 0:
                    self.class_log.info(
                        f"Added {self._spk_counters[elec_grp_id]['encoding']} "
                        f"spikes to encoding model of nTrode {elec_grp_id}"
                    )

        self._spk_counters[elec_grp_id]['total'] += 1
        if self._spk_counters[elec_grp_id]['total'] % self.p['num_total_disp'] == 0:
            self.class_log.info(
                f"Received {self._spk_counters[elec_grp_id]['total']} "
                f"total spikes from ntrode {elec_grp_id}"
            )

    def _process_pos(self, pos_msg):
        """Process a new position data point"""

        if pos_msg.timestamp <= self._pos_timestamp:
            self.class_log.warning(
                f"Duplicate or backwards timestamp. New timestamp: {pos_msg.timestamp}, "
                f"Most recent timestamp: {self._pos_timestamp}"
            )
            return

        self._pos_timestamp = pos_msg.timestamp

        if self._pos_counter % self.p['num_pos_points'] == 0:

            self._task_state = self._task_state_handler.get_task_state(
                self._pos_timestamp
            )

        #################################################################################################################
        # debugging, remove when done
        if pos_msg.x == 0:
            self.class_log.info(f"{pos_msg.timestamp} got a 0 xloc, {pos_msg.x}, {pos_msg.y}, {pos_msg.x2}, {pos_msg.y2}")
        ##################################################################################################################

        # calculate velocity using the midpoints
        xmid = (pos_msg.x + pos_msg.x2)/2
        ymid = (pos_msg.y + pos_msg.y2)/2
        # we don't care about x and y returned by compute_kinematics(),
        # as we are using the position mapper to get the appropriate
        # linear coordinates
        _1, _2, self._current_vel = self._kinestimator.compute_kinematics(
            xmid, ymid,
            smooth_x=self.p['smooth_x'],
            smooth_y=self.p['smooth_y'],
            smooth_speed=self.p['smooth_speed']
        )

        # map position to linear coordinates. None means the animal
        # couldn't be confidently placed (e.g. hex mode, lost tracking)
        # -- freeze at the last known position rather than propagate
        # None into code that assumes an int
        mapped_pos = self._pos_mapper.map_position(pos_msg)
        if mapped_pos is not None:
            self._current_pos = mapped_pos

        self._record_position(pos_msg.timestamp)

        #####################################################################################################
        # For testing, remove when finalized
        # self.write_record(
        #     binary_record.RecordIDs.POS_INFO, pos_msg.timestamp,
        #     pos_msg.x, pos_msg.y, pos_msg.x2, pos_msg.y2,
        #     pos_msg.segment, pos_msg.position, _1, _2,
        #     self._current_vel, self._current_pos
        # )
        # self.class_log.info(f"{pos_msg.timestamp/30000}, {pos_msg.x}, {pos_msg.y}, {pos_msg.y}, {pos_msg.y2}")
        #####################################################################################################

        update_occupancy = self._is_training_epoch()
        for encoder in self._encoders.values():
            encoder.update_position(self._current_pos, update_occupancy)
            if self._task_state != 1 and self._save_early:
                # we also save encoder models at the end of the program,
                # but we do it here as well just to be safe
                
                # rows in use. (this was min(_mark_idx, rows - 1), which kept one
                # row fewer than _mark_idx when the buffer was exactly full, so
                # the next add_new_mark() crashed. a model loaded from a file
                # saved with only its rows in use is always exactly full)
                n_spikes_currently_in_buffer = encoder._mark_idx
                print(f"n_spikes_current_in_buffer in encoder {encoder._trode}: {n_spikes_currently_in_buffer}")
                n_spikes_capacity_buffer = self._config['encoder']['bufsize']
                if n_spikes_currently_in_buffer > n_spikes_capacity_buffer:
                    encoder._chosen_indices = np.sort(np.random.choice(n_spikes_currently_in_buffer,n_spikes_currently_in_buffer,replace=False))
                    self.class_log.info(
                            f"in encoder {encoder._trode}: choosing {n_spikes_capacity_buffer} from {n_spikes_currently_in_buffer} spikes"
                            )
                    encoder._marks = copy.deepcopy(encoder._marks[encoder._chosen_indices])
                    encoder._positions = copy.deepcopy(encoder._positions[encoder._chosen_indices])
                    encoder._counts = copy.deepcopy(encoder._counts[encoder._chosen_indices])
                
                else:
                    encoder._chosen_indices = np.arange(encoder._mark_idx)
                
                encoder.save()
                # Compacting the buffers is only safe once we are done
                # collecting: it shrinks _marks to exactly _mark_idx rows
                # (zero for a trode with no spikes yet; add_new_mark() grows
                # them again for a spike that fired before the switch).
                # every array of the model, and the unmerged copy, is shrunk
                # together so they stay aligned
                if not self.p['train_all_task_states']:
                    n_keep = int(np.min([n_spikes_currently_in_buffer,n_spikes_capacity_buffer]))
                    encoder._marks = encoder._marks[:n_keep]
                    encoder._positions = encoder._positions[:n_keep]
                    encoder._counts = encoder._counts[:n_keep]
                    encoder._mark_idx = n_keep
                    encoder._raw_marks = encoder._raw_marks[:encoder._n_spikes]
                    encoder._raw_positions = encoder._raw_positions[:encoder._n_spikes]
                self.class_log.info(
                        f"encoder {encoder._trode} shape: {encoder._marks.shape}")

                self._save_early = False

        self._pos_counter += 1
        if self._pos_counter % self.p['num_pos_disp'] == 0:
            self.class_log.debug(f"Received {self._pos_counter} pos points")

    def _get_peak_amplitude_relevant_channels(self,
            features: np.ndarray,
            printbit: bool = False
    )-> np.ndarray:
        '''
        (DS)get the output of _get_peak_amplitude and make the values distance away from the peak zero
        features: np.ndarray, shape (n_spikes, n_channels) -- output of _get_peak_amplitude
        distance: int -- number of channels away from the peak to keep ; if 2, then 5 channels will be kept (peak and 2 on each side),
            default value of 2 was chosen based on quantification of decoding error study by DS.
        '''
        distance = self.p['use_channel_dist_from_max_amp']

        if printbit:
            print("features.shape", features.shape)

        
        modified_features = np.zeros(features.shape)
        if len(features.shape) == 1:
            max_abs_index = np.argmax(np.abs(features))
            start_index = max(0, max_abs_index - distance)
            end_index = min(features.shape[0], max_abs_index + (distance+1))
            modified_features[start_index:end_index] = features[start_index:end_index]

        elif len(features.shape) == 2:
            for i in range(features.shape[0]):
                max_abs_index = np.argmax(np.abs(features[i]))
                start_index = max(0, max_abs_index - distance)
                end_index = min(features.shape[1], max_abs_index + (distance+1))
                modified_features[i, start_index:end_index] = features[i, start_index:end_index]


        return modified_features


    def _compute_mark(self, datapoint):
        """Compute mark vector given an object containing spike waveform
        data"""

        # Make sure format is (n_channels, n_waveform_points)
        spike_data = np.atleast_2d(datapoint.data)

        # Determine the peak value for each channel
        channel_peaks = np.max(spike_data, axis=1)

        # Find out which of the channels has the highest peak value
        peak_channel_ind = np.argmax(channel_peaks)

        # Determine at which index the peak value was observed, given
        # the channel computed immediately above
        t_ind = np.argmax(spike_data[peak_channel_ind])

        # Find the spike waveform values for each channel (i.e. a vector)
        # given the index computed immediately above
        amp_mark = spike_data[:, t_ind]

        if amp_mark.shape[0] > 2*self.p['use_channel_dist_from_max_amp'] + 1: #if nTrode sortgroup is larger (2*dist + 1) -- where this is meaningful
            amp_mark = self._get_peak_amplitude_relevant_channels(features = amp_mark)
        return amp_mark

    def _is_training_epoch(self, velocity=None, task_state=None):
        """Whether or not the encoding model is in the training phase.
        Uses the current speed and task state unless given (e.g. the ones
        at a spike's own time)"""

        if velocity is None:
            velocity = self._current_vel
        if task_state is None:
            task_state = self._task_state

        res = (
            abs(velocity) >= self.p['vel_thresh'] and
            (task_state == 1 or self.p['train_all_task_states']) and
            not self.p['frozen_model']
        )
        return res

    def _record_timings(
        self, trode, timestamp,
        t_send_data, t_recv_data,
        t_start_kde, t_end_kde,
        t_start_enc_send, t_end_enc_send,
        kde_rows
    ):
        """Record timing information for a processed spike event"""

        ind = self._times_ind[trode]

        # expand timings array if necessary
        if ind == len(self._times[trode]):
            self._times[trode] = np.hstack((
                self._times[trode],
                np.zeros(
                    self.p['timings_bufsize'],
                    dtype=self._times[trode].dtype
                )
            ))

        # write to timings array
        tarr = self._times[trode]
        tarr[ind]['elec_grp_id'] = trode
        tarr[ind]['timestamp'] = timestamp
        tarr[ind]['t_send_data'] = t_send_data
        tarr[ind]['t_recv_data'] = t_recv_data
        tarr[ind]['t_start_kde'] = t_start_kde
        tarr[ind]['t_end_kde'] = t_end_kde
        tarr[ind]['t_start_enc_send'] = t_start_enc_send
        tarr[ind]['t_end_enc_send'] = t_end_enc_send
        tarr[ind]['kde_rows'] = kde_rows
        self._times_ind[trode] += 1

    def _save_timings(self):
        """Save timing data"""

        for trode in self._times:
            filename = os.path.join(
                self._config['files']['output_dir'],
                f"{self._config['files']['prefix']}_encoder_trode_{trode}." +
                f"{self._config['files']['timing_postfix']}.npz"
            )
            data = self._times[trode]
            ind = self._times_ind[trode]
            np.savez(filename, timings=data[:ind])
            self.class_log.info(
                f"Wrote timings file for trode {trode} to {filename}")

    def _set_up_trodes(self, trodes:List[int]):
        """Set up data objects given a list of electrode groups
        this object will be handling/managing"""

        for trode in trodes:
            self._spikes_interface.register_datatype_channel(trode)

            self._encoders[trode] = Encoder(
                self._config,
                trode,
                position.PositionBinStruct(
                    self._config['encoder']['position']['lower'],
                    self._config['encoder']['position']['upper'],
                    self._config['encoder']['position']['num_bins']
                )
            )

            self._spk_counters[trode] = {}
            self._spk_counters[trode]['total'] = 0
            self._spk_counters[trode]['encoding'] = 0

            try:
                dch = self._config['encoder']['dead_channels'][trode]
                self._dead_channels[trode] = dch
                self.class_log.info(f"Set dead channels for trode {trode}")
            except KeyError:
                pass

            for dec_rank, dec_trodes in self._config['decoder_assignment'].items():
                if trode in dec_trodes:
                    self._decoder_map[trode] = dec_rank

            self._init_timings(trode)

    def finalize(self):
        """Final method called before exiting the main data processing loop"""

        for key in self._spk_counters:
            self.class_log.info(
                f"Got {self._spk_counters[key]} spikes for electrode "
                f"group {key}"
            )
            self._encoders[key].save()
        self._save_timings()
        self._spikes_interface.deactivate()
        self._pos_interface.deactivate()
        self.stop_record_writing()

####################################################################################
# Processes
####################################################################################

class EncoderProcess(base.RealtimeProcess):
    """Top level object for encoder_process"""

    def __init__(
        self, comm, rank, config, spikes_interface, pos_interface, pos_mapper
    ):
        super().__init__(comm, rank, config)

        try:
            self._encoder_manager = EncoderManager(
                rank, config, EncoderMPISendInterface(comm, rank, config),
                spikes_interface, pos_interface, pos_mapper
            )
        except:
            self.class_log.exception("Exception in init!")

        self._mpi_recv = base.StandardMPIRecvInterface(
            comm, rank, config, messages.MPIMessageTag.COMMAND_MESSAGE,
            self._encoder_manager
        )

        self._gui_recv = base.StandardMPIRecvInterface(
            comm, rank, config, messages.MPIMessageTag.GUI_PARAMETERS,
            self._encoder_manager
        )

    def main_loop(self):
        """Main data processing loop"""

        try:
            self._encoder_manager.setup_mpi()
            while True:
                self._mpi_recv.receive()
                self._gui_recv.receive()
                self._encoder_manager.next_iter()

        except StopIteration as ex:
            self.class_log.info("Exiting normally")
        except Exception as e:
            self.class_log.exception(
                "Encoder process exception occurred!"
            )

        self._encoder_manager.finalize()
        self.class_log.info("Exited main loop")
