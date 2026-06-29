/* ===========================================================
   焊口管理系統 前端邏輯 (vanilla JS)
   =========================================================== */
const State = { project: null, projects: [], lookups: {}, drawings: [] };

/* ---------- 共用工具 ---------- */
const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];
const operator = () => $('#operator').value.trim() || 'user';

async function api(method, path, body) {
  const opt = { method, headers: {} };
  if (body !== undefined) {
    if (body && typeof body === 'object' && !(body instanceof FormData)) {
      body._operator = operator();
      opt.headers['Content-Type'] = 'application/json';
      opt.body = JSON.stringify(body);
    } else { opt.body = body; }
  }
  const r = await fetch('/api' + path, opt);
  if (!r.ok) {
    let msg = r.status;
    try { msg = (await r.json()).detail || msg; } catch (e) {}
    toast('錯誤:' + msg, 'err');
    throw new Error(msg);
  }
  const ct = r.headers.get('content-type') || '';
  return ct.includes('json') ? r.json() : r;
}

function toast(msg, type = 'ok') {
  const t = document.createElement('div');
  t.className = 'toast ' + type; t.textContent = msg;
  $('#toast').appendChild(t);
  setTimeout(() => t.remove(), 2800);
}

const esc = s => (s == null ? '' : String(s).replace(/[&<>"]/g, c =>
  ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c])));

function statusBadge(s) {
  const map = { '規劃': 'gray', '組對': 'blue', '完銲': 'blue', '待檢': 'amber',
    '合格': 'green', '不合格': 'red', '試壓': 'amber', '完成': 'green' };
  return `<span class="badge ${map[s] || 'gray'}">${esc(s || '—')}</span>`;
}

/* ---------- Modal ---------- */
function openModal(title, bodyHTML, buttons) {
  $('#modalTitle').textContent = title;
  $('#modalBody').innerHTML = bodyHTML;
  const f = $('#modalFooter'); f.innerHTML = '';
  (buttons || []).forEach(b => {
    const btn = document.createElement('button');
    btn.className = 'btn ' + (b.cls || '');
    btn.textContent = b.label;
    btn.onclick = b.onClick;
    f.appendChild(btn);
  });
  $('#overlay').classList.add('show');
}
const closeModal = () => $('#overlay').classList.remove('show');
$('#modalClose').onclick = closeModal;
$('#overlay').onclick = e => { if (e.target === $('#overlay')) closeModal(); };

/* ---------- 表單產生器 ---------- */
function fieldHTML(f, data) {
  const v = data && data[f.key] != null ? data[f.key] : (f.default ?? '');
  const id = 'f_' + f.key;
  let inner;
  if (f.type === 'select') {
    const opts = (f.options || []).map(o =>
      `<option value="${esc(o.v)}" ${String(o.v) === String(v) ? 'selected' : ''}>${esc(o.t)}</option>`).join('');
    inner = `<select id="${id}">${f.empty !== false ? '<option value="">—</option>' : ''}${opts}</select>`;
  } else if (f.type === 'textarea') {
    inner = `<textarea id="${id}" placeholder="${esc(f.ph || '')}">${esc(v)}</textarea>`;
  } else if (f.type === 'checkbox') {
    inner = `<select id="${id}"><option value="0" ${!v || v == 0 ? 'selected' : ''}>否</option><option value="1" ${v == 1 ? 'selected' : ''}>是</option></select>`;
  } else {
    inner = `<input id="${id}" type="${f.type || 'text'}" value="${esc(v)}" placeholder="${esc(f.ph || '')}">`;
  }
  return `<div class="fg ${f.full ? 'full' : ''}"><label>${esc(f.label)}</label>${inner}</div>`;
}

function formHTML(fields, data) {
  let html = '<div class="formgrid">';
  fields.forEach(f => {
    if (f.section) html += `<div class="section-label">${esc(f.section)}</div>`;
    html += fieldHTML(f, data);
  });
  return html + '</div>';
}

function collectForm(fields) {
  const out = {};
  fields.forEach(f => {
    const elx = $('#f_' + f.key);
    if (!elx) return;
    let val = elx.value;
    if (val === '') val = null;
    else if (f.type === 'number' || f.type === 'checkbox') val = Number(val);
    out[f.key] = val;
  });
  return out;
}

/* ---------- 啟動 ---------- */
async function boot() {
  $('#operator').value = localStorage.getItem('op') || '';
  $('#operator').onchange = () => localStorage.setItem('op', $('#operator').value);
  bindTabs();
  bindButtons();
  await loadProjects();
}

function bindTabs() {
  $$('#tabs button').forEach(b => b.onclick = () => {
    $$('#tabs button').forEach(x => x.classList.remove('active'));
    b.classList.add('active');
    $$('.view').forEach(v => v.classList.remove('active'));
    $('#view-' + b.dataset.view).classList.add('active');
    renderView(b.dataset.view);
  });
}

async function loadProjects() {
  State.projects = await api('GET', '/projects');
  const sel = $('#projectSel');
  sel.innerHTML = State.projects.map(p => `<option value="${p.id}">${esc(p.code)} — ${esc(p.name)}</option>`).join('')
    || '<option value="">(尚無專案,請先匯入或新增)</option>';
  sel.onchange = () => selectProject(Number(sel.value));
  if (State.projects.length) await selectProject(State.projects[0].id);
  else renderView('dashboard');
}

