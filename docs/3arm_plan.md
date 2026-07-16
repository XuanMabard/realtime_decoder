# 3-Arm Version Plan

Working notes for updating the realtime decoder to the 3-arm task version.
This file is the source of truth for design decisions — updated as we go.

## Overview / Design (initial plan, 2026-07-13)

1. **Textfile instead of socket** for communication with the Python observer,
   so the system can be tested with playback files.
2. **Timer inside the realtime system** (`stimulation.py`).
3. Timer **starts** when input arrives from the Python observer through the text file.
4. **Poke & sound cue logging**: timer only elapses once the observer reports
   the rat poked the center port. Use current time + subtraction to get time
   spent within the proximity. When the observer sends the go cue, the timer
   stops and logs for that trial.
5. The same timer (sampled from the distribution in step 3) sends a **shortcut
   message to StateScript** — if no sound-cue signal is received back, resend
   after 3 s.
6. If **RR detected**: `trigger(30)`, with a debounce (don't send another for
   ~0.5 s — reuse the already-implemented logic).
7. (outside of this repo) Statescript runs all the time, but only **active when target location == 3**.
8. Needs a **textfile that initializes and reports sound cue** (read the last
   line with timestamp).

## Decisions

_(Decisions get logged here as we make them, with rationale.)_

- 2026-07-13 — Use textfile rather than socket for observer → decoder
  communication. **Why:** enables testing with playback files.
- 2026-07-13 — Timer delay is **sampled from previously recorded RRs** (an
  empirical distribution), not a parametric distribution.
- 2026-07-13 — Textfile is `config/task_trial_timeline.txt`. The observer
  appends lines of the form `"{TRIAL_NO} INITIAL CENTER POKE at {CURRENT_TIME}"`
  and `"{TRIAL_NO} SOUND CUE at {CURRENT_TIME}"`. `stimulation.py` reads the
  last line + timestamp.
- 2026-07-13 — **[SUPERSEDED]** Originally: no target-location gating in the
  decoder. **Revised:** the decoder reads `target_location.txt` and only sends
  the arm-3 cue (scm 30) when `target_location == 3`; StateScript `function 30`
  also gates on `== 3`. **Why:** explicit, avoids confusion. Arms 1/2 keep using
  the existing replay path (scm 14/6).
- 2026-07-13 — StateScript shortcut resend: **retry forever every 3 s until a
  SOUND CUE line is read** (no max retry count).
- 2026-07-13 — **What the empirical distribution is made of:** for each trial,
  the value stored is the time from INITIAL CENTER POKE to SOUND CUE **counting
  only ticks where `self._is_center_well_proximate == True`** (proximate-time
  budget). Stored as a vector, one entry appended per completed trial.
- 2026-07-13 — **Distribution seeding:** a config file provides a starting
  vector from a previous session, so trial 1 has values to sample from before
  the current session has accumulated any.
- 2026-07-13 — Timer delay is **sampled fresh per trial** from this vector.
- 2026-07-13 — `CURRENT_TIME` in the textfile uses **wall-clock**
  (`time.time()`), written by the external observer process.
- 2026-07-13 — **Add a trial-number counter** in the decoder (none exists today).

### Trial lifecycle (per trial)

1. Observer appends `"{TRIAL_NO} INITIAL CENTER POKE at {TIME}"` → decoder
   starts the trial and samples a proximate-time budget from the vector.
2. Each tick, accumulate elapsed time **only while
   `self._is_center_well_proximate == True`**.
3. When accumulated proximate time ≥ sampled budget → send the shortcut message
   to trigger the sound cue. If no `SOUND CUE` line appears within 3 s → resend,
   forever until it does.
4. Observer appends `"{TRIAL_NO} SOUND CUE at {TIME}"` → timer stops; the
   **actual accumulated proximate duration** is appended to the vector.
5. RR (replay) detection for arms 1/2 is UNCHANGED — the decoder still sends
   scm 14/6 via the existing `_handle_replay` path. Arm 3's cue comes ONLY from
   the timer above (scm 30). The decoder no longer sends scm 38/39.

## Final implemented design (2026-07-13)

