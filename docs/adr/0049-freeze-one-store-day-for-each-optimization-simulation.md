# Freeze one store day for each optimization simulation

Status: accepted

Every Daily Optimization Simulation explicitly selects one store and one calendar date interpreted in that store's timezone. A completed historical date covers local 00:00 through 23:59:59. The current local date is also selectable, but the Daily Evidence Snapshot and resulting report are marked partial and record the run-start cutoff time.

The snapshot freezes its evidence identifiers when the run starts. Interactions arriving after the cutoff never enter an in-flight analysis or mutate its report. An administrator must explicitly rerun the date to include later evidence, producing a new immutable snapshot and report rather than updating the earlier result in place.
