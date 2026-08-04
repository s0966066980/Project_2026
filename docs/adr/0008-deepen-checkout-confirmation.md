# Deepen Checkout Confirmation

Status: accepted

Checkout will use two explicit operations. Prepare Checkout reads an authoritative server-side Cart revision and creates an immutable, store-scoped Checkout Quote containing the cart snapshot, prices, promotions, fees, total, and validity. Confirm Checkout accepts only the Quote identity and an idempotency key; the Kiosk displays the Quote without recalculating commercial values or resubmitting client-priced cart contents.

A Cart module owns server-side line-item editing and its monotonically increasing revision. Each ordering session has at most one active Quote: repeated preparation for the same revision returns it, a new Quote supersedes the old one, and a cart mutation makes it stale. An unexpired Quote keeps its quoted price even if pricing rules later change, but it does not reserve inventory. Confirmation revalidates all fulfillment constraints and either creates the complete Order or creates no Order and returns structured unavailable items.

The confirmation transaction atomically consumes the Quote, creates the Order and immutable order lines and pricing snapshot, closes the ordering session to further cart mutation, and writes an OrderConfirmed outbox event. Checkout Confirmation owns the Quote lifecycle, Confirmation Attempts, idempotency decisions, outcome lookup, and this atomic conversion. Cart editing, Payment lifecycle, later Order fulfillment, recommendation attribution, member updates, emotion outcomes, telemetry, and cleanup keep independent interfaces and rules.

Order Confirmation proves only that the Order was accepted. It never implies Payment success. Manual payment produces Payment Pending until the Payment module records an explicit result. Post-commit consumers initiate payment and process analytics, profile, attribution, archival, and other side effects; consumer failure cannot reverse or obscure an already confirmed Order.

Order creation is unique by both Quote and idempotency key. Repeating the same key and Quote or presenting a consumed Quote returns the existing Order; reusing a key for a different Quote is a conflict. A transport timeout leaves the Kiosk in Confirmation Outcome Unknown with the original Quote and key. It queries or retries using that identity until it finds the Order or receives an authoritative rejection, and never assumes uncertainty means failure.

## Consequences

- Checkout returns typed results such as confirmed, quote expired, quote stale, items unavailable, idempotency conflict, and confirmation rejected. Only authoritative rejection guarantees that no Order exists.
- Checkout Quotes, Confirmation Attempts, Orders, immutable order lines, and outbox events are independent store-scoped durable records. Production uses Postgres; Local Development Runtime and tests use SQLite with equivalent constraints and transaction semantics.
- Consumed Quotes and Confirmation Attempts remain linked to Orders for audit. Unconsumed expired, stale, or superseded Quotes follow a short retention policy without shortening the idempotency lookup window.
- Interface scenario tests replace tests coupled to `process_checkout` arguments, session-log side effects, local Kiosk totals, or parsed error strings. Route tests remain thin, and a small browser smoke suite covers the customer flow.
