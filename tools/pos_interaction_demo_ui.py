#!/usr/bin/env python3
"""
Project_2026 POS 互動障礙事件測試工具

用途：
  1. 模擬 POS 異常操作事件，預設呼叫 UI_API 的 /api/demo/trigger_scenario。
  2. 可勾選 legacy 模式，改用 /api/interaction_event + /api/barrier_state。
  3. 透過 /ws/demo/{session_id} 監看 realtime events，確認 POS/Admin/demo 是否收到 intervention。

使用方式：
  1. 啟動 UI_API：
       cd /home/oliver/Project_2026/UI_API
       python main.py

  2. 開啟 POS，建議使用固定 session_id：
       http://127.0.0.1:8000/pos?session_id=pos_demo_001

  3. 執行此工具：
       cd /home/oliver/Project_2026
       python3 tools/pos_interaction_demo_ui.py

  4. API Base URL 保持 http://127.0.0.1:8000，session_id 與 POS URL 相同。
     按下「付款失敗」等按鈕後，POS 應顯示對應 intervention。

依賴：
  - requests
  - websocket-client，可選。若未安裝，GUI 仍可做 REST 測試，但不監看 websocket。
"""

from __future__ import annotations

import json
import queue
import threading
import time
import tkinter as tk
from tkinter import scrolledtext, ttk
from urllib.parse import urlparse

try:
    import requests
except ImportError as exc:
    raise SystemExit("缺少 requests，請先安裝：pip install requests") from exc

try:
    import websocket
except ImportError:
    websocket = None


SCENARIOS = {
    "付款失敗": {
        "scenario_key": "payment_failed",
        "page_id": "payment_page",
        "event_type": "payment_failed",
        "button_id": "demo_payment",
        "dwell_time_sec": 35,
        "payment_fail_count": 1,
        "metadata": {"source": "demo", "payment": "failed"},
        "speech_text": "我不能刷卡，付款一直失敗。",
    },
    "付款頁停留過久": {
        "scenario_key": "long_payment_dwell",
        "page_id": "payment_page",
        "event_type": "page_dwell_timeout",
        "button_id": "demo_timer",
        "dwell_time_sec": 45,
        "metadata": {"reason": "demo_long_dwell", "source": "demo"},
        "speech_text": "我在付款頁停很久，不知道下一步要按哪裡。",
    },
    "無效點擊": {
        "scenario_key": "invalid_touch",
        "page_id": "menu_page",
        "event_type": "invalid_touch",
        "button_id": "demo_invalid_touch",
        "dwell_time_sec": 20,
        "invalid_touch_count": 3,
        "metadata": {"reason": "demo_invalid_touch", "source": "demo"},
        "speech_text": "我看不懂怎麼點。",
    },
    "操作困惑": {
        "scenario_key": "operation_confusion_explicit",
        "page_id": "menu_page",
        "event_type": "invalid_touch",
        "button_id": "demo_operation_confusion",
        "dwell_time_sec": 35,
        "invalid_touch_count": 3,
        "metadata": {"reason": "operation_confusion_explicit", "source": "demo"},
        "speech_text": "我不會操作，不知道怎麼點餐。",
    },
    "優惠券錯誤": {
        "scenario_key": "coupon_error",
        "page_id": "coupon_page",
        "event_type": "coupon_error",
        "button_id": "demo_coupon",
        "dwell_time_sec": 28,
        "coupon_error_count": 1,
        "metadata": {"reason": "demo_coupon_error", "source": "demo"},
        "speech_text": "優惠券掃碼失敗，折扣碼不能用。",
    },
    "重複返回": {
        "scenario_key": "back_navigation",
        "page_id": "checkout_page",
        "event_type": "back_navigation",
        "button_id": "demo_back",
        "dwell_time_sec": 32,
        "back_count": 2,
        "metadata": {"reason": "demo_back_navigation", "source": "demo"},
        "speech_text": "我一直返回，不知道要怎麼確認餐點。",
    },
    "客服求助": {
        "scenario_key": "customer_service_requested",
        "page_id": "menu_page",
        "event_type": "customer_service_requested",
        "button_id": "demo_service",
        "dwell_time_sec": 31,
        "metadata": {"reason": "demo_customer_service", "source": "demo"},
        "speech_text": "我需要客服幫忙操作。",
    },
    "客訴風險": {
        "scenario_key": "complaint_risk",
        "page_id": "payment_page",
        "event_type": "payment_failed",
        "button_id": "demo_complaint",
        "dwell_time_sec": 38,
        "payment_fail_count": 1,
        "metadata": {"reason": "demo_complaint_risk", "source": "demo"},
        "speech_text": "付款一直失敗，太誇張了，我要找經理客訴。",
    },
}


def api_to_ws_url(api_base: str, session_id: str) -> str:
    parsed = urlparse(api_base.strip())
    scheme = "wss" if parsed.scheme == "https" else "ws"
    host = parsed.netloc or "127.0.0.1:8000"
    return f"{scheme}://{host}/ws/demo/{session_id}"


class DemoApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Project_2026 POS 互動障礙偵測測試端")
        self.events = queue.Queue()
        self.ws_app = None
        self.ws_thread = None
        self.ws_session = ""
        self.ws_url = ""
        self._build_ui()
        self._poll_events()
        self._connect_ws()

    def _build_ui(self):
        self.root.geometry("1120x760")
        self.root.minsize(940, 620)

        main = ttk.Frame(self.root, padding=12)
        main.pack(fill=tk.BOTH, expand=True)

        title = ttk.Label(main, text="事件觸發式 POS 顧客互動障礙偵測測試端", font=("Noto Sans CJK TC", 18, "bold"))
        title.pack(anchor=tk.W, pady=(0, 6))
        desc = ttk.Label(
            main,
            text="送出 POS 操作事件後，系統會計算風險分數；達門檻時會推論互動障礙狀態與服務介入動作。",
        )
        desc.pack(anchor=tk.W, pady=(0, 12))

        form = ttk.LabelFrame(main, text="請求設定", padding=12)
        form.pack(fill=tk.X, pady=(0, 12))
        form.columnconfigure(1, weight=1)
        form.columnconfigure(3, weight=1)

        ttk.Label(form, text="API Base URL").grid(row=0, column=0, sticky=tk.W, padx=(0, 8))
        self.api_base_var = tk.StringVar(value="http://127.0.0.1:8000")
        ttk.Entry(form, textvariable=self.api_base_var).grid(row=0, column=1, sticky=tk.EW, padx=(0, 16))

        ttk.Label(form, text="session_id").grid(row=0, column=2, sticky=tk.W, padx=(0, 8))
        self.session_var = tk.StringVar(value="pos_demo_001")
        ttk.Entry(form, textvariable=self.session_var).grid(row=0, column=3, sticky=tk.EW, padx=(0, 8))
        ttk.Button(form, text="重新連線 WS", command=self._connect_ws).grid(row=0, column=4, sticky=tk.E)
        self.legacy_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            form,
            text="使用 legacy /api/interaction_event + /api/barrier_state",
            variable=self.legacy_var,
        ).grid(row=1, column=0, columnspan=5, sticky=tk.W, pady=(10, 0))

        body = ttk.Frame(main)
        body.pack(fill=tk.BOTH, expand=True)
        body.columnconfigure(0, weight=0)
        body.columnconfigure(1, weight=1)
        body.rowconfigure(0, weight=1)

        left = ttk.LabelFrame(body, text="模擬事件", padding=12)
        left.grid(row=0, column=0, sticky=tk.NS, padx=(0, 12))

        for idx, label in enumerate(SCENARIOS.keys()):
            ttk.Button(left, text=label, command=lambda name=label: self._send_scenario(name)).grid(
                row=idx, column=0, sticky=tk.EW, pady=4
            )
        ttk.Separator(left).grid(row=len(SCENARIOS), column=0, sticky=tk.EW, pady=8)
        ttk.Button(left, text="清空輸出", command=self._clear_output).grid(row=len(SCENARIOS) + 1, column=0, sticky=tk.EW, pady=4)

        right = ttk.Frame(body)
        right.grid(row=0, column=1, sticky=tk.NSEW)
        right.rowconfigure(1, weight=1)
        right.columnconfigure(0, weight=1)

        self.status_var = tk.StringVar(value="尚未送出事件")
        status = ttk.LabelFrame(right, text="辨識結果", padding=12)
        status.grid(row=0, column=0, sticky=tk.EW, pady=(0, 12))
        ttk.Label(status, textvariable=self.status_var, font=("Noto Sans CJK TC", 13, "bold")).pack(anchor=tk.W)

        output_box = ttk.LabelFrame(right, text="HTTP response / realtime events", padding=8)
        output_box.grid(row=1, column=0, sticky=tk.NSEW)
        output_box.rowconfigure(0, weight=1)
        output_box.columnconfigure(0, weight=1)
        self.output = scrolledtext.ScrolledText(output_box, wrap=tk.WORD, height=26)
        self.output.grid(row=0, column=0, sticky=tk.NSEW)

    def _log(self, message: str):
        ts = time.strftime("%H:%M:%S")
        self.output.insert(tk.END, f"[{ts}] {message}\n")
        self.output.see(tk.END)

    def _clear_output(self):
        self.output.delete("1.0", tk.END)
        self.status_var.set("已清空輸出")

    def _base(self) -> str:
        return self.api_base_var.get().strip().rstrip("/")

    def _session_id(self) -> str:
        return self.session_var.get().strip() or "pos_demo_001"

    def _connect_ws(self):
        session_id = self._session_id()
        ws_url = api_to_ws_url(self._base(), session_id)
        if self.ws_app:
            try:
                self.ws_app.close()
            except Exception:
                pass
        self.ws_session = session_id
        self.ws_url = ws_url
        if websocket is None:
            self._log("websocket-client 未安裝，REST 測試可用，但 websocket 監看未啟用。安裝：pip install websocket-client")
            return

        def on_open(ws):
            self.events.put(("log", f"WebSocket 已連線：{ws_url}"))
            try:
                ws.send(json.dumps({"type": "ping"}))
            except Exception:
                pass

        def on_message(_ws, message):
            try:
                event = json.loads(message)
            except Exception:
                event = {"raw": message}
            self.events.put(("ws", event))

        def on_error(_ws, error):
            self.events.put(("log", f"WebSocket 錯誤：{error}"))

        def on_close(_ws, _code, _reason):
            self.events.put(("log", "WebSocket 已斷線"))

        self.ws_app = websocket.WebSocketApp(
            ws_url,
            on_open=on_open,
            on_message=on_message,
            on_error=on_error,
            on_close=on_close,
        )
        self.ws_thread = threading.Thread(target=self.ws_app.run_forever, daemon=True)
        self.ws_thread.start()

    def _send_scenario(self, name: str):
        threading.Thread(target=self._send_scenario_worker, args=(name,), daemon=True).start()

    def _send_scenario_worker(self, name: str):
        base = self._base()
        session_id = self._session_id()
        scenario = dict(SCENARIOS[name])
        scenario_key = scenario.pop("scenario_key", "payment_failed")
        speech_text = scenario.pop("speech_text", "")
        if not self.legacy_var.get():
            payload = {
                "session_id": session_id,
                "scenario": scenario_key,
                "speech_text": speech_text,
            }
            try:
                response = requests.post(f"{base}/api/demo/trigger_scenario", json=payload, timeout=10)
                data = response.json()
                self.events.put(("http", {"scenario": f"{name} / demo", "response": data}))
                if (data.get("risk_result") or {}).get("triggered"):
                    self.events.put(("log", "risk_result.triggered=true，等待 POS websocket intervention"))
            except Exception as exc:
                self.events.put(("log", f"{name} demo 送出失敗：{exc}"))
            return

        payload = {
            "session_id": session_id,
            "back_count": 0,
            "invalid_touch_count": 0,
            "payment_fail_count": 0,
            "coupon_error_count": 0,
            "cart_edit_count": 0,
            "idle_time_sec": 0,
            **scenario,
            "ui_context": {
                "page_id": scenario.get("page_id"),
                "cart_count": 1,
                "promotion_paused": False,
                "service_open": False,
            },
        }
        try:
            response = requests.post(f"{base}/api/interaction_event", json=payload, timeout=10)
            data = response.json()
            self.events.put(("http", {"scenario": name, "response": data}))

            risk = data.get("risk_result") if isinstance(data, dict) else {}
            if risk.get("triggered"):
                self.events.put(("log", "risk_result.triggered=true，等待 POS websocket intervention"))
                barrier_payload = {
                    "session_id": session_id,
                    "speech_text": speech_text,
                    "emotion_structured": {},
                    "media_signals": {},
                    "ui_context": payload["ui_context"],
                }
                barrier_response = requests.post(f"{base}/api/barrier_state", json=barrier_payload, timeout=10)
                self.events.put(("http", {
                    "scenario": f"{name} / barrier_state",
                    "response": barrier_response.json(),
                }))
        except Exception as exc:
            self.events.put(("log", f"{name} 送出失敗：{exc}"))

    def _render_http(self, payload: dict):
        data = payload.get("response", {})
        risk = data.get("risk_result") if isinstance(data, dict) else {}
        risk_score = risk.get("risk_score", "-")
        triggered = risk.get("triggered", False)
        reasons = risk.get("trigger_reasons", [])
        self.status_var.set(f"{payload.get('scenario')} | risk_score={risk_score} | triggered={triggered}")
        self._log(f"HTTP {payload.get('scenario')}")
        self._log(f"risk_score: {risk_score}")
        self._log(f"triggered: {triggered}")
        self._log(f"trigger_reasons: {', '.join(reasons) if reasons else '-'}")
        barrier = data.get("barrier_result") if isinstance(data, dict) else {}
        intervention = data.get("intervention") if isinstance(data, dict) else {}
        if isinstance(barrier, dict) and barrier:
            self._log(f"barrier_state: {barrier.get('barrier_state', '-')}")
        if isinstance(intervention, dict) and intervention:
            self._log(f"intervention_action: {intervention.get('action', '-')}")
        self._log(json.dumps(data, ensure_ascii=False, indent=2))

    def _render_ws(self, event: dict):
        event_type = event.get("type", "unknown")
        if event_type in {"interaction_intervention", "emotion_analysis_started", "emotion_analysis_completed"}:
            self.status_var.set(f"收到 realtime event：{event_type}")
        self._log(f"WebSocket event: {event_type}")
        self._log(json.dumps(event, ensure_ascii=False, indent=2))

    def _poll_events(self):
        try:
            while True:
                kind, payload = self.events.get_nowait()
                if kind == "http":
                    self._render_http(payload)
                elif kind == "ws":
                    self._render_ws(payload)
                else:
                    self._log(str(payload))
        except queue.Empty:
            pass
        self.root.after(100, self._poll_events)


def main():
    root = tk.Tk()
    style = ttk.Style()
    try:
        style.theme_use("clam")
    except tk.TclError:
        pass
    DemoApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
