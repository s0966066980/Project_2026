from datetime import datetime


def _base_patch() -> dict:
    return {
        "show_modal": "",
        "highlight": [],
        "disable_promotion": False,
        "simplified_mode": False,
    }


def decide_intervention(barrier_result: dict, ui_context: dict | None = None) -> dict:
    result = barrier_result or {}
    state = result.get("barrier_state", "low_confidence")
    severity = float(result.get("severity") or 0)
    patch = _base_patch()
    action = result.get("recommended_action") or "none"
    action_level = "low"
    staff_notify = False
    reason = "互動狀態正常，暫不介入。"
    tts_text = ""

    if state == "payment_confusion":
        action = "show_payment_tutorial"
        action_level = "medium"
        patch.update({
            "show_modal": "payment_guide",
            "highlight": ["payment_method_panel"],
            "disable_promotion": True,
        })
        tts_text = "我可以協助您完成付款，請選擇下方付款方式。"
        reason = "偵測到付款頁停留與付款失敗，顧客可能付款卡關。"
    elif state == "coupon_confusion":
        action = "show_coupon_guide"
        action_level = "medium"
        patch.update({
            "show_modal": "coupon_guide",
            "highlight": ["coupon_input"],
        })
        tts_text = "我可以協助您使用優惠券，請確認折扣碼或掃碼內容。"
        reason = "偵測到優惠券或掃碼錯誤，顧客可能卡在折扣流程。"
    elif state == "operation_confusion":
        action = "show_operation_hint"
        action_level = "medium"
        patch.update({
            "show_modal": "operation_hint",
            "simplified_mode": True,
        })
        tts_text = "我可以協助您操作，請先點選想要的餐點再加入購物車。"
        reason = "偵測到操作困惑，介面切換為較簡化的協助模式。"
    elif state == "menu_hesitation":
        action = "recommend_popular_combo"
        tts_text = "需要我推薦熱門搭配嗎？"
        reason = "偵測到菜單選擇猶豫，可提供熱門組合降低選擇負擔。"
    elif state == "impatience_detected":
        action = "call_staff_or_fast_mode"
        action_level = "high" if severity >= 0.75 else "medium"
        staff_notify = severity >= 0.75
        patch["disable_promotion"] = True
        tts_text = "我會優先協助您加快流程，並提供較快完成的餐點選項。"
        reason = "偵測到等待不耐或趕時間，暫停促銷干擾並切換快速協助。"
    elif state in {"service_needed", "potential_complaint"}:
        action = "call_staff"
        action_level = "high"
        staff_notify = True
        patch["disable_promotion"] = True
        tts_text = "已通知服務人員協助您處理。"
        reason = "偵測到需要真人協助或疑似抱怨，通知服務人員介入。"
    elif state == "low_confidence":
        action = "ask_clarifying_question"
        tts_text = "請問您需要我協助點餐、付款，或使用優惠券嗎？"
        reason = "目前資訊不足，先以釐清問題的方式低干擾介入。"
    else:
        action = "none"
        action_level = "none"

    return {
        "action": action,
        "action_level": action_level,
        "staff_notify": staff_notify,
        "tts_text": tts_text,
        "ui_patch": patch,
        "reason": reason,
        "ui_context": ui_context or {},
    }


def build_intervention_log(
    session_id: str,
    barrier_result: dict,
    intervention: dict,
    ui_context: dict | None = None,
) -> dict:
    return {
        "session_id": session_id or "anonymous",
        "timestamp": datetime.now().isoformat(),
        "barrier_result": barrier_result or {},
        "intervention": intervention or {},
        "ui_context": ui_context or {},
        "result": {},
    }
