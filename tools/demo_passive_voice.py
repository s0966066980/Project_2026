"""
被動語音關鍵詞偵測 Web Demo（本地 Whisper 版）
- 瀏覽器 MediaRecorder 錄音 → WebSocket → 本地 Whisper STT → 關鍵詞比對
- 支援即時切換 Whisper 模型大小

執行方式：見 tools/README.md 的臨時 Docker container 指令。
"""
import json
import os
import re
import subprocess
import tempfile
import time
from pathlib import Path
from dotenv import load_dotenv

_SCRIPT_DIR = Path(__file__).resolve().parent
_REPO_DIR = _SCRIPT_DIR.parent
_UI_API_DIR = _REPO_DIR / "UI_API"
load_dotenv(_UI_API_DIR / ".env")

MENU_PATH        = _UI_API_DIR / "backend" / "capabilities" / "catalog" / "seed" / "menu.json"
SETTINGS_PATH    = _UI_API_DIR / "learning_data" / "settings.json"
DEMO_PORT        = int(os.getenv("DEMO_PORT", "8088"))
DEFAULT_KEYWORDS = ["找不到", "在哪裡", "哪邊有", "哪裡有", "哪裡可以"]
COOLDOWN_SEC     = 10
WHISPER_SIZES    = ["tiny", "base", "small", "medium", "large"]
DEFAULT_SIZE     = "small"
CHUNK_MS         = 5000   # 預設 chunk 長度（毫秒），較長減少句子被截斷的機率


# ── 工具 ──────────────────────────────────────────────────────
def _normalize(s: str) -> str:
    return re.sub(r"[™©\s]", "", s).replace("鷄", "雞")


def load_keywords() -> list[str]:
    try:
        with open(SETTINGS_PATH, encoding="utf-8") as f:
            s = json.load(f)
        kws = s.get("PASSIVE_VOICE_KEYWORDS")
        if isinstance(kws, list) and kws:
            return kws
    except Exception:
        pass
    return DEFAULT_KEYWORDS


def load_menu() -> list[dict]:
    try:
        with open(MENU_PATH, encoding="utf-8") as f:
            data = json.load(f)
        items = data if isinstance(data, list) else data.get("items", [])
        return [i for i in items if i.get("id") and i.get("name")]
    except Exception as e:
        print(f"[Demo] ⚠ 菜單載入失敗：{e}")
        return []


# ── 全域狀態 ──────────────────────────────────────────────────
_keywords:        list[str]   = []
_menu:            list[dict]  = []
_norm_menu:       list[tuple] = []   # (item, norm_full_name)
_match_index:     list[tuple] = []   # (item, form_str, form_label) — 擴展後的所有可比對形式
_last_trigger:    float       = 0.0
_whisper_prompt:  str         = ""
_last_transcript: str         = ""

# 常見尾綴，去除後作為短形（例：麥香魚堡 → 麥香魚）
_SUFFIXES = ["套餐", "堡", "排", "雞", "翅", "餅", "捲", "球", "飯", "麵", "杯", "桶", "盒", "組", "包"]


def _short_forms(norm_name: str) -> list[str]:
    """從品項正規化名稱產生可能的口語短形。"""
    forms = []
    # 去除一個尾綴
    for sfx in _SUFFIXES:
        if norm_name.endswith(sfx) and len(norm_name) - len(sfx) >= 2:
            forms.append(norm_name[: -len(sfx)])
            break
    # 去除兩個尾綴（例：麥辣雞腿堡 → 麥辣雞腿 → 麥辣雞）
    for form in forms[:]:
        for sfx in _SUFFIXES:
            if form.endswith(sfx) and len(form) - len(sfx) >= 2:
                forms.append(form[: -len(sfx)])
                break
    # 前 N 字（≥ 4 字的品項取前 3 字，避免誤觸）
    if len(norm_name) >= 4:
        forms.append(norm_name[:3])
    return list(dict.fromkeys(forms))  # 去重保序


def build_match_index(menu: list[dict], aliases: dict[str, list[str]]) -> list[tuple]:
    """
    為每個品項建立所有可比對形式：
      - 完整正規化名稱
      - 自動短形（去除尾綴）
      - Admin 設定的別名
    回傳 list of (item, form, label)
    """
    index = []
    for item in menu:
        norm_name = _normalize(item.get("name", ""))
        if not norm_name:
            continue
        forms = [(norm_name, "完整名稱")]
        for sf in _short_forms(norm_name):
            forms.append((sf, f"短形「{sf}」"))
        for alias in aliases.get(item["id"], []):
            norm_alias = _normalize(alias)
            if norm_alias:
                forms.append((norm_alias, f"別名「{alias}」"))
        for form, label in forms:
            index.append((item, form, label))
    return index