**Components / versions in use:**
- StateScript: `timer_instructive_three_arm_three_0708_DS03.sc` — `function 30`
  is a clean external arm-3 shortcut (no internal timer). One edit: gate changed
  from `target_location == 3 || 4` to `== 3` only.
- Observer: `..._3_arm_version_DS09.py` — built fresh from the known-good
  `..._three_arms_DS08_.py` because DS04 caused **false trial starts** (DS04 had
  rewired trial control: `NEXT_TRIAL`→`NEW TRIAL` for `startContentTrial`,
  `trigger(16)`→`(8)`, and a `content_trial_time` gating change). DS09 keeps
  DS08_'s trial control + `content_trial_time` logic/values intact and only adds:
  arm-3 support (counters/orders/goals + `target_location_choices=[1,2,3]`,
  3-arm `generate_list`, default `target_location_vec = vec3` so arm 3 is
  targeted), and **observe-only** `NEW TRIAL` / `start content trial of TARGET
  ARM` handlers that write the timeline file + the `target_location` integer
  (they do NOT call `startContentTrial`). Pairs with the DS03 statescript.
- Decoder: `realtime_decoder/stimulation.py` (`_init_trial_timer`,
  `_update_trial_timer`, `_start_new_trial`, `_close_trial`) + parsers in
  `realtime_decoder/utils.py` (`parse_trial_timeline`, `read_float_vector`).
- Config: `config/RS64_nTrode8_three_arm.yml` (`trodes.task_trial_timeline`,
  `trodes.target_location_file`, `trodes.trial_budget_seed_file`,
  `stimulation.trial_timer`).

**Shortcut-message numbers:** 14 = arm 1, 6 = arm 2 (RR/replay, unchanged);
30 = arm-3 go cue (the decoder timer). 38/39 removed from the decoder.

**Clock:** the observer writes wall-clock (`time.time()`) into the textfile, but
the decoder's internal stopwatch and 3 s resend use **neural sample timestamps**
(`msg[0]['timestamp']` ÷ sampling rate) — playback-safe, consistent with the
existing elapsed-time code. Only POKE/CUE *events* are read from the file.

**Files (all under `config/`):** `task_trial_timeline.txt` (observer→decoder,
POKE/CUE lines), `target_location.txt` (observer→decoder, one int per line),
`prior_budgets.txt` (optional seed, one float per line).

**Trial number:** observer uses `len(ts2_center_initial_poke_timestamp)`; the
decoder matches POKE/CUE by that number and closes a stale trial when a new,
higher-numbered POKE arrives.

**Verification status:** parsers + the observer↔decoder format contract are
verified in a dev shell; end-to-end (timer/observer/statescript) needs Trodes
playback — see the `CLAUDE.md` runtime constraint. A standalone appender script
is provided for that test.

## Codebase Anchors (from exploration, 2026-07-13)

- **Main object:** `TwoArmTrodesStimDecider` in `realtime_decoder/stimulation.py:42`
  (created at `runscript.py:174`). Has a hard-coded 2-arm guard at
  `stimulation.py:56-60` that a 3-arm version must relax.
- **NOT a self-driven loop — it's message-driven.** `handle_message`
  (`stimulation.py:214`) dispatches incoming MPI messages. The real `while True`
  loop lives in `main_process.py:457`. **Implication:** the "timer" can't
  `sleep()`; it must be *checked* on each message tick. Best hook:
  `_update_velocity_position` (`stimulation.py:456-469`), the per-position-frame
  callback that already re-polls task state every N frames (`:466-469`).
- **Send shortcut to StateScript:** `self._trodes_client.send_statescript_shortcut_message(N)`
  (`trodesnet.py:187`); `N` = `function N` in the `.sc`. Existing: 14 (arm1),
  6 (arm2), 22 (ripple, currently commented out at `stimulation.py:385`).
  **`function 30` does NOT yet exist** in `trodes_statescripts/timer_instructive_three_arm_0626.sc`
  — must be added there.
- **RR debounce / lockout:** defined at `stimulation.py:1462-1466`
  (`_replay_event_ls`, in samples), enforced at `:851-855`, reset at `:970`.
  Duration is config `stimulation.replay.event_lockout` (e.g. 0.2s). Reuse this
  pattern for any new cadence limit.
