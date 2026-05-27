# Admin 端完整重設計 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 刪除現有 8-tab admin HTML/JS，重寫為白色簡潔、儀表板優先的五畫面後台（儀表板 + 4 個設定頁）。

**Architecture:** 單一 HTML，五個 `admin-section` div（show/hide），底部固定導航列切換。儀表板從 `api.getInterventionStats()` 取最新介入資料，每 4 秒自動刷新；Emotion/AI 設定從 `api.getSettings()` 讀寫；Clips / Menu / RAG 重用現有後端 API。

**Tech Stack:** Vanilla JS（無框架）、FastAPI 後端、現有 `api.js` 方法

---

## 檔案異動清單

| 檔案 | 異動 |
|---|---|
| `UI_API/index.html` | 刪除 `<div id="view-admin">` 內部全部內容（lines 298-781），重寫五畫面 HTML |
| `UI_API/static/app.js` | 新增 `switchAdminSection` / `loadDashboard` / `loadEmotionSettings` / `saveEmotionSettings` / `loadClipsPage` / `clearClipsPage` / `loadMenuPage` / `saveMenuJson` / `loadRagPage`；刪除舊 admin 函式；更新 `Object.assign(window, {...})` |
| `UI_API/static/ui.js` | 刪除 `switchAdminTab` 函式（7 行）及其在 app.js import 中的引用 |

---

## Task 1：新 Admin HTML 骨架

**Files:**
- Modify: `UI_API/index.html:298-781`

舊 admin 內部從 line 298（`<nav class="admin-nav...`）到 line 781（`</div>`，即 `id="view-admin"` 的最後一個子元素）全部替換。保留 line 297 的注釋、line 298 的 `<div id="view-admin"...>` 開標籤、line 782 的 `</div>` 結束標籤不動。

- [ ] **Step 1：確認邊界行**

```bash
sed -n '297,300p' UI_API/index.html
# 預期：<!-- ============ 後台視圖 ... 和 <div id="view-admin"...
sed -n '779,783p' UI_API/index.html
# 預期：</div> 以及 </div> 接著 <!-- Tutorial popup
```

- [ ] **Step 2：替換 view-admin 內部**

用你的編輯器或 Edit tool，把 `UI_API/index.html` 中 `<div id="view-admin"...>` 的整個開標籤到 `</div>` 之間的內容（不含外層兩行），替換為以下 HTML：