def _item_payload(item: dict) -> dict:
    return {
        "id":    item.get("id"),
        "name":  item.get("name"),
        "price": item.get("price"),
        "image": item.get("official_image_url") or item.get("image", ""),
    }


def load_aliases() -> dict[str, list[str]]:
    """從 settings.json 讀取 PASSIVE_VOICE_ALIASES：{"MCDxxx": ["別名1", ...]}"""
    try:
        with open(SETTINGS_PATH, encoding="utf-8") as f:
            s = json.load(f)
        raw = s.get("PASSIVE_VOICE_ALIASES", {})
        if isinstance(raw, dict):
            return {k: v for k, v in raw.items() if isinstance(v, list)}
    except Exception:
        pass
    return {}


# ── 比對邏輯 ──────────────────────────────────────────────────
def check_transcript(transcript: str) -> dict:
    global _last_trigger
    if not transcript.strip():
        return {"status": "empty"}

    now = time.time()
    if now - _last_trigger < COOLDOWN_SEC:
        return {
            "status":        "cooldown",
            "cooldown_left": round(COOLDOWN_SEC - (now - _last_trigger), 1),
        }

    matched_kw = next((kw for kw in _keywords if kw and kw in transcript), None)
    if not matched_kw:
        return {"status": "no_keyword"}

    norm_t = _normalize(transcript)
    # 依長度降序搜尋，優先匹配最長（最精確）的形式
    hit = next(
        ((item, form, label) for item, form, label in
         sorted(_match_index, key=lambda x: len(x[1]), reverse=True)
         if form and form in norm_t),
        None,
    )
    if not hit:
        return {"status": "no_item", "keyword": matched_kw, "norm": norm_t}

    matched, matched_form, matched_label = hit
    _last_trigger = now
    return {
        "status":        "hit",
        "keyword":       matched_kw,
        "matched_form":  matched_form,
        "matched_label": matched_label,
        "item":          _item_payload(matched),
    }


# ── Whisper ────────────────────────────────────────────────────
import threading

_whisper_model      = None
_whisper_model_size = DEFAULT_SIZE
_whisper_ready      = threading.Event()   # set() 後才允許辨識
_whisper_lock       = threading.Lock()


def get_whisper(size: str | None = None):
    global _whisper_model, _whisper_model_size
    target = size or _whisper_model_size
    with _whisper_lock:
        if _whisper_model is not None and _whisper_model_size == target:
            return _whisper_model
        _whisper_ready.clear()
        print(f"[Demo] 載入 Whisper {target} 模型…")
        from faster_whisper import WhisperModel
        _whisper_model      = WhisperModel(target, device="cpu", compute_type="int8")
        _whisper_model_size = target
        _whisper_ready.set()
        print(f"[Demo] ✅ Whisper {target} 就緒")
        return _whisper_model


def _preload_whisper(size: str):
    """在背景執行緒預載模型，不阻塞主程式。"""
    get_whisper(size)


def transcribe_bytes(audio_bytes: bytes) -> str:
    global _last_transcript
    with tempfile.NamedTemporaryFile(suffix=".webm", delete=False) as f:
        f.write(audio_bytes)
        tmp_path = f.name
    try:
        # initial_prompt = 菜單詞彙偏好 + 上一段末尾（rolling context）
        # 兩者合併讓 Whisper 在同音字中優先選餐廳相關詞，並銜接被切斷的句子
        prompt_parts = []
        if _whisper_prompt:
            prompt_parts.append(_whisper_prompt)
        if _last_transcript:
            # 只取最後 30 字，避免 prompt 太長
            prompt_parts.append(_last_transcript[-30:])
        prompt = "".join(prompt_parts) or None

        segs, _ = get_whisper().transcribe(
            tmp_path, language="zh", beam_size=1,
            vad_filter=True, without_timestamps=True,
            initial_prompt=prompt,
        )
        text = "".join(s.text for s in segs).strip()
        _last_transcript = text
        return text
    finally:
        try:
            os.remove(tmp_path)
        except OSError:
            pass


# ── FastAPI ────────────────────────────────────────────────────
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse
import uvicorn
import asyncio

app = FastAPI()


