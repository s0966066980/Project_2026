#!/usr/bin/env python3
"""
Project_2026 專利流程 Demo Tool 啟動器 (v2 - 含 CLI 驗證模式)

用途：
  - 開啟 UI_API 內建的 /demo-tool HTML 測試介面（含 PDF 流程驗證分頁）。
  - HTML 介面保留 PDF PoC 5 大情境，新增「PDF 流程驗證」分頁：
    自動執行 5 大情境並以 PASS/FAIL 表格呈現 barrier_state / intervention_action 驗證結果。

使用方式：
  1. 先啟動 UI_API：
       cd /home/oliver/Project_2026/UI_API
       conda activate emotion_ui
       python main.py

  2. 執行本工具（開啟瀏覽器）：
       cd /home/oliver/Project_2026
       python3 tools/pos_interaction_demo_ui.py

  3. 瀏覽器會開啟：
       http://127.0.0.1:8000/demo-tool

  4. CLI 驗證模式（不需瀏覽器）：
       python3 tools/pos_interaction_demo_ui.py --verify

選項：
  --api-base http://127.0.0.1:8000  指定 UI_API 位置
  --print-html                      輸出 demo-tool HTML，供 UI_API /demo-tool route 使用
  --verify                          CLI 模式：直接對 API 跑 5 大情境驗證並印 PASS/FAIL
"""

from __future__ import annotations

import argparse
import json
import sys
import textwrap
import urllib.request
import webbrowser


# ──────────────────────────────────────────────────────────────────────
# PDF 五大情境期望值 (對應 PDF 技術特徵 1/7~3/7 流程圖)
# ──────────────────────────────────────────────────────────────────────
_PDF_VERIFY_SCENARIOS = [
    {
        "id": "operation_confusion",
        "label": "問題1：不會操作機台",
        "pdf_category": "操作失敗、不會點餐",
        "speech": "我不會操作，不知道怎麼點餐。",
        "expect_triggered": True,
        "expect_barrier_states": ["operation_confusion"],
        "expect_actions": ["show_operation_hint"],
        "expect_patent_intervention": "operation_hint",
        "expect_staff_notify": False,
    },
    {
        "id": "decision_hesitation",
        "label": "問題2：無法決定餐點",
        "pdf_category": "困惑、無法決定餐點",
        "speech": "我不知道要吃什麼，可以推薦嗎？",
        "expect_triggered": True,
        "expect_barrier_states": ["menu_hesitation", "low_confidence"],
        "expect_actions": ["recommend_popular_combo", "ask_clarifying_question"],
        "expect_patent_intervention": "recommendation",
        "expect_staff_notify": False,
    },
    {
        "id": "payment_failed",
        "label": "問題3：付款失敗",
        "pdf_category": "操作失敗、不會點餐",
        "speech": "付款一直失敗，請協助我完成付款。",
        "expect_triggered": True,
        "expect_barrier_states": ["payment_confusion"],
        "expect_actions": ["show_payment_tutorial"],
        "expect_patent_intervention": "payment_tutorial",
        "expect_staff_notify": False,
    },
    {
        "id": "human_service",
        "label": "問題4：真人客服/客訴",
        "pdf_category": "詢問餐點、客服情況",
        "speech": "付款一直失敗，太誇張了，我要找經理客訴。",
        "expect_triggered": True,
        "expect_barrier_states": ["potential_complaint", "service_needed"],
        "expect_actions": ["call_staff", "call_staff_or_fast_mode"],
        "expect_patent_intervention": "human_service",
        "expect_staff_notify": True,
    },
    {
        "id": "low_risk",
        "label": "問題5：低風險正常操作",
        "pdf_category": "低風險 → 只記錄事件",
        "speech": "",
        "expect_triggered": False,
        "expect_barrier_states": ["normal_operation", None],
        "expect_actions": ["none", None],
        "expect_patent_intervention": "normal_interface",
        "expect_staff_notify": False,
    },
]


def _post_json_cli(api_base: str, path: str, payload: dict) -> dict:
    url = api_base.rstrip("/") + path
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        url, data=data, method="POST",
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read())


def _check(label: str, ok: bool, detail: str = "") -> str:
    mark = "✅ PASS" if ok else "❌ FAIL"
    line = f"  {mark}  {label}"
    if detail:
        line += f"  [{detail}]"
    return line