```
  <!-- 通知欄 -->
  <div id="adminNotificationBox" class="hidden mx-4 mt-3 rounded-xl px-4 py-3 text-sm font-semibold" style="background:#fff4e8;border:1.5px solid #f0c9a5;color:#6b3b19"></div>

  <!-- 頂部列 -->
  <div style="background:#fff;border-bottom:1px solid #e2e8f0;padding:12px 20px;display:flex;justify-content:space-between;align-items:center;position:sticky;top:0;z-index:10">
    <div>
      <span style="font-size:15px;font-weight:700;color:#1e1b4b">智慧自助點餐介入系統</span>
      <span style="font-size:11px;color:#94a3b8;margin-left:8px">後台管理</span>
    </div>
    <div style="display:flex;align-items:center;gap:10px">
      <span id="admin-live-badge" style="background:#dcfce7;color:#166534;font-size:10px;padding:3px 10px;border-radius:99px;font-weight:600">● 監控中</span>
      <a href="/admin" style="background:#f1f5f9;border:none;border-radius:6px;padding:5px 10px;font-size:12px;color:#64748b;cursor:pointer;text-decoration:none">⟳ 重整</a>
    </div>
  </div>

  <!-- 儀表板 -->
  <div id="admin-sec-dashboard" class="admin-section" style="padding:16px 20px;display:flex;flex-direction:column;gap:12px">
    <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:12px">
      <div style="background:#fff;border:1px solid #e2e8f0;border-radius:12px;padding:16px;box-shadow:0 1px 4px rgba(0,0,0,.06)">
        <div style="font-size:10px;color:#94a3b8;text-transform:uppercase;letter-spacing:.5px;margin-bottom:6px">介入次數</div>
        <div id="dash-total" style="font-size:36px;font-weight:800;color:#7c3aed;line-height:1">—</div>
        <div style="font-size:10px;color:#94a3b8;margin-top:4px">成功率 <span id="dash-rate" style="color:#059669;font-weight:600">—</span></div>
      </div>
      <div style="background:#fff;border:1px solid #e2e8f0;border-radius:12px;padding:16px;box-shadow:0 1px 4px rgba(0,0,0,.06)">
        <div style="font-size:10px;color:#94a3b8;text-transform:uppercase;letter-spacing:.5px;margin-bottom:6px">最新障礙</div>
        <div id="dash-barrier" style="font-size:13px;font-weight:700;color:#d97706;line-height:1.4;word-break:break-all">—</div>
        <div style="font-size:10px;color:#94a3b8;margin-top:6px">barrier_state</div>
      </div>
      <div style="background:#fff;border:1px solid #e2e8f0;border-radius:12px;padding:16px;box-shadow:0 1px 4px rgba(0,0,0,.06)">
        <div style="font-size:10px;color:#94a3b8;text-transform:uppercase;letter-spacing:.5px;margin-bottom:6px">最新介入</div>
        <div id="dash-action" style="font-size:12px;font-weight:700;color:#0891b2;line-height:1.4;word-break:break-all">—</div>
        <div style="font-size:10px;color:#94a3b8;margin-top:6px">intervention_action</div>
      </div>
    </div>
    <div id="dash-intervention-banner" style="background:linear-gradient(135deg,#fef2f2,#fff5f5);border:1px solid #fca5a5;border-radius:10px;padding:12px 16px;display:flex;align-items:center;justify-content:space-between">
      <div>
        <div style="font-size:10px;color:#dc2626;text-transform:uppercase;letter-spacing:.5px;margin-bottom:2px">最近介入動作</div>
        <div id="dash-last-action" style="font-size:14px;font-weight:700;color:#991b1b">尚無介入紀錄</div>
      </div>
      <div id="dash-last-action-time" style="font-size:10px;color:#94a3b8;text-align:right"></div>
    </div>
    <div style="background:#fff;border:1px solid #e2e8f0;border-radius:10px;padding:14px 16px;box-shadow:0 1px 3px rgba(0,0,0,.04)">
      <div style="font-size:10px;color:#94a3b8;text-transform:uppercase;letter-spacing:.5px;margin-bottom:8px">最近 POS 事件</div>
      <div id="dash-event-log" style="display:flex;flex-direction:column;gap:5px">
        <div style="font-size:11px;color:#94a3b8">載入中...</div>
      </div>
    </div>
  </div>

  <!-- Emotion / AI 設定 -->
  <div id="admin-sec-emotion" class="admin-section" style="padding:16px 20px;display:none;flex-direction:column;gap:10px">
    <div style="display:flex;align-items:center;gap:10px;margin-bottom:2px">
      <button onclick="switchAdminSection('dashboard')" style="background:#f1f5f9;border:none;border-radius:6px;padding:5px 10px;font-size:12px;color:#64748b;cursor:pointer">← 返回監控</button>
      <span style="font-size:14px;font-weight:700;color:#1e1b4b">😊 Emotion / AI 設定</span>
    </div>
    <div style="background:#fff;border:1px solid #e2e8f0;border-radius:10px;padding:14px;box-shadow:0 1px 3px rgba(0,0,0,.04)">
      <div style="font-size:11px;color:#7c3aed;font-weight:700;text-transform:uppercase;letter-spacing:.5px;margin-bottom:10px">情緒偵測</div>
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px">
        <div>
          <label style="font-size:11px;color:#64748b;display:block;margin-bottom:3px">偵測間隔（秒）</label>
          <input id="inp-emotion-interval" type="number" style="width:100%;border:1px solid #e2e8f0;border-radius:6px;padding:6px 10px;font-size:13px;color:#1e293b;background:#f8fafc;box-sizing:border-box" />
        </div>
        <div>
          <label style="font-size:11px;color:#64748b;display:block;margin-bottom:3px">影片截取長度（ms）</label>
          <input id="inp-emotion-record-ms" type="number" style="width:100%;border:1px solid #e2e8f0;border-radius:6px;padding:6px 10px;font-size:13px;color:#1e293b;background:#f8fafc;box-sizing:border-box" />
        </div>
        <div>
          <label style="font-size:11px;color:#64748b;display:block;margin-bottom:3px">音量門檻（dBFS）</label>
          <input id="inp-whisper-low-db" type="number" style="width:100%;border:1px solid #e2e8f0;border-radius:6px;padding:6px 10px;font-size:13px;color:#1e293b;background:#f8fafc;box-sizing:border-box" />
        </div>
        <div>
          <label style="font-size:11px;color:#64748b;display:block;margin-bottom:3px">推播最短間隔（秒）</label>
          <input id="inp-recommend-interval" type="number" style="width:100%;border:1px solid #e2e8f0;border-radius:6px;padding:6px 10px;font-size:13px;color:#1e293b;background:#f8fafc;box-sizing:border-box" />
        </div>
      </div>
    </div>
    <div style="background:#fff;border:1px solid #e2e8f0;border-radius:10px;padding:14px;box-shadow:0 1px 3px rgba(0,0,0,.04)">
      <div style="font-size:11px;color:#0891b2;font-weight:700;text-transform:uppercase;letter-spacing:.5px;margin-bottom:10px">LLM 推論</div>
      <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:10px">
        <div>
          <label style="font-size:11px;color:#64748b;display:block;margin-bottom:3px">推論溫度</label>
          <input id="inp-temp" type="number" step="0.1" style="width:100%;border:1px solid #e2e8f0;border-radius:6px;padding:6px 10px;font-size:13px;color:#1e293b;background:#f8fafc;box-sizing:border-box" />
        </div>
        <div>
          <label style="font-size:11px;color:#64748b;display:block;margin-bottom:3px">輸出上限（tokens）</label>
          <input id="inp-num-predict" type="number" style="width:100%;border:1px solid #e2e8f0;border-radius:6px;padding:6px 10px;font-size:13px;color:#1e293b;background:#f8fafc;box-sizing:border-box" />
        </div>
        <div>
          <label style="font-size:11px;color:#64748b;display:block;margin-bottom:3px">問答來源</label>
          <select id="inp-ai-provider" style="width:100%;border:1px solid #e2e8f0;border-radius:6px;padding:6px 10px;font-size:13px;color:#1e293b;background:#f8fafc;box-sizing:border-box">
            <option value="ollama">Ollama（本地）</option>
            <option value="gemini">Gemini API</option>
          </select>
        </div>
      </div>
      <input id="inp-model-name" type="hidden" />
      <input id="inp-ask-model-name" type="hidden" />
      <input id="inp-gemini-model-name" type="hidden" value="gemini-3-flash-preview" />
      <input id="inp-gemini-fallback" type="hidden" value="true" />
      <input id="inp-performance-mode" type="hidden" value="balanced" />
      <input id="inp-rag-top-k" type="hidden" value="3" />
      <input id="inp-tts-cache" type="hidden" value="true" />
      <input id="inp-voice-assist-model" type="hidden" value="qwen3.5:9b" />
    </div>
    <div style="background:#fff;border:1px solid #e2e8f0;border-radius:10px;padding:14px;box-shadow:0 1px 3px rgba(0,0,0,.04)">
      <div style="font-size:11px;color:#059669;font-weight:700;text-transform:uppercase;letter-spacing:.5px;margin-bottom:10px">Prompt 設定</div>
      <div style="display:flex;flex-direction:column;gap:8px">
        <div>
          <label style="font-size:11px;color:#64748b;display:block;margin-bottom:3px">語音問答 Prompt（繁中）</label>
          <textarea id="inp-ask-prompt" style="width:100%;border:1px solid #e2e8f0;border-radius:6px;padding:8px 10px;font-size:11px;color:#1e293b;background:#f8fafc;resize:vertical;height:56px;font-family:monospace;box-sizing:border-box"></textarea>
        </div>
        <div>
          <label style="font-size:11px;color:#64748b;display:block;margin-bottom:3px">推播推薦 Prompt</label>
          <textarea id="inp-recommend-prompt" style="width:100%;border:1px solid #e2e8f0;border-radius:6px;padding:8px 10px;font-size:11px;color:#1e293b;background:#f8fafc;resize:vertical;height:56px;font-family:monospace;box-sizing:border-box"></textarea>
        </div>
        <textarea id="inp-ask-prompt-en" style="display:none"></textarea>
        <textarea id="inp-emotion-prompt" style="display:none"></textarea>
        <textarea id="inp-voice-assist-prompt" style="display:none"></textarea>
      </div>
    </div>
    <div style="background:#fff;border:1px solid #e2e8f0;border-radius:10px;padding:14px;box-shadow:0 1px 3px rgba(0,0,0,.04)">
      <div style="font-size:11px;color:#d97706;font-weight:700;text-transform:uppercase;letter-spacing:.5px;margin-bottom:10px">答案品質</div>
      <div style="display:flex;flex-direction:column;gap:8px">
        <label style="display:flex;align-items:center;gap:8px;font-size:12px;color:#374151;cursor:pointer">
          <input id="inp-rag-strict-grounding" type="checkbox" style="accent-color:#7c3aed" /> 嚴格來源限制（僅從 RAG 知識庫回答）
        </label>
        <label style="display:flex;align-items:center;gap:8px;font-size:12px;color:#374151;cursor:pointer">
          <input id="inp-rag-answer-verification" type="checkbox" style="accent-color:#7c3aed" /> LLM 答案驗證
        </label>
        <label style="display:flex;align-items:center;gap:8px;font-size:12px;color:#374151;cursor:pointer">
          <input id="inp-rag-fail-closed" type="checkbox" style="accent-color:#7c3aed" /> 評估失敗時拒答
        </label>
      </div>
    </div>
    <button onclick="saveEmotionSettings()" style="background:#7c3aed;color:#fff;border:none;border-radius:8px;padding:10px;font-size:13px;font-weight:600;cursor:pointer;width:100%">儲存設定</button>
  </div>

  <!-- 影像片段 -->
  <div id="admin-sec-clips" class="admin-section" style="padding:16px 20px;display:none;flex-direction:column;gap:12px">
    <div style="display:flex;align-items:center;justify-content:space-between">
      <div style="display:flex;align-items:center;gap:10px">
        <button onclick="switchAdminSection('dashboard')" style="background:#f1f5f9;border:none;border-radius:6px;padding:5px 10px;font-size:12px;color:#64748b;cursor:pointer">← 返回監控</button>
        <span style="font-size:14px;font-weight:700;color:#1e1b4b">🎬 影像片段</span>
      </div>
      <div style="display:flex;gap:8px">
        <button onclick="loadClipsPage()" style="background:#f1f5f9;border:none;border-radius:6px;padding:5px 12px;font-size:12px;color:#64748b;cursor:pointer">↻ 重新整理</button>
        <button onclick="clearClipsPage()" style="background:#fef2f2;border:none;border-radius:6px;padding:5px 12px;font-size:12px;color:#dc2626;cursor:pointer">🗑 清除</button>
      </div>
    </div>
    <div id="admin-clips-count" style="font-size:11px;color:#94a3b8"></div>
    <div id="emotionClipList" style="display:grid;grid-template-columns:1fr 1fr;gap:12px"></div>
  </div>

  <!-- 菜單管理 -->
  <div id="admin-sec-menu" class="admin-section" style="padding:16px 20px;display:none;flex-direction:column;gap:12px">
    <div style="display:flex;align-items:center;justify-content:space-between">
      <div style="display:flex;align-items:center;gap:10px">
        <button onclick="switchAdminSection('dashboard')" style="background:#f1f5f9;border:none;border-radius:6px;padding:5px 10px;font-size:12px;color:#64748b;cursor:pointer">← 返回監控</button>
        <span style="font-size:14px;font-weight:700;color:#1e1b4b">🍔 菜單管理</span>
      </div>
      <button onclick="saveMenuJson()" style="background:#7c3aed;color:#fff;border:none;border-radius:6px;padding:5px 14px;font-size:12px;font-weight:600;cursor:pointer">💾 儲存</button>
    </div>
    <div id="admin-menu-list" style="display:flex;flex-direction:column;gap:8px"></div>
    <div style="background:#fff;border:1px solid #e2e8f0;border-radius:10px;padding:14px">
      <div style="font-size:11px;color:#94a3b8;margin-bottom:8px">完整 JSON（進階編輯）</div>
      <textarea id="menuEditor" style="width:100%;height:300px;font-family:monospace;font-size:11px;border:1px solid #e2e8f0;border-radius:6px;padding:8px;background:#f8fafc;color:#1e293b;resize:vertical;box-sizing:border-box"></textarea>
    </div>
  </div>

  <!-- RAG 知識庫 -->
  <div id="admin-sec-rag" class="admin-section" style="padding:16px 20px;display:none;flex-direction:column;gap:10px">
    <div style="display:flex;align-items:center;justify-content:space-between">
      <div style="display:flex;align-items:center;gap:10px">
        <button onclick="switchAdminSection('dashboard')" style="background:#f1f5f9;border:none;border-radius:6px;padding:5px 10px;font-size:12px;color:#64748b;cursor:pointer">← 返回監控</button>
        <span style="font-size:14px;font-weight:700;color:#1e1b4b">📄 RAG 知識庫</span>
      </div>
      <button onclick="clearAllRagDocs()" style="background:#fef2f2;border:none;border-radius:6px;padding:5px 12px;font-size:12px;color:#dc2626;cursor:pointer">🗑 清空</button>
    </div>
    <div style="background:#fff;border:1px solid #e2e8f0;border-radius:10px;padding:14px">
      <div style="font-size:11px;color:#059669;font-weight:700;text-transform:uppercase;letter-spacing:.5px;margin-bottom:8px">新增 RAG 文本</div>
      <textarea id="ragNewText" style="width:100%;height:72px;font-size:12px;border:1px solid #e2e8f0;border-radius:6px;padding:8px;background:#f8fafc;resize:vertical;box-sizing:border-box" placeholder="輸入補充知識，送出後由 Ollama 審查。"></textarea>
      <button onclick="addRagDoc()" style="margin-top:8px;background:#059669;color:#fff;border:none;border-radius:6px;padding:6px 14px;font-size:12px;cursor:pointer">＋ 審查並保存</button>
    </div>
    <div style="background:#fff;border:1px solid #e2e8f0;border-radius:10px;padding:14px">
      <div style="font-size:11px;color:#0891b2;font-weight:700;text-transform:uppercase;letter-spacing:.5px;margin-bottom:8px">匯入 PDF</div>
      <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap">
        <input type="file" id="ragPdfFile" accept="application/pdf" style="font-size:12px;flex:1" />
        <label style="display:flex;align-items:center;gap:4px;font-size:12px;color:#64748b;cursor:pointer;white-space:nowrap">
          <input type="checkbox" id="ragPdfReview" /> 逐 chunk 審查
        </label>
        <button onclick="uploadRagPdf()" style="background:#0891b2;color:#fff;border:none;border-radius:6px;padding:6px 12px;font-size:12px;cursor:pointer;white-space:nowrap">匯入</button>
      </div>
    </div>
    <div style="background:#fff;border:1px solid #e2e8f0;border-radius:10px;padding:14px">
      <div style="font-size:11px;color:#94a3b8;text-transform:uppercase;letter-spacing:.5px;margin-bottom:8px">已保存文件 <span id="rag-doc-count"></span></div>
      <div id="ragDocsList" style="display:flex;flex-direction:column;gap:8px;max-height:480px;overflow-y:auto"></div>
    </div>
  </div>

  <!-- 底部導航列 -->
  <div style="background:#fff;border-top:1px solid #e2e8f0;padding:6px 16px;display:grid;grid-template-columns:repeat(4,1fr);gap:4px;position:sticky;bottom:0;z-index:10">
    <button id="admin-nav-emotion" onclick="switchAdminSection('emotion')" style="display:flex;flex-direction:column;align-items:center;padding:7px 4px;border-radius:8px;cursor:pointer;background:none;border:none">
      <span style="font-size:20px">😊</span>
      <span style="font-size:10px;color:#64748b;margin-top:2px">Emotion / AI</span>
    </button>
    <button id="admin-nav-clips" onclick="switchAdminSection('clips')" style="display:flex;flex-direction:column;align-items:center;padding:7px 4px;border-radius:8px;cursor:pointer;background:none;border:none">
      <span style="font-size:20px">🎬</span>
      <span style="font-size:10px;color:#64748b;margin-top:2px">影像片段</span>
    </button>
    <button id="admin-nav-menu" onclick="switchAdminSection('menu')" style="display:flex;flex-direction:column;align-items:center;padding:7px 4px;border-radius:8px;cursor:pointer;background:none;border:none">
      <span style="font-size:20px">🍔</span>
      <span style="font-size:10px;color:#64748b;margin-top:2px">菜單管理</span>
    </button>
    <button id="admin-nav-rag" onclick="switchAdminSection('rag')" style="display:flex;flex-direction:column;align-items:center;padding:7px 4px;border-radius:8px;cursor:pointer;background:none;border:none">
      <span style="font-size:20px">📄</span>
      <span style="font-size:10px;color:#64748b;margin-top:2px">RAG 知識庫</span>
    </button>
  </div>

- [ ] **Step 3：確認 HTML 結構**

```bash
node -e "
const fs = require('fs');
const html = fs.readFileSync('UI_API/index.html', 'utf8');
['view-admin','adminNotificationBox','admin-sec-dashboard','dash-total','dash-barrier',
 'admin-sec-emotion','inp-emotion-interval','inp-whisper-low-db',
 'admin-sec-clips','emotionClipList',
 'admin-sec-menu','menuEditor',
 'admin-sec-rag','ragDocsList','ragNewText',
 'admin-nav-emotion','admin-nav-rag'].forEach(id => {
  if (!html.includes('id=\"' + id + '\"')) console.error('MISSING:', id);
  else process.stdout.write('OK:' + id + ' ');
});
console.log();
"
# 預期：全部 OK
```

- [ ] **Step 4：Commit**

```bash
git add UI_API/index.html
git commit -m "feat: 新 admin HTML 骨架（五畫面 + 底部導航）"
```

---

## Task 2：儀表板 JS（loadDashboard）

**Files:**
- Modify: `UI_API/static/app.js`

- [ ] **Step 1：在 `function loadAdminData()` 前（line ~2360）插入 `loadDashboard`**

```javascript
async function loadDashboard() {
  try {
    const data = await api.getInterventionStats();
    if (data.status !== 'success') return;

    const set = (id, v) => { const el = document.getElementById(id); if (el) el.textContent = v; };
    set('dash-total', String(data.total_interventions ?? 0));
    set('dash-rate',  Math.round((data.success_rate ?? 0) * 100) + '%');

    const lastLog  = Array.isArray(data.recent_logs) ? data.recent_logs[0] : null;
    const barrier  = lastLog?.barrier_result?.barrier_state || '—';
    const action   = lastLog?.intervention?.action || '—';
    set('dash-barrier', barrier);
    set('dash-action',  action);

    const bannerAction = document.getElementById('dash-last-action');
    const bannerTime   = document.getElementById('dash-last-action-time');
    if (bannerAction) bannerAction.textContent = lastLog ? ('⚡ ' + action) : '尚無介入紀錄';
    if (bannerTime && lastLog?.timestamp) {
      bannerTime.textContent = new Date(lastLog.timestamp).toLocaleTimeString();
    }

    const logBox = document.getElementById('dash-event-log');
    if (logBox) {
      const events = Array.isArray(data.recent_events) ? data.recent_events.slice(0, 3) : [];
      if (!events.length) {
        logBox.textContent = '尚無 POS 事件。';
      } else {
        const levelBg   = { urgent:'#fee2e2', watch:'#fef9c3', assist:'#fef9c3', stable:'#f1f5f9', critical:'#fecaca' };
        const levelFg   = { urgent:'#dc2626', watch:'#92400e', assist:'#92400e', stable:'#64748b', critical:'#991b1b' };
        logBox.textContent = '';
        events.forEach(ev => {
          const row  = document.createElement('div');
          row.style.cssText = 'display:flex;justify-content:space-between;font-size:11px';
          const ts   = ev.timestamp ? new Date(ev.timestamp).toLocaleTimeString() : '';
          const desc = String(ev.event_type || ev.button_id || '-');
          const page = String(ev.page_id || '');
          const lvl  = String(ev.risk_level || 'stable');
          const left = document.createElement('span');
          left.style.color = '#64748b';
          left.textContent = ts + '  ' + desc + (page ? ' ／ ' + page : '');
          const badge = document.createElement('span');
          badge.style.cssText = 'padding:1px 6px;border-radius:4px;font-size:10px;background:' +
            (levelBg[lvl] || '#f1f5f9') + ';color:' + (levelFg[lvl] || '#64748b');
          badge.textContent = lvl;
          row.appendChild(left);
          row.appendChild(badge);
          logBox.appendChild(row);
        });
      }
    }
  } catch { /* 靜默失敗 */ }
}
```

- [ ] **Step 2：更新 `startAdminLiveRefresh`（line ~1099）**

找到：
```javascript
    loadInterventionStats();