async function selectProject(pid) {
  State.project = State.projects.find(p => p.id === pid);
  $('#projectSel').value = pid;
  State.lookups = await api('GET', `/projects/${pid}/lookups`);
  // 狀態/系統篩選下拉
  $('#jointStatus').innerHTML = '<option value="">全部狀態</option>' +
    State.lookups.statuses.map(s => `<option>${s}</option>`).join('');
  $('#jointSystem').innerHTML = '<option value="">全部系統</option>' +
    State.lookups.systems.map(s => `<option value="${esc(s.code)}">${esc(s.code)}</option>`).join('');
  const active = $('#tabs button.active').dataset.view;
  renderView(active);
}

function renderView(v) {
  if (!State.project && v !== 'io' && v !== 'dashboard') {
    $('#view-' + v).querySelectorAll('.tablewrap tbody').forEach(b => b.innerHTML = '');
  }
  ({ dashboard: renderDashboard, drawings: renderDrawings, joints: renderJoints,
     spools: renderSpools, billing: renderBilling, issues: renderIssues, master: renderMaster,
     audit: renderAudit, io: () => {} }[v] || (() => {}))();
}

/* ===========================================================
   儀表板
   =========================================================== */
async function renderDashboard() {
  if (!State.project) { $('#kpiCards').innerHTML = '<div class="card">尚無專案,請到「匯入/匯出」匯入,或新增專案。</div>'; return; }
  $('#dashSub').textContent = `${State.project.code} — ${State.project.name}` + (State.project.owner ? ` ｜ 業主:${State.project.owner}` : '');
  const d = await api('GET', `/projects/${State.project.id}/dashboard`);
  $('#kpiCards').innerHTML = [
    kpi('焊口總數', d.total_joints, `已完銲 ${d.welded}`, d.pct, ''),
    kpi('完成率 (口數)', d.pct + '%', `${d.welded}/${d.total_joints}`, d.pct, ''),
    kpi('DB 數完成率', d.db_pct + '%', `${d.db_done}/${d.db_total}`, d.db_pct, 'blue'),
    kpi('RT 合格率', d.rt_pass_pct + '%', `已檢 ${d.rt_done}・不合格 ${d.rt_fail}`, d.rt_pass_pct, 'amber'),
    kpi('圖面 / 已掃描', `${d.scanned}/${d.drawings}`, '預製圖掃描', d.drawings ? d.scanned / d.drawings * 100 : 0, 'blue'),
    kpi('待處理問題', d.issues_open, d.issues_open ? '需追蹤' : '無', d.issues_open ? 100 : 0, 'amber'),
  ].join('');
  distrib('#bySystem', d.by_system, r => r.code, r => r.n, r => `${r.done}/${r.n}`);
  distrib('#byType', d.by_type, r => r.code, r => r.n, r => `${r.done}/${r.n}`);
  distrib('#byStatus', d.by_status, r => r.status, r => r.n, r => r.n);
  distrib('#byBilling', d.by_billing, r => r.code, r => r.db, r => r.db);
}
function kpi(label, value, sub, pct, cls) {
  return `<div class="card kpi ${cls}"><div class="label">${label}</div>
    <div class="value">${value} <small>${sub || ''}</small></div>
    <div class="bar"><i style="width:${Math.min(pct || 0, 100)}%"></i></div></div>`;
}
function distrib(sel, rows, kf, vf, lf) {
  if (!rows || !rows.length) { $(sel).innerHTML = '<div class="muted">無資料</div>'; return; }
  const max = Math.max(...rows.map(vf), 1);
  $(sel).innerHTML = rows.map(r =>
    `<div class="item"><div>${esc(kf(r))}</div>
      <div class="track"><i style="width:${vf(r) / max * 100}%"></i></div>
      <div class="num">${esc(lf(r))}</div></div>`).join('');
}

/* ===========================================================
   圖面
   =========================================================== */
async function renderDrawings() {
  if (!State.project) return;
  const q = $('#drawingSearch').value.trim();
  const res = await api('GET', `/projects/${State.project.id}/drawings?q=${encodeURIComponent(q)}`);
  const cols = ['流水號', '圖號', '系統', '管線', '尺寸', '等級', '版次', '掃描日期', '焊口數', '狀態', ''];
  $('#drawingTable thead').innerHTML = '<tr>' + cols.map(c => `<th>${c}</th>`).join('') + '</tr>';
  $('#drawingTable tbody').innerHTML = res.rows.length ? res.rows.map(r => `<tr>
    <td class="mono">${esc(r.serial_no)}</td><td>${esc(r.drawing_no)}</td>
    <td>${esc(r.system_code)}</td><td class="muted">${esc(r.line_no)}</td>
    <td>${esc(r.size)}</td><td>${esc(r.pipe_class)}</td><td>${esc(r.current_rev)}</td>
    <td>${esc(r.scan_date) || '<span class="muted">未掃</span>'}</td>
    <td class="mono">${r.joint_count}</td><td>${esc(r.status)}</td>
    <td><button class="btn sm" onclick="editDrawing(${r.id})">編輯</button></td></tr>`).join('')
    : `<tr><td colspan="11" class="empty">尚無圖面</td></tr>`;
}
$('#drawingSearch').oninput = debounce(renderDrawings, 300);