def _run_verify_cli(api_base: str) -> int:
    """CLI 驗證模式：呼叫 API 跑 5 大情境並印 PASS/FAIL。"""
    print(f"\n{'='*65}")
    print(f"Project_2026 PDF 流程驗證  API={api_base}")
    print(f"對應 PDF 技術特徵 1/7~3/7 流程圖")
    print(f"{'='*65}")
    passed = failed = 0

    for sc in _PDF_VERIFY_SCENARIOS:
        print(f"\n{'─'*60}")
        print(f"▶ {sc['label']}  (PDF分類: {sc['pdf_category']})")
        try:
            resp = _post_json_cli(api_base, "/api/demo/trigger_scenario", {
                "session_id": "cli_verify_session",
                "scenario": sc["id"],
                "speech_text": sc["speech"],
            })
        except Exception as e:
            print(f"  ❌ API 呼叫失敗: {e}")
            failed += 1
            continue

        risk   = resp.get("risk_result")    or {}
        barrier= resp.get("barrier_result") or {}
        interv = resp.get("intervention")   or {}

        actual_triggered = bool(risk.get("triggered"))
        actual_barrier   = barrier.get("barrier_state")
        actual_action    = interv.get("action")
        actual_staff     = bool(interv.get("staff_notify"))
        actual_patent    = interv.get("patent_intervention_type", "")
        risk_score       = risk.get("risk_score", 0)

        ok_t = actual_triggered == sc["expect_triggered"]
        ok_b = actual_barrier   in sc["expect_barrier_states"]
        ok_a = actual_action    in sc["expect_actions"]
        ok_s = actual_staff     == sc["expect_staff_notify"]
        ok_p = actual_patent    == sc["expect_patent_intervention"] or not actual_patent

        print(_check("S3 風險分數達門檻",
                     ok_t, f"triggered={actual_triggered}, score={risk_score}"))
        print(_check("S8 互動障礙狀態",
                     ok_b, f"實際={actual_barrier}, 期望={sc['expect_barrier_states']}"))
        print(_check("S9 介入動作",
                     ok_a, f"實際={actual_action}, 期望={sc['expect_actions']}"))
        print(_check("S9 真人客服通知",
                     ok_s, f"staff_notify={actual_staff}"))
        print(_check("S9 PDF介入類型",
                     ok_p, f"實際={actual_patent}, 期望={sc['expect_patent_intervention']}"))

        reasons = risk.get("trigger_reasons") or []
        if reasons:
            print(f"     trigger_reasons: {reasons}")

        checks = [ok_t, ok_b, ok_a, ok_s, ok_p]
        passed += sum(1 for c in checks if c)
        failed += sum(1 for c in checks if not c)

    print(f"\n{'='*65}")
    total = passed + failed
    print(f"驗證結果：PASS {passed}/{total}  FAIL {failed}/{total}")
    if failed == 0:
        print("🎉 全部通過！PDF 技術特徵 1/7~3/7 流程驗證完成。")
    else:
        print("⚠️  有項目未通過，請檢查上方 FAIL 項目。")
    print(f"{'='*65}\n")
    return 0 if failed == 0 else 1


