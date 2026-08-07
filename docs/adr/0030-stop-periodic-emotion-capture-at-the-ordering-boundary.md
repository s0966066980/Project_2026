# Stop periodic emotion capture at the ordering boundary

Status: accepted

Periodic Ordering emotion capture begins only after the customer enters the menu and ends when the order is confirmed, ordering is cancelled, the ordering session reaches its inactivity timeout, or the Kiosk resets. Reaching this boundary immediately prevents another capture from starting and discards any media whose capture has not completed.

Inference already submitted before the boundary may finish and persist its result under the originating ordering session because its evidence was collected while ordering was active. Completion never starts another clip. This preserves one-at-a-time inference, avoids retaining partial media, and gives every accepted pre-boundary observation a deterministic outcome.