function drawingFields() {
  return [
    { key: 'drawing_no', label: '圖號 (業主) *', full: false },
    { key: 'serial_no', label: '流水號 (留空自動配)' },
    { key: 'system_id', label: '系統', type: 'select', options: State.lookups.systems.map(s => ({ v: s.id, t: s.code })) },
    { key: 'line_id', label: '管線', type: 'select', options: State.lookups.lines.map(s => ({ v: s.id, t: s.line_no })) },
    { key: 'size', label: '尺寸' }, { key: 'pipe_class', label: '管道等級' },
    { key: 'sheet_index', label: '第幾張', type: 'number' }, { key: 'num_sheets', label: '共幾張', type: 'number' },
    { key: 'current_rev', label: '現行版次' }, { key: 'rev_date', label: '版次日期', type: 'date' },
    { key: 'scan_date', label: '預製掃描日期', type: 'date' },
    { key: 'status', label: '狀態', type: 'select', empty: false, options: [{ v: '啟用', t: '啟用' }, { v: '作廢', t: '作廢' }] },
    { key: 'pdf_path', label: 'PDF 路徑/連結', full: true },
    { key: 'remark', label: '備註', type: 'textarea', full: true },
  ];
}
async function editDrawing(id) {
  const data = id ? (await api('GET', `/projects/${State.project.id}/drawings`)).rows.find(r => r.id === id) : {};
  const fields = drawingFields();
  openModal(id ? '編輯圖面' : '新增圖面', formHTML(fields, data), [
    id ? { label: '刪除', cls: 'danger', onClick: () => delDrawing(id) } : null,
    { label: '取消', onClick: closeModal },
    { label: '儲存', cls: 'primary', onClick: async () => {
        const body = collectForm(fields);
        if (!body.drawing_no) return toast('請填圖號', 'err');
        if (id) await api('PUT', `/drawings/${id}`, body);
        else await api('POST', `/projects/${State.project.id}/drawings`, body);
        toast('已儲存'); closeModal(); renderDrawings();
      } },
  ].filter(Boolean));
}
async function delDrawing(id) {
  if (!confirm('確定刪除此圖面?其焊口的圖面關聯會被清除。')) return;
  await api('DELETE', `/drawings/${id}?operator=${encodeURIComponent(operator())}`);
  toast('已刪除'); closeModal(); renderDrawings();
}
$('#addDrawingBtn').onclick = () => editDrawing(0);

/* ===========================================================
   焊口
   =========================================================== */
async function renderJoints() {
  if (!State.project) return;
  const p = new URLSearchParams({
    q: $('#jointSearch').value.trim(), status: $('#jointStatus').value,
    system: $('#jointSystem').value, limit: 300,
  });
  const res = await api('GET', `/projects/${State.project.id}/joints?` + p);
  $('#jointCount').textContent = `共 ${res.total} 筆` + (res.total > 300 ? '(顯示前 300)' : '');
  const cols = ['流水號', '圖號', '銲口', '尺寸', '材質', '型式', 'S/F', 'Spool', '完成日期', '狀態', '檢驗', '請款期別', ''];
  $('#jointTable thead').innerHTML = '<tr>' + cols.map(c => `<th>${c}</th>`).join('') + '</tr>';
  $('#jointTable tbody').innerHTML = res.rows.length ? res.rows.map(r => `<tr class="clickable" onclick="editJoint(${r.id})">
    <td class="mono">${esc(r.serial_no)}</td><td>${esc(r.drawing_no)}</td>
    <td class="mono">${esc(r.joint_no)}</td><td>${esc(r.size)}</td><td>${esc(r.material)}</td>
    <td>${esc(r.weld_type)}</td><td>${esc(r.shop_field)}</td><td class="mono">${esc(r.spool_no) || ''}</td><td>${esc(r.weld_date) || ''}</td>
    <td>${statusBadge(r.status)}</td>
    <td>${r.nde_result ? esc(r.nde_result) : (r.nde_type ? '<span class="muted">待檢</span>' : '')}</td>
    <td>${esc(r.billing_period) || ''}</td>
    <td><button class="btn sm" onclick="event.stopPropagation();advanceJoint(${r.id})">推進▶</button></td></tr>`).join('')
    : `<tr><td colspan="13" class="empty">尚無焊口</td></tr>`;
}
['jointSearch'].forEach(id => $('#' + id).oninput = debounce(renderJoints, 300));
['jointStatus', 'jointSystem'].forEach(id => $('#' + id).onchange = renderJoints);

