# Separate RAG publication permissions

Status: accepted

RAG authorization is independent from administrator-identity management. `rag.read` views knowledge and evaluation, `rag.write` manages drafts and test cases, and `rag.publish` changes Published knowledge or Retrieval Configuration. We rejected coupling publication to `admin_identity.manage` because account administration is not evidence of responsibility for store knowledge.

The redesigned Admin and public application API deliberately expose no full-library reset action or `rag.reset` permission. The one-time clean reset is a deployment migration; any future full reset requires a controlled infrastructure maintenance command.