```
（在 `startAdminLiveRefresh` 的 setInterval 內）改為：
```javascript
    const sec = document.getElementById('admin-sec-dashboard');
    if (sec && sec.style.display !== 'none') loadDashboard();
```

- [ ] **Step 3：更新 `handleRealtimeEmotionAnalysisCompleted`**

找到：
```javascript
  loadInterventionStats();
```
（在 `handleRealtimeEmotionAnalysisCompleted` 內）改為：
```javascript
  loadDashboard();
```

- [ ] **Step 4：語法確認**

```bash
node --check UI_API/static/app.js
# 預期：無輸出
```

- [ ] **Step 5：Commit**

```bash
git add UI_API/static/app.js
git commit -m "feat: loadDashboard + 即時刷新接線"
```

---

## Task 3：Emotion / AI 設定 JS

**Files:**
- Modify: `UI_API/static/app.js`（在 `loadDashboard` 後插入）

- [ ] **Step 1：插入 `loadEmotionSettings` 和 `saveEmotionSettings`**

```javascript
async function loadEmotionSettings() {
  try {
    fullSettings = await api.getSettings();
    runtimeSettings = { ...runtimeSettings, ...fullSettings };
    const set = (id, v) => { const el = document.getElementById(id); if (el) el.value = v; };
    const chk = (id, v) => { const el = document.getElementById(id); if (el) el.checked = Boolean(v); };
    set('inp-emotion-interval',   fullSettings.EMOTION_PING_INTERVAL_SEC ?? 15);
    set('inp-emotion-record-ms',  fullSettings.EMOTION_RECORD_MS ?? 900);
    set('inp-whisper-low-db',     fullSettings.WHISPER_LOW_AUDIO_DB ?? -58);
    set('inp-recommend-interval', fullSettings.RECOMMEND_INTERVAL_SEC ?? 30);
    set('inp-temp',               fullSettings.OLLAMA_TEMPERATURE ?? 0.8);
    set('inp-num-predict',        fullSettings.OLLAMA_NUM_PREDICT ?? 220);
    const allowGemini = fullSettings.ENABLE_GEMINI_OPTIONS === true;
    set('inp-ai-provider', allowGemini ? (fullSettings.QA_AI_PROVIDER || 'ollama') : 'ollama');
    set('inp-model-name',         fullSettings.MODEL_NAME || 'llama3.2');
    set('inp-ask-model-name',     fullSettings.MODEL_NAME || 'llama3.2');
    set('inp-gemini-model-name',  fullSettings.GEMINI_MODEL_NAME || 'gemini-3-flash-preview');
    set('inp-performance-mode',   fullSettings.PERFORMANCE_MODE || 'balanced');
    set('inp-rag-top-k',          fullSettings.RAG_TOP_K ?? 3);
    set('inp-voice-assist-model', fullSettings.VOICE_ASSIST_MODEL || 'qwen3.5:9b');
    set('inp-ask-prompt',         fullSettings.ASK_SYSTEM_PROMPT || '');
    set('inp-recommend-prompt',   fullSettings.RECOMMEND_SYSTEM_PROMPT || '');
    set('inp-ask-prompt-en',      fullSettings.ASK_SYSTEM_PROMPT_EN || '');
    set('inp-emotion-prompt',     fullSettings.EMOTION_LLAMA_PROMPT || '');
    set('inp-voice-assist-prompt',fullSettings.VOICE_ASSIST_SYSTEM_PROMPT || '');
    const gemFbEl = document.getElementById('inp-gemini-fallback');
    if (gemFbEl) gemFbEl.value = fullSettings.GEMINI_FALLBACK_TO_OLLAMA !== false ? 'true' : 'false';
    const ttsEl = document.getElementById('inp-tts-cache');
    if (ttsEl) ttsEl.value = fullSettings.ENABLE_TTS_CACHE !== false ? 'true' : 'false';
    const rag = fullSettings.rag || {};
    chk('inp-rag-strict-grounding',    rag.strict_grounding === true);
    chk('inp-rag-answer-verification', rag.answer_verification === true);
    chk('inp-rag-fail-closed',         rag.fail_closed_on_eval_error === true);
  } catch { /* 靜默失敗 */ }
}

