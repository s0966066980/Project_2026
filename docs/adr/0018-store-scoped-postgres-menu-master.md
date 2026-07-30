# Store-scoped Postgres menu master

Status: accepted

The sellable product catalog is a per-store master in PostgreSQL, not a global `menu.json` file. Each [[Store Menu Item]] belongs to one commercial scope (`tenant_id` + `store_id`), carries name, category label, price, description, and image reference, and is read by kiosk and checkout only through that scope. Catalog Availability (normal / low stock / sold out / disabled and service periods) remains an operational overlay on those items—editable in the same Admin product workbench, but not the same thing as authoring or retiring an item.

We rejected keeping JSON as the runtime source of truth and rejected a hybrid “Postgres overrides + JSON fallback.” The rest of the pilot path already treats JSON as non-runtime; a global file cannot express store-scoped price and image edits without lying to the second store. `menu.json` remains a seed only: bootstrap imports it into a store that has zero items, and never overwrites a store that already has catalog rows.

Identity is system-assigned and immutable after create (seeded ids from the JSON import are preserved). “Delete” is [[Menu Item Retirement]]—hidden from sellable surfaces, recoverable by managers—not a hard purge, so order history and push-copy references stay addressable. Uploaded images are normalized server-side into object storage; external http(s) URLs remain valid for import compatibility. Staff Mode may change Catalog Availability only; Manager Mode alone authors items, uploads images, and retires or restores.

**Consequences:** every former `menu_repository.get_menu()` runtime caller must become scope-aware; checkout and cart paths already re-price from the current master and must refuse retired or unavailable items; Admin’s availability page becomes the product workbench (per-item catalog saves, batch availability save). A one-time schema migration and empty-store seed path are required before local pilot can drop JSON as the live menu.
