"""Stable Admin permission machine names for the current operational surface."""

ADMIN_PERMISSION_CATALOG: tuple[tuple[str, str], ...] = (
    ("operations.read", "Read operational health, logs, and interaction evidence"),
    ("operations.write", "Clear or mutate operational records"),
    ("settings.read", "Read runtime settings"),
    ("settings.write", "Change runtime settings"),
    ("catalog.availability.read", "Read store catalog availability"),
    ("catalog.availability.write", "Change store catalog availability"),
    ("catalog.items.read", "Read store menu items (product catalog)"),
    ("catalog.items.write", "Create, edit, retire, and restore store menu items and images"),
    ("members.read", "Read masked member records"),
    ("members.write", "Record verified member service preferences"),
    ("members.export", "Export masked member records"),
    ("members.delete", "Delete or clear member records"),
    ("recommendations.read", "Read recommendation events"),
    ("recommendations.effectiveness.read", "Read scoped recommendation and campaign effectiveness"),
    ("campaigns.read", "Read scoped campaigns and previews"),
    ("campaigns.write", "Create and revise campaign drafts"),
    ("campaigns.publish", "Review, publish, pause, end, and archive campaigns"),
    ("recommendations.write", "Clear recommendation events"),
    ("rag.read", "Read RAG Studio knowledge, retrieval status, tests, and evaluations"),
    ("rag.write", "Create and revise RAG drafts, imports, and test cases"),
    ("rag.publish", "Publish or retire RAG knowledge and retrieval configurations"),
    ("audit.read", "Read scoped Admin audit records"),
    ("admin_identity.manage", "Manage Admin users, roles, permissions, and sessions"),
    ("device_identity.manage", "Issue, rotate, and revoke Kiosk device credentials"),
    ("system.debug", "Use explicitly enabled diagnostic endpoints"),
)

ADMIN_PERMISSION_NAMES = frozenset(machine_name for machine_name, _description in ADMIN_PERMISSION_CATALOG)

# 現場員工不需要主管密碼即可使用的最小權限集合。
# 刻意不含 operations.read：健康頁與統計頁共用該權限，而健康屬於主管功能。
# 也刻意不含 system.debug：Manager LLM Debug Access 不得暴露於員工模式。
STAFF_PERMISSION_NAMES = frozenset({
    "catalog.availability.read",
    "catalog.availability.write",
    "recommendations.effectiveness.read",
})

assert STAFF_PERMISSION_NAMES <= ADMIN_PERMISSION_NAMES
