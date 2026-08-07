# Confine non-core proposals to new isolated modules

Status: accepted

The Project Change Proposal workflow may add documents only under `docs/proposals/` and features only as new Non-Core Extension Modules under `extensions/<name>/`. An extension owns a small interface, configuration contract, error modes, and tests and can be verified without editing or running the current production system.

Proposals cannot modify existing files or depend on UI API internals, business database tables, Kiosk state, authentication, ordering, payment, migrations, runtime configuration, Docker integration, or R1-Omni internals. Integrating a proposed document or extension into Admin, Docker, or any production business flow is a separately authorized core change outside the Project Core Brain.
