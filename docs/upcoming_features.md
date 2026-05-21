# Upcoming Features

## Wake Planner: Bio-Aware Wake

Planned, not implemented yet.

- Optional `bio_state` entity input, typically from the `benni_context` module.
- If `bio_state` becomes `awake` before today's wake window, mark the current wake as already handled and avoid firing a later wake event.
- Track `sleep` transitions as `last_sleep_started` for diagnostics and future planning.
- Configurable sleep bounds:
  - minimum sleep, for example 6 hours
  - target/maximum sleep, for example 8 hours
- On free days, holidays, or days without a fixed wake requirement, respect the sleep target instead of forcing the normal profile.
- Optional fallback after maximum sleep:
  - emit event only
  - call `bennis_toolbox.benni_context_mark_awake`
  - no action

Design constraint: Wake Planner should consume Bio State and emit decisions/events. It should not own the Bio State state machine directly; `benni_context` remains the source of truth.
