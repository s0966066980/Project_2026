#!/usr/bin/env python3
"""
Project_2026 專利流程 Demo Tool 啟動器

用途：
  - 開啟 UI_API 內建的 /demo-tool HTML 測試介面。
  - HTML 介面只保留專利 PoC 需要的事件觸發測試：
    操作困惑、付款卡關、優惠券卡關、客訴風險、短片段 fallback、AI 主動推薦。

使用方式：
  1. 先啟動 UI_API：
       cd /home/oliver/Project_2026/UI_API
       conda activate emotion_ui
       python main.py

  2. 執行本工具：
       cd /home/oliver/Project_2026
       python3 tools/pos_interaction_demo_ui.py

  3. 瀏覽器會開啟：
       http://127.0.0.1:8000/demo-tool

選項：
  --api-base http://127.0.0.1:8000  指定 UI_API 位置
  --print-html                      輸出 demo-tool HTML，供 UI_API /demo-tool route 使用
"""

from __future__ import annotations

import argparse
import sys
import textwrap
import webbrowser


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
        <h2>專利流程對照</h2>
        <div class="body"><div class="steps">S1 POS 端短時間 rolling buffer，不長期保存原始影像
S2 送出付款失敗、優惠券錯誤、無效點擊等 POS 事件
S3 後端計算 risk_score 與 trigger_reasons
S4 達門檻時可擷取事件前後短片段
S5 先做人物偵測與媒體有效性檢查
S6 Whisper / Emotion-LLaMA 僅作為多模態證據來源
S7 建立 multimodal_evidence
S8 推理 barrier_state
S9 產生 intervention_action
S10 WebSocket 推送 POS / Admin / Demo
S11 checkout 後回寫 intervention_result</div></div>
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
connectWs();
</script>
</body>
</html>
"""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Open Project_2026 demo-tool HTML")
    parser.add_argument("--api-base", default="http://127.0.0.1:8000", help="UI_API base URL")
    parser.add_argument("--print-html", action="store_true", help="print embedded demo-tool HTML")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.print_html:
        sys.stdout.write(HTML_CONTENT.strip() + "\n")
        return 0
    url = args.api_base.rstrip("/") + "/demo-tool"
    print(textwrap.dedent(f"""
    Project_2026 Demo Tool
    - UI_API: {args.api_base.rstrip('/')}
    - Browser: {url}
    """).strip())
    opened = webbrowser.open(url)
    if not opened:
        print(f"請手動開啟：{url}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