async function saveEmotionSettings() {
  const g    = id => document.getElementById(id);
  const flt  = (id, d) => parseFloat(g(id)?.value || d);
  const int  = (id, d) => parseInt(g(id)?.value || d, 10);
  const str  = (id, d) => g(id)?.value?.trim() || d;
  const bool = (id, d) => g(id) ? (g(id).type === 'checkbox' ? g(id).checked : g(id).value === 'true') : d;
  const allowGemini = fullSettings.ENABLE_GEMINI_OPTIONS === true;
  fullSettings.AI_PROVIDER            = 'ollama';
  fullSettings.QA_AI_PROVIDER         = allowGemini ? str('inp-ai-provider', 'ollama') : 'ollama';
  fullSettings.EMOTION_AI_PROVIDER    = 'ollama';
  fullSettings.MODEL_NAME             = str('inp-model-name', 'llama3.2');
  fullSettings.ASK_MODEL_NAME         = str('inp-ask-model-name', 'llama3.2');
  fullSettings.GEMINI_MODEL_NAME      = str('inp-gemini-model-name', 'gemini-3-flash-preview');
  fullSettings.GEMINI_FALLBACK_TO_OLLAMA = bool('inp-gemini-fallback', true);
  fullSettings.OLLAMA_TEMPERATURE     = flt('inp-temp', '0.8');
  fullSettings.PERFORMANCE_MODE       = str('inp-performance-mode', 'balanced');
  fullSettings.OLLAMA_NUM_PREDICT     = int('inp-num-predict', '220');
  fullSettings.RAG_TOP_K              = int('inp-rag-top-k', '3');
  fullSettings.ENABLE_TTS_CACHE       = bool('inp-tts-cache', true);
  fullSettings.EMOTION_PING_INTERVAL_SEC = flt('inp-emotion-interval', '15');
  fullSettings.EMOTION_RECORD_MS         = int('inp-emotion-record-ms', '900');
  fullSettings.RECOMMEND_INTERVAL_SEC    = flt('inp-recommend-interval', '30');
  fullSettings.WHISPER_LOW_AUDIO_DB      = flt('inp-whisper-low-db', '-58');
  fullSettings.ASK_SYSTEM_PROMPT         = str('inp-ask-prompt', '');
  fullSettings.RECOMMEND_SYSTEM_PROMPT   = str('inp-recommend-prompt', '');
  fullSettings.ASK_SYSTEM_PROMPT_EN      = g('inp-ask-prompt-en')?.value || '';
  fullSettings.EMOTION_LLAMA_PROMPT      = g('inp-emotion-prompt')?.value || '';
  fullSettings.VOICE_ASSIST_MODEL        = str('inp-voice-assist-model', 'qwen3.5:9b');
  fullSettings.VOICE_ASSIST_SYSTEM_PROMPT = g('inp-voice-assist-prompt')?.value || '';
  const _existingRag = fullSettings.rag || {};
  fullSettings.rag = {
    ..._existingRag,
    strict_grounding:          bool('inp-rag-strict-grounding', false),
    answer_verification:       bool('inp-rag-answer-verification', false),
    fail_closed_on_eval_error: bool('inp-rag-fail-closed', false),
  };
  try {
    await api.saveSettings(fullSettings);
    runtimeSettings = { ...runtimeSettings, ...fullSettings };
    restartLoops();
    showAdminNotice('設定已儲存。', 'success');
  } catch {
    showAdminNotice('儲存失敗，請重試。', 'error');
  }
}
```

- [ ] **Step 2：語法確認**

```bash
node --check UI_API/static/app.js
# 預期：無輸出
```

- [ ] **Step 3：Commit**

```bash
git add UI_API/static/app.js
git commit -m "feat: loadEmotionSettings / saveEmotionSettings"
```

---

## Task 4：影像片段頁 JS

**Files:**
- Modify: `UI_API/static/app.js`

- [ ] **Step 1：確認舊函式行號**

```bash
grep -n "^async function loadEmotionClips\|^async function clearEmotionClips" UI_API/static/app.js
```

- [ ] **Step 2：刪除舊 `loadEmotionClips` 和 `clearEmotionClips`，替換為**

```javascript
async function loadClipsPage() {
  const box      = document.getElementById('emotionClipList');
  const countBox = document.getElementById('admin-clips-count');
  if (!box) return;
  box.textContent = '';
  const placeholder = document.createElement('div');
  placeholder.style.cssText = 'font-size:12px;color:#94a3b8;grid-column:span 2';
  placeholder.textContent = '載入影像片段中...';
  box.appendChild(placeholder);
  try {
    const data  = await api.getEmotionClips(sessionId);
    const clips = data.clips || [];
    if (countBox) countBox.textContent = '共 ' + clips.length + ' 筆';
    box.textContent = '';
    if (!clips.length) {
      const empty = document.createElement('div');
      empty.style.cssText = 'font-size:12px;color:#94a3b8;grid-column:span 2';
      empty.textContent = '目前無影像片段。';
      box.appendChild(empty);
      return;
    }
    [...clips].reverse().forEach((clip, idx) => {
      const card = document.createElement('div');
      card.style.cssText = 'background:#fff;border:1px solid #e2e8f0;border-radius:10px;overflow:hidden;box-shadow:0 1px 3px rgba(0,0,0,.05)';
      const suffix = clip.url && clip.url.includes('?') ? api.adminQuerySuffix('&') : api.adminQuerySuffix();
      const url    = clip.url ? (API_BASE + clip.url + suffix) : '';
      if (url) {
        const video = document.createElement('video');
        video.controls = true;
        video.muted = true;
        video.setAttribute('playsinline', '');
        video.preload = 'metadata';
        video.src = url;
        video.style.cssText = 'width:100%;display:block;max-height:120px;object-fit:cover';
        card.appendChild(video);
      } else {
        const noMedia = document.createElement('div');
        noMedia.style.cssText = 'background:#f1f5f9;height:80px;display:flex;align-items:center;justify-content:center;font-size:11px;color:#94a3b8';
        noMedia.textContent = '無媒體（僅分析資料）';
        card.appendChild(noMedia);
      }
      const info = document.createElement('div');
      info.style.cssText = 'padding:10px;font-size:11px';
      const emotion = String(clip.emotion_display || clip.emotion || '-');
      const ts      = clip.created_at ? new Date(clip.created_at).toLocaleString() : '-';
      const signals = clip.media_signals || {};
      const sigTxt  = signals.motion_level
        ? '音量 ' + (signals.audio_mean_db ?? '-') + ' dB / 動作 ' + signals.motion_level
        : '';
      const title = document.createElement('div');
      title.style.cssText = 'font-weight:700;color:#1e293b;margin-bottom:2px';
      title.textContent = '片段 ' + (clips.length - idx);
      const badge = document.createElement('span');
      badge.style.cssText = 'background:#f1f5f9;color:#7c3aed;padding:1px 6px;border-radius:4px;margin-left:4px';
      badge.textContent = emotion;
      title.appendChild(badge);
      const timeEl = document.createElement('div');
      timeEl.style.color = '#94a3b8';
      timeEl.textContent = ts;
      info.appendChild(title);
      info.appendChild(timeEl);
      if (sigTxt) {
        const sigEl = document.createElement('div');
        sigEl.style.cssText = 'color:#94a3b8;margin-top:2px';
        sigEl.textContent = sigTxt;
        info.appendChild(sigEl);
      }
      if (clip.emotion_evidence) {
        const evEl = document.createElement('div');
        evEl.style.cssText = 'color:#64748b;margin-top:3px';
        evEl.textContent = clip.emotion_evidence;
        info.appendChild(evEl);
      }
      card.appendChild(info);
      box.appendChild(card);
    });
  } catch {
    box.textContent = '';
    const err = document.createElement('div');
    err.style.cssText = 'font-size:12px;color:#dc2626;grid-column:span 2';
    err.textContent = '影像片段讀取失敗。';
    box.appendChild(err);
  }
}