function jointFields() {
  const L = State.lookups;
  return [
    { section: '基本資料' },
    { key: 'drawing_id', label: '所屬圖面', type: 'select', options: State.drawings.map(d => ({ v: d.id, t: (d.serial_no ? d.serial_no + '｜' : '') + d.drawing_no })) },
    { key: 'spool_id', label: 'Spool 分段', type: 'select', options: (State.spoolOptions || []).map(s => ({ v: s.id, t: s.spool_no + (s.shop_field ? ` (${s.shop_field})` : '') })) },
    { key: 'joint_no', label: '銲口編號 *' },
    { key: 'size', label: '尺寸' }, { key: 'thickness', label: '厚度' },
    { key: 'schedule', label: 'SCH' }, { key: 'material', label: '材質' },
    { key: 'weld_type_id', label: '銲接型式', type: 'select', options: L.weld_types.map(w => ({ v: w.id, t: w.code + (w.name ? ' ' + w.name : '') })) },
    { key: 'joint_category', label: '分類 (消防/工業級…)' },
    { key: 'db_factor', label: '係數', type: 'number', default: 1 }, { key: 'db_count', label: 'DB 數(留空自動計算)', type: 'number' },
    { key: 'shop_field', label: '預製S/現場F', type: 'select', options: [{ v: 'S', t: 'S 預製' }, { v: 'F', t: 'F 現場' }] },
    { section: '製程與追溯' },
    { key: 'welding_process', label: '銲接製程 (GTAW…)' },
    { key: 'wps_id', label: 'WPS', type: 'select', options: L.wps.map(w => ({ v: w.id, t: w.wps_no })) },
    { key: 'welder_root_id', label: '打底焊工', type: 'select', options: L.welders.map(w => ({ v: w.id, t: w.stamp + (w.name ? ' ' + w.name : '') })) },
    { key: 'welder_cap_id', label: '蓋面焊工', type: 'select', options: L.welders.map(w => ({ v: w.id, t: w.stamp + (w.name ? ' ' + w.name : '') })) },
    { key: 'fitup_by', label: '組對者' }, { key: 'fitup_date', label: '組對日期', type: 'date' },
    { key: 'weld_date', label: '完銲(配管完成)日期', type: 'date' }, { key: 'heat_no', label: '爐號' },
    { section: '檢驗 NDE' },
    { key: 'nde_type', label: '檢驗方式', type: 'select', empty: true, options: ['RT', 'PT', 'MT', 'UT', 'VT'].map(x => ({ v: x, t: x })) },
    { key: 'nde_percent', label: '比例 (10%/100%)' }, { key: 'nde_date', label: '檢驗日期', type: 'date' },
    { key: 'nde_result', label: '結果', type: 'select', options: [{ v: '合格', t: '合格' }, { v: '不合格', t: '不合格' }] },
    { key: 'nde_report_no', label: '報告/RT圖號' }, { key: 'repair_count', label: '補焊次數', type: 'number', default: 0 },
    { section: 'PWHT / 試壓' },
    { key: 'pwht_required', label: '需 PWHT', type: 'checkbox' }, { key: 'pwht_done', label: 'PWHT 完成', type: 'checkbox' },
    { key: 'pwht_date', label: 'PWHT 日期', type: 'date' }, { key: 'test_package', label: '試壓包' },
    { key: 'test_date', label: '試壓日期', type: 'date' }, { key: 'test_result', label: '試壓結果' },
    { section: '狀態與商務' },
    { key: 'status', label: '狀態', type: 'select', empty: false, options: L.statuses.map(s => ({ v: s, t: s })) },
    { key: 'subcontractor', label: '承包商' },
    { key: 'billing_period_id', label: '請款期別', type: 'select', options: L.billing_periods.map(b => ({ v: b.id, t: b.code })) },
    { key: 'claim_status', label: '請款狀態', type: 'select', empty: false, options: [{ v: '未請款', t: '未請款' }, { v: '已請款', t: '已請款' }] },
    { key: 'remark', label: '備註', type: 'textarea', full: true },
  ];
}

