# realtime_decoder — project notes for Claude

## Design docs

- `docs/3arm_plan.md` is the source of truth for the 3-arm task design.
  Whenever we make a design decision about the 3-arm version (or change an
  earlier one), update that file: add the decision + rationale under
  **Decisions**, resolve/add items under **Open Questions**, and append a
  dated entry to the **Change Log**.

## Runtime constraint: Trodes coupling

The StateScript (`.sc`) files, the pythonobserver scripts, and the realtime
decoder all run *inside* the Trodes data acquisition system: the observer is
driven by Trodes callback lines and replies via `SCQTMESSAGE:` stdout, the
statescript runs on the ECU, and the decoder rides on MPI + live/playback Trodes
data. **None of these can be meaningfully executed or verified standalone.**
Only run/verify Trodes-independent pieces directly (pure functions like the
`utils.py` parsers, syntax/compile checks). For observer/statescript/decoder
behavior, keep edits minimal and surgical (mirror existing patterns) and hand
off runtime verification to Trodes playback — e.g. a standalone appender that
drives the input textfiles during playback. Don't claim end-to-end verification
that requires Trodes.

## Working style

Durable knowledge goes in the repo (this file, `docs/`), not a hidden store.
Donghoon is deliberately building the skill of working with coding agents, so:
surface assumptions and what's uncertain, explain non-obvious logic back rather
than expecting a full line-by-line read, and end substantive changes with a
short "check these N things" summary (highest-leverage spots + a verification
step).