@app.get("/", response_class=HTMLResponse)
async def index():
    return HTMLResponse(_HTML)


@app.get("/api/keywords")
async def api_keywords():
    return {
        "keywords":    _keywords,
        "menu_count":  len(_menu),
        "model_size":  _whisper_model_size,
        "model_sizes": WHISPER_SIZES,
    }


@app.post("/api/set_model")
async def api_set_model(payload: dict):
    size = payload.get("size", "").strip().lower()
    if size not in WHISPER_SIZES:
        return JSONResponse(status_code=400, content={"error": f"無效的模型大小，可選：{WHISPER_SIZES}"})
    if size == _whisper_model_size and _whisper_model is not None:
        return {"status": "already_loaded", "model_size": size}
    print(f"[Demo] 切換 Whisper 模型：{_whisper_model_size} → {size}")
    await asyncio.to_thread(get_whisper, size)   # 切換時仍需等待，避免錄音途中換模型
    return {"status": "ok", "model_size": size}


@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket):
    await ws.accept()
    # 若模型還在背景載入中，先通知前端等待
    if not _whisper_ready.is_set():
        await ws.send_json({"type": "loading", "msg": f"Whisper {_whisper_model_size} 載入中，請稍候…"})
        await asyncio.to_thread(_whisper_ready.wait)
    await ws.send_json({
        "type": "ready",
        "msg": f"Whisper {_whisper_model_size} 就緒，可以開始錄音",
        "model_size": _whisper_model_size,
    })
    try:
        while True:
            data = await ws.receive_bytes()
            await ws.send_json({"type": "processing", "msg": f"Whisper {_whisper_model_size} 辨識中…"})
            transcript = await asyncio.to_thread(transcribe_bytes, data)
            result = check_transcript(transcript)
            result["type"]       = "result"
            result["transcript"] = transcript
            result["model_size"] = _whisper_model_size
            await ws.send_json(result)
    except WebSocketDisconnect:
        pass


