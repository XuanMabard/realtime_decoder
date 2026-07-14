import xml.etree.ElementTree as ET
import numpy as np
import os
import fcntl
import pathlib
import glob

from typing import List

"""Various useful utilities"""

def _extract_configuration(recfile):
    """Extracts the configuration section of a .rec file"""
    lines = []
    with open(recfile, 'rb') as f:
        fileline = ''
        while True:
            fileline = f.readline()
            lines.append(fileline)
            if b'</Configuration>' in fileline:
                break

    root = ET.fromstringlist(lines)
    return root

def get_xml_root(file):

    """Returns the root node of the configuration section
    (an XML tree) in a .trodesconf or .rec file"""
    p = pathlib.Path(file)
    suffix = p.suffix

    if suffix == '.trodesconf':
        xmltree = ET.parse(file)
        root = xmltree.getroot()
    elif suffix == '.rec':
        root = _extract_configuration(file)
    else:
        raise ValueError(f"Could not get xml tree from file {file}")

    return root

def nop():
    """No-op method, does nothing"""
    pass

def get_ntrode_inds(file, ntrode_ids):

    """Given a list of ntrode_ids (integers), determines
    which indices those ids map to"""
    # ntrode_ids should be a list of integers
    inds_to_extract = []

    root = get_xml_root(file)
    for ii, ntrode in enumerate(root.iter("SpikeNTrode")):
        ntid = int(ntrode.get("id"))
        if ntid in ntrode_ids:
            inds_to_extract.append(ii)

    return inds_to_extract

def get_network_address(file):
    """Determines the network address of the machine running a Trodes
    server instance"""
    root = get_xml_root(file)
    network_config = root.find("NetworkConfiguration")

    if network_config is None:
        raise ValueError("NetworkConfiguration section not defined")

    try:
        address = network_config.attrib["trodesHost"]
        port = network_config.attrib["trodesPort"]
    except KeyError:
        return None

    if "tcp://" in address:
        return address + ":" + port
    else:
        return "tcp://" + address + ":" + port

def estimate_new_stats(new_value, mean, M2, count):

    """Online method for estimating point estimates"""
    count += 1
    delta = (new_value - mean)
    mean += delta / count
    delta2 = (new_value - mean)
    M2 += (delta*delta2)
    return mean, M2, count

def normalize_to_probability(distribution):
    '''Ensure the distribution integrates to 1 so that it is a probability
    distribution
    '''
    return distribution / np.nansum(distribution)

def apply_no_anim_boundary(x_bins, arm_coor, image, fill=0):

    """Given an array denoting the boundaries of maze arms,
    and an array denoting valid bins, fills a 1D or 2D array
    with a specified value corresponding to bins where an
    animal is never supposed to be"""

    # note: mutates data!
    # from util.py script in offline decoder folder

    # calculate no-animal boundary
    arm_coor = np.array(arm_coor, dtype='float64')
    arm_coor[:,0] -= x_bins[1] - x_bins[0]
    bounds = np.vstack([[x_bins[-1], 0], arm_coor])
    bounds = np.roll(bounds, -1)

    boundary_ind = np.searchsorted(x_bins, bounds, side='right')
    #boundary_ind[:,1] -= 1

    for bounds in boundary_ind:
        if image.ndim == 1:
            image[bounds[0]:bounds[1]] = fill
        elif image.ndim == 2:
            image[bounds[0]:bounds[1], :] = fill
            image[:, bounds[0]:bounds[1]] = fill
    return image

def get_last_num(textfile):

    """Gets the last number of a text file. The text file
    is assumed to consist of one integer per line"""

    # assumes each line consists of one integer

    with open(textfile, 'rb') as f:
        fd = f.fileno()
        fcntl.fcntl(fd, fcntl.F_SETFL, os.O_NONBLOCK)

        try:
            f.seek(-2, os.SEEK_END)
            while f.read(1) != b'\n':
                f.seek(-2, os.SEEK_CUR)
        except: # file probably only has one line
            f.seek(0) # go back to start of file

        val = f.readline().decode().rstrip('\r\n')
        last_num = int(val)

    return last_num

def write_text_file(textfile, val):

    """Appends an integer value to a file as a new line"""

    with open(textfile, 'a') as f:

        f.write(str(val) + '\n')

def parse_trial_timeline(textfile, last_offset):

    """Parse newly appended lines of the trial-timeline text file written by
    the python observer.

    The file grows over the session; each line has the form
        "{trial_no} INITIAL CENTER POKE at {wall_time}"
        "{trial_no} SOUND CUE at {wall_time}"

    Reading starts at ``last_offset`` (a byte offset) and consumes only lines
    that are newline-terminated, leaving any partial trailing line for the next
    call. This guards against reading a line the observer is mid-write on.

    Returns ``(events, new_offset)`` where events is a list of
    ``(trial_no, event_type, wall_time)`` tuples with event_type in
    ``{'POKE', 'CUE'}``. A missing file yields ``([], last_offset)``."""

    events = []

    try:
        with open(textfile, 'rb') as f:
            fd = f.fileno()
            fcntl.fcntl(fd, fcntl.F_SETFL, os.O_NONBLOCK)

            f.seek(last_offset)
            data = f.read()
    except FileNotFoundError:
        return events, last_offset

    # only consume up to the last newline; keep any partial trailing line
    nl = data.rfind(b'\n')
    if nl == -1:
        return events, last_offset

    consumed = data[:nl + 1]
    new_offset = last_offset + len(consumed)

    for raw in consumed.decode(errors='ignore').splitlines():
        line = raw.strip()
        if not line:
            continue

        tokens = line.split()
        try:
            trial_no = int(tokens[0])
        except (IndexError, ValueError):
            continue

        if 'INITIAL CENTER POKE' in line:
            event_type = 'POKE'
        elif 'SOUND CUE' in line:
            event_type = 'CUE'
        else:
            continue

        # wall_time follows the final "at " token; optional / best-effort
        wall_time = None
        if ' at ' in line:
            try:
                wall_time = float(line.rsplit(' at ', 1)[1].split()[0])
            except (IndexError, ValueError):
                wall_time = None

        events.append((trial_no, event_type, wall_time))

    return events, new_offset

def read_float_vector(textfile):

    """Reads a text file of one float per line into a list of floats. A
    missing or empty file yields an empty list. Used to seed the empirical
    budget distribution from a previous session."""

    values = []

    try:
        with open(textfile, 'r') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    values.append(float(line))
                except ValueError:
                    continue
    except FileNotFoundError:
        return values

    return values

def get_switch_time(taskfile):

    """Given a state script log file, finds out the time when
    the task switched to task 2"""

    with open(taskfile, 'r') as f:
        lines = f.readlines()

    t = []
    for line in lines:
        # not interested in comment lines
        if 'DECODER_TASK2' in line and line[0] != '#':
            t.append(int(line.split(' ')[0]))

    if len(t) != 1:
        raise ValueError(
            f"Switch times are {t}, expected exactly only one switch time"
        )

    # the return value is in milliseconds NOT sample number
    return t[0]

def find_unique_file(pattern, desc):

    """Searches for a file matching a given pattern and ensures
    it is unique; otherwise this method raise an error"""

    files = glob.glob(pattern)

    if len(files) != 1:
        raise ValueError(
            f"Expected exactly one {desc} file but got {files}"
        )

    return files[0]