async function clearClipsPage() {
  if (!confirm('確定清除目前這筆訂單的影像片段？')) return;
  await api.clearEmotionClips(sessionId);
  await loadClipsPage();
}
```

- [ ] **Step 3：語法確認**

```bash
node --check UI_API/static/app.js
# 預期：無輸出
```

- [ ] **Step 4：Commit**

```bash
git add UI_API/static/app.js
git commit -m "feat: loadClipsPage / clearClipsPage（DOM API 取代 innerHTML）"
```

---

## Task 5：菜單管理頁 JS

**Files:**
- Modify: `UI_API/static/app.js`

- [ ] **Step 1：確認舊函式行號**

```bash
grep -n "^async function loadAdminMenu\|^async function saveMenu\b" UI_API/static/app.js
```

- [ ] **Step 2：刪除舊 `loadAdminMenu` 和 `saveMenu`，替換為**

```javascript
async function loadMenuPage() {
  try {
    const menu   = await api.getMenu();
    const editor = document.getElementById('menuEditor');
    if (editor) editor.value = JSON.stringify(menu, null, 2);
    const listBox = document.getElementById('admin-menu-list');
    if (!listBox) return;
    listBox.textContent = '';
    const items = Array.isArray(menu) ? menu : [];
    items.slice(0, 10).forEach(item => {
      const row = document.createElement('div');
      row.style.cssText = 'background:#fff;border:1px solid #e2e8f0;border-radius:8px;padding:10px 14px;display:flex;justify-content:space-between;align-items:center;font-size:12px';
      const left = document.createElement('div');
      const nameSpan = document.createElement('span');
      nameSpan.style.cssText = 'font-weight:700;color:#1e293b';
      nameSpan.textContent = String(item.name || '-');
      const idSpan = document.createElement('span');
      idSpan.style.cssText = 'color:#94a3b8;margin-left:8px';
      idSpan.textContent = String(item.id || '');
      left.appendChild(nameSpan);
      left.appendChild(idSpan);
      const right = document.createElement('div');
      right.style.cssText = 'display:flex;gap:16px;align-items:center';
      const priceSpan = document.createElement('span');
      priceSpan.style.color = '#7c3aed';
      priceSpan.textContent = '$' + (item.price ?? '-');
      const catSpan = document.createElement('span');
      catSpan.style.color = '#94a3b8';
      catSpan.textContent = String(item.category || '-');
      right.appendChild(priceSpan);
      right.appendChild(catSpan);
      row.appendChild(left);
      row.appendChild(right);
      listBox.appendChild(row);
    });
    if (items.length > 10) {
      const more = document.createElement('div');
      more.style.cssText = 'text-align:center;font-size:11px;color:#94a3b8;padding:6px';
      more.textContent = '…還有 ' + (items.length - 10) + ' 筆，請用下方 JSON 編輯器';
      listBox.appendChild(more);
    }
  } catch {
    showAdminNotice('菜單載入失敗。', 'error');
  }
}