async function editJoint(id) {
  // 確保 drawings 下拉資料
  if (!State.drawings.length || State.drawings._pid !== State.project.id) {
    const dr = await api('GET', `/projects/${State.project.id}/drawings?limit=2000`);
    State.drawings = dr.rows; State.drawings._pid = State.project.id;
  }
  const data = id ? await api('GET', `/joints/${id}`) : {};
  State.spoolOptions = [];
  if (data.drawing_id) {
    try { State.spoolOptions = await api('GET', `/drawings/${data.drawing_id}/spools`); } catch (e) {}
  }
  const fields = jointFields();
  let body = formHTML(fields, data);
  if (id && data.inspections) body += inspectionBlock(id, data.inspections);
  if (id) body += materialBlock(id, data.materials || []);
  openModal(id ? `編輯焊口  ${esc(data.joint_no || '')}` : '新增焊口', body, [
    id ? { label: '刪除', cls: 'danger', onClick: () => delJoint(id) } : null,
    { label: '取消', onClick: closeModal },
    { label: '儲存', cls: 'primary', onClick: async () => {
        const b = collectForm(fields);
        if (!b.joint_no) return toast('請填銲口編號', 'err');
        if (id) await api('PUT', `/joints/${id}`, b);
        else await api('POST', `/projects/${State.project.id}/joints`, b);
        toast('已儲存'); closeModal(); renderJoints();
      } },
  ].filter(Boolean));
}
function inspectionBlock(jid, list) {
  const rows = list.map(i => `<tr><td>${esc(i.method)}</td><td>${esc(i.percent)}</td>
    <td>${esc(i.inspect_date)}</td><td>${esc(i.result)}</td><td>${esc(i.report_no)}</td></tr>`).join('')
    || '<tr><td colspan="5" class="muted">尚無檢驗紀錄</td></tr>';
  return `<div class="section-label" style="margin-top:18px">檢驗紀錄</div>
    <table style="width:100%;font-size:13px"><thead><tr><th>方式</th><th>比例</th><th>日期</th><th>結果</th><th>報告</th></tr></thead><tbody>${rows}</tbody></table>
    <div class="formgrid three" style="margin-top:10px">
      <div class="fg"><label>方式</label><select id="i_method"><option>RT</option><option>PT</option><option>MT</option><option>UT</option><option>VT</option></select></div>
      <div class="fg"><label>日期</label><input id="i_date" type="date"></div>
      <div class="fg"><label>結果</label><select id="i_result"><option>合格</option><option>不合格</option></select></div>
      <div class="fg"><label>報告號</label><input id="i_report"></div>
      <div class="fg" style="align-self:end"><button class="btn sm primary" onclick="addInspection(${jid})">＋ 新增檢驗</button></div>
    </div>`;
}
async function addInspection(jid) {
  await api('POST', `/joints/${jid}/inspections`, {
    method: $('#i_method').value, inspect_date: $('#i_date').value || null,
    result: $('#i_result').value, report_no: $('#i_report').value || null,
  });
  toast('已新增檢驗'); editJoint(jid);
}
function materialBlock(jid, list) {
  const L = State.lookups;
  const rows = (list || []).map(m => `<tr><td>${esc(m.role)}</td><td>${esc(m.heat_no) || ''}</td>
    <td>${esc(m.batch_no) || ''}${m.aws_class ? ' ' + esc(m.aws_class) : ''}</td>
    <td><button class="btn sm danger" onclick="delJointMaterial(${m.id},${jid})">刪</button></td></tr>`).join('')
    || '<tr><td colspan="4" class="muted">尚無材料</td></tr>';
  const heatOpts = (L.heats || []).map(h => `<option value="${h.id}">${esc(h.heat_no)}</option>`).join('');
  const fillerOpts = (L.fillers || []).map(f => `<option value="${f.id}">${esc(f.batch_no)}</option>`).join('');
  return `<div class="section-label" style="margin-top:18px">材料追溯 (爐號 / 銲材)</div>
    <table style="width:100%;font-size:13px"><thead><tr><th>角色</th><th>爐號</th><th>銲材</th><th></th></tr></thead><tbody>${rows}</tbody></table>
    <div class="formgrid three" style="margin-top:10px">
      <div class="fg"><label>角色</label><select id="m_role"><option>A側母材</option><option>B側母材</option><option>銲材</option><option>背檔氣</option></select></div>
      <div class="fg"><label>爐號</label><select id="m_heat"><option value="">—</option>${heatOpts}</select></div>
      <div class="fg"><label>銲材</label><select id="m_filler"><option value="">—</option>${fillerOpts}</select></div>
      <div class="fg" style="align-self:end"><button class="btn sm primary" onclick="addJointMaterial(${jid})">＋ 新增材料</button></div>
    </div>`;
}
async function addJointMaterial(jid) {
  const payload = { role: $('#m_role').value, heat_id: $('#m_heat').value || null, filler_id: $('#m_filler').value || null };
  if (!payload.heat_id && !payload.filler_id) return toast('請選爐號或銲材', 'err');
  await api('POST', `/joints/${jid}/materials`, payload);
  toast('已新增材料'); editJoint(jid);
}
async function delJointMaterial(mid, jid) {
  await api('DELETE', `/jmaterials/${mid}?operator=${encodeURIComponent(operator())}`);
  toast('已刪除'); editJoint(jid);
}
async function advanceJoint(id) {
  await api('POST', `/joints/${id}/advance`, {});
  toast('狀態已推進'); renderJoints();
}
async function delJoint(id) {
  if (!confirm('確定刪除此焊口?')) return;
  await api('DELETE', `/joints/${id}?operator=${encodeURIComponent(operator())}`);
  toast('已刪除'); closeModal(); renderJoints();
}
$('#addJointBtn').onclick = () => editJoint(0);
$('#recomputeDbBtn').onclick = async () => {
  if (!State.project) return;
  if (!confirm('將為「DB數空白」且有尺寸的焊口自動補算 DB數(max(1,吋)×係數),確定?')) return;
  const r = await api('POST', `/projects/${State.project.id}/joints/recompute-db`, { only_blank: true });
  toast(`已補算 ${r.updated} 筆`); renderJoints();
};

/* ===========================================================
   Spool 分段
   =========================================================== */
async function renderSpools() {
  if (!State.project) return;
  const q = $('#spoolSearch').value.trim();
  const res = await api('GET', `/projects/${State.project.id}/spools?q=${encodeURIComponent(q)}`);
  $('#spoolCount').textContent = `共 ${res.total} 個`;
  const cols = ['圖號', '流水號', 'Spool 編號', 'S/F', '狀態', '焊口數', '完成', 'DB數', '預製圖掃描', ''];
  $('#spoolTable thead').innerHTML = '<tr>' + cols.map(c => `<th>${c}</th>`).join('') + '</tr>';
  $('#spoolTable tbody').innerHTML = res.rows.length ? res.rows.map(r => `<tr>
    <td>${esc(r.drawing_no)}</td><td class="mono">${esc(r.serial_no)}</td>
    <td class="mono">${esc(r.spool_no)}</td><td>${esc(r.shop_field)}</td>
    <td>${statusBadge(r.status)}</td><td class="mono">${r.joint_count}</td>
    <td class="mono">${r.welded}/${r.joint_count}</td><td class="mono">${r.db}</td>
    <td>${esc(r.scan_date) || '<span class="muted">—</span>'}</td>
    <td><button class="btn sm" onclick="editSpool(${r.id})">編輯</button></td></tr>`).join('')
    : `<tr><td colspan="10" class="empty">尚無 spool,可按「自動建立預製 spool」或「新增 spool」</td></tr>`;
}
$('#spoolSearch').oninput = debounce(renderSpools, 300);

