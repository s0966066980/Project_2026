# Use device-authenticated Admin access without Manager Mode

Admin runs on a store device and grants every scoped management capability after that device presents a valid Kiosk device credential. The password-authenticated Manager Mode, limited Staff Mode, unlock/lock controls, and idle manager lock are removed; an anonymous browser without the device credential remains unauthorised. This deliberately makes protection of the device credential the sole Admin access boundary in exchange for a direct, failure-resistant Admin experience.