- **Textfile polling primitive:** `utils.get_last_num(textfile)`
  (`utils.py:125-146`) reads the last **integer** line, non-blocking. Companion
  writer `utils.write_text_file` (`utils.py:148`). Task-state polling
  (`taskstate.py:20,49`) is the model to copy. NOTE: `get_last_num` only parses
  integers — our `"{TRIAL_NO} ... at {CURRENT_TIME}"` lines need a **new parser**.
- **Timestamps / elapsed time:** neural-sample timestamps on every message
  (`msg[0]['bin_timestamp_l']`, `['timestamp']`) → seconds via
  `/ config['sampling_rate']['spikes']`. Existing elapsed-time example at
  `stimulation.py:978-984`. Wall-clock `time.time()` also available.
- **RR log on disk:** every reward event written as `STIM_MESSAGE` binary record
  (schema `stimulation.py:96-107`, written `:1049-1073`). This is where prior
  RRs live — but it's a packed binary record, not a plain readable list.
- **No trial-number counter exists yet** — the feature must introduce its own.

## Open Questions

- [x] The vector **keeps growing** across the session with each completed
      trial's actual proximate duration (seeded from config, then appended to
      live). Accept possible drift.
- [x] Distribution source → in-memory vector of per-trial proximate durations,
      seeded from a config file. (Not the binary `STIM_MESSAGE` records.)
- [x] Sample timing → fresh per trial.
- [x] Clock → wall-clock `time.time()`.
- [x] Need a new line parser for `"{TRIAL_NO} EVENT at {TIME}"` (get_last_num is
      integer-only).
## 2-arm config (preserving the 2-arm version)

`config/RS64_nTrode8_two_arm.yml` runs the 2-arm version on the RS64 rig. It is
the 3-arm config with: `stimulation.three_arm: false` (the master flag — turns
off ALL 3-arm decoder behavior: timer, arm-3 detection/scm 35, debounce, extra
prints; `_find_replay` uses the 2-arm branch), `trial_timer.enabled: false`, the
3-arm timer file paths removed (decoder reads only `taskstate.txt`),
`encoder.position` set to the 2-arm track geometry (`arm_ids [0,1,2]`,
`arm_coords [[0,8],[13,24],[29,40]]`, 41 bins — matches SC85 and the RS64 3-arm
track minus arm3), and `event_lockout` back to 0.2. All RS64 hardware settings
are unchanged. The 2-arm observer only needs to write `taskstate.txt`.

## Change Log — later note

- **2026-07-15** — The `[proximity] ENTERED/LEFT` transition print now shows in
  **both** 2-arm and 3-arm modes (ungated from `three_arm`). The timer /
  `[empirical dist]` / `[trial timer]` prints remain 3-arm-only (they live inside
  the timer path, which only runs when `three_arm`).

## Change Log

- **2026-07-13** — File created with initial 8-point plan from Donghoon.
- **2026-07-13** — Resolved 4 open questions (distribution source, textfile
  format/name, target-location gating, retry policy); moved to Decisions.
  Raised 3 new follow-up questions.