function spoolFields() {
  return [
    { key: 'drawing_id', label: '所屬圖面 *', type: 'select', options: State.drawings.map(d => ({ v: d.id, t: (d.serial_no ? d.serial_no + '｜' : '') + d.drawing_no })) },
    { key: 'spool_no', label: 'Spool 編號 *' },
    { key: 'shop_field', label: '性質', type: 'select', empty: false, options: [{ v: 'S', t: 'S 預製' }, { v: 'F', t: 'F 現場' }] },
    { key: 'status', label: '狀態', type: 'select', empty: false, options: ['規劃', '下料', '組對', '銲接', 'NDE', '油漆', '完成', '出貨'].map(s => ({ v: s, t: s })) },
    { key: 'fab_dwg_no', label: '預製圖號' },
    { key: 'scan_date', label: '預製圖掃描日期', type: 'date' },
    { key: 'ship_date', label: '出貨到場日', type: 'date' },
    { key: 'remark', label: '備註', type: 'textarea', full: true },
  ];
}
async function editSpool(id) {
  if (!State.drawings.length || State.drawings._pid !== State.project.id) {
    const dr = await api('GET', `/projects/${State.project.id}/drawings?limit=2000`);
    State.drawings = dr.rows; State.drawings._pid = State.project.id;
  }
  const data = id ? (await api('GET', `/projects/${State.project.id}/spools`)).rows.find(r => r.id === id) : {};
  const fields = spoolFields();
  openModal(id ? '編輯 spool' : '新增 spool', formHTML(fields, data), [
    id ? { label: '刪除', cls: 'danger', onClick: () => delSpool(id) } : null,
    { label: '取消', onClick: closeModal },
    { label: '儲存', cls: 'primary', onClick: async () => {
        const b = collectForm(fields);
        if (!b.drawing_id) return toast('請選圖面', 'err');
        if (!b.spool_no) return toast('請填 spool 編號', 'err');
        if (id) await api('PUT', `/spools/${id}`, b);
        else await api('POST', `/projects/${State.project.id}/spools`, b);
        toast('已儲存'); closeModal(); renderSpools();
      } },
  ].filter(Boolean));
}
async function delSpool(id) {
  if (!confirm('確定刪除此 spool?其焊口的 spool 關聯會被清除(焊口本身保留)。')) return;
  await api('DELETE', `/spools/${id}?operator=${encodeURIComponent(operator())}`);
  toast('已刪除'); closeModal(); renderSpools();
}
$('#addSpoolBtn').onclick = () => editSpool(0);
$('#autoBuildSpoolBtn').onclick = async () => {
  if (!State.project) return;
  if (!confirm('將為每張圖的「預製(S)」焊口各建一個預設 spool 並掛上(只處理尚未歸 spool 的),確定?')) return;
  const r = await api('POST', `/projects/${State.project.id}/spools/auto-build`, {});
  toast(`已建立 ${r.built} 個 spool,已歸 spool 焊口共 ${r.assigned_total}`); renderSpools();
};

/* ===========================================================
   請款
   =========================================================== */
async function renderBilling() {
  if (!State.project) return;
  const rows = await api('GET', `/projects/${State.project.id}/billing`);
  $('#billingTable thead').innerHTML = '<tr><th>期別</th><th>起</th><th>迄</th><th>焊口數</th><th>DB數</th><th>狀態</th></tr>';
  $('#billingTable tbody').innerHTML = rows.length ? rows.map(r => `<tr>
    <td><b>${esc(r.code)}</b></td><td>${esc(r.date_from)}</td><td>${esc(r.date_to)}</td>
    <td class="mono">${r.joints}</td><td class="mono">${r.db}</td>
    <td><span class="badge ${r.status === '已請款' ? 'green' : 'gray'}">${esc(r.status)}</span></td></tr>`).join('')
    : `<tr><td colspan="6" class="empty">尚無期別,可按「自動歸期」</td></tr>`;
}
$('#addBillingBtn').onclick = () => {
  const fields = [{ key: 'code', label: '期別代碼 (如 2026.03) *' },
    { key: 'date_from', label: '起日', type: 'date' }, { key: 'date_to', label: '迄日', type: 'date' },
    { key: 'unit_price', label: '單口單價', type: 'number' },
    { key: 'status', label: '狀態', type: 'select', empty: false, options: ['未請款', '已送審', '已請款'].map(s => ({ v: s, t: s })) }];
  openModal('新增請款期別', formHTML(fields, {}), [
    { label: '取消', onClick: closeModal },
    { label: '儲存', cls: 'primary', onClick: async () => {
        const b = collectForm(fields); if (!b.code) return toast('請填期別代碼', 'err');
        await api('POST', `/projects/${State.project.id}/billing`, b); toast('已新增'); closeModal(); renderBilling();
      } }]);
};
$('#autoAssignBtn').onclick = async () => {
  if (!State.project) return;
  if (!confirm('將依每個焊口的「完成日期」自動歸入對應月份期別(不存在則建立),確定?')) return;
  const r = await api('POST', `/projects/${State.project.id}/billing/auto-assign`, {});
  toast(`已歸期 ${r.assigned} 個焊口`); renderBilling();
};

/* ===========================================================
   問題追蹤
   =========================================================== */