HTML_CONTENT = r"""
<!doctype html>
<html lang="zh-Hant">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Project_2026 專利流程 Demo Tool</title>
  <style>
    :root{--bg:#f7f2eb;--panel:#fffdf8;--line:#ded2c5;--text:#1f2420;--muted:#6d756d;--accent:#e96545;--accent2:#66785d;--ok:#2f8a5f;--bad:#b94b4b;--warn:#b87927}
    *{box-sizing:border-box} body{margin:0;background:var(--bg);color:var(--text);font-family:"Noto Sans TC","Segoe UI",system-ui,sans-serif}.shell{width:min(1480px,calc(100vw - 32px));margin:16px auto;border:1px solid var(--line);border-radius:16px;background:rgba(255,255,255,.72);box-shadow:0 24px 60px rgba(45,35,24,.08);overflow:hidden}.titlebar{height:44px;display:flex;align-items:center;justify-content:center;border-bottom:1px solid var(--line);background:#f4eee7;font-weight:900;position:relative}.dots{position:absolute;left:22px;display:flex;gap:8px}.dots span{width:12px;height:12px;border-radius:999px}.red{background:#ff5f57}.yellow{background:#ffbd2e}.green{background:#28c840}header{padding:30px 34px 18px;display:flex;justify-content:space-between;gap:20px;align-items:flex-start}h1{margin:0;font-size:30px;line-height:1.2}p{color:var(--muted);margin:8px 0 0}.actions{display:flex;gap:10px;flex-wrap:wrap}button,input,textarea{font:inherit;border-radius:10px;border:1.5px solid var(--line);background:white;color:var(--text)}button{cursor:pointer;padding:12px 16px;font-weight:900}button.primary{background:var(--accent2);color:white;border-color:transparent}button.accent{background:var(--accent);color:white;border-color:transparent}button:disabled{opacity:.55;cursor:wait}main{display:grid;grid-template-columns:minmax(460px,.92fr) minmax(460px,1.08fr);gap:16px;padding:0 28px 28px}.panel{background:var(--panel);border:1.5px solid var(--line);border-radius:12px;overflow:hidden}.panel h2{margin:0;padding:16px 20px;border-bottom:1px solid var(--line);font-size:18px}.body{padding:18px 20px}.grid{display:grid;grid-template-columns:1fr 1fr;gap:14px 16px}label{display:grid;gap:7px;font-size:13px;font-weight:850}input,textarea{width:100%;padding:12px 13px;outline:none}textarea{min-height:92px;resize:vertical}.scenario-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px;margin-top:16px}.metric-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin-bottom:14px}.metric{border:1px solid var(--line);border-radius:12px;padding:14px 16px;background:white}.metric span{display:block;color:var(--muted);font-size:13px;font-weight:850}.metric b{display:block;font-size:34px;color:var(--accent);margin-top:8px}.metric small{display:block;color:var(--muted);margin-top:4px}pre{margin:0;padding:16px;overflow:auto;min-height:260px;max-height:430px;background:#f1ede6;border-radius:10px;color:#26332e;font-size:12px;line-height:1.5;user-select:text}.log{display:grid;gap:8px;max-height:300px;overflow:auto}.row{display:grid;grid-template-columns:84px 1fr;gap:10px;align-items:start;padding:10px 12px;border:1px solid var(--line);border-radius:8px;background:white;font-size:13px}.badge{display:inline-flex;width:fit-content;padding:4px 10px;border-radius:999px;background:#edf0e7;color:var(--accent2);font-size:12px;font-weight:900}.steps{white-space:pre-wrap;color:#36423c}.ok{color:var(--ok)}.bad{color:var(--bad)}@media(max-width:980px){main{grid-template-columns:1fr}.metric-grid,.grid{grid-template-columns:1fr}header{flex-direction:column}.scenario-grid{grid-template-columns:1fr}}
  </style>
</head>
<body>
  <div class="shell">
    <div class="titlebar"><div class="dots"><span class="red"></span><span class="yellow"></span><span class="green"></span></div>Project_2026 POS 專利流程測試工具</div>
    <header>
      <div>
        <h1>事件觸發式 POS 顧客互動障礙偵測 Demo</h1>
        <p>此工具只保留專利 PoC 測試問題：POS 操作異常 → risk_score → barrier_state → intervention_action → realtime 推送。</p>
      </div>
      <div class="actions">
        <button id="openPosBtn">開啟 POS</button>
        <button id="openAdminBtn">開啟後台</button>
        <button id="connectWsBtn" class="primary">連線 WebSocket</button>
      </div>
    </header>
    <main>
      <section class="panel">
        <h2>測試設定</h2>
        <div class="body">
          <div class="grid">
            <label>API Base URL<input id="apiBase" value="http://127.0.0.1:8000"></label>
            <label>Admin URL<input id="adminBase" value="http://127.0.0.1:8001"></label>
            <label>Session ID<input id="sessionId" value="pos_demo_001"></label>
            <label>WebSocket Token<input id="wsToken" value="ws-demo-token"></label>
            <label>POS Token<input id="posToken" value="pos-demo-token"></label>
            <label>Admin Token<input id="adminToken" value="admin-demo-token"></label>
          </div>
          <label style="margin-top:14px">顧客語音文字 speech_text<textarea id="speechText">我不會操作，不知道怎麼點餐。</textarea></label>
          <div class="scenario-grid">
            <button class="accent" data-scenario="operation_confusion" data-speech="我不會操作，不知道怎麼點餐。">問題 1：不會操作</button>
            <button data-scenario="decision_hesitation" data-speech="我不知道要吃什麼，可以推薦嗎？">問題 2：無法決定餐點</button>
            <button data-scenario="payment_failed" data-speech="我不能刷卡，付款一直失敗。">問題 3：付款失敗</button>
            <button data-scenario="human_service" data-speech="付款一直失敗，太誇張了，我要找經理客訴。">問題 4：真人客服 / 客訴</button>
            <button data-scenario="low_risk" data-speech="">問題 5：低風險正常操作</button>
            <button id="shortClipBtn">短片段 fallback</button>
            <button id="recommendBtn">AI 主動推薦</button>
            <button id="clearBtn">清空輸出</button>
          </div>
        </div>
      </section>
      <section class="panel">
        <h2>辨識結果</h2>
        <div class="body">
          <div class="metric-grid">
            <div class="metric"><span>風險分數</span><b id="riskScore">-</b><small id="riskTriggered">triggered=-</small></div>
            <div class="metric"><span>互動障礙狀態</span><b id="barrierState" style="font-size:22px;color:var(--text)">-</b></div>
            <div class="metric"><span>介入動作</span><b id="actionName" style="font-size:22px;color:var(--accent2)">-</b></div>
          </div>
          <pre id="responseBox">{}</pre>
        </div>
      </section>
      <section class="panel">
        <h2>Realtime 事件</h2>
        <div class="body"><span id="wsStatus" class="badge">未連線</span><div id="eventLog" class="log" style="margin-top:12px"></div></div>
      </section>
      <section class="panel">
        <h2>專利流程對照 (PDF 技術特徵 1~3/7)</h2>
        <div class="body"><div class="steps">S1 POS端短時間 rolling buffer (media_buffer.js)，不長期保存原始影像
S2 送出 POS 操作事件 → POST /api/interaction_event
   欄位: event_type / dwell_time_sec / back_count / invalid_touch_count / payment_fail_count
S3 後端計算 risk_score 與 trigger_reasons
   interaction_event_service.calculate_interaction_risk()
   ├─ 否 → 儲存低風險事件 (interaction_events.json)
   └─ 是 → 觸發多模態 → POST /api/triggered_multimodal_analysis
S4 達門檻時擷取事件前後短片段
S5 媒體有效性 (ffprobe)
   ├─ 無效 → fallback POS events
   └─ 有效繼續
S6 Whisper STT + Emotion-LLaMA（多模態證據來源）
S7 multimodal_evidence_service.build_multimodal_evidence()
S8 barrier_state_service.infer_barrier_state()
   → operation_confusion / payment_confusion / menu_hesitation / ...
S9 intervention_service.decide_intervention() → 介入動作
   需要真人客服？ 是 → staff_notify  否 → 即時推播
S10 event_bus WebSocket 推送 POS + Admin
S11 POST /api/checkout → 回寫 resolved_by_checkout / time_to_checkout_sec</div></div>
      </section>
      <section class="panel" style="grid-column:1/-1">
        <h2>PDF 流程驗證 (自動比對 PASS / FAIL)</h2>
        <div class="body">
          <div style="display:flex;gap:10px;margin-bottom:14px;align-items:center">
            <button id="runAllVerifyBtn" style="background:#3a5ca8;color:white;border-color:transparent">▶ 執行全部 5 大情境驗證</button>
            <button id="clearVerifyBtn">清空</button>
            <span id="verifySummary" style="font-size:13px;color:#6d756d">尚未執行驗證</span>
          </div>
          <div style="overflow-x:auto">
            <table id="verifyTable" style="width:100%;border-collapse:collapse;font-size:12px">
              <thead>
                <tr style="background:#f0ebe3;border-bottom:2px solid #ded2c5">
                  <th style="padding:7px 11px;text-align:left">情境</th>
                  <th style="padding:7px 11px;text-align:left">PDF分類</th>
                  <th style="padding:7px 11px">S3 達門檻</th>
                  <th style="padding:7px 11px">S8 障礙狀態</th>
                  <th style="padding:7px 11px">S9 介入動作</th>
                  <th style="padding:7px 11px">S9 真人通知</th>
                  <th style="padding:7px 11px">總結</th>
                </tr>
              </thead>
              <tbody id="verifyBody">
                <tr id="vr-operation_confusion"><td style="padding:7px 11px">問題1：不會操作</td><td style="padding:7px 11px;color:#6d756d">操作失敗、不會點餐</td><td style="padding:7px 11px;text-align:center;color:#6d756d">-</td><td style="padding:7px 11px;text-align:center;color:#6d756d">-</td><td style="padding:7px 11px;text-align:center;color:#6d756d">-</td><td style="padding:7px 11px;text-align:center;color:#6d756d">-</td><td style="padding:7px 11px;text-align:center;color:#6d756d">待驗證</td></tr>
                <tr id="vr-decision_hesitation"><td style="padding:7px 11px">問題2：無法決定餐點</td><td style="padding:7px 11px;color:#6d756d">困惑、無法決定餐點</td><td style="padding:7px 11px;text-align:center;color:#6d756d">-</td><td style="padding:7px 11px;text-align:center;color:#6d756d">-</td><td style="padding:7px 11px;text-align:center;color:#6d756d">-</td><td style="padding:7px 11px;text-align:center;color:#6d756d">-</td><td style="padding:7px 11px;text-align:center;color:#6d756d">待驗證</td></tr>
                <tr id="vr-payment_failed"><td style="padding:7px 11px">問題3：付款失敗</td><td style="padding:7px 11px;color:#6d756d">操作失敗、不會點餐</td><td style="padding:7px 11px;text-align:center;color:#6d756d">-</td><td style="padding:7px 11px;text-align:center;color:#6d756d">-</td><td style="padding:7px 11px;text-align:center;color:#6d756d">-</td><td style="padding:7px 11px;text-align:center;color:#6d756d">-</td><td style="padding:7px 11px;text-align:center;color:#6d756d">待驗證</td></tr>
                <tr id="vr-human_service"><td style="padding:7px 11px">問題4：真人客服/客訴</td><td style="padding:7px 11px;color:#6d756d">詢問餐點、客服情況</td><td style="padding:7px 11px;text-align:center;color:#6d756d">-</td><td style="padding:7px 11px;text-align:center;color:#6d756d">-</td><td style="padding:7px 11px;text-align:center;color:#6d756d">-</td><td style="padding:7px 11px;text-align:center;color:#6d756d">-</td><td style="padding:7px 11px;text-align:center;color:#6d756d">待驗證</td></tr>
                <tr id="vr-low_risk"><td style="padding:7px 11px">問題5：低風險正常</td><td style="padding:7px 11px;color:#6d756d">低風險→只記錄事件</td><td style="padding:7px 11px;text-align:center;color:#6d756d">-</td><td style="padding:7px 11px;text-align:center;color:#6d756d">-</td><td style="padding:7px 11px;text-align:center;color:#6d756d">-</td><td style="padding:7px 11px;text-align:center;color:#6d756d">-</td><td style="padding:7px 11px;text-align:center;color:#6d756d">待驗證</td></tr>
              </tbody>
            </table>
          </div>
        </div>
      </section>
    </main>
  </div>
<script>
const $ = id => document.getElementById(id);
let ws = null;
function base(){ return $('apiBase').value.trim().replace(/\/$/, ''); }
function adminBase(){ return $('adminBase').value.trim().replace(/\/$/, ''); }
function sessionId(){ return $('sessionId').value.trim() || 'pos_demo_001'; }
function tokenQuery(token, prefix='?'){ return token ? `${prefix}token=${encodeURIComponent(token)}` : ''; }
function log(kind,msg){ const row=document.createElement('div'); row.className='row'; row.innerHTML=`<b>${new Date().toLocaleTimeString()}</b><div><span class="badge">${kind}</span><pre style="min-height:0;max-height:180px;margin-top:8px">${escapeHtml(typeof msg==='string'?msg:JSON.stringify(msg,null,2))}</pre></div>`; $('eventLog').prepend(row); }
function escapeHtml(s){ return String(s??'').replace(/[&<>"']/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m])); }
function updateResult(data){ const risk=data.risk_result||{}; const barrier=data.barrier_result||{}; const intervention=data.intervention||{}; $('riskScore').textContent = risk.risk_score ?? '-'; $('riskTriggered').textContent = `triggered=${risk.triggered ?? '-'}`; $('barrierState').textContent = barrier.barrier_state || '-'; $('actionName').textContent = intervention.action || '-'; $('responseBox').textContent = JSON.stringify(data,null,2); }
async function postJson(path,payload){ const res=await fetch(`${base()}${path}`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)}); const data=await res.json(); updateResult(data); log('HTTP',data); return data; }
async function triggerScenario(scenario,speech){ $('speechText').value=speech||$('speechText').value; await postJson('/api/demo/trigger_scenario',{session_id:sessionId(),scenario,speech_text:$('speechText').value}); }
function wsUrl(){ const u=new URL(base()); u.protocol = u.protocol === 'https:' ? 'wss:' : 'ws:'; u.pathname = `/ws/demo/${encodeURIComponent(sessionId())}`; const token=$('wsToken').value.trim(); if(token) u.searchParams.set('token',token); return u.toString(); }
function connectWs(){ if(ws) ws.close(); ws=new WebSocket(wsUrl()); $('wsStatus').textContent='連線中'; ws.onopen=()=>{ $('wsStatus').textContent='已連線'; ws.send(JSON.stringify({type:'ping'})); }; ws.onmessage=e=>{ try{ log('WS',JSON.parse(e.data)); }catch{ log('WS',e.data); } }; ws.onerror=()=>{$('wsStatus').textContent='連線錯誤'}; ws.onclose=e=>{$('wsStatus').textContent=`已斷線 ${e.code||''}`}; }
document.querySelectorAll('[data-scenario]').forEach(btn=>btn.onclick=()=>triggerScenario(btn.dataset.scenario,btn.dataset.speech));
$('shortClipBtn').onclick=async()=>{ const fd=new FormData(); fd.append('session_id',sessionId()); fd.append('video',new Blob(['tiny'],{type:'video/webm'}),'tiny.webm'); fd.append('risk_result_json',JSON.stringify({risk_score:7,triggered:true,threshold:5,trigger_reasons:['demo tiny clip fallback']})); fd.append('ui_context_json',JSON.stringify({page_id:'payment_page',cart_count:1})); fd.append('interaction_context','Demo tiny clip fallback test'); const res=await fetch(`${base()}/api/triggered_multimodal_analysis`,{method:'POST',body:fd}); const data=await res.json(); updateResult(data); log('HTTP',data); };
$('recommendBtn').onclick=async()=>{ const fd=new FormData(); fd.append('session_id',sessionId()); fd.append('ab_mode','single'); const res=await fetch(`${base()}/api/auto_recommend`,{method:'POST',body:fd}); const data=await res.json(); $('responseBox').textContent=JSON.stringify(data,null,2); log('HTTP',data); };
$('openPosBtn').onclick=()=>window.open(`${base()}/pos?session_id=${encodeURIComponent(sessionId())}${tokenQuery($('posToken').value.trim(),'&')}`,'_blank');
$('openAdminBtn').onclick=()=>window.open(`${adminBase()}/admin${tokenQuery($('adminToken').value.trim())}`,'_blank');
$('connectWsBtn').onclick=connectWs; $('clearBtn').onclick=()=>{ $('eventLog').innerHTML=''; $('responseBox').textContent='{}'; updateResult({}); };

// ── PDF 流程驗證 ──
const PDF_VERIFY_SCENARIOS = [
  { id:'operation_confusion', speech:'我不會操作，不知道怎麼點餐。',
    eT:true,  eB:['operation_confusion'],         eA:['show_operation_hint'],                      eS:false },
  { id:'decision_hesitation', speech:'我不知道要吃什麼，可以推薦嗎？',
    eT:true,  eB:['menu_hesitation','low_confidence'], eA:['recommend_popular_combo','ask_clarifying_question'], eS:false },
  { id:'payment_failed',      speech:'付款一直失敗，請協助我完成付款。',
    eT:true,  eB:['payment_confusion'],           eA:['show_payment_tutorial'],                    eS:false },
  { id:'human_service',       speech:'付款一直失敗，太誇張了，我要找經理客訴。',
    eT:true,  eB:['potential_complaint','service_needed'], eA:['call_staff','call_staff_or_fast_mode'], eS:true },
  { id:'low_risk',            speech:'',
    eT:false, eB:['normal_operation',null],       eA:['none',null],                                eS:false },
];

function vCell(ok, actual, expected) {
  const exp = Array.isArray(expected) ? expected.join('/') : String(expected);
  const val = actual === null ? 'null' : String(actual ?? '-');
  return `${ok ? '✅' : '❌'} ${val} <small style="color:#6d756d">(${exp})</small>`;
}

async function runOneVerify(sc) {
  const row = $(`vr-${sc.id}`);
  if (!row) return false;
  const cells = [...row.querySelectorAll('td')];
  [2,3,4,5,6].forEach(i => { cells[i].style.color='#b87927'; cells[i].textContent='⋯'; });
  let data;
  try {
    const res = await fetch(`${base()}/api/demo/trigger_scenario`, {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({ session_id:'verify_session', scenario:sc.id, speech_text:sc.speech }),
    });
    data = await res.json();
  } catch(e) {
    cells[6].style.color='var(--bad)'; cells[6].textContent=`❌ ${e}`; return false;
  }
  const risk   = data.risk_result    || {};
  const barrier= data.barrier_result || {};
  const interv = data.intervention   || {};
  const aT = !!risk.triggered, aB = barrier.barrier_state??null, aA = interv.action??null, aS = !!interv.staff_notify;
  const okT=aT===sc.eT, okB=sc.eB.includes(aB), okA=sc.eA.includes(aA), okS=aS===sc.eS;
  cells[2].style.color = okT?'var(--ok)':'var(--bad)'; cells[2].innerHTML = vCell(okT,aT,sc.eT);
  cells[3].style.color = okB?'var(--ok)':'var(--bad)'; cells[3].innerHTML = vCell(okB,aB,sc.eB);
  cells[4].style.color = okA?'var(--ok)':'var(--bad)'; cells[4].innerHTML = vCell(okA,aA,sc.eA);
  cells[5].style.color = okS?'var(--ok)':'var(--bad)'; cells[5].innerHTML = vCell(okS,aS,sc.eS);
  const allOk = okT&&okB&&okA&&okS;
  cells[6].style.color = allOk?'var(--ok)':'var(--bad)';
  cells[6].textContent = allOk ? '✅ PASS' : '❌ FAIL';
  return allOk;
}

if ($('runAllVerifyBtn')) {
  $('runAllVerifyBtn').onclick = async () => {
    $('runAllVerifyBtn').disabled = true;
    $('verifySummary').style.color='#b87927'; $('verifySummary').textContent='驗證執行中…';
    let pass=0, fail=0;
    for (const sc of PDF_VERIFY_SCENARIOS) { (await runOneVerify(sc)) ? pass++ : fail++; }
    $('runAllVerifyBtn').disabled = false;
    const total = pass+fail;
    if (fail===0) {
      $('verifySummary').style.color='var(--ok)';
      $('verifySummary').textContent=`🎉 全部通過  PASS ${pass}/${total}  — PDF 技術特徵 1~3/7 流程驗證完成`;
    } else {
      $('verifySummary').style.color='var(--bad)';
      $('verifySummary').textContent=`⚠️  PASS ${pass}/${total}  FAIL ${fail}/${total}`;
    }
  };
}
if ($('clearVerifyBtn')) {
  $('clearVerifyBtn').onclick = () => {
    document.querySelectorAll('#verifyBody td').forEach(td => { td.style.color='#6d756d'; td.textContent='-'; });
    document.querySelectorAll('#verifyBody tr').forEach(tr => { [...tr.cells][6].textContent='待驗證'; });
    $('verifySummary').style.color='#6d756d'; $('verifySummary').textContent='尚未執行驗證';
  };
}

connectWs();
</script>
</body>
</html>
"""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Project_2026 Demo Tool v2")
    parser.add_argument("--api-base", default="http://127.0.0.1:8000", help="UI_API base URL")
    parser.add_argument("--print-html", action="store_true", help="print embedded demo-tool HTML")
    parser.add_argument(
        "--verify", action="store_true",
        help="CLI 驗證模式：直接對 API 跑 5 大情境驗證並印 PASS/FAIL",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.print_html:
        sys.stdout.write(HTML_CONTENT.strip() + "\n")
        return 0
    if args.verify:
        return _run_verify_cli(args.api_base)
    url = args.api_base.rstrip("/") + "/demo-tool"
    print(textwrap.dedent(f"""
    Project_2026 Demo Tool v2
    - UI_API:    {args.api_base.rstrip('/')}
    - Browser:   {url}
    - CLI驗證:   python3 tools/pos_interaction_demo_ui.py --verify
    """).strip())
    opened = webbrowser.open(url)
    if not opened:
        print(f"請手動開啟：{url}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