- **2026-07-13** — Corrected during planning/build: RR stays scm 14/6 (30 is the
  timer's arm-3 cue, not RR); added decoder-side `target_location == 3` gate
  (reversing "no gating"); StateScript base = DS03 (gate → `== 3`); observer
  base = DS04; removed decoder scm 38/39; internal clock = neural timestamps.
  Implemented across `utils.py`, `stimulation.py`, the config, and the DS04
  observer. See "Final implemented design".
- **2026-07-14** — Observer switched from DS04 to **DS09**: DS04 produced false
  trial starts (its trial-control rewiring). DS09 = the working DS08_ base +
  arm-3 support + arm-3 target generation (`vec3`) + observe-only timeline/target
  file writes; DS08_'s `content_trial_time` logic/values kept. Added diagnostic
  prints to the decoder (`[proximity]`, `[trial timer]`, `[empirical dist]`),
  gated on `trial_timer.enabled`. StateScript DS03 `function 30` gate set to
  `== 3`. Pairing: DS09 observer + DS03 statescript.
- **2026-07-14** — Started a new batch of 3-arm changes, gated behind a master
  `stimulation.three_arm` flag (absent/false → 2-arm preserved unchanged).
  Batch 1: `three_arm` flag added; empirical-dist print now shows
  mean/var/min/max + the full vector; **timer-triggered** trial durations are
  no longer appended to the empirical vector (only natural-cue trials, to avoid
  self-bias); arm-3 timer cue print made salient (banner); proximity prints
  gated on `three_arm`. Still pending: arm-3 detection (scm 35) + arm1/2
  suppression, 2 s RR↔timer debounce, observer `target_arm_vec` fix, and saving
  scm 30 + empirical distribution to the rec.
- **2026-07-15** — Added a salient banner print when a target==3 trial's timer
  is armed. Observer (DS09): writes a `# EPOCH START at <wall>` header to
  `task_trial_timeline.txt` and `target_location.txt` at observer load (safe:
  the timeline parser skips `#` lines, the target reader uses only the last
  integer line); `target_arm_vec` now appends 3 on `TARGET ARM3`. Remaining
  pending: arm-3 detection (scm 35) + arm1/2 suppression, 2 s RR↔timer debounce,
  saving scm 30 + empirical distribution to the rec.
- **2026-07-15** — Arm-3 detection (decoder side): `_compute_region_probs`
  computes arm3's tip prob (last `within_angle_range` bins of `arm_coords[3]`,
  i.e. bins 51–56 of arm3's 12) when `three_arm`; `region_ps_buff` col 3 filled.
  The single-decoder `_find_replay` branch (RS64 uses 1 decoder) gains an arm-3
  candidate: `tip>0.25 and center/arm1/arm2 whole-arm <other_thresh` →
  `_handle_replay(3)` → **scm 35** (detection marker only, no reward/cue — the
  arm-3 go cue still comes from the timer's scm 30). Arm1/arm2 suppression now
  also requires arm3 quiet. All gated on `three_arm`; the 2-arm branch is
  byte-identical. Still pending: **statescript `function 35`** (disp-only, in a
  new DS04), 2 s RR↔timer debounce, and saving scm 30 + empirical dist to rec.
  NOTE: arm-3 detection was added only to the single-decoder branch (RS64); the
  2-decoder branch would need the same if ever used for a 3-arm task.
- **2026-07-15** — Statescript: created
  `timer_instructive_three_arm_three_0708_DS03_scm35.sc` (= our DS03 + a
  disp-only `function 35` → `disp('ARM3 REMOTE REPRESENTATION DETECTED')`).
  Chose a new filename rather than overwriting the old DS04 lineage. **Pairing
  now: DS09 observer + `..._0708_DS03_scm35.sc` statescript.** This completes the
  arm-3 detection item. Remaining: 2 s RR↔timer debounce; save scm 30 +
  empirical distribution to the rec.
- **2026-07-15** — RR↔timer debounce, unified with the existing replay lockout:
  raised `stimulation.replay.event_lockout` 0.2 → 0.5 s, and the arm-3 timer cue
  (scm 30, send + resend) is now held off within one `event_lockout` of the last
  RR detection, reusing the replay detector's own `_replay_event_ts` /
  `_replay_event_ls` (no separate variable or config key). Since every RR
  candidate (>0.25) resets `_replay_event_ts` in `_handle_replay`, the timer
  waits ≥ one lockout after any RR before firing. NOTE: raising `event_lockout`
  to 0.5 s also lengthens the minimum gap between arm1/arm2 replay detections
  (reward cadence) in RS64. Only remaining item: save scm 30 + empirical
  distribution to the rec.
- **2026-07-15** — Added a big `!!!!! ... HELD ... !!!!!` banner: when the arm-3
  cue (scm 30) is due (budget reached, target 3) but held off by the RR
  debounce, print a prominent banner — throttled to once per RR (a *new* RR that
  extends the hold re-prints; the same RR doesn't spam). Clarified mechanism: a
  debounce-blocked cue is retried every tick and fires as soon as the lockout
  clears (~0.5 s after the last RR); the 3 s resend only applies *after* scm 30
  was sent without a SOUND CUE ack.
