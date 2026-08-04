# Make Campaign the customer-visible activity authority

Status: accepted

Admin-authored Campaigns are the only source of customer-visible activities. Kiosk banner selection may read the compatibility `promotion_records` projection for its response shape, but it must first require a matching Campaign in `active` or `scheduled` status. An orphaned or independently active promotion projection is ignored. Existing orphaned test projections were removed from the local pilot database.

The system temporarily kept two representations: versioned Campaigns for the Admin lifecycle and legacy promotion records for older pricing and banner paths. The legacy path checked its own `active` flag and schedule, so records left behind after a Campaign was ended—or records created by old test tooling—could remain visible while the Admin Campaign list was empty. That split violated the domain rule that publication is the moment an activity becomes visible to customers.

We considered making Admin list legacy promotion records as well. That would make the UI appear complete, but it would turn an undocumented projection into an authoring surface with no Campaign version or lifecycle history. We instead keep the projection for compatibility consumers and make the customer-facing read fail closed when the authoritative Campaign is absent or not on air.

The consequence is that any future migration or import that creates a promotion projection must create the corresponding Campaign first and publish it through the Campaign lifecycle. Ending, pausing, or archiving a Campaign now makes its projection ineligible for Kiosk display even if stale payload fields remain.