async function saveMenuJson() {
  const editor = document.getElementById('menuEditor');
  if (!editor) return;
  try {
    const data = JSON.parse(editor.value);
    await api.saveMenu(data);
    showAdminNotice('菜單已儲存。', 'success');
    await loadMenuPage();
  } catch (e) {
    showAdminNotice(e instanceof SyntaxError ? 'JSON 格式錯誤！' : '儲存失敗。', 'error');
  }
}
```

- [ ] **Step 3：語法確認**

```bash
node --check UI_API/static/app.js
# 預期：無輸出
```

- [ ] **Step 4：Commit**

```bash
git add UI_API/static/app.js
git commit -m "feat: loadMenuPage / saveMenuJson"
```

---

## Task 6：RAG 知識庫頁 JS

**Files:**
- Modify: `UI_API/static/app.js`

- [ ] **Step 1：確認舊函式行號**

```bash
grep -n "^async function loadRagData\|^async function loadOllamaModelOptions" UI_API/static/app.js
```

- [ ] **Step 2：刪除 `loadRagData` 和 `loadOllamaModelOptions`，替換為 `loadRagPage`**

```javascript
async function loadRagPage() {
  try {
    const data  = await api.getRagDocs();
    const docs  = (data.docs || []).filter(d => !d.deleted);
    const countEl = document.getElementById('rag-doc-count');
    if (countEl) countEl.textContent = '（' + docs.length + ' 筆）';
    const listBox = document.getElementById('ragDocsList');
    if (!listBox) return;
    listBox.textContent = '';
    if (!docs.length) {
      const empty = document.createElement('div');
      empty.style.cssText = 'font-size:12px;color:#94a3b8';
      empty.textContent = '目前沒有 RAG 文本。';
      listBox.appendChild(empty);
      return;
    }
    [...docs].reverse().forEach(doc => {
      const row = document.createElement('div');
      row.style.cssText = 'background:#f8fafc;border:1px solid #e2e8f0;border-radius:8px;padding:10px 12px';
      const header = document.createElement('div');
      header.style.cssText = 'display:flex;justify-content:space-between;align-items:flex-start;gap:8px;margin-bottom:6px';
      const info = document.createElement('div');
      const title = document.createElement('span');
      title.style.cssText = 'font-weight:700;font-size:12px;color:#1e293b';
      title.textContent = String(doc.source_type || '') + ' / ' + String(doc.source_id || doc.id || '');
      const meta = document.createElement('div');
      meta.style.cssText = 'font-size:10px;color:#94a3b8;margin-top:1px';
      meta.textContent = String(doc.updated_at || '') + ' · ' + String(doc.review_status || '-');
      info.appendChild(title);
      info.appendChild(meta);
      const delBtn = document.createElement('button');
      delBtn.style.cssText = 'background:#fef2f2;border:none;border-radius:4px;padding:3px 8px;font-size:11px;color:#dc2626;cursor:pointer;flex-shrink:0';
      delBtn.textContent = '刪除';
      delBtn.onclick = async () => {
        if (!confirm('確定刪除這段 RAG 文本？')) return;
        await api.deleteRagDoc(doc.id);
        await loadRagPage();
      };
      header.appendChild(info);
      header.appendChild(delBtn);
      const preview = document.createElement('div');
      preview.style.cssText = 'font-size:11px;color:#374151;max-height:60px;overflow:hidden;line-height:1.4';
      const txt = String(doc.reviewed_text || '');
      preview.textContent = txt.length > 200 ? txt.slice(0, 200) + '…' : txt;
      row.appendChild(header);
      row.appendChild(preview);
      listBox.appendChild(row);
    });
  } catch {
    showAdminNotice('RAG 資料載入失敗。', 'error');
  }
}
```

- [ ] **Step 3：更新三個呼叫點（`addRagDoc`、`uploadRagPdf`、`clearAllRagDocs`）**

在 `addRagDoc` 內找到：
```javascript
    await loadRagData();
    alert('已完成 Ollama 審查並保存。');