# ── HTML ──────────────────────────────────────────────────────
_HTML = """<!DOCTYPE html>
<html lang="zh-TW">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>被動語音 Demo（Whisper）</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:sans-serif;background:#f5f7fa;color:#222;padding:16px;max-width:620px;margin:auto}
h1{font-size:19px;margin-bottom:14px;color:#3b7aee}
.card{background:#fff;border-radius:12px;padding:18px;margin-bottom:12px;
      box-shadow:0 2px 8px rgba(0,0,0,.08)}
.card h2{font-size:11px;font-weight:700;color:#8494b0;margin-bottom:10px;
         letter-spacing:.5px;text-transform:uppercase}
button{background:#3b7aee;color:#fff;border:none;border-radius:8px;padding:11px 26px;
       font-size:15px;cursor:pointer}
button:hover{background:#2a5ecc}
button.active{background:#e53e3e}
button:disabled{background:#bbb;cursor:not-allowed}
#status{margin-top:7px;font-size:13px;color:#8494b0;min-height:18px}
#transcript{font-size:15px;min-height:32px;padding:8px 10px;background:#f0f4ff;
            border-radius:8px;margin-top:8px;word-break:break-all}
.kw-badge{display:inline-block;background:#eef2ff;color:#3b7aee;border-radius:5px;
          padding:3px 8px;font-size:12px;margin:2px}

/* 模型選擇 */
.model-row{display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin-top:4px}
.model-btn{background:#f0f4ff;color:#3b7aee;border:2px solid transparent;border-radius:8px;
           padding:7px 16px;font-size:13px;cursor:pointer;font-weight:600;transition:.15s}
.model-btn:hover{background:#dce8ff}
.model-btn.selected{border-color:#3b7aee;background:#dce8ff}
.model-btn:disabled{opacity:.5;cursor:not-allowed}
#modelStatus{font-size:12px;color:#8494b0;margin-top:6px;min-height:16px}

/* 冷卻條 */
#cooldownBar{display:none;margin-top:8px}
#cooldownTrack{height:6px;background:#f0f0f0;border-radius:3px;overflow:hidden}
#cooldownFill{height:100%;background:#f5a623;border-radius:3px;transition:width .9s linear}
#cooldownLabel{font-size:11px;color:#856404;margin-top:3px}

/* log */
#log-wrap{max-height:320px;overflow-y:auto}
#log-hint{font-size:10px;color:#bbb;padding:3px 4px 0;margin-bottom:2px}
.log-row{border-bottom:1px solid #f0f4ff;padding:7px 4px;font-size:12px}
.log-ts{font-size:10px;color:#bbb;margin-bottom:2px}
.log-tr{color:#333;margin-bottom:3px;word-break:break-all}
.tag-hit {display:inline-block;background:#d4f4e8;color:#0a7a4a;border-radius:4px;padding:1px 7px;font-weight:700}
.tag-miss{display:inline-block;background:#fce8ec;color:#c0392b;border-radius:4px;padding:1px 7px}
.tag-skip{display:inline-block;background:#f0f0f0;color:#888;border-radius:4px;padding:1px 7px}
.tag-cool{display:inline-block;background:#fff3cd;color:#856404;border-radius:4px;padding:1px 7px}

/* Modal */
.modal{display:none;position:fixed;inset:0;background:rgba(0,0,0,.55);
       justify-content:center;align-items:center;z-index:99}
.modal.show{display:flex}
.mcard{background:#fff;border-radius:16px;padding:24px;max-width:320px;
       width:90%;text-align:center;box-shadow:0 8px 40px rgba(0,0,0,.25)}
.mcard .name{font-size:22px;font-weight:800;margin:6px 0}
.mcard .price{font-size:17px;color:#3b7aee;margin-bottom:14px}
.mcard img{max-width:110px;border-radius:8px;margin-bottom:8px}
.cbtn{background:#f0f4ff;border:none;border-radius:8px;padding:9px 22px;
      font-size:13px;cursor:pointer;color:#3b7aee}
</style>
</head>
<body>
<h1>🎤 被動語音 Demo <small style="font-size:13px;color:#8494b0">（本地 Whisper）</small></h1>

<div class="card">
  <h2>關鍵詞</h2>
  <div id="kwList">載入中…</div>
</div>

<div class="card">
  <h2>Whisper 模型大小</h2>
  <div class="model-row" id="modelBtns"></div>
  <div id="modelStatus"></div>
</div>

<div class="card">
  <h2>錄音控制</h2>
  <button id="recBtn" onclick="toggleRec()" disabled>等待 Whisper 載入…</button>
  <div id="status">連線中…</div>
  <div id="transcript">（辨識結果顯示於此）</div>
</div>

<div class="card">
  <h2>比對記錄</h2>
  <div id="cooldownBar">
    <div id="cooldownTrack"><div id="cooldownFill" style="width:100%"></div></div>
    <div id="cooldownLabel"></div>
  </div>
  <div id="log-wrap">
    <div id="log-hint">↑ 最新記錄在上方</div>
    <div id="log"></div>
  </div>
</div>

<div class="modal" id="modal">
  <div class="mcard">
    <h3 style="font-size:11px;color:#8494b0;margin-bottom:4px">🎯 猶豫彈跳視窗觸發！</h3>
    <img id="mImg" src="" alt="" style="display:none">
    <div class="name" id="mName"></div>
    <div class="price" id="mPrice"></div>
    <button class="cbtn" onclick="document.getElementById('modal').classList.remove('show')">關閉</button>
  </div>
</div>

<script>
const wsUrl = (location.protocol==='https:'?'wss':'ws')+'://'+location.host+'/ws';
let ws, recorder, processing = false;
const CHUNK_MS = 5000;
const COOLDOWN_SEC = 10;
let currentModel = 'small';
let _cooldownTimer = null;

/* ── 模型按鈕 ── */
function renderModelBtns(sizes, selected){
  const wrap = document.getElementById('modelBtns');
  wrap.innerHTML = '';
  sizes.forEach(s => {
    const btn = document.createElement('button');
    btn.className = 'model-btn' + (s===selected?' selected':'');
    btn.textContent = s;
    btn.dataset.size = s;
    btn.onclick = () => switchModel(s);
    wrap.appendChild(btn);
  });
}

async function switchModel(size){
  if(size === currentModel) return;
  document.querySelectorAll('.model-btn').forEach(b => b.disabled = true);
  document.getElementById('modelStatus').textContent = `⏳ 載入 ${size} 模型中（依大小需時 10–60 秒）…`;
  try {
    const r = await fetch('/api/set_model', {
      method: 'POST',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify({size})
    });
    const d = await r.json();
    if(r.ok){
      currentModel = d.model_size;
      document.getElementById('modelStatus').textContent = `✅ 已切換至 ${currentModel}`;
    } else {
      document.getElementById('modelStatus').textContent = `⚠ 切換失敗：${d.error}`;
    }
  } catch(e){
    document.getElementById('modelStatus').textContent = `⚠ ${e.message}`;
  }
  document.querySelectorAll('.model-btn').forEach(b => {
    b.disabled = false;
    b.classList.toggle('selected', b.dataset.size === currentModel);
  });
}

/* ── WebSocket ── */
function connectWs(){
  ws = new WebSocket(wsUrl);
  ws.binaryType = 'arraybuffer';
  ws.onopen  = ()=> setStatus('WebSocket 已連線');
  ws.onclose = ()=>{ setStatus('WebSocket 斷線，3 秒後重連'); setTimeout(connectWs,3000); };
  ws.onerror = ()=> setStatus('WebSocket 錯誤');
  ws.onmessage = e => {
    const d = JSON.parse(e.data);
    if(d.type==='loading'){
      setStatus('⏳ '+d.msg);
      document.getElementById('recBtn').textContent = '模型載入中…';
    }
    if(d.type==='ready'){
      setStatus('準備就緒，點「開始錄音」後說話');
      document.getElementById('recBtn').disabled = false;
      document.getElementById('recBtn').textContent = '開始錄音';
      if(d.model_size){
        currentModel = d.model_size;
        document.querySelectorAll('.model-btn').forEach(b =>
          b.classList.toggle('selected', b.dataset.size === currentModel));
        document.getElementById('modelStatus').textContent = `目前：${currentModel}`;
      }
    }
    if(d.type==='processing') setStatus('⏳ '+d.msg);
    if(d.type==='result') handleResult(d);
  };
}

function setStatus(t){ document.getElementById('status').textContent = t; }

/* ── 冷卻倒數條 ── */
function startCooldownBar(secondsLeft){
  const bar   = document.getElementById('cooldownBar');
  const fill  = document.getElementById('cooldownFill');
  const label = document.getElementById('cooldownLabel');
  if(_cooldownTimer) clearInterval(_cooldownTimer);
  bar.style.display = 'block';
  let rem = secondsLeft;
  const update = () => {
    fill.style.width = (rem / COOLDOWN_SEC * 100) + '%';
    label.textContent = `觸發冷卻中，還剩 ${rem.toFixed(0)} 秒後才能再次觸發`;
    if(rem <= 0){ clearInterval(_cooldownTimer); bar.style.display='none'; }
    rem -= 1;
  };
  update();
  _cooldownTimer = setInterval(update, 1000);
}

/* ── 結果處理 ── */
function handleResult(d){
  processing = false;
  setStatus(`就緒（${d.model_size}）`);
  document.getElementById('transcript').textContent = d.transcript || '（靜音）';

  const s = d.status;
  if(s==='empty') return;

  // 命中時啟動冷卻倒數條
  if(s==='hit') startCooldownBar(COOLDOWN_SEC);
  // 冷卻中時更新剩餘秒數（以 server 回傳為準）
  if(s==='cooldown') startCooldownBar(d.cooldown_left);

  const ts  = new Date().toLocaleTimeString('zh-TW');
  let tag, detail = '';
  if(s==='cooldown')  { tag = `<span class="tag-cool">⏳ 冷卻中，還剩 ${d.cooldown_left}s</span>`; }
  else if(s==='no_keyword') { tag = `<span class="tag-skip">— 無關鍵詞</span>`; }
  else if(s==='no_item')    { tag = `<span class="tag-miss">✗ 無品項</span>`; detail = `<span style="color:#999;font-size:11px"> norm:「${d.norm}」</span>`; }
  else if(s==='hit')        { tag = `<span class="tag-hit">✅ ${d.item.name}</span><span style="font-size:10px;color:#666;margin-left:4px">${d.matched_label||''}</span>`; }
  else                      { tag = `<span class="tag-skip">${s}</span>`; }

  document.getElementById('log').insertAdjacentHTML('afterbegin',
    `<div class="log-row">
       <div class="log-ts">[${ts}] ${d.model_size}</div>
       <div class="log-tr">「${d.transcript}」</div>
       <div>${tag}${detail}</div>
     </div>`);

  if(s==='hit'){
    const item = d.item;
    document.getElementById('mName').textContent  = item.name || '';
    document.getElementById('mPrice').textContent = item.price ? `$${item.price}` : '';
    const img = document.getElementById('mImg');
    if(item.image){ img.src=item.image; img.style.display='block'; } else img.style.display='none';
    document.getElementById('modal').classList.add('show');
  }
}

/* ── 錄音 ── */
let recording = false, recStream = null, recTimer = null;

function toggleRec(){ recording ? stopRec() : startRec(); }

function startRec(){
  navigator.mediaDevices.getUserMedia({audio:true}).then(stream=>{
    recStream = stream; recording = true;
    document.getElementById('recBtn').textContent = '停止錄音';
    document.getElementById('recBtn').classList.add('active');
    setStatus('🎙 錄音中（每 3 秒辨識）');
    scheduleChunk();
  }).catch(e=>{ setStatus('麥克風權限被拒：'+e.message); });
}

function scheduleChunk(){
  if(!recording) return;
  const chunks = [];
  recorder = new MediaRecorder(recStream, {mimeType:'audio/webm'});
  recorder.ondataavailable = e => { if(e.data && e.data.size>0) chunks.push(e.data); };
  recorder.onstop = () => {
    if(!recording) return;
    const blob = new Blob(chunks, {type:'audio/webm'});
    if(blob.size > 500 && ws.readyState===1 && !processing){
      processing = true;
      blob.arrayBuffer().then(buf => ws.send(buf));
    }
    scheduleChunk();
  };
  recorder.start();
  recTimer = setTimeout(()=>{ if(recorder.state==='recording') recorder.stop(); }, CHUNK_MS);
}

function stopRec(){
  recording = false;
  clearTimeout(recTimer);
  try{ recorder?.stop(); }catch{}
  recStream?.getTracks().forEach(t=>t.stop());
  recStream = null;
  document.getElementById('recBtn').textContent = '開始錄音';
  document.getElementById('recBtn').classList.remove('active');
  setStatus('已停止');
}

// 初始化
fetch('/api/keywords').then(r=>r.json()).then(d=>{
  currentModel = d.model_size;
  document.getElementById('kwList').innerHTML =
    d.keywords.map(k=>`<span class="kw-badge">${k}</span>`).join('');
  renderModelBtns(d.model_sizes, d.model_size);
  document.getElementById('modelStatus').textContent = `目前：${d.model_size}`;
});

connectWs();
</script>
</body>
</html>"""


