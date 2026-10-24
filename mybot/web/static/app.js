import {markdown, copyText} from './markdown.js';
const $ = id => document.getElementById(id);
const node = (tag, text, cls) => { const n = document.createElement(tag); if (text !== undefined) n.textContent = text; if (cls) n.className = cls; return n; };
let boot, selected, stream, current, approvalId = null, approving = false, nearBottom = true;
const labels = {output_truncated:'输出截断，回答不完整',content_filtered:'回复被过滤',empty_response:'空回复，未完成',provider_error:'供应商状态异常',response_unconfirmed:'结束状态未确认',idle:'准备就绪',running:'正在分析问题',waiting_approval:'正在等待审批',completed:'模型回复已返回',failed:'执行失败',cancelled:'已停止',stopped:'已停止',cleanup_uncertain:'清理状态不确定',stopping:'正在停止并清理',settling:'正在完成资源清理'};
const toolLabels = {list_files:'正在查看项目结构',search_code:'正在查找代码',read_file_range:'正在读取文件',read_file:'正在读取文件',apply_patch:'正在处理代码修改',run_command:'正在执行命令',create_plan:'正在制定计划',update_plan:'正在更新计划'};
const busy = () => current && ['running','waiting_approval','stopping','settling'].includes(current.status);
function notice(text) { $('notice').textContent = text; $('notice').hidden = !text; }
async function api(path, method='GET', data) {
  const controller = new AbortController(); const timer = setTimeout(() => controller.abort(), 30000);
  try {
    const response = await fetch('/api/' + path, {method, credentials:'same-origin', signal:controller.signal,
      headers: method === 'GET' ? {} : {'Content-Type':'application/json','X-Mybot-CSRF':boot.csrf},
      body: data === undefined ? undefined : JSON.stringify(data)});
    if (!response.ok) { const detail = await response.json().catch(()=>({})); const message = detail.error === 'conversation_limit' ? '本进程最多保留 20 个对话。请保留需要的内容后重启服务。' : detail.error === 'web_control_unsupported' ? 'Web 第一版不支持跨轮 Undo 与 /changes。请使用活动面板查看修改；清空对话请使用设置按钮。' : response.status === 409 ? '工作区正忙，或本次审批已失效。请查看正在运行的对话。' : response.status === 403 ? '连接授权已过期，请刷新页面。' : '请求未完成，请检查输入或本地配置。'; throw Error(message); }
    return await response.json();
  } catch(error) { throw Error(error.name === 'AbortError' ? '请求超时；后台状态未确认，请刷新后查看。' : error.message); }
  finally { clearTimeout(timer); }
}
function renderHistory() {
  $('history').replaceChildren(); $('history-count').textContent = boot.conversations.length;
  for (const c of [...boot.conversations].reverse()) {
    const button = node('button', undefined, 'history-item' + (c.id === selected ? ' active' : ''));
    button.append(node('span', ['running','waiting_approval','stopping','settling'].includes(c.status) ? '◉' : '◌'), node('span', c.title, 'history-title'));
    button.addEventListener('click', () => select(c.id)); $('history').append(button);
  }
}
function renderMessages() {
  const container = $('messages'); container.replaceChildren(); $('welcome').hidden = current.messages.length > 0;
  for (const m of current.messages) {
    const article = node('article', undefined, 'message ' + m.role), head = node('div', undefined, 'message-head');
    head.append(node('span', m.role === 'user' ? '你' : '✦', 'message-avatar'), node('span', m.role === 'user' ? '你' : 'mybot-mini'));
    const time = node('time', new Date(m.time*1000).toLocaleTimeString('zh-CN',{hour:'2-digit',minute:'2-digit'})); head.append(time); article.append(head);
    const body = node('div', undefined, 'message-body'); if (m.role === 'assistant') body.append(markdown(m.content)); else body.textContent = m.content;
    article.append(body);
    if (m.role === 'assistant') { const actions = node('div', undefined, 'message-actions'), copy = node('button','⧉ 复制回复','copy-reply'); copy.addEventListener('click', () => copyText(m.content, copy)); actions.append(copy); article.append(actions); }
    container.append(article);
  }
  $('running-indicator').hidden = !busy();
  if (nearBottom) { $('chat-scroll').scrollTop = $('chat-scroll').scrollHeight; $('new-message').hidden = true; }
  else if (current.messages.length) $('new-message').hidden = false;
}
function renderActivity() {
  const contract = current.contract;
  $('contract-panel').hidden = !contract;
  if (contract) {
    $('contract-summary').textContent = `合同${contract.established ? '已建立' : '未建立'} · 当前 Revision ${contract.current_revision} · 用户明确要求 ${contract.user_explicit_count} · 测试记录关联 ${contract.test_evidence_count} · 缺少独立验收 ${contract.missing_acceptance_count} · 需求覆盖 ${contract.requirement_coverage} · 任务正确性 unknown`;
    const rows = $('contract-rows'); rows.replaceChildren();
    const sources = {user_explicit:'用户原文已核对', project_documented:'版本化文件读取', agent_suggestion:'模型建议', unresolved:'待确认'};
    const states = {identified:'已识别，未验证', implementation_claimed:'模型声称实现', test_evidence_observed:'真实测试记录关联，覆盖未知', independently_verified:'独立断言通过', unverified:'来源未确证', blocked:'执行受阻，未验证'};
    for (const r of contract.requirements || []) {
      const user = [...current.messages].reverse().find(m => m.role === 'user');
      const source = r.source_type === 'user_explicit' && user && [...user.content].length === r.source_message_chars && r.source_span;
      const brief = source ? [...user.content].slice(...r.source_span).join('').slice(0, 100) : r.requirement_text;
      rows.append(node('p', `${r.requirement_id}: ${brief} · ${r.category} · ${sources[r.source_type]} · ${states[r.status]} · Revision ${r.current_revision} · ${r.reason}`));
    }
  }
  const r = current.resources || {}, context = r.context || {};
  const compact = context.context_compaction_status || 'not_needed';
  const compactLabel = ({not_needed:'无需压缩',deterministic:'规则摘录',semantic_applied:'语义摘要已应用',semantic_applied_partial:'语义摘要部分应用：无效引用已拒绝，历史覆盖未验证',semantic_applied_pruned:'语义摘要删减后已应用，部分历史可能遗漏',semantic_skipped_insufficient_room:'空间不足，未请求语义摘要；规则摘录可能遗漏历史',fallback_output_truncated:'摘要输出被截断，已回退规则摘录',fallback_timeout:'摘要超时，已回退规则摘录',semantic_reused:'复用本轮摘要',call_limit:'压缩次数用尽，使用规则摘录'})[compact] || (compact.startsWith('fallback_') ? '语义压缩未应用，已回退规则摘录' : '未触发');
  $('request-count').textContent = r.logical_requests ?? current.requests;
  const reported = r.provider_reported_total_tokens ?? null;
  $('token-count').textContent = reported === null ? '未知' : reported.toLocaleString();
  $('resource-detail').textContent = `物理调用 ${r.physical_requests ?? 0} · HTTP 尝试 ${r.http_dispatch_attempts ?? '未知'} · 备用模型 ${r.fallback_used ? '已使用' : '未使用'}。` +
    (context.estimated_input_tokens !== undefined ? `当前输入估算 ${context.estimated_input_tokens} Token（保守估算，非账单）；${context.request_chars} 字符 / ${context.request_utf8_bytes} 字节。窗口 ${context.model_window_tokens ?? '未知'}；输出预留 ${context.output_reserved_tokens}。` : '') +
    ` 压缩请求 ${r.compaction_requests ?? 0}；${compactLabel}；保留 ${context.history_turns_kept ?? 0} 轮 / 摘要 ${context.history_turns_summarized ?? 0} 轮。` +
    ` 工具失败 ${r.tool_failures ?? 0} 次；用户任务正确性未知。` +
    (r.request_budget_exhausted ? '请求预算不足，本轮未完整完成。' : '') +
    (context.compaction_evidence ? ` 引用有效 ${context.compaction_evidence.valid_entries ?? 0} / 无效 ${context.compaction_evidence.invalid_entries ?? 0} / 已删除 ${context.compaction_evidence.removed_entries ?? 0}。` : '') +
    (context.history_information_incomplete ? '历史仅为节选，决定或未知事项可能遗漏；原会话保留。' : '') +
    (context.context_truncated ? '部分上下文已裁剪或摘要，不能视为完整阅读。' : '');
  let latest = current.events.at(-1), status = labels[current.status] || '状态未知';
  if (current.status === 'completed' && current.report?.state === 'edited_unverified') status = '已修改，尚未验证';
  if (current.status === 'completed' && current.report?.state === 'verified') status = '当前修改已验证';
  if (busy() && latest?.type === 'tool_started') status = toolLabels[latest.tool] || '正在调用工具';
  $('task-state').replaceChildren(node('span', undefined,'status-orb'), document.createTextNode(status));
  $('running-label').textContent = status;
  $('task-detail').textContent = current.report?.state === 'execution_uncertain' ? '执行结果无法确认，文件可能已经变化。请检查工作区并重启服务，切勿盲目重放修改。' : current.report ? `当前版本 ${current.report.current_revision} · 修改 ${current.report.committed_patches} 次 · 有效通过 ${current.report.tests_passed_after_last_patch} 项指定测试。仅代表已执行的测试范围。` : '显示后端实际状态；回复完整性与任务正确性分别报告。';
  const model = [...current.events].reverse().find(e => e.type === 'model_request_finished');
  $('model-label').textContent = model ? `${model.provider} / ${model.model}` : `${boot.provider || '未配置'} / ${boot.model}`;
  const cards = new Map(); let plan = [];
  for (const event of current.events) {
    if (event.type === 'message_started') plan = [];
    if (event.type === 'tool_started') cards.set(event.call_id, {...event, running:true});
    if (event.type === 'tool_finished') { cards.set(event.call_id, event); plan = event.plan || plan; }
  }
  $('plan').replaceChildren(); $('plan-count').textContent = plan.length || '—';
  for (const step of plan) { const li = node('li', step.description + (step.status === 'completed' ? ' ✓' : '')); li.dataset.status = step.status; $('plan').append(li); }
  $('tool-count').textContent = cards.size;
  const timeline = $('timeline');
  if (!cards.size) { if (!timeline.querySelector('.timeline-empty')) { const empty = node('div', undefined,'timeline-empty'); empty.append(node('span','⌁'),node('p','等待第一次行动'),node('small','工具实际执行后会显示在这里')); timeline.replaceChildren(empty); } }
  else {
    const opened = new Set([...timeline.querySelectorAll('details[open]')].map(d=>d.dataset.call)); timeline.replaceChildren();
    for (const [id, event] of cards) {
      const card = node('details', undefined, 'tool-card'); card.dataset.call = id; card.open = opened.has(id);
      const summary = node('summary'); summary.append(node('span', event.running ? '◌' : event.success ? '✓' : '×'),node('strong',event.tool),node('small',event.running ? (current.approval ? '待审批' : busy() ? '调用中' : '已中断') : `${event.duration_seconds.toFixed(2)}s`)); card.append(summary);
      const content = node('div', undefined, 'tool-content'), meta = event.metadata || {};
      let description = event.running ? (current.approval ? '等待批准；命令尚未执行。' : busy() ? '实际调用正在进行。' : '调用未返回，已停止；不能确认执行完成。') : event.success ? '调用已完成。' : '调用未成功，后端保持原停止策略。';
      if (event.tool === 'apply_patch' && !event.running) description = meta.operation_intent === 'preview' ? 'Patch Preview · 仅预览，尚未写入。' : meta.applied && event.success ? 'Patch Commit · 修改已正式发布。' : 'Patch 未确认成功提交。';
      if (event.tool === 'run_command' && !event.running) description = `命令退出码：${meta.exit_code ?? '未知'}。测试证据以当前 Revision 的后端报告为准。`;
      if (meta.authority_denied) description = '权限拒绝：工具未执行，没有本次写入副作用。';
      content.append(node('p', description));
      if (event.changed_files?.length) content.append(node('p','相关文件：' + event.changed_files.join('、')));
      if (meta.receipt_created) content.append(node('p','已生成当前对话的一次性提交凭据（内容隐藏）。'));
      if (meta.safe_error_code) content.append(node('p','安全诊断：' + meta.safe_error_code + ' · ' + meta.failure_phase + ' · ' + meta.operation_intent));
      if (meta.guidance_code === 'check_workspace_metadata') content.append(node('p',meta.safe_error_code === 'unsupported_metadata' ? '文件扩展元数据不符合安全写入前提。请检查 ACL、xattr 和文件 mode；本次没有执行写入。' : '文件所有权或属组不符合安全写入前提。请检查当前测试工作区的文件元数据；本次没有执行写入。'));
      else if (meta.guidance_code) content.append(node('p',meta.guidance_code === 'inspect_state_no_replay' ? '请检查当前文件和执行状态，不要自动重放 Patch。本次没有确认任何修改已提交。' : 'Patch 输入未通过验证，具体原因尚未确认。本次没有确认任何修改已提交。'));
      if (meta.relative_path) content.append(node('p','已读文件：' + meta.relative_path));
      if (meta.requested_start_line != null) content.append(node('p',`请求行 ${meta.requested_start_line}–${meta.requested_end_line ?? '?'}；返回行 ${meta.returned_start_line ?? '?'}–${meta.returned_end_line ?? '?'}；截断：${!!meta.truncated}；还有更多行：${!!meta.has_more_lines}`));
      if (meta.receipt_error_category) content.append(node('p','安全诊断：' + meta.receipt_error_category));
      if (meta.diff_truncated || event.display_truncated) content.append(node('p','部分活动或 Diff 已因大小限制省略；不能视为完整审阅。'));
      if (event.diff) { const pre = node('pre',undefined,'diff'); for (const line of event.diff.split('\n')) pre.append(node('span',line,'diff-line' + (line.startsWith('+') ? ' add' : line.startsWith('-') ? ' remove' : ''))); content.append(pre); }
      card.append(content); timeline.append(card);
    }
  }
}
function renderApproval() {
  const pending = current.approval, dialog = $('approval-dialog');
  if (!pending) { approvalId = null; if (dialog.open) dialog.close(); return; }
  approvalId = pending.id;
  $('approval-title').textContent = pending.kind === 'file' ? '等待批准兼容文件覆盖' : pending.kind === 'mcp' ? '等待批准 MCP 工具调用' : '等待批准执行命令';
  let details; try { details = JSON.parse(pending.display); } catch { details = null; }
  if (!details) { notice('无法完整展示审批内容；请拒绝或停止任务。'); return; }
  $('approval-details').textContent = pending.display; // Retain escaped bidi/control characters from inspectable backend JSON.
  $('approval-warning').textContent = pending.kind === 'file' ? '兼容写入：完整覆盖指定文件，无 OS 沙盒；本次批准不授权后续写入。' : details.execution_mode === 'host_confirm' ? '高权限操作：host_confirm 没有 OS 隔离，可读写外部文件、访问网络或启动其他程序。请逐项审核完整命令。' : pending.kind === 'mcp' ? '远程工具可能有外部副作用。本次确认不授权后续调用。' : 'macOS Seatbelt：工作区只读，网络禁止，仅本次临时目录可写；自检失败会拒绝执行。';
  $('approval-expiry').textContent = '本次审批到期：' + new Date(pending.expires_at*1000).toLocaleTimeString();
  $('approve').disabled = $('deny').disabled = approving;
  if (!dialog.open) dialog.showModal();
}
function controls() {
  const running = busy(); $('send').hidden = running; $('stop').hidden = !running;
  $('send').disabled = !$('message-input').value.trim() || !!boot.busy || boot.cleanup_uncertain;
  if (boot.cleanup_uncertain) notice('工作区执行或清理状态无法确认，新任务已禁用。请人工检查并重启服务。');
  $('clear-chat').disabled = !!boot.busy; $('chat-title').textContent = current?.title || '新对话';
}
async function refresh() {
  if (!selected) return;
  const id = selected; const state = await api(`conversations/${id}`); if (selected !== id || (current?.id === id && state.sequence < current.sequence)) return;
  current = state;
  if (state.status === 'output_truncated') notice('模型达到本轮输出长度限制，以下回答可能不完整。可以要求继续回答，或在下一轮调整允许的输出长度。');
  if (state.status === 'failed') notice('Agent 未完成请求。请检查本地模型、工作区配置或活动面板中的安全停止状态。');
  if (state.status === 'cleanup_uncertain') notice('资源清理无法确认，已阻止新任务。请检查运行环境并重启服务。');
  const c = boot.conversations.find(c=>c.id===id); if(c) {c.status=state.status;c.title=state.title;}
  if (busy()) boot.busy = id; else if (boot.busy === id) boot.busy = null;
  renderHistory(); renderMessages(); renderActivity(); renderApproval(); controls();
}
async function select(id) {
  selected = id; stream?.close(); $('sidebar').parentElement.classList.remove('nav-open'); nearBottom = true;
  await refresh();
  if (selected !== id) return;
  stream = new EventSource(`/api/conversations/${id}/events`);
  stream.addEventListener('activity', () => refresh().catch(e=>notice(e.message)));
  stream.addEventListener('reset', () => refresh().catch(e=>notice(e.message)));
  stream.onopen = () => { $('connection').replaceChildren(node('i'), document.createTextNode('本地连接')); };
  stream.onerror = () => { $('connection').textContent = '连接断开 · 正在重连'; };
}
async function newChat() {
  try { const c = await api('conversations','POST',{}); boot.conversations.push(c); await select(c.id); notice(''); }
  catch(error) { notice(error.message); }
}
$('composer').addEventListener('submit',async event => {
  event.preventDefault(); const text = $('message-input').value.trim(); if (!text || boot.busy) return;
  $('send').disabled = true; notice('');
  try { await api(`conversations/${selected}/messages`,'POST',{message:text}); $('message-input').value=''; $('message-input').style.height='auto'; nearBottom=true; await refresh(); }
  catch(error) { notice(error.message); controls(); }
});
$('message-input').addEventListener('input',()=>{ $('message-input').style.height='auto'; $('message-input').style.height=Math.min($('message-input').scrollHeight,170)+'px'; controls(); });
$('message-input').addEventListener('keydown', event => { if(event.key==='Enter' && !event.shiftKey && !event.isComposing) {event.preventDefault(); $('composer').requestSubmit();} });
$('new-chat').addEventListener('click',newChat);
$('stop').addEventListener('click',async()=>{ $('stop').disabled=true; try {await api(`conversations/${selected}/stop`,'POST',{});await refresh();}catch(e){notice(e.message);}finally{$('stop').disabled=false;} });
async function decide(allow) {
  if(!approvalId || approving) return; approving=true; $('approve').disabled=$('deny').disabled=true;
  try {await api(`conversations/${selected}/approval`,'POST',{id:approvalId,allow});await refresh();}catch(e){notice(e.message); await refresh();}finally{approving=false;renderApproval();}
}
$('approve').addEventListener('click',()=>decide(true)); $('deny').addEventListener('click',()=>decide(false));
$('approval-dialog').addEventListener('cancel',event=>{event.preventDefault();decide(false);});
$('settings').addEventListener('click',()=>{
  const details=$('settings-details');details.replaceChildren();
  for(const [label,value] of [['模型',`${boot.provider || '未配置'} / ${boot.model}`],['工作区',boot.workspace],['执行模式',boot.command_mode],['Patch 协议',boot.receipt?'Preview Receipt':'Legacy'],['历史存储','仅本次进程内存']]) details.append(node('dt',label),node('dd',value));
  $('settings-dialog').showModal();
});
$('close-settings').addEventListener('click',()=>$('settings-dialog').close());
$('clear-chat').addEventListener('click',async()=>{try{await api(`conversations/${selected}/clear`,'POST',{});$('settings-dialog').close();await refresh();}catch(e){notice(e.message);}});
$('theme').addEventListener('click',()=>{const theme=document.documentElement.dataset.theme==='dark'?'light':'dark';document.documentElement.dataset.theme=theme;try{localStorage.setItem('mybot-theme',theme);}catch{}});
$('activity-toggle').addEventListener('click',()=>document.querySelector('.shell').classList.toggle('activity-hidden'));
$('close-activity').addEventListener('click',()=>document.querySelector('.shell').classList.add('activity-hidden'));
$('menu').addEventListener('click',()=>document.querySelector('.shell').classList.toggle('nav-open'));
$('chat-scroll').addEventListener('scroll',()=>{const s=$('chat-scroll');nearBottom=s.scrollHeight-s.scrollTop-s.clientHeight<90;if(nearBottom)$('new-message').hidden=true;});
$('new-message').addEventListener('click',()=>{nearBottom=true;$('chat-scroll').scrollTop=$('chat-scroll').scrollHeight;$('new-message').hidden=true;});
for(const button of document.querySelectorAll('[data-prompt]')) button.addEventListener('click',()=>{$('message-input').value=button.dataset.prompt;$('message-input').dispatchEvent(new Event('input'));$('message-input').focus();});
try {const theme=localStorage.getItem('mybot-theme');if(['light','dark'].includes(theme))document.documentElement.dataset.theme=theme;}catch{}
if(innerWidth<1180)document.querySelector('.shell').classList.add('activity-hidden');
try {boot=await api('bootstrap');$('workspace').textContent=boot.workspace;renderHistory();if(boot.conversations.length)await select(boot.busy || boot.conversations.at(-1).id);else await newChat();
  setInterval(async()=>{try{const b=await api('bootstrap');boot={...boot,...b};renderHistory();controls();}catch{}},3000);
}catch(error){notice(error.message);$('model-label').textContent='连接不可用';}
