"""Deployment-only one-time reset for the RAG Intelligence Studio cutover."""

from __future__ import annotations

import argparse
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

import config
from repositories import rag_governance_repository, rag_studio_repository
from services import object_storage_service


def reset(*, deployment_id: str, actor: str) -> dict[str, object]:
    governance_rows = rag_governance_repository.load_assets()
    documents = {str(row.get("document_id") or "") for row in governance_rows}
    deleted_objects = 0
    for row in governance_rows:
        content_ref = str(row.get("content_ref") or "")
        tenant_id = str(row.get("tenant_id") or "")
        if not content_ref.startswith("object:") or not tenant_id:
            continue
        try:
            object_storage_service.storage().delete(
                content_ref.removeprefix("object:"),
                tenant_id=UUID(tenant_id),
            )
            deleted_objects += 1
        except Exception:
            # Missing compatibility objects do not invalidate the authoritative reset.
            pass
    rag_governance_repository.delete_documents(sorted(documents))

    deleted_files = 0
    documents_root = Path(config.RAG_DOCUMENTS_DIR)
    if not documents_root.is_absolute():
        documents_root = Path(config.PROJECT_DIR) / documents_root
    if documents_root.exists():
        deleted_files = sum(path.is_file() for path in documents_root.rglob("*"))
        shutil.rmtree(documents_root)
    documents_root.mkdir(parents=True, exist_ok=True)

    chroma_root = Path(config.RAG_CHROMA_DIR)
    deleted_index_files = 0
    if chroma_root.exists():
        deleted_index_files = sum(path.is_file() for path in chroma_root.rglob("*"))
        shutil.rmtree(chroma_root)

    deleted_states = rag_studio_repository.delete_local_states()
    deleted_state_files = 0
    learning_root = Path(config.LEARNING_DATA_DIR)
    legacy_patterns = (
        "rag_*.json",
        "faq_*.json",
        "knowledge_gap*.json",
    )
    for pattern in legacy_patterns:
        for path in learning_root.glob(pattern):
            if path.name == "rag_reset_receipt.json":
                continue
            path.unlink(missing_ok=True)
            deleted_state_files += 1
    receipt = {
        "deployment_id": deployment_id,
        "actor": actor,
        "reset_at": datetime.now(timezone.utc).isoformat(),
        "deletion_counts": {
            "documents": len(documents),
            "versions": len(governance_rows),
            "content_objects": deleted_objects,
            "materialized_files": deleted_files,
            "index_files": deleted_index_files,
            "studio_states": deleted_states,
            "legacy_state_files": deleted_state_files,
        },
        "contains_content": False,
    }
    receipt_path = Path(config.LEARNING_DATA_DIR) / "rag_reset_receipt.json"
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.write_text(
        json.dumps(receipt, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Permanently erase legacy RAG state before Studio deployment."
    )
    parser.add_argument("--deployment-id", required=True)
    parser.add_argument("--actor", required=True)
    parser.add_argument(
        "--confirm",
        required=True,
        choices=["DELETE_ALL_LEGACY_RAG"],
        help="Explicit destructive-action confirmation.",
    )
    args = parser.parse_args()
    print(json.dumps(reset(deployment_id=args.deployment_id, actor=args.actor), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