```
替換為：
```javascript
    await loadRagPage();
    showAdminNotice('已完成審查並保存。', 'success');
```

在 `uploadRagPdf` 內找到：
```javascript
  await loadRagData();
  alert(`PDF 已匯入 ${data.chunks || 0} 個 chunk。`);
```
替換為：
```javascript
  await loadRagPage();
  showAdminNotice('PDF 已匯入 ' + (data.chunks || 0) + ' 個 chunk。', 'success');
```

在 `clearAllRagDocs` 內找到：
```javascript
  await loadRagData();
  alert('RAG 已清空並重建菜單基礎資料。');
```
替換為：
```javascript
  await loadRagPage();
  showAdminNotice('RAG 已清空並重建菜單基礎資料。', 'success');
```

- [ ] **Step 4：語法確認**

```bash
node --check UI_API/static/app.js
# 預期：無輸出
```

- [ ] **Step 5：Commit**

```bash
git add UI_API/static/app.js
git commit -m "feat: loadRagPage（RAG 知識庫頁）"
```

---

## Task 7：導航接線 + 舊程式碼清理

**Files:**
- Modify: `UI_API/static/app.js`
- Modify: `UI_API/static/ui.js`

### 7a：新增 `switchAdminSection`

- [ ] **Step 1：在 `loadDashboard` 前插入 `switchAdminSection`**

```javascript
function switchAdminSection(section) {
  ['dashboard', 'emotion', 'clips', 'menu', 'rag'].forEach(s => {
    const el = document.getElementById('admin-sec-' + s);
    if (el) el.style.display = (s === section) ? 'flex' : 'none';
  });
  ['emotion', 'clips', 'menu', 'rag'].forEach(s => {
    const btn   = document.getElementById('admin-nav-' + s);
    const label = btn?.querySelector('span:last-child');
    if (btn)   btn.style.background  = (s === section) ? '#f5f3ff' : 'none';
    if (label) label.style.color     = (s === section) ? '#7c3aed' : '#64748b';
  });
  if (section === 'emotion') loadEmotionSettings();
  if (section === 'clips')   loadClipsPage();
  if (section === 'menu')    loadMenuPage();
  if (section === 'rag')     loadRagPage();
}
```

### 7b：更新 `loadAdminData`

- [ ] **Step 2：找到 `function loadAdminData()` 並替換整個函式體**

舊：
```javascript
function loadAdminData() {
  loadLogs();
  loadInterventionStats();
  loadSettings();
  loadAdminMenu();
  loadRagData();
  loadEmotionClips();
  loadOllamaModelOptions();
}
```
新：
```javascript
function loadAdminData() {
  switchAdminSection('dashboard');
  loadDashboard();
}
```

### 7c：刪除舊函式

- [ ] **Step 3：確認行號後刪除以下完整函式**

```bash
grep -n "^function initAdminToggles\|^function updateEmotionAdminVisibility\|^async function loadEmotionStatus\|^function switchAdminTab\|^async function loadInterventionStats\|^async function loadLogs\b\|^async function clearPushLogs\|^function topCountLabel\|^function renderCountList\b\|^async function loadSettings\b\|^async function saveSettings\b" UI_API/static/app.js
```

需刪除的函式（每個刪除整個函式體，從 `function xxx` 到對應的 `}`）：
- `initAdminToggles`
- `updateEmotionAdminVisibility`
- `loadEmotionStatus`
- `switchAdminTab`（app.js 版本）
- `loadInterventionStats`
- `loadLogs`
- `clearPushLogs`
- `topCountLabel`
- `renderCountList`
- `loadSettings`（已被 `loadEmotionSettings` 取代）
- `saveSettings`（已被 `saveEmotionSettings` 取代）

刪除後語法確認：
```bash
node --check UI_API/static/app.js
# 預期：無輸出
```

### 7d：更新 `Object.assign(window, {...})`

- [ ] **Step 4：找到並更新 window exports**

```bash
grep -n "Object.assign(window" UI_API/static/app.js
```

替換整個 `Object.assign(window, {...})` 區塊為：
```javascript
Object.assign(window, {
  closeVoiceBubble,
  switchMainView,
  switchAdminSection,
  loadClipsPage,
  loadEmotionSettings,
  saveEmotionSettings,
  clearClipsPage,
  saveMenuJson,
  loadRagPage,
  clearAllRagDocs,
  addRagDoc,
  reviewAllRagDocs,
  uploadRagPdf,
  updateCartQty: trackedUpdateCartQty,
  deleteCartItem: trackedDeleteCartItem,
  trackInteractionEvent,
  reportInteractionEvent,
  maybeCheckBarrierState,
  switchInterventionTab: window.switchInterventionTab,
  clearInterventionHistory: window.clearInterventionHistory,
});
```

### 7e：更新 startup 程式碼

- [ ] **Step 5：移除 POS startup 中的 `initAdminToggles()` 呼叫**

找到：
```javascript
  applyFeaturesToPOS();
  initAdminToggles();
  initRealtimeClients();
