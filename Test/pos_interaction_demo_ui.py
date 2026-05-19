#!/usr/bin/env python3
"""
Project_2026 POS 互動障礙偵測 HTML 實施例介面。

啟動後會開啟瀏覽器 UI。瀏覽器端按「送出事件」後，本腳本會代理呼叫
UI_API 的 /api/interaction_event 與 /api/barrier_state，避免額外調整 CORS。

使用方式：
    cd /home/oliver/Project_2026
    python3 Test/pos_interaction_demo_ui.py
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


DEFAULT_API_BASE = os.getenv("UI_API_BASE", "http://127.0.0.1:8000")
DEMO_HOST = os.getenv("POS_DEMO_HOST", "127.0.0.1")
DEMO_PORT = int(os.getenv("POS_DEMO_PORT", "8765"))


HTML = r"""<!doctype html>
<html lang="zh-Hant">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Project_2026 POS 互動障礙偵測測試介面</title>
  <style>
    :root {
      --bg: #f7f3ec;
      --surface: #fffdf8;
      --surface2: #f2eee6;
      --line: #ded7cc;
      --text: #182a28;
      --muted: #72807a;
      --green: #607a59;
      --orange: #ef6a45;
      --red: #e5413e;
      --shadow: 0 18px 50px rgba(45, 35, 25, .08);
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      min-height: 100vh;
      font-family: "Noto Sans TC", "PingFang TC", "Microsoft JhengHei", system-ui, sans-serif;
      background: radial-gradient(circle at 20% 0%, #fffaf2, var(--bg) 42%, #f5efe5);
      color: var(--text);
    }
    .window {
      width: min(1500px, calc(100vw - 32px));
      margin: 16px auto;
      border: 1px solid var(--line);
      border-radius: 16px;
      background: rgba(255,255,255,.72);
      box-shadow: var(--shadow);
      overflow: hidden;
    }
    .chrome {
      height: 44px;
      display: grid;
      grid-template-columns: 120px 1fr 120px;
      align-items: center;
      border-bottom: 1px solid var(--line);
      background: rgba(255,255,255,.55);
      backdrop-filter: blur(14px);
    }
    .dots { display: flex; gap: 10px; padding-left: 18px; }
    .dot { width: 14px; height: 14px; border-radius: 999px; }
    .red { background:#ff5f57; } .yellow { background:#ffbd2e; } .green { background:#28c840; }
    .chrome-title { text-align: center; font-weight: 800; color:#302d28; }
    main { padding: 30px 36px 34px; }
    header {
      display:flex; justify-content:space-between; gap:20px; align-items:flex-start; margin-bottom:28px;
    }
    h1 { margin:0 0 8px; font-size:32px; letter-spacing:.02em; }
    .subtitle { margin:0; color:var(--muted); font-weight:600; }
    .top-actions { display:flex; gap:12px; }
    button {
      border: 1px solid var(--line);
      background: var(--surface);
      color: var(--text);
      border-radius: 10px;
      padding: 12px 18px;
      font-weight: 800;
      cursor: pointer;
      box-shadow: 0 4px 16px rgba(0,0,0,.04);
    }
    button.primary {
      border-color: #587251;
      background: linear-gradient(135deg, #5c7655, #435f3f);
      color: white;
    }
    button:disabled { opacity:.55; cursor:not-allowed; }
    .grid { display:grid; grid-template-columns: 1.45fr .85fr; gap:18px; }
    .card {
      background: var(--surface);
      border: 1px solid var(--line);
      border-radius: 14px;
      overflow: hidden;
      box-shadow: 0 8px 28px rgba(38, 28, 18, .04);
    }
    .card-title {
      padding: 16px 22px;
      border-bottom: 1px solid var(--line);
      background: rgba(250,247,240,.85);
      font-size: 17px;
      font-weight: 900;
      color: #4c6248;
    }
    .card-body { padding: 20px 22px; }
    .form-grid { display:grid; grid-template-columns: 1fr 1fr; gap:16px 24px; }
    label { display:block; margin-bottom:7px; font-size:14px; font-weight:900; color:#3e4845; }
    input, select, textarea {
      width:100%;
      border: 1px solid var(--line);
      background:#fffefa;
      border-radius: 9px;
      padding: 12px 13px;
      font-size:16px;
      color: var(--text);
      outline: none;
    }
    textarea { min-height: 92px; resize: vertical; line-height:1.6; }
    .wide { grid-column: 1 / -1; }
    .actions { display:flex; gap:14px; align-items:center; margin-top:20px; flex-wrap:wrap; }
    .check { display:flex; align-items:center; gap:8px; color:var(--muted); font-weight:800; }
    .check input { width:auto; }
    .result-head { display:flex; justify-content:space-between; gap:12px; align-items:center; }
    .badge { padding: 7px 12px; border-radius:999px; background:#e7f3df; color:#4e6d42; font-size:13px; font-weight:900; }
    .risk-card { border:1px solid var(--line); border-radius:12px; padding:18px; margin-top:16px; }
    .score { font-size:42px; color:var(--red); font-weight:950; line-height:1; }
    .bar { height:8px; border-radius:99px; background:linear-gradient(90deg,#6e963d,#e1b517,#ef6a45,#e5413e); margin:14px 0 10px; position:relative; }
    .knob { width:15px; height:15px; background:white; border:1px solid var(--line); border-radius:50%; position:absolute; top:-4px; left:0; box-shadow:0 2px 8px rgba(0,0,0,.18); }
    .result-grid { display:grid; grid-template-columns:1fr 1fr; gap:16px; margin-top:16px; }
    .mini { border:1px solid var(--line); border-radius:12px; padding:18px; text-align:center; min-height:150px; }
    .mini-icon { font-size:30px; color:var(--orange); margin:14px 0 8px; }
    .mini strong { display:block; font-size:20px; color:var(--orange); }
    .pill { display:inline-block; margin-top:12px; padding:7px 12px; border-radius:999px; background:#f8e8dd; color:#a5522d; font-size:13px; font-weight:900; }
    pre {
      margin: 0;
      white-space: pre-wrap;
      word-break: break-word;
      background:#fbf8f1;
      border:1px solid var(--line);
      border-radius:12px;
      padding:18px;
      max-height: 245px;
      overflow:auto;
      color:#47625b;
      line-height:1.45;
    }
    .logs { margin-top:12px; display:grid; gap:10px; }
    .log { display:flex; justify-content:space-between; gap:12px; border-bottom:1px solid var(--line); padding:10px 4px; color:var(--muted); }
    @media (max-width: 980px) {
      .grid, .form-grid, .result-grid { grid-template-columns:1fr; }
      header { flex-direction:column; }
    }
  </style>
</head>
<body>
  <div class="window">
    <div class="chrome">
      <div class="dots"><i class="dot red"></i><i class="dot yellow"></i><i class="dot green"></i></div>
      <div class="chrome-title">Project_2026 POS 互動障礙偵測測試介面</div>
      <div></div>
    </div>
    <main>
      <header>
        <div>
          <h1>事件觸發式 POS 顧客互動障礙偵測測試介面</h1>
          <p class="subtitle">送出 POS 操作事件後，系統會計算風險分數，再推論互動障礙狀態與服務介入動作。</p>
        </div>
        <div class="top-actions">
          <button id="helpBtn">？ 使用說明</button>
          <button id="openAdminBtn">↗ 開啟後台</button>
        </div>
      </header>
      <section class="grid">
        <div class="card">
          <div class="card-title">● 請求設定</div>
          <div class="card-body">
            <div class="form-grid">
              <div><label>API Base</label><input id="apiBase" value="__API_BASE__"></div>
              <div><label>Session ID</label><input id="sessionId"></div>
              <div class="wide"><label>情境 Scenario</label><select id="scenario"></select></div>
              <div><label>頁面 page_id</label><input id="pageId"></div>
              <div><label>事件 event_type</label><input id="eventType"></div>
              <div><label>按鈕 button_id</label><input id="buttonId"></div>
              <div><label>停留秒數 dwell_time_sec</label><input id="dwellTime" type="number" min="0"></div>
              <div><label>付款失敗 payment_fail_count</label><input id="paymentFail" type="number" min="0"></div>
              <div><label>優惠券錯誤 coupon_error_count</label><input id="couponError" type="number" min="0"></div>
              <div><label>無效點擊 invalid_touch_count</label><input id="invalidTouch" type="number" min="0"></div>
              <div><label>返回次數 back_count</label><input id="backCount" type="number" min="0"></div>
              <div><label>購物車修改 cart_edit_count</label><input id="cartEdit" type="number" min="0"></div>
              <div class="wide"><label>顧客語音文字 speech_text</label><textarea id="speechText" maxlength="200"></textarea></div>
              <div class="wide"><label>進階設定 metadata</label><textarea id="metadata" maxlength="1000"></textarea></div>
            </div>
            <div class="actions">
              <button class="primary" id="sendBtn">➤ 送出事件 Send Event</button>
              <button id="resetBtn">↻ 清除表單 Reset</button>
              <label class="check"><input id="openAdminAfter" type="checkbox" checked> 送出後開啟後台管理頁面</label>
            </div>
          </div>
        </div>
        <div>
          <div class="card">
            <div class="card-title result-head"><span>辨識結果</span><span id="status" class="badge">尚未送出</span></div>
            <div class="card-body">
              <div class="risk-card">
                <label>風險分數 risk_score</label>
                <div><span id="riskScore" class="score">0</span> / 100</div>
                <div class="bar"><i id="riskKnob" class="knob"></i></div>
                <div id="riskLevel" style="font-weight:900;color:var(--muted)">風險等級：待測試</div>
              </div>
              <div class="result-grid">
                <div class="mini">
                  <label>互動障礙狀態 barrier_state</label>
                  <div class="mini-icon">❔</div>
                  <strong id="barrierState">-</strong>
                  <span id="barrierRaw" class="pill">-</span>
                </div>
                <div class="mini">
                  <label>建議介入動作 suggested_action</label>
                  <div class="mini-icon">🎧</div>
                  <strong id="actionState" style="color:var(--green)">-</strong>
                  <span id="actionRaw" class="pill" style="background:#e9f1e6;color:#55724f">-</span>
                </div>
              </div>
              <div style="margin-top:18px"><label>完整回應 response</label><pre id="responseBox">{}</pre></div>
            </div>
          </div>
          <div class="card" style="margin-top:12px">
            <div class="card-title result-head"><span>事件紀錄 Logs</span><button id="clearLogsBtn">清除</button></div>
            <div id="logs" class="card-body logs"></div>
          </div>
        </div>
      </section>
    </main>
  </div>
  <script>
    const scenarios = {
      "付款卡關": {
        page_id: "payment_page", event_type: "payment_failed", button_id: "linepay_button",
        speech_text: "我不能刷 LINE Pay，付款一直失敗。", dwell_time_sec: 42,
        payment_fail_count: 1, coupon_error_count: 0, invalid_touch_count: 0, back_count: 0, cart_edit_count: 0,
        metadata: { source: "demo_ui", payment: "linepay", reason: "payment_failed" }
      },
      "操作困惑": {
        page_id: "menu_page", event_type: "page_dwell_timeout", button_id: "menu_grid",
        speech_text: "我看不懂怎麼點餐，可以教我嗎？", dwell_time_sec: 38,
        payment_fail_count: 0, coupon_error_count: 0, invalid_touch_count: 3, back_count: 0, cart_edit_count: 0,
        metadata: { source: "demo_ui", reason: "operation_confusion" }
      },
      "優惠券卡關": {
        page_id: "payment_page", event_type: "coupon_error", button_id: "coupon_input",
        speech_text: "優惠券掃碼不能用，折扣碼一直錯。", dwell_time_sec: 31,
        payment_fail_count: 0, coupon_error_count: 1, invalid_touch_count: 0, back_count: 0, cart_edit_count: 0,
        metadata: { source: "demo_ui", reason: "coupon_error" }
      },
      "等待不耐": {
        page_id: "menu_page", event_type: "customer_service_clicked", button_id: "service_button",
        speech_text: "我趕時間，等很久了，可以快一點嗎？", dwell_time_sec: 25,
        payment_fail_count: 0, coupon_error_count: 0, invalid_touch_count: 0, back_count: 0, cart_edit_count: 0,
        metadata: { source: "demo_ui", reason: "urgent_request" }
      }
    };
    const zhBarrier = {
      normal_operation: "正常操作", menu_hesitation: "菜單選擇猶豫", operation_confusion: "操作困惑",
      payment_confusion: "付款卡關", coupon_confusion: "優惠券或掃碼卡關", impatience_detected: "等待不耐",
      service_needed: "需要真人協助", potential_complaint: "疑似客訴", low_confidence: "資訊不足"
    };
    const zhAction = {
      none: "不介入", show_payment_tutorial: "顯示付款教學", show_coupon_guide: "顯示優惠券指引",
      show_operation_hint: "顯示操作提示", recommend_popular_combo: "推薦熱門組合",
      call_staff_or_fast_mode: "通知店員或快速模式", call_staff: "通知店員", ask_clarifying_question: "詢問釐清問題"
    };
    const $ = id => document.getElementById(id);
    $("sessionId").value = "demo_" + Math.floor(Date.now() / 1000);
    Object.keys(scenarios).forEach(name => {
      const option = document.createElement("option");
      option.value = name;
      option.textContent = name;
      $("scenario").appendChild(option);
    });
    function applyScenario() {
      const item = scenarios[$("scenario").value];
      $("pageId").value = item.page_id;
      $("eventType").value = item.event_type;
      $("buttonId").value = item.button_id;
      $("speechText").value = item.speech_text;
      $("dwellTime").value = item.dwell_time_sec;
      $("paymentFail").value = item.payment_fail_count;
      $("couponError").value = item.coupon_error_count;
      $("invalidTouch").value = item.invalid_touch_count;
      $("backCount").value = item.back_count;
      $("cartEdit").value = item.cart_edit_count;
      $("metadata").value = JSON.stringify(item.metadata, null, 2);
    }
    function readMetadata() {
      try { return JSON.parse($("metadata").value || "{}"); }
      catch { throw new Error("metadata 必須是有效 JSON"); }
    }
    function payload() {
      return {
        session_id: $("sessionId").value.trim(),
        page_id: $("pageId").value.trim(),
        event_type: $("eventType").value.trim(),
        button_id: $("buttonId").value.trim(),
        dwell_time_sec: Number($("dwellTime").value || 0),
        back_count: Number($("backCount").value || 0),
        invalid_touch_count: Number($("invalidTouch").value || 0),
        payment_fail_count: Number($("paymentFail").value || 0),
        coupon_error_count: Number($("couponError").value || 0),
        cart_edit_count: Number($("cartEdit").value || 0),
        idle_time_sec: 0,
        metadata: readMetadata(),
        ui_context: { page_id: $("pageId").value.trim(), cart_count: 0, promotion_paused: false, service_open: false }
      };
    }
    async function proxy(path, body) {
      const response = await fetch(path, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body)
      });
      const data = await response.json();
      if (!response.ok || data.status === "error") throw new Error(data.message || JSON.stringify(data));
      return data;
    }
    function addLog(text) {
      const row = document.createElement("div");
      row.className = "log";
      row.innerHTML = `<span>${new Date().toLocaleTimeString()}</span><strong>${text}</strong>`;
      $("logs").prepend(row);
    }
    function updateResult(data) {
      const barrier = data.barrier_state_response?.barrier_result || {};
      const intervention = data.barrier_state_response?.intervention || {};
      const risk = data.barrier_state_response?.risk_result || data.interaction_event_response?.risk_result || {};
      const score = Math.max(0, Math.min(100, Number(risk.risk_score || 0) * 10));
      $("riskScore").textContent = score;
      $("riskKnob").style.left = `calc(${score}% - 7px)`;
      $("riskLevel").textContent = score >= 70 ? "風險等級：高風險" : score >= 40 ? "風險等級：中風險" : "風險等級：低風險";
      $("riskLevel").style.color = score >= 70 ? "var(--red)" : score >= 40 ? "var(--orange)" : "var(--green)";
      $("barrierState").textContent = zhBarrier[barrier.barrier_state] || "-";
      $("barrierRaw").textContent = barrier.barrier_state || "-";
      $("actionState").textContent = zhAction[intervention.action] || "-";
      $("actionRaw").textContent = intervention.action || "-";
      $("responseBox").textContent = JSON.stringify(data, null, 2);
      $("status").textContent = "已完成";
    }
    async function sendEvent() {
      $("sendBtn").disabled = true;
      $("status").textContent = "送出中";
      try {
        const eventPayload = payload();
        const eventResult = await proxy("/proxy/interaction_event", eventPayload);
        addLog("互動事件已送出");
        const barrierPayload = {
          session_id: eventPayload.session_id,
          speech_text: $("speechText").value.trim(),
          ui_context: eventPayload.ui_context,
          emotion_structured: {},
          media_signals: {}
        };
        const barrierResult = await proxy("/proxy/barrier_state", barrierPayload);
        addLog("互動障礙狀態已推論");
        const combined = { interaction_event_response: eventResult, barrier_state_response: barrierResult };
        updateResult(combined);
        if ($("openAdminAfter").checked) window.open($("apiBase").value.replace(/\/$/, "") + "/?view=admin", "_blank");
      } catch (error) {
        $("status").textContent = "失敗";
        $("responseBox").textContent = String(error.message || error);
        addLog("送出失敗");
      } finally {
        $("sendBtn").disabled = false;
      }
    }
    $("scenario").addEventListener("change", applyScenario);
    $("sendBtn").addEventListener("click", sendEvent);
    $("resetBtn").addEventListener("click", applyScenario);
    $("clearLogsBtn").addEventListener("click", () => $("logs").innerHTML = "");
    $("openAdminBtn").addEventListener("click", () => window.open($("apiBase").value.replace(/\/$/, "") + "/?view=admin", "_blank"));
    $("helpBtn").addEventListener("click", () => alert("1. 先啟動 UI_API。\\n2. 選擇情境或修改欄位。\\n3. 按送出事件，本腳本會依序呼叫互動事件與互動障礙狀態 API。\\n4. 勾選後台選項可直接觀察 UI_API 儀表板更新。"));
    applyScenario();
  </script>
</body>
</html>
"""


class DemoHandler(BaseHTTPRequestHandler):
    api_base = DEFAULT_API_BASE

    def _send_json(self, status: int, payload: dict):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):  # noqa: N802
        if self.path in ("/", "/index.html"):
            body = HTML.replace("__API_BASE__", self.api_base).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        self._send_json(404, {"status": "error", "message": "not found"})

    def do_POST(self):  # noqa: N802
        path_map = {
            "/proxy/interaction_event": "/api/interaction_event",
            "/proxy/barrier_state": "/api/barrier_state",
        }
        target_path = path_map.get(self.path)
        if not target_path:
            self._send_json(404, {"status": "error", "message": "unknown proxy path"})
            return
        length = int(self.headers.get("Content-Length", "0") or 0)
        raw_body = self.rfile.read(length)
        try:
            target_url = self.api_base.rstrip("/") + target_path
            req = urllib.request.Request(
                target_url,
                data=raw_body,
                method="POST",
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=20) as resp:
                response_body = resp.read()
                self.send_response(resp.status)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(response_body)))
                self.end_headers()
                self.wfile.write(response_body)
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="ignore")
            self._send_json(exc.code, {"status": "error", "message": detail})
        except Exception as exc:
            self._send_json(502, {"status": "error", "message": f"無法連線到 UI_API：{exc}"})

    def log_message(self, fmt: str, *args):
        print(f"[demo-ui] {self.address_string()} - {fmt % args}")


def main():
    DemoHandler.api_base = DEFAULT_API_BASE
    server = ThreadingHTTPServer((DEMO_HOST, DEMO_PORT), DemoHandler)
    url = f"http://{DEMO_HOST}:{DEMO_PORT}/"
    print(f"✅ POS 互動障礙偵測測試介面已啟動：{url}")
    print(f"🔗 UI_API 目標：{DEFAULT_API_BASE}")
    webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止測試介面。")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
