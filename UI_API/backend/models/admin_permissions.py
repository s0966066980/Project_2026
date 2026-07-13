"""Stable Admin permission machine names for the current operational surface."""

ADMIN_PERMISSION_CATALOG: tuple[tuple[str, str], ...] = (
    ("operations.read", "Read operational health, logs, and interaction evidence"),
    ("operations.write", "Clear or mutate operational records"),
    ("settings.read", "Read runtime settings"),
    ("settings.write", "Change runtime settings"),
    ("catalog.availability.read", "Read store catalog availability"),
    ("catalog.availability.write", "Change store catalog availability"),
    ("members.read", "Read masked member records"),
    ("members.export", "Export masked member records"),
    ("members.delete", "Delete or clear member records"),
    ("recommendations.read", "Read recommendation events"),
    ("recommendations.write", "Clear recommendation events"),
    ("rag.read", "Read RAG documents, status, reviews, and alerts"),
    ("rag.write", "Upload, change, or remove RAG documents and promotions"),
    ("rag.review", "Review and publish governed RAG content"),
    ("audit.read", "Read scoped Admin audit records"),
    ("admin_identity.manage", "Manage Admin users, roles, permissions, and sessions"),
    ("system.debug", "Use explicitly enabled diagnostic endpoints"),
)

ADMIN_PERMISSION_NAMES = frozenset(machine_name for machine_name, _description in ADMIN_PERMISSION_CATALOG)
