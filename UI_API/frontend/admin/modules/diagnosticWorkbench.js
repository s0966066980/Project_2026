// The workbench owns the operator-facing workflow for Daily Diagnostic Questions.
// It talks to the capability client and renders only bounded report fields; it does
// not know about storage tables or the private voice-evidence access mechanism.

/** @param {unknown} value */
const text = value => String(value ?? '').trim();
/** @param {unknown} value */
const escapeHtml = value => text(value)
  .replaceAll('&', '&amp;')
  .replaceAll('<', '&lt;')
  .replaceAll('>', '&gt;')
  .replaceAll('"', '&quot;')
  .replaceAll("'", '&#039;');

/** @param {any} report */
function findingsFrom(report) {
  const direct = report?.findings;
  if (Array.isArray(direct)) return direct;
  const section = (report?.sections || []).find((/** @type {any} */ item) => item?.id === 'findings_and_guidance');
  return Array.isArray(section?.data?.findings) ? section.data.findings : [];
}

/** @param {any} report */
function evidenceFrom(report) {
  const count = Number(report?.evidence_count ?? report?.evidence_summary?.count ?? 0);
  const level = text(report?.evidence_summary?.level)
    || text(findingsFrom(report)[0]?.evidence_level)
    || (count === 0 ? 'No Evidence' : '');
  if (count === 0) return { label: '當日沒有可分析的語音互動證據。', count, level };
  if (level === 'Observation Signal' || level === 'Insufficient Evidence') {
    return { label: `目前有 ${count} 筆證據，但證據不足以提出變更建議。`, count, level };
  }
  return { label: `已納入 ${count} 筆去識別化語音互動證據。`, count, level };
}

/**
 * Converts the API report into stable UI language. Keeping this boundary pure makes
 * the browser contract testable without coupling tests to private DOM details.
 *
 * The parameters are typed because their defaults are not: TypeScript infers
 * `null` from `report = null` and rejects every caller that passes a report.
 *
 * @param {{
 *   questions?: any[],
 *   report?: Record<string, any> | null,
 *   candidate?: Record<string, any> | null,
 *   error?: string,
 * }} [input]
 */
export function buildDiagnosticWorkbenchView({ questions = [], report = null, candidate = null, error = '' } = {}) {
  const snapshot = report?.diagnostic_question || {};
  const dialogue = report?.dialogue || {};
  const findings = findingsFrom(report).map((/** @type {any} */ finding) => ({
    label: text(finding.classification || finding.failure_type) || '未分類訊號',
    detail: `${Number(finding.occurrences || 0)} 次｜${text(finding.evidence_level) || '待確認'}`,
  }));
  const activeCandidate = candidate || report?.knowledge_change_candidate || null;
  const candidateVisible = Boolean(activeCandidate && activeCandidate.status === 'pending');
  const candidateAction = text(activeCandidate?.action).toLowerCase();
  return {
    questionLabel: text(snapshot.display_name) || text(questions[0]?.display_name) || '尚未選擇診斷問題',
    questionCount: questions.length,
    dialogue: {
      question: text(dialogue.question) || text(snapshot.prompt) || '尚無診斷結果',
      answer: text(dialogue.answer) || '執行診斷後，分析結果會顯示在這裡。',
    },
    findings,
    evidence: evidenceFrom(report),
    candidate: {
      visible: candidateVisible,
      actionLabel: candidateAction === 'update' ? '建議更新既有 RAG 知識' : '建議新增 RAG 知識',
      canConfirm: candidateVisible && activeCandidate.offline_acceptance === 'passed',
      value: activeCandidate,
    },
    status: error ? `本次診斷失敗：${text(error)}；保留上一份成功結果。` : '',
    statusTone: error ? 'attention' : '',
  };
}

function today() {
  const now = new Date();
  const offset = now.getTimezoneOffset() * 60_000;
  return new Date(now.getTime() - offset).toISOString().slice(0, 10);
}

/** @param {Document | undefined} root @param {string} id */
function element(root, id) {
  return root?.getElementById?.(id) || document.getElementById(id);
}

/** @param {Document | undefined} root @param {string} id @param {unknown} value */
function setValue(root, id, value) {
  const node = /** @type {HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement | null} */ (element(root, id));
  if (node) node.value = String(value ?? '');
}

