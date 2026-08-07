# Record submitted emotion inference failures safely

Status: accepted

An emotion inference that was submitted but ends in timeout, unavailable runtime, or unreadable media creates one Emotion Analysis Record rather than disappearing from history. The shared minimal schema represents failure with Undetermined emotion and intensity, Not Observed facial and vocal evidence, and an overall description selected from safe operator-facing failure reasons.

Failure descriptions never contain raw exceptions, filesystem paths, request bodies, credentials, or internal network details. No record is created when analysis was disabled, was explicitly skipped before submission, or an incomplete capture was discarded at the Ordering Emotion Capture Boundary. This distinguishes attempted failure from analysis that never ran without adding a separate historical schema.