async function renderIssues() {
  if (!State.project) return;
  const rows = await api('GET', `/projects/${State.project.id}/issues`);
  $('#issueTable thead').innerHTML = '<tr><th>類型</th><th>說明</th><th>關聯圖號</th><th>銲口</th><th>狀態</th><th>建立</th><th></th></tr>';
  $('#issueTable tbody').innerHTML = rows.length ? rows.map(r => `<tr>
    <td>${esc(r.issue_type)}</td><td>${esc(r.description)}</td><td>${esc(r.drawing_no)}</td>
    <td>${esc(r.joint_no)}</td>
    <td><span class="badge ${r.status === '已處理' ? 'green' : 'amber'}">${esc(r.status)}</span></td>
    <td class="muted">${esc((r.created_at || '').slice(0, 10))}</td>
    <td><button class="btn sm" onclick="toggleIssue(${r.id},'${r.status}')">${r.status === '已處理' ? '重開' : '結案'}</button></td></tr>`).join('')
    : `<tr><td colspan="7" class="empty">尚無問題紀錄</td></tr>`;
}
async function toggleIssue(id, cur) {
  await api('PUT', `/issues/${id}`, { status: cur === '已處理' ? '待處理' : '已處理' });
  renderIssues();
}
$('#addIssueBtn').onclick = () => {
  const fields = [
    { key: 'issue_type', label: '類型', type: 'select', empty: false, options: ['欠接頭', '新增焊口', '圖面問題', '缺漏', '其他'].map(s => ({ v: s, t: s })) },
    { key: 'description', label: '說明', type: 'textarea', full: true },
    { key: 'drawing_id', label: '關聯圖面', type: 'select', options: State.drawings.map(d => ({ v: d.id, t: d.drawing_no })) }];
  openModal('新增問題', formHTML(fields, {}), [
    { label: '取消', onClick: closeModal },
    { label: '儲存', cls: 'primary', onClick: async () => {
        await api('POST', `/projects/${State.project.id}/issues`, collectForm(fields));
        toast('已新增'); closeModal(); renderIssues();
      } }]);
};

/* ===========================================================
   基礎資料
   =========================================================== */
async function renderMaster() {
  if (!State.project) return;
  const pid = State.project.id;
  const [sys, wel, wps, heats, fillers] = await Promise.all([
    api('GET', `/projects/${pid}/systems`), api('GET', `/projects/${pid}/welders`), api('GET', `/projects/${pid}/wps`),
    api('GET', `/projects/${pid}/heats`), api('GET', `/projects/${pid}/fillers`)]);
  $('#systemTable thead').innerHTML = '<tr><th>代碼</th><th>中文</th><th>等級</th><th>材質</th></tr>';
  $('#systemTable tbody').innerHTML = sys.map(s => `<tr><td><b>${esc(s.code)}</b></td><td>${esc(s.name_zh)}</td><td>${esc(s.pipe_class)}</td><td>${esc(s.material)}</td></tr>`).join('') || emptyRow(4);
  $('#welderTable thead').innerHTML = '<tr><th>鋼印</th><th>姓名</th><th>證照</th><th>製程</th></tr>';
  $('#welderTable tbody').innerHTML = wel.map(s => `<tr><td><b>${esc(s.stamp)}</b></td><td>${esc(s.name)}</td><td>${esc(s.cert_no)}</td><td>${esc(s.process)}</td></tr>`).join('') || emptyRow(4);
  $('#wpsTable thead').innerHTML = '<tr><th>WPS No.</th><th>製程</th><th>材料群組</th><th>厚度範圍</th></tr>';
  $('#wpsTable tbody').innerHTML = wps.map(s => `<tr><td><b>${esc(s.wps_no)}</b></td><td>${esc(s.process)}</td><td>${esc(s.material_group)}</td><td>${esc(s.thk_min || '')}~${esc(s.thk_max || '')}</td></tr>`).join('') || emptyRow(4);
  $('#heatTable thead').innerHTML = '<tr><th>爐號</th><th>規格</th><th>P-No</th><th>MTR</th><th>PMI</th></tr>';
  $('#heatTable tbody').innerHTML = heats.map(s => `<tr><td><b>${esc(s.heat_no)}</b></td><td>${esc(s.spec)}</td><td>${esc(s.p_no)}</td><td>${esc(s.mtr_no)}</td><td>${s.pmi_done ? '✓' : ''}</td></tr>`).join('') || emptyRow(5);
  $('#fillerTable thead').innerHTML = '<tr><th>批號</th><th>AWS</th><th>F-No</th><th>規格</th></tr>';
  $('#fillerTable tbody').innerHTML = fillers.map(s => `<tr><td><b>${esc(s.batch_no)}</b></td><td>${esc(s.aws_class)}</td><td>${esc(s.f_no)}</td><td>${esc(s.spec)}</td></tr>`).join('') || emptyRow(4);
}
const emptyRow = n => `<tr><td colspan="${n}" class="muted">尚無資料</td></tr>`;
function masterAdd(title, fields, path, after) {
  openModal(title, formHTML(fields, {}), [
    { label: '取消', onClick: closeModal },
    { label: '儲存', cls: 'primary', onClick: async () => {
        await api('POST', `/projects/${State.project.id}/${path}`, collectForm(fields));
        toast('已新增'); closeModal(); after();
      } }]);
}
$('#addSystemBtn').onclick = () => masterAdd('新增系統',
  [{ key: 'code', label: '代碼 *' }, { key: 'name_zh', label: '中文名' }, { key: 'pipe_class', label: '等級' }, { key: 'material', label: '材質' }, { key: 'color', label: '3D顏色' }],
  'systems', () => { renderMaster(); selectProject(State.project.id); });