```
替換為：
```javascript
  applyFeaturesToPOS();
  initRealtimeClients();
```

### 7f：更新 ui.js

- [ ] **Step 6：刪除 `UI_API/static/ui.js` 中的 `switchAdminTab` 函式（lines 87-93）**

找到並刪除：
```javascript
export function switchAdminTab(id, callbacks = {}) {
  document.querySelectorAll('.admin-tab-content').forEach(el => el.classList.add('hidden'));
  document.querySelectorAll('.admin-tab').forEach(el => el.classList.remove('active'));
  document.getElementById('tab-' + id)?.classList.remove('hidden');
  document.getElementById('tab-btn-' + id)?.classList.add('active');
  if (id === 'clips') callbacks.loadEmotionClips?.();
}
```

- [ ] **Step 7：刪除 app.js 頂部的 import 引用**

找到 import 區塊中的：
```javascript
  switchAdminTab as switchAdminTabUI,
```
刪除這一行（連同換行）。

### 7g：最終確認

- [ ] **Step 8：全語法確認**

```bash
node --check UI_API/static/app.js
node --check UI_API/static/ui.js
node --check UI_API/static/api.js
# 預期：三個都無輸出
```

- [ ] **Step 9：後端 API 健在確認**

```bash
curl -s http://127.0.0.1:8000/api/settings | python3 -c "import sys,json; d=json.load(sys.stdin); print('port 8000 OK, keys:', len(d))"
curl -s http://127.0.0.1:8001/api/settings | python3 -c "import sys,json; d=json.load(sys.stdin); print('port 8001 OK, keys:', len(d))"
# 預期：各輸出 port xxxx OK, keys: <數字>
```

- [ ] **Step 10：Commit**

```bash
git add UI_API/static/app.js UI_API/static/ui.js
git commit -m "feat: switchAdminSection + 清理舊 admin 函式與 imports"
```

---

## 完成驗收

- [ ] **瀏覽器驗收（port 8001）**
  1. 開啟 `http://127.0.0.1:8001/admin`
  2. 預設畫面為儀表板：三格指標 + 介入橫幅 + 事件 Log + 底部四個導航按鈕
  3. 點「😊 Emotion/AI」→ 四個白色卡片 + 儲存按鈕，「← 返回監控」可回
  4. 點「🎬 影像片段」→ clips grid（或空狀態訊息）
  5. 點「🍔 菜單管理」→ 品項列表 + JSON 編輯器
  6. 點「📄 RAG 知識庫」→ 新增欄位 + 文件列表
  7. 儀表板每 4 秒自動刷新
  8. POS 端（port 8000）購物流程正常
