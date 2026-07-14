"""Architecture: provider HTTP clients only under integrations/ (target)."""

from __future__ import annotations

import ast
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2] / "backend"
SERVICES = BACKEND / "services"


def test_manual_payment_and_pos_adapters_exist() -> None:
    assert (BACKEND / "integrations/payment/manual.py").is_file()
    assert (BACKEND / "integrations/pos/manual.py").is_file()
    from integrations.payment.manual import ManualPaymentAdapter
    from integrations.pos.manual import ManualPOSAdapter

    pay = ManualPaymentAdapter().authorize(amount=100, currency="TWD", order_ref="o1")
    assert pay.status == "pending_manual_payment"
    pos = ManualPOSAdapter().submit_order(order_ref="o1")
    assert pos.status == "pending_manual_entry"


def test_identity_application_does_not_import_httpx() -> None:
    path = BACKEND / "modules/identity/application.py"
    if not path.is_file():
        return
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            assert all(a.name != "httpx" for a in node.names)
        if isinstance(node, ast.ImportFrom):
            assert node.module != "httpx"
