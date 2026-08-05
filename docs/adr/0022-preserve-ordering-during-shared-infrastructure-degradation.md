# Preserve Ordering During Shared Infrastructure Degradation

Status: accepted

Redis is required to admit a Pilot Release Candidate, but a temporary Redis outage does not stop menu browsing, cart operations, or order confirmation. Cache operations may miss and rate limiting may fall back to bounded process-local protection, while any operation that requires a distributed lock fails closed; readiness reports Shared Infrastructure Degradation and operators are alerted. Failing the entire Kiosk was rejected because Redis does not own authoritative order data, while silently bypassing lock-dependent protections was rejected because it could violate transaction and publication invariants.
