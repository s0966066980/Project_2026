from uuid import uuid4

import pytest
from modules.ordering_entry import EntryFlowError, OrderingEntryFlowModule, SQLiteEntryFlowStore, transition

from models.commercial_scope import CommercialScope


def test_guest_flow_binds_one_session_and_resumes(tmp_path):
    scope = CommercialScope(uuid4(), uuid4(), uuid4())
    module = OrderingEntryFlowModule(SQLiteEntryFlowStore(tmp_path / "entry.db"))
    flow = module.start(scope=scope, policy_version="v1", policy={"membership_enabled": True})
    assert (
        module.start(scope=scope, policy_version="v2", policy={"membership_enabled": False})["entry_flow_id"]
        == flow["entry_flow_id"]
    )
    flow = module.command(
        scope=scope, entry_flow_id=flow["entry_flow_id"], phase_revision=flow["phase_revision"], command="choose_guest"
    )
    session = flow["ordering_session_id"]
    assert session
    flow = module.command(
        scope=scope, entry_flow_id=flow["entry_flow_id"], phase_revision=flow["phase_revision"], command="menu_failed"
    )
    flow = module.command(
        scope=scope, entry_flow_id=flow["entry_flow_id"], phase_revision=flow["phase_revision"], command="retry_menu"
    )
    flow = module.command(
        scope=scope,
        entry_flow_id=flow["entry_flow_id"],
        phase_revision=flow["phase_revision"],
        command="menu_initialized",
    )
    assert flow["state"] == "menu_ready" and flow["ordering_session_id"] == session


def test_member_not_found_never_opens_registration_automatically():
    state, effects = transition("member_lookup", "member_not_found")
    assert state == "registration_offered" and effects == []


def test_stale_async_result_is_rejected(tmp_path):
    scope = CommercialScope(uuid4(), uuid4(), uuid4())
    module = OrderingEntryFlowModule(SQLiteEntryFlowStore(tmp_path / "entry.db"))
    flow = module.start(scope=scope, policy_version="safe", policy={})
    module.command(
        scope=scope, entry_flow_id=flow["entry_flow_id"], phase_revision=flow["phase_revision"], command="choose_member"
    )
    with pytest.raises(EntryFlowError, match="entry_flow_revision_conflict"):
        module.command(
            scope=scope,
            entry_flow_id=flow["entry_flow_id"],
            phase_revision=flow["phase_revision"],
            command="choose_guest",
        )
