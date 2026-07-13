# Pilot Security / Privacy Checklist

Each item requires an owner and evidence link; unchecked means pilot Gate FAIL.

- [ ] Secret only from environment/Secret Manager; scan Git and artifacts.
- [ ] CORS allowlist, HTTPS/TLS and security headers verified on deployed origin.
- [ ] Admin Auth/RBAC and per-device identity enabled; legacy Token flags disabled or time-bounded with owner.
- [ ] PII encrypted/masked; log redaction and no raw model-sensitive input verified.
- [ ] Backup / Restore exercise completed in isolation with checksum evidence.
- [ ] Audit records, tenant/store scope and deletion/anonymization path sampled.
- [ ] Rate Limit behavior and multi-instance limitation documented.
- [ ] Upload/path/URL size, type, authorization and trust boundary validated.
- [ ] Dependency and secret scanning results triaged; critical findings blocked.
- [ ] Retention periods, deletion owners and legal/privacy review recorded.
