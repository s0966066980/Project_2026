from __future__ import annotations

from typing import Any, Protocol


class EntryFlowError(RuntimeError):
    def __init__(self, code: str, *, details: dict[str, Any] | None = None):
        super().__init__(code)
        self.code = code
        self.details = details or {}


TERMINAL = {"menu_ready", "abandoned"}


def transition(state: str, command: str, payload: dict[str, Any] | None = None) -> tuple[str, list[dict[str, Any]]]:
    payload = payload or {}
    effects = []
    legal = {
        ("choosing_mode", "choose_member"): "member_lookup",
        ("choosing_mode", "choose_guest"): "initializing_menu",
        ("member_lookup", "member_found"): "initializing_menu",
        ("member_lookup", "member_not_found"): "registration_offered",
        ("member_lookup", "member_unavailable"): "member_lookup_degraded",
        ("registration_offered", "begin_registration"): "member_registration",
        ("registration_offered", "retry_member"): "member_lookup",
        ("registration_offered", "choose_guest"): "initializing_menu",
        ("member_lookup_degraded", "choose_guest"): "initializing_menu",
        ("member_lookup_degraded", "retry_member"): "member_lookup",
        ("member_registration", "retry_member"): "member_lookup",
        ("member_registration", "registration_completed"): "initializing_menu",
        ("member_registration", "choose_guest"): "initializing_menu",
        ("initializing_menu", "menu_initialized"): "menu_ready",
        ("initializing_menu", "menu_failed"): "menu_initialization_failed",
        ("menu_initialization_failed", "retry_menu"): "initializing_menu",
        ("member_lookup", "return_to_mode"): "choosing_mode",
        ("registration_offered", "return_to_mode"): "choosing_mode",
        ("member_lookup_degraded", "return_to_mode"): "choosing_mode",
        ("member_registration", "return_to_mode"): "choosing_mode",
        ("menu_initialization_failed", "return_to_mode"): "choosing_mode",
    }
    if command == "abandon" and state not in TERMINAL:
        return "abandoned", [{"type": "clear_sensitive_input"}, {"type": "close_cart"}]
    target = legal.get((state, command))
    if not target:
        raise EntryFlowError("invalid_entry_flow_transition", details={"state": state, "command": command})
    if target == "initializing_menu":
        effects.append({"type": "ensure_ordering_session", "member_ref": str(payload.get("member_ref") or "")})
    if command in {"choose_guest"}:
        effects.append({"type": "clear_sensitive_input"})
    if target == "menu_ready":
        effects.append({"type": "start_optional_capabilities"})
    return target, effects


class EntryStore(Protocol):
    def start(self, **values) -> dict[str, Any]: ...
    def command(self, **values) -> dict[str, Any]: ...
    def get(self, **values) -> dict[str, Any]: ...


class OrderingEntryFlowModule:
    def __init__(self, store: EntryStore, menu_bootstrap=None):
        self._store = store
        self._menu_bootstrap = menu_bootstrap

    def start(
        self,
        *,
        scope,
        policy_version: str,
        policy: dict[str, Any],
        entry_flow_id: str = "",
        policy_loaded: bool = True,
    ):
        if scope.device_id is None:
            raise EntryFlowError("device_scope_required")
        membership_enabled = policy.get("membership_enabled") is not False
        return self._store.start(
            scope=scope,
            entry_flow_id=entry_flow_id,
            policy_version=policy_version or "safe-default",
            policy_result="loaded" if policy_loaded else "safe_default",
            policy_snapshot=dict(policy or {"membership_enabled": True}),
            initial_state="choosing_mode" if membership_enabled else "initializing_menu",
            create_session=not membership_enabled,
        )

    def command(
        self, *, scope, entry_flow_id: str, phase_revision: int, command: str, payload: dict[str, Any] | None = None
    ):
        current = self._store.get(scope=scope, entry_flow_id=entry_flow_id)
        if int(current["phase_revision"]) != int(phase_revision):
            raise EntryFlowError(
                "entry_flow_revision_conflict", details={"current_revision": current["phase_revision"]}
            )
        if command == "menu_initialized" and self._menu_bootstrap is not None:
            self._menu_bootstrap.initialize(scope=scope, session_id=current["ordering_session_id"])
        target, effects = transition(current["state"], command, payload)
        result = self._store.command(
            scope=scope,
            entry_flow_id=entry_flow_id,
            expected_revision=phase_revision,
            target=target,
            command=command,
            payload=payload or {},
            effects=effects,
        )
        if target == "abandoned" and current.get("ordering_session_id") and self._menu_bootstrap is not None:
            self._menu_bootstrap.abandon(scope=scope, session_id=current["ordering_session_id"])
        return result

    def get(self, *, scope, entry_flow_id: str):
        return self._store.get(scope=scope, entry_flow_id=entry_flow_id)