/** @param {Document | undefined} root @param {string} id */
function getValue(root, id) {
  return text(
    /** @type {HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement | null} */ (element(root, id))?.value,
  );
}

/**
 * The defaults alone infer `never[]` and `null`, so every real question,
 * profile, report and candidate the client returns is rejected. The state is
 * typed here rather than at each of the fifty use sites.
 *
 * @param {{
 *   client?: any,
 *   root?: Document,
 *   confirmAction?: (message: string) => boolean,
 * }} input
 */
export function createDiagnosticWorkbench({ client, root = document, confirmAction = message => window.confirm(message) }) {
  /** @type {{questions: any[], profiles: any[], report: any, candidate: any, error: string, loading: boolean, editingQuestionId: string}} */
  let state = { questions: [], profiles: [], report: null, candidate: null, error: '', loading: false, editingQuestionId: '' };

  function status(message = '', tone = '') {
    const node = element(root, 'diagnosticStatus');
    if (!node) return;
    node.textContent = message;
    node.className = `diagnostic-status${tone ? ` ${tone}` : ''}`;
  }

  function renderQuestions() {
    const list = element(root, 'diagnosticQuestionList');
    const count = element(root, 'diagnosticQuestionCount');
    if (count) count.textContent = `${state.questions.length} 個`;
    const select = /** @type {HTMLSelectElement & HTMLInputElement | null} */ (element(root, 'diagnosticQuestion'));
    if (select) {
      select.innerHTML = state.questions.map((/** @type {any} */ question) => `<option value="${escapeHtml(question.question_id)}">${escapeHtml(question.display_name)}</option>`).join('');
      if (state.report?.diagnostic_question?.question_id) select.value = state.report.diagnostic_question.question_id;
    }
    if (!list) return;
    if (!state.questions.length) {
      list.innerHTML = '<div class="diagnostic-empty">尚未建立診斷問題。</div>';
      return;
    }
    list.innerHTML = state.questions.map((/** @type {any} */ question) => `
      <article class="diagnostic-question-card" data-question-id="${escapeHtml(question.question_id)}">
        <div><strong>${escapeHtml(question.display_name)}</strong><p>${escapeHtml(question.prompt)}</p></div>
        <div class="diagnostic-card-actions">
          <button type="button" class="btn diagnostic-edit-question" data-question-id="${escapeHtml(question.question_id)}">編輯</button>
          <button type="button" class="btn diagnostic-delete-question" data-question-id="${escapeHtml(question.question_id)}">刪除</button>
        </div>
      </article>`).join('');
    list.querySelectorAll('.diagnostic-edit-question').forEach(button => button.addEventListener('click', () => {
      const question = state.questions.find((/** @type {any} */ item) => item.question_id === /** @type {HTMLElement} */ (button).dataset.questionId);
      if (!question) return;
      state.editingQuestionId = question.question_id;
      setValue(root, 'diagnosticQuestionName', question.display_name);
      setValue(root, 'diagnosticQuestionPrompt', question.prompt);
      const save = element(root, 'diagnosticQuestionSave');
      if (save) save.textContent = '儲存問題';
    }));
    list.querySelectorAll('.diagnostic-delete-question').forEach(button => button.addEventListener('click', async () => {
      if (!confirmAction('刪除後不會再自動建立這個問題，既有報告仍會保留。確定刪除？')) return;
      try {
        await client.deleteQuestion(/** @type {HTMLElement} */ (button).dataset.questionId);
        state.questions = (await client.questions()).questions || [];
        renderQuestions();
        status('問題已刪除。');
      } catch (/** @type {any} */ error) { status(`刪除失敗：${text(error.message)}`, 'attention'); }
    }));
  }

  function renderReport() {
    const view = buildDiagnosticWorkbenchView(state);
    const question = element(root, 'diagnosticDialogueQuestion');
    const answer = element(root, 'diagnosticDialogueAnswer');
    if (question) question.textContent = view.dialogue.question;
    if (answer) answer.textContent = view.dialogue.answer;
    const evidence = element(root, 'diagnosticEvidence');
    if (evidence) evidence.textContent = view.evidence.label;
    const findings = element(root, 'diagnosticFindings');
    if (findings) findings.innerHTML = view.findings.length
      ? view.findings.map((/** @type {any} */ item) => `<li><strong>${escapeHtml(item.label)}</strong><span>${escapeHtml(item.detail)}</span></li>`).join('')
      : '<li><span>目前沒有可顯示的分類結果。</span></li>';
    const candidatePanel = element(root, 'diagnosticCandidate');
    if (candidatePanel) candidatePanel.hidden = !view.candidate.visible;
    if (view.candidate.visible) {
      const candidate = view.candidate.value;
      setValue(root, 'diagnosticCandidateTitle', candidate.proposed?.title);
      setValue(root, 'diagnosticCandidateCategory', candidate.proposed?.category);
      setValue(root, 'diagnosticCandidateType', candidate.proposed?.content_type);
      setValue(root, 'diagnosticCandidateContent', candidate.proposed?.content);
      const action = element(root, 'diagnosticCandidateAction');
      if (action) action.textContent = view.candidate.actionLabel;
      const confirm = /** @type {HTMLButtonElement | null} */ (element(root, 'diagnosticCandidateConfirm'));
      if (confirm) confirm.disabled = !view.candidate.canConfirm;
    }
    status(view.status, view.statusTone);
  }

  function renderProfiles() {
    const select = /** @type {HTMLSelectElement & HTMLInputElement | null} */ (element(root, 'diagnosticProfile'));
    if (!select) return;
    const dataScope = getValue(root, 'diagnosticDataScope') || 'customer_evidence';
    const profiles = state.profiles.filter((/** @type {any} */ profile) => (profile.data_scopes || []).includes(dataScope));
    select.innerHTML = profiles.map((/** @type {any} */ profile) => `<option value="${escapeHtml(profile.id)}" data-ready="${profile.ready ? 'true' : 'false'}">${escapeHtml(profile.id)}${profile.ready ? '' : '（未就緒）'}</option>`).join('');
    const model = /** @type {HTMLSelectElement & HTMLInputElement | null} */ (element(root, 'diagnosticModel'));
    const selected = profiles.find((/** @type {any} */ profile) => profile.id === select.value) || profiles.find((/** @type {any} */ profile) => profile.ready);
    if (selected) {
      select.value = selected.id;
      if (model && !getValue(root, 'diagnosticModel')) model.value = selected.models?.[0] || '';
    }
  }

  async function load() {
    state.loading = true;
    status('正在載入診斷工作台…');
    try {
      const [questions, profiles, latest, pending] = await Promise.all([
        client.questions(), client.profiles(), client.latest(), client.candidate(),
      ]);
      state.questions = questions.questions || [];
      state.profiles = profiles.profiles || [];
      state.report = latest.report || null;
      state.candidate = pending.candidate || null;
      state.error = '';
      renderQuestions(); renderProfiles(); renderReport();
      if (element(root, 'diagnosticDate') && !getValue(root, 'diagnosticDate')) setValue(root, 'diagnosticDate', today());
    } catch (/** @type {any} */ error) {
      state.error = error.message || '無法載入診斷工作台';
      status(`載入失敗：${state.error}`, 'attention');
    } finally { state.loading = false; }
  }

  /** @param {Event} event */
  async function saveQuestion(event) {
    event?.preventDefault?.();
    const displayName = getValue(root, 'diagnosticQuestionName');
    const prompt = getValue(root, 'diagnosticQuestionPrompt');
    if (!displayName || !prompt) { status('請填寫問題名稱與完整 Prompt。', 'attention'); return; }
    try {
      if (state.editingQuestionId) await client.updateQuestion(state.editingQuestionId, { display_name: displayName, prompt });
      else await client.createQuestion({ display_name: displayName, prompt });
      state.editingQuestionId = '';
      setValue(root, 'diagnosticQuestionName', ''); setValue(root, 'diagnosticQuestionPrompt', '');
      const save = element(root, 'diagnosticQuestionSave'); if (save) save.textContent = '新增問題';
      state.questions = (await client.questions()).questions || [];
      renderQuestions(); status('問題已儲存，未來診斷會使用最新內容。');
    } catch (/** @type {any} */ error) { status(`儲存問題失敗：${text(error.message)}`, 'attention'); }
  }

  async function run() {
    const profile = getValue(root, 'diagnosticProfile');
    const model = getValue(root, 'diagnosticModel');
    const effort = getValue(root, 'diagnosticEffort');
    if (!profile || !model || !effort || !state.questions.length) {
      status('請先選擇問題、分析設定檔、模型與推理強度。', 'attention'); return;
    }
    if (state.candidate?.status === 'pending') {
      if (!confirmAction('目前有待確認的 RAG 候選。開始新診斷前必須放棄它，確定繼續？')) return;
      try { await client.abandonCandidate(state.candidate.candidate_id); state.candidate = null; }
      catch (/** @type {any} */ error) { status(`無法放棄候選：${text(error.message)}`, 'attention'); return; }
    }
    const button = /** @type {HTMLButtonElement | null} */ (element(root, 'diagnosticRun'));
    if (button) button.disabled = true;
    const previous = state.report;
    status('正在分析今日營運證據…');
    try {
      const response = await client.simulate({
        store_date: getValue(root, 'diagnosticDate') || today(),
        timezone: Intl.DateTimeFormat().resolvedOptions().timeZone || 'Asia/Taipei',
        profile, model, effort, data_scope: getValue(root, 'diagnosticDataScope') || 'customer_evidence',
        question_id: getValue(root, 'diagnosticQuestion'),
      });
      state.report = response;
      state.candidate = response.knowledge_change_candidate || null;
      state.error = '';
      renderReport();
    } catch (/** @type {any} */ error) {
      state.report = previous;
      state.error = text(error.message) || '分析失敗';
      renderReport();
    } finally { if (button) button.disabled = false; }
  }

  async function saveCandidate() {
    const candidate = state.candidate;
    if (!candidate) return;
    try {
      state.candidate = (await client.editCandidate(candidate.candidate_id, {
        title: getValue(root, 'diagnosticCandidateTitle'),
        category: getValue(root, 'diagnosticCandidateCategory'),
        content_type: getValue(root, 'diagnosticCandidateType'),
        content: getValue(root, 'diagnosticCandidateContent'),
      })).candidate;
      renderReport(); status('候選已更新，離線驗證已重新執行。');
    } catch (/** @type {any} */ error) { status(`候選預覽失敗：${text(error.message)}`, 'attention'); }
  }

  async function confirmCandidate() {
    if (!state.candidate) return;
    try {
      state.candidate = (await client.confirmCandidate(state.candidate.candidate_id)).candidate;
      renderReport(); status('已送入既有 RAG 發布流程。');
    } catch (/** @type {any} */ error) { status(`RAG 確認失敗：${text(error.message)}`, 'attention'); }
  }

  element(root, 'diagnosticQuestionForm')?.addEventListener('submit', saveQuestion);
  element(root, 'diagnosticRun')?.addEventListener('click', run);
  element(root, 'diagnosticCandidateSave')?.addEventListener('click', saveCandidate);
  element(root, 'diagnosticCandidateConfirm')?.addEventListener('click', confirmCandidate);
  element(root, 'diagnosticCandidateAbandon')?.addEventListener('click', async () => {
    if (!state.candidate || !confirmAction('放棄這份 RAG 候選？既有報告仍會保留。')) return;
    try { state.candidate = (await client.abandonCandidate(state.candidate.candidate_id)).candidate; renderReport(); status('候選已放棄。'); }
    catch (/** @type {any} */ error) { status(`放棄候選失敗：${text(error.message)}`, 'attention'); }
  });
  element(root, 'diagnosticProfile')?.addEventListener('change', event => {
    const selected = state.profiles.find((/** @type {any} */ profile) => profile.id === /** @type {HTMLInputElement} */ (event.target).value);
    setValue(root, 'diagnosticModel', selected?.models?.[0] || '');
  });
  element(root, 'diagnosticDataScope')?.addEventListener('change', () => {
    setValue(root, 'diagnosticModel', '');
    renderProfiles();
  });

  return { load, run, saveQuestion, saveCandidate, confirmCandidate, render: renderReport, getState: () => state };
}
