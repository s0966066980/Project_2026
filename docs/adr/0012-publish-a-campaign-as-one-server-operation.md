# Publish a campaign as one server operation

Status: accepted

Campaign Publication is a single request, `POST /api/v1/campaigns/publish`, that the server completes end to end: it validates Campaign Content, stores it as a new version, moves the Campaign through review, and lands it on scheduled or active depending on whether its start time is still ahead in store time. The request carries the authored payload, and — when the Campaign already exists — its identifier and the version the operator's form was based on. The generic transition endpoint remains for the lifecycle actions an operator takes from the campaign list: pause, resume, end, and archive.

Admin previously drove publication from the browser as three ordered requests — save the draft, move to review, then move to scheduled or active — and decided between scheduled and active from the browser clock. That sequence had no atomicity and no shared clock. Any interruption after the first request left the Campaign part-published while the wizard still held the version it started with, so the next attempt failed optimistic concurrency and reported a bare conflict. The same stale snapshot was reused after a successful publication, which made pressing the button a second time fail as well. A device with a skewed clock could also put a future Campaign on air immediately.

We considered keeping the sequence in the browser and re-synchronising the held version after every step. That is a smaller change, but publication stays non-atomic: a Campaign can still be observed in review by the kiosk projection and by other managers, and the store-time decision stays on the client. We chose the server-side operation because publication is the moment a Campaign becomes visible to customers, and that moment should have one owner, one clock, and one failure boundary.

Optimistic concurrency stays strict rather than being relaxed to make retries easier. A version mismatch fails closed and Admin offers the operator an explicit reload, keeping the in-progress form on the device first. Silently retrying against the newest version would let one manager's publication overwrite another's edit without either of them seeing it.
