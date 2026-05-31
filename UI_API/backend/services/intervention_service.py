from datetime import datetime


def _base_patch() -> dict:
    return {
        "show_modal": "",
        "highlight": [],
        "disable_promotion": False,
        "simplified_mode": False,
    }


_STATE_PRESENTATION = {
    "payment_confusion": {
        "action_level": "medium",
        "patch": {
            "show_modal": "payment_guide",
            "highlight": ["payment_method_panel"],
            "disable_promotion": True,
        },
        "tts_text": "我可以協助您完成付款，請選擇下方付款方式。",
        "reason": "偵測到付款頁停留與付款失敗，顧客可能付款卡關。",
    },
    "coupon_confusion": {
        "action_level": "medium",
        "patch": {"show_modal": "coupon_guide", "highlight": ["coupon_input"]},
        "tts_text": "我可以協助您使用優惠券，請確認折扣碼或掃碼內容。",
        "reason": "偵測到優惠券或掃碼錯誤，顧客可能卡在折扣流程。",
    },
    "operation_confusion": {
        "action_level": "medium",
        "patch": {"show_modal": "operation_hint", "simplified_mode": True},
        "tts_text": "我可以協助您操作，請先點選想要的餐點再加入購物車。",
        "reason": "偵測到操作困惑，介面切換為較簡化的協助模式。",
    },
    "menu_hesitation": {
        "action_level": "low",
        "patch": {
            "show_modal": "recommendation_card",
            "highlight": ["menu_recommendation_area"],
            "disable_promotion": False,
        },
        "tts_text": "如果還沒決定，我可以推薦幾個熱門餐點給您。",
        "reason": "偵測到餐點選擇猶豫，提供餐點推薦以降低選擇負擔。",
    },
    "impatience_detected": {
        "action_level": "medium",
        "patch": {"disable_promotion": True},
        "tts_text": "我會優先協助您加快流程，並提供較快完成的餐點選項。",
        "reason": "偵測到等待不耐或趕時間，暫停促銷干擾並切換快速協助。",
        "severity_high_level": "high",
        "severity_high_notify": True,
    },
    "service_needed": {
        "action_level": "high",
        "patch": {"disable_promotion": True},
        "tts_text": "已通知服務人員協助您處理。",
        "reason": "偵測到需要真人協助或疑似抱怨，通知服務人員介入。",
        "staff_notify": True,
    },
    "potential_complaint": {
        "action_level": "high",
        "patch": {"disable_promotion": True},
        "tts_text": "已通知服務人員協助您處理。",
        "reason": "偵測到需要真人協助或疑似抱怨，通知服務人員介入。",
        "staff_notify": True,
    },
    "low_confidence": {
        "action_level": "low",
        "patch": {},
        "tts_text": "請問您需要我協助點餐、付款，或使用優惠券嗎？",
        "reason": "目前資訊不足，先以釐清問題的方式低干擾介入。",
    },
}


PATENT_INTERVENTION_MAP = {
    "show_payment_tutorial": "payment_tutorial",
    "show_coupon_guide": "operation_hint",
    "show_operation_hint": "operation_hint",
    "recommend_popular_combo": "recommendation",
    "call_staff_or_fast_mode": "human_service",
    "call_staff": "human_service",
    "ask_clarifying_question": "voice_explanation",
    "none": "normal_interface",
}

PATENT_INTERVENTION_LABELS = {
    "payment_tutorial": "付款教學",
    "operation_hint": "操作提示",
    "recommendation": "推薦",
    "human_service": "真人客服",
    "voice_explanation": "語音說明",
    "normal_interface": "維持正常介面",
}


def map_action_to_patent_intervention(action: str) -> dict:
    key = PATENT_INTERVENTION_MAP.get(action or "none", "voice_explanation")
    return {
        "patent_intervention_type": key,
        "patent_intervention_label": PATENT_INTERVENTION_LABELS.get(key, ""),
    }


def decide_intervention(barrier_result: dict, ui_context: dict | None = None) -> dict:
    result = barrier_result or {}
    state = result.get("barrier_state", "low_confidence")
    severity = float(result.get("severity") or 0)
    action = result.get("recommended_action") or "none"
    patch = _base_patch()
    action_level = "low"
    staff_notify = False
    reason = "互動狀態正常，暫不介入。"
    tts_text = ""

    preset = _STATE_PRESENTATION.get(state)
    if preset:
        action_level = preset.get("action_level", "low")
        patch.update(preset.get("patch") or {})
        tts_text = preset.get("tts_text", "")
        reason = preset.get("reason", reason)
        staff_notify = preset.get("staff_notify", False)
        if severity >= 0.75:
            if "severity_high_level" in preset:
                action_level = preset["severity_high_level"]
            if preset.get("severity_high_notify"):
                staff_notify = True
        if state == "payment_confusion" and (
            severity >= 0.75 or int(result.get("payment_fail_count") or 0) >= 2
        ):
            action_level = "high"
            staff_notify = True
            if int(result.get("payment_fail_count") or 0) >= 2:
                action = "call_staff_or_fast_mode"
                patch["disable_promotion"] = True
    elif state == "normal_operation":
        action = "none"
        action_level = "none"
    else:
        action = "none"
        action_level = "none"

    patent_info = map_action_to_patent_intervention(action)
    return {
        "action": action,
        "action_level": action_level,
        "staff_notify": staff_notify,
        "tts_text": tts_text,
        "ui_patch": patch,
        "reason": reason,
        "ui_context": ui_context or {},
        **patent_info,
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
