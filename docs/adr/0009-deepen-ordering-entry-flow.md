# Deepen Ordering Entry Flow

Status: accepted

Kiosk entry will be coordinated by a durable state machine with an explicit lifecycle: Startup, Loading Entry Policy, Choosing Mode, Member Lookup or Registration, Initializing Menu, and Menu Ready, with recoverable degraded and failure states. UI views render state and submit commands; DOM visibility, callback continuations, page-load session IDs, and process-local flags are not business state.

Pressing Start creates a stable, store- and device-scoped `entry_flow_id`. Each Kiosk device may have at most one active Entry Flow, and retries or reloads resume it. A dedicated, immutable Ordering Entry Policy is captured by version for the flow. Policy loading may delay the choice for at most three seconds; failure uses the safe default that offers member and guest entry, while only a successfully loaded policy that explicitly disables membership skips the choice. Ordinary policy updates affect new flows only; emergency store availability is a separate gate.

An Ordering Session is created and bound idempotently only after the customer chooses guest entry or completes member identification or registration. Member Found, Not Found, and Service Unavailable are distinct results. Not Found offers registration, guest entry, or phone correction and never opens registration automatically. Registration requires explicit acceptance of necessary terms, while order-history and personalization consent are independent, optional, and unchecked by default.

Switching to guest entry clears unsubmitted member PII and consent drafts and creates no member association. Durable flow records store only opaque references, typed outcomes, versions, timestamps, and sanitized reasons. Sensitive form drafts remain in Kiosk memory and are cleared when the flow is left or times out.

Menu initialization succeeds when an Ordering Session, store-scoped available Menu snapshot, and server-side Cart are ready. Microphone, camera, Voice, Emotion, recommendations, promotion banners, realtime, and passive listening start only after Menu Ready and may degrade independently. Retry after Menu Initialization Failed resumes the same session; returning to mode selection keeps the same incomplete flow and session, may reuse a verified member identity, and may detach it for guest entry before Menu Ready.

Ordering Entry Flow owns lifecycle, legal transitions, resume, timeout, terminal outcome, policy and result references, and session binding. Member, Consent, Ordering Policy, Menu, Cart, Availability, and media capabilities retain independent interfaces and rules. A pure state machine produces effects for injected API, clock, navigation, secure-input, and menu-bootstrap adapters; asynchronous results must match both `entry_flow_id` and phase revision.

## Consequences

- Entry Flow and Ordering Session are independent durable records with store/device scope, active-flow uniqueness, phase revision, and session binding. Production uses Postgres; Local Development Runtime and tests use SQLite with equivalent constraints.
- Idle timeout marks the flow Abandoned, closes an unconfirmed Cart, clears sensitive Kiosk memory, and returns to Startup. Completed flows follow Ordering Session audit retention; failed and abandoned flows use shorter retention.
- State-machine scenario tests replace tests coupled to overlay classes, callback continuations, global flags, fixed timers, or page-load session IDs. SQLite integration tests cover concurrency and resume, DOM tests cover state-to-view mapping, and a small browser smoke suite covers member, guest, and menu-failure recovery.