$('#addWelderBtn').onclick = () => masterAdd('新增焊工',
  [{ key: 'stamp', label: '鋼印代號 *' }, { key: 'name', label: '姓名' }, { key: 'cert_no', label: '證照號' }, { key: 'cert_expiry', label: '到期日', type: 'date' }, { key: 'process', label: '合格製程' }],
  'welders', () => { renderMaster(); selectProject(State.project.id); });
$('#addWpsBtn').onclick = () => masterAdd('新增 WPS',
  [{ key: 'wps_no', label: 'WPS No. *' }, { key: 'process', label: '製程' }, { key: 'material_group', label: '材料群組 (P-No)' }, { key: 'thk_min', label: '厚度下限', type: 'number' }, { key: 'thk_max', label: '厚度上限', type: 'number' }, { key: 'remark', label: '備註', full: true }],
  'wps', () => { renderMaster(); selectProject(State.project.id); });
$('#addHeatBtn').onclick = () => masterAdd('新增爐號 / MTR',
  [{ key: 'heat_no', label: '爐號 *' }, { key: 'spec', label: '材質規格' }, { key: 'p_no', label: 'P-No' }, { key: 'size', label: '尺寸' }, { key: 'schedule', label: 'SCH' }, { key: 'mtr_no', label: 'MTR 文件號' }, { key: 'mtr_path', label: 'MTR 路徑/連結', full: true }, { key: 'pmi_done', label: 'PMI 完成', type: 'checkbox' }, { key: 'remark', label: '備註', full: true }],
  'heats', () => { renderMaster(); selectProject(State.project.id); });
$('#addFillerBtn').onclick = () => masterAdd('新增銲材',
  [{ key: 'batch_no', label: '批號 *' }, { key: 'aws_class', label: 'AWS class' }, { key: 'f_no', label: 'F-No' }, { key: 'spec', label: '規格' }, { key: 'bake_log', label: '烘箱紀錄' }, { key: 'remark', label: '備註', full: true }],
  'fillers', () => { renderMaster(); selectProject(State.project.id); });

/* ===========================================================
   稽核
   =========================================================== */
async function renderAudit() {
  const rows = await api('GET', '/audit?limit=300');
  $('#auditTable thead').innerHTML = '<tr><th>時間</th><th>操作人</th><th>動作</th><th>對象</th><th>說明</th></tr>';
  $('#auditTable tbody').innerHTML = rows.length ? rows.map(r => `<tr>
    <td class="muted mono">${esc(r.ts)}</td><td>${esc(r.operator)}</td>
    <td><span class="badge ${({CREATE:'green',UPDATE:'blue',DELETE:'red',IMPORT:'amber'}[r.action]) || 'gray'}">${esc(r.action)}</span></td>
    <td class="muted">${esc(r.entity)} #${r.entity_id || ''}</td><td>${esc(r.summary)}</td></tr>`).join('')
    : `<tr><td colspan="5" class="empty">尚無紀錄</td></tr>`;
}

/* ===========================================================
   匯入 / 匯出 / 新專案
   =========================================================== */
function bindButtons() {
  $('#newProjectBtn').onclick = () => {
    const fields = [{ key: 'code', label: '專案代號 *' }, { key: 'name', label: '專案名稱 *' },
      { key: 'owner', label: '業主' }, { key: 'contractor', label: '承攬商' },
      { key: 'description', label: '說明', type: 'textarea', full: true }];
    openModal('新增專案', formHTML(fields, {}), [
      { label: '取消', onClick: closeModal },
      { label: '建立', cls: 'primary', onClick: async () => {
          const b = collectForm(fields);
          if (!b.code || !b.name) return toast('請填代號與名稱', 'err');
          const p = await api('POST', '/projects', b);
          toast('已建立'); closeModal(); await loadProjects(); selectProject(p.id);
        } }]);
  };
  $('#doImportBtn').onclick = async () => {
    const f = $('#impFile').files[0];
    if (!f) return toast('請選擇 Excel 檔', 'err');
    if (!$('#impCode').value || !$('#impName').value) return toast('請填代號與名稱', 'err');
    const fd = new FormData();
    fd.append('file', f); fd.append('code', $('#impCode').value); fd.append('name', $('#impName').value);
    fd.append('owner', $('#impOwner').value); fd.append('operator', operator());
    $('#importResult').innerHTML = '<span class="muted">匯入中,請稍候…</span>';
    try {
      const r = await api('POST', '/import', fd);
      $('#importResult').innerHTML = `<div class="hint">✓ 匯入完成:圖面 <b>${r.drawings}</b>、焊口 <b>${r.joints}</b>、系統 ${r.systems}、管線 ${r.lines}、檢驗 ${r.inspections}、期別 ${r.billing_periods}</div>`;
      await loadProjects(); selectProject(r.project_id);
    } catch (e) { $('#importResult').innerHTML = '<span style="color:#c0392b">匯入失敗</span>'; }
  };
  $('#exportJointsBtn').onclick = () => {
    if (!State.project) return toast('請先選專案', 'err');
    window.location = `/api/projects/${State.project.id}/export/joints.xlsx`;
  };
}

function debounce(fn, ms) { let t; return (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); }; }

boot();
