"""Versioned compatibility endpoints grouped by capability.

These routes keep the published envelope stable while Admin/Kiosk consumers
move to their capability-owned surfaces.
"""

# ruff: noqa: F403, F405

from __future__ import annotations

from routes.v1_support import *  # noqa: F401,F403


def create_router(_deps: dict | None = None) -> APIRouter:
    router = APIRouter(
        prefix="/api/v1",
        dependencies=[Security(_document_admin_security)],
        responses={
            401: {"model": ApiErrorResponse, "description": "Authentication required"},
            403: {"model": ApiErrorResponse, "description": "Permission denied"},
            422: {"model": ApiErrorResponse, "description": "Request validation failed"},
            500: {"model": ApiErrorResponse, "description": "Safe internal error"},
        },
    )

    @router.get(
        "/rag/knowledge", tags=["v1-rag"], operation_id="v1_list_rag_knowledge", response_model=ApiResponse[dict]
    )
    async def list_rag_knowledge(request: Request) -> ApiResponse[dict]:

        scope = _scope(request, "rag.read")

        data = await asyncio.to_thread(knowledge_publication_runtime.default_module().list_items, scope=scope)

        return ApiResponse(data=data, meta=_meta(request))

    @router.post(
        "/rag/knowledge", tags=["v1-rag"], operation_id="v1_create_rag_knowledge", response_model=ApiResponse[dict]
    )
    async def create_rag_knowledge(request: Request, body: RagKnowledgeUpsertRequest) -> ApiResponse[dict]:

        scope = _scope(request, "rag.write")

        try:
            row = await asyncio.to_thread(
                knowledge_publication_runtime.default_module().create_draft,
                scope=scope,
                category=body.category,
                content_type=body.content_type,
                title=body.title,
                content=body.content,
                actor=_admin_actor(request),
                override_near_duplicate=body.override_near_duplicate,
            )

        except PublicationError as exc:
            raise _publication_http_error(exc) from exc

        row = {**row, "autopublish": await _autopublish(request, scope, str(row.get("item_id") or ""))}

        return ApiResponse(data=row, meta=_meta(request))

    @router.put(
        "/rag/knowledge/{item_id}",
        tags=["v1-rag"],
        operation_id="v1_revise_rag_knowledge",
        response_model=ApiResponse[dict],
    )
    async def revise_rag_knowledge(
        request: Request, item_id: str, body: RagKnowledgeUpsertRequest
    ) -> ApiResponse[dict]:

        scope = _scope(request, "rag.write")

        if body.expected_row_revision is None:
            raise HTTPException(status_code=422, detail={"code": "expected_row_revision_required"})

        try:
            row = await asyncio.to_thread(
                knowledge_publication_runtime.default_module().revise_draft,
                scope=scope,
                item_id=item_id,
                expected_row_revision=body.expected_row_revision,
                category=body.category,
                content_type=body.content_type,
                title=body.title,
                content=body.content,
                actor=_admin_actor(request),
                override_near_duplicate=body.override_near_duplicate,
            )

        except PublicationError as exc:
            raise _publication_http_error(exc) from exc

        row = {**row, "autopublish": await _autopublish(request, scope, item_id)}

        return ApiResponse(data=row, meta=_meta(request))

    @router.post(
        "/rag/knowledge/publish",
        tags=["v1-rag"],
        operation_id="v1_publish_rag_knowledge",
        response_model=ApiResponse[dict],
    )
    async def publish_rag_knowledge(request: Request, body: RagKnowledgePublishRequest) -> ApiResponse[dict]:

        scope = _scope(request, "rag.publish")

        try:
            row = await asyncio.to_thread(
                knowledge_publication_runtime.default_module().request_publication,
                scope=scope,
                item_ids=body.item_ids,
                actor=_admin_actor(request),
                retry_failures_only=body.retry_failures_only,
            )

        except PublicationError as exc:
            raise _publication_http_error(exc) from exc

        return ApiResponse(data=row, meta=_meta(request))

    @router.post(
        "/rag/knowledge/publication-attempts/{attempt_id}/resume",
        tags=["v1-rag"],
        operation_id="v1_resume_rag_publication_attempt",
        response_model=ApiResponse[dict],
    )
    async def resume_rag_publication_attempt(request: Request, attempt_id: str) -> ApiResponse[dict]:

        scope = _scope(request, "rag.publish")

        try:
            row = await asyncio.to_thread(
                knowledge_publication_runtime.default_module().ensure_attempt_enqueued,
                scope=scope,
                attempt_id=attempt_id,
                actor=_admin_actor(request),
            )

        except PublicationError as exc:
            raise _publication_http_error(exc) from exc

        return ApiResponse(data=row, meta=_meta(request))

    @router.post(
        "/rag/knowledge/{item_id}/retire",
        tags=["v1-rag"],
        operation_id="v1_retire_rag_knowledge",
        response_model=ApiResponse[dict],
    )
    async def retire_rag_knowledge(
        request: Request, item_id: str, body: RagKnowledgeActionRequest
    ) -> ApiResponse[dict]:

        scope = _scope(request, "rag.publish")

        try:
            row = await asyncio.to_thread(
                knowledge_publication_runtime.default_module().retire,
                scope=scope,
                item_id=item_id,
                expected_row_revision=body.expected_row_revision,
                actor=_admin_actor(request),
            )

        except PublicationError as exc:
            raise _publication_http_error(exc) from exc

        return ApiResponse(data=row, meta=_meta(request))

    @router.delete(
        "/rag/knowledge/{item_id}",
        tags=["v1-rag"],
        operation_id="v1_delete_rag_knowledge",
        response_model=ApiResponse[dict],
    )
    async def delete_rag_knowledge(
        request: Request, item_id: str, expected_row_revision: Annotated[int, Query(ge=1)]
    ) -> ApiResponse[dict]:
        """徹底刪除一筆知識（先下架清索引，再移除紀錄）。稽核事件保留可追溯。"""

        scope = _scope(request, "rag.publish")

        try:
            row = await asyncio.to_thread(
                knowledge_publication_runtime.default_module().delete,
                scope=scope,
                item_id=item_id,
                expected_row_revision=expected_row_revision,
                actor=_admin_actor(request),
            )

        except PublicationError as exc:
            raise _publication_http_error(exc) from exc

        return ApiResponse(data=row, meta=_meta(request))

    @router.post(
        "/rag/retrieval/test", tags=["v1-rag"], operation_id="v1_test_rag_retrieval", response_model=ApiResponse[dict]
    )
    async def test_rag_knowledge(request: Request, body: RagKnowledgeTestRequest) -> ApiResponse[dict]:

        scope = _scope(request, "rag.read")

        try:
            result = await retrieval_check_runtime.default_module().execute(
                query=body.query,
                scope=scope,
                method=body.method,
                top_k=body.top_k,
                relevance_policy=body.relevance_policy,
            )

        except RetrievalCheckError as exc:
            raise _retrieval_check_http_error(exc) from exc

        return ApiResponse(data=result, meta=_meta(request))

    @router.post(
        "/rag/retrieval/checks/{check_id}/confirm",
        tags=["v1-rag"],
        operation_id="v1_confirm_rag_retrieval_check",
        response_model=ApiResponse[dict],
    )
    async def confirm_rag_retrieval_check(request: Request, check_id: str) -> ApiResponse[dict]:

        scope = _scope(request, "rag.publish")

        try:
            result = await asyncio.to_thread(
                retrieval_check_runtime.default_module().confirm,
                scope=scope,
                check_id=check_id,
                actor=_admin_actor(request),
            )

        except RetrievalCheckError as exc:
            raise _retrieval_check_http_error(exc) from exc

        return ApiResponse(data=result, meta=_meta(request))

    @router.get(
        "/rag/retrieval/configurations",
        tags=["v1-rag"],
        operation_id="v1_list_rag_configurations",
        response_model=ApiResponse[dict],
    )
    async def list_rag_configurations(request: Request) -> ApiResponse[dict]:

        scope = _scope(request, "rag.read")

        return ApiResponse(data=rag_knowledge_service.list_configurations(scope), meta=_meta(request))

    @router.post(
        "/rag/retrieval/configurations",
        tags=["v1-rag"],
        operation_id="v1_publish_rag_configuration",
        response_model=ApiResponse[dict],
    )
    async def publish_rag_configuration(request: Request, body: RagRetrievalConfigurationRequest) -> ApiResponse[dict]:

        scope = _scope(request, "rag.publish")

        try:
            row = rag_knowledge_service.publish_configuration(
                scope=scope,
                method=body.method,
                top_k=body.top_k,
                relevance_policy=body.relevance_policy,
                source_version=body.source_version,
                actor=_admin_actor(request),
            )

        except rag_knowledge_service.RagKnowledgeError as exc:
            raise _rag_http_error(exc) from exc

        return ApiResponse(data=row, meta=_meta(request))

    @router.delete(
        "/rag/retrieval/configurations/{version}",
        tags=["v1-rag"],
        operation_id="v1_delete_rag_configuration",
        response_model=ApiResponse[dict],
    )
    async def delete_rag_configuration(request: Request, version: int) -> ApiResponse[dict]:

        scope = _scope(request, "rag.publish")

        actor = _admin_actor(request)

        try:
            row = rag_knowledge_service.delete_configuration(scope=scope, version=version, actor=actor)

        except rag_knowledge_service.RagKnowledgeError as exc:
            raise _rag_http_error(exc) from exc

        await asyncio.to_thread(
            operations.record_admin_action,
            "rag.retrieval_configuration.delete",
            target_type="rag_retrieval_configuration",
            target_id=str(version),
            request=request,
            metadata={"actor_id": actor},
            scope=scope,
        )

        return ApiResponse(data=row, meta=_meta(request))

    return router