# ── 主程式 ────────────────────────────────────────────────────
def main():
    global _keywords, _menu, _norm_menu

    print("=" * 60)
    print("  被動語音 Web Demo（本地 Whisper）")
    print("=" * 60)

    _keywords  = load_keywords()
    _menu      = load_menu()
    _norm_menu = [(_i, _normalize(_i["name"])) for _i in _menu]
    aliases    = load_aliases()

    global _match_index, _whisper_prompt
    _match_index = build_match_index(_menu, aliases)

    names = [i["name"] for i in _menu if i.get("name")]
    _whisper_prompt = "麥當勞菜單：" + "、".join(names[:60])

    print(f"[Demo] 關鍵詞（{len(_keywords)}）: {_keywords}")
    print(f"[Demo] 菜單品項數: {len(_menu)}，比對形式數: {len(_match_index)}")
    alias_count = sum(len(v) for v in aliases.values())
    if alias_count:
        print(f"[Demo] 已載入別名 {alias_count} 個")
    print(f"[Demo] Whisper prompt 前 80 字：{_whisper_prompt[:80]}…")

    # 背景載入模型，不阻塞 ngrok 啟動與 URL 顯示
    threading.Thread(target=_preload_whisper, args=(DEFAULT_SIZE,), daemon=True).start()

    public_url = None
    ngrok_token = os.getenv("NGROK_AUTHTOKEN", "")
    try:
        import time as _time
        subprocess.run(["pkill", "-f", "ngrok"], capture_output=True)
        _time.sleep(2)
        from pyngrok import ngrok
        if ngrok_token:
            ngrok.set_auth_token(ngrok_token)
        tunnel = ngrok.connect(DEMO_PORT, "http")
        public_url = tunnel.public_url
        print(f"\n[Demo] 🌐 ngrok URL : {public_url}")
    except Exception as e:
        print(f"[Demo] ⚠ ngrok 失敗（{e}）")

    print(f"[Demo] 🏠 本機 URL  : http://127.0.0.1:{DEMO_PORT}")
    print(f"\n[Demo] 說話範例：「大麥克在哪裡」、「找不到薯條」")
    print(f"[Demo] Ctrl+C 停止\n")

    uvicorn.run(app, host="0.0.0.0", port=DEMO_PORT, log_level="warning")


if __name__ == "__main__":
    main()
