import {markdown, copyText} from './markdown.js';
const $ = id => document.getElementById(id);
const node = (tag, text, cls) => { const n = document.createElement(tag); if (text !== undefined) n.textContent = text; if (cls) n.className = cls; return n; };
let boot, selected, stream, current, approvalId = null, approving = false, nearBottom = true;
const labels = {output_truncated:'输出截断，回答不完整',content_filtered:'回复被过滤',empty_response:'空回复，未完成',provider_error:'供应商状态异常',response_unconfirmed:'结束状态未确认',idle:'准备就绪',running:'正在分析问题',waiting_approval:'正在等待审批',completed:'模型回复已返回',failed:'执行失败',cancelled:'已停止',stopped:'已停止',interrupted:'任务中断，未自动续跑',execution_uncertain:'执行结果不确定',pending:'任务尚未完成',cleanup_uncertain:'清理状态不确定',stopping:'正在停止并清理',settling:'正在完成资源清理'};
const toolLabels = {list_files:'正在查看项目结构',search_code:'正在查找代码',read_file_range:'正在读取文件',read_file:'正在读取文件',apply_patch:'正在处理代码修改',run_command:'正在执行命令',create_plan:'正在制定计划',update_plan:'正在更新计划'};
let olderMessages = [], pinSource = null, pendingDataAction = null;
const busy = () => current && ['running','waiting_approval','stopping','settling'].includes(current.status);
function notice(text) { $('notice').textContent = text; $('notice').hidden = !text; }
async function api(path, method='GET', data) {
  const controller = new AbortController(); const timer = setTimeout(() => controller.abort(), 30000);
  try {
    const response = await fetch('/api/' + path, {method, credentials:'same-origin', signal:controller.signal,
      headers: method === 'GET' ? {} : {'Content-Type':'application/json','X-Mybot-CSRF':boot.csrf},
      body: data === undefined ? undefined : JSON.stringify(data)});
    if (!response.ok) { const detail = await response.json().catch(()=>({})); const message = detail.status === 'stale_turn' ? '补充指令目标已过期，请刷新当前任务。' : detail.status === 'rejected' ? '补充指令被拒绝：请核对当前任务、容量及审批状态。' : detail.error === 'conversation_limit' ? '本进程最多保留 20 个对话。请保留需要的内容后重启服务。' : detail.error === 'web_control_unsupported' ? 'Web 第一版不支持跨轮 Undo 与 /changes。请使用活动面板查看修改；清空对话请使用设置按钮。' : response.status === 409 ? '工作区正忙，或本次审批已失效。请查看正在运行的对话。' : response.status === 403 ? '连接授权已过期，请刷新页面。' : '请求未完成，请检查输入或本地配置。'; throw Error(message); }
    return await response.json();
  } catch(error) { throw Error(error.name === 'AbortError' ? '请求超时；后台状态未确认，请刷新后查看。' : error.message); }
  finally { clearTimeout(timer); }
}
let previewFrame=0, refreshTimer=0;
function scheduleRefresh(){if(!refreshTimer)refreshTimer=setTimeout(()=>{refreshTimer=0;refresh().catch(e=>notice(e.message));},100);}
function renderPreview(){
  const v=current?.stream_preview || {}, container=$('stream-preview');
  container.hidden=!v.stream_id || (current.status==='completed' && v.status==='complete') || v.status==='tool_calls' || v.status==='discarded';
  if(container.hidden)return;
  const streamErrors={stream_transport_interrupted:'流中断',stream_local_timeout:'流等待超时',stream_close_unconfirmed:'关闭状态未知',stream_local_buffer_limit:'本地输出上限',stream_terminal_missing:'结束状态未确认',stream_host_failure:'宿主处理失败'};
  const protocolCodes=new Set(['stream_choices_invalid','stream_choice_index_invalid','stream_role_invalid','stream_content_type_invalid','stream_legacy_function_call_unsupported','stream_legacy_function_call_invalid','stream_after_finish_payload','stream_duplicate_finish','stream_tool_fragment_invalid','stream_tool_arguments_invalid','stream_tool_index_gap','stream_provider_error_frame']);
  $('stream-label').textContent=v.status==='generating'?'生成中 · 临时预览，尚未正式保存':v.status==='complete'?'生成结束 · 正在可靠保存':'回复不完整 · '+v.status;
  if(v.error_code)$('stream-label').textContent+=' · '+(streamErrors[v.error_code] || (protocolCodes.has(v.error_code)?'协议结构不兼容':'本轮未完成'));
  $('stream-body').replaceChildren(markdown(v.text || '等待可安全展示的文本…'));
  if(nearBottom)$('chat-scroll').scrollTop=$('chat-scroll').scrollHeight;
}
function renderSteer(){
  const enabled=boot.steer_enabled, row=(current.steers || []).at(-1), pending=row?.status==='queued';
  $('steer-form').hidden=!enabled || !busy();
  $('steer-send').disabled=!enabled || pending || current.status!=='running';
  $('steer-hint').textContent=current.status==='waiting_approval'?'请先审批、拒绝或停止当前操作；补充指令不能代替审批。':'';
  const box=$('steer-summary');box.replaceChildren();if(!enabled || !row)return;
  const text={queued:'已排队，等待下一安全步骤',applied:'已在下一模型步骤应用（不代表模型遵从）',not_applied:'任务在下一模型步骤前已结束，本次补充未生效',discarded_on_stop:'停止后补充指令已失效'}[row.status] || '补充指令未生效';
  box.append(node('p',text));
  if(['not_applied','discarded_on_stop'].includes(row.status)){
    const b=node('button','填入下一轮消息');b.type='button';b.addEventListener('click',()=>{$('message-input').value=row.text;$('message-input').dispatchEvent(new Event('input'));});box.append(b);
  }
}
function streamActivity(event){
  const e=JSON.parse(event.data);if(!current || e.sequence<=current.sequence)return;
  if(e.type.startsWith('model_stream') || e.type==='model_text_delta'){
    if(e.turn_id!==current.active_turn_id){scheduleRefresh();return;}
    const previous=current.stream_preview || {};
    if(previous.stream_id===e.stream_id && (e.preview_revision??0)<(previous.preview_revision??0))return;
    current.stream_preview={...e,status:e.status || 'generating'};current.sequence=e.sequence;
    if(!previewFrame)previewFrame=requestAnimationFrame(()=>{previewFrame=0;renderPreview();});
  }else scheduleRefresh();
}
function renderHistory() {
  $('storage-label').textContent=boot.persistence?'聊天已启用本地SQLite明文存储':'对话仅保存在本次服务内存中';
  $('history').replaceChildren(); $('history-count').textContent = boot.conversations.length;
  for (const c of [...boot.conversations].reverse()) {
    const button = node('button', undefined, 'history-item' + (c.id === selected ? ' active' : ''));
    button.append(node('span', ['running','waiting_approval','stopping','settling'].includes(c.status) ? '◉' : '◌'), node('span', c.title, 'history-title'));
    button.addEventListener('click', () => select(c.id)); $('history').append(button);
  }
}
function renderMessages() {
  const container = $('messages'); container.replaceChildren(); $('welcome').hidden = current.messages.length > 0;
  $('recovery-notice').textContent = current.recovery_notice || '';
  const visibleMessages = [...new Map([...olderMessages,...current.messages].map(m=>[m.id || m.time+':'+m.role,m])).values()];
  for (const m of visibleMessages) {
    const article = node('article', undefined, 'message ' + m.role), head = node('div', undefined, 'message-head');
    head.append(node('span', m.role === 'user' ? '你' : '✦', 'message-avatar'), node('span', m.role === 'user' ? '你' : 'mybot-mini'));
    const time = node('time', new Date(m.time*1000).toLocaleTimeString('zh-CN',{hour:'2-digit',minute:'2-digit'})); head.append(time); article.append(head);
    const body = node('div', undefined, 'message-body'); if (m.role === 'assistant') body.append(markdown(m.content)); else body.textContent = m.content;
    article.append(body);
    if (m.role === 'assistant') { const actions = node('div', undefined, 'message-actions'), copy = node('button','⧉ 复制回复','copy-reply'); copy.addEventListener('click', () => copyText(m.content, copy)); actions.append(copy); article.append(actions); }
    if (m.role === 'user' && m.id) {const pin = node('button','固定此消息片段','copy-reply');pin.disabled=!!boot.busy;pin.addEventListener('click',()=>openPin(m));article.append(pin);}
    if(m.truncated)article.append(node('p','此历史文本因存储预算截断，不代表完整原文。'));
    container.append(article);
  }
  $('running-indicator').hidden = !busy();
  if (nearBottom) { $('chat-scroll').scrollTop = $('chat-scroll').scrollHeight; $('new-message').hidden = true; }
  else if (current.messages.length) $('new-message').hidden = false;
}
function renderActivity() {
  const allPins = current.pins || [], activePins = allPins.filter(p=>p.status==='active');
  $('pins-notice').textContent = `${activePins.length} 条当前固定事项。${boot.persistence ? '保存在本地明文数据库。' : '仅本次进程，重启不保留。'} 模型回答、建议和推断不是宿主已确认事项。只确认来源原文，不确认更强改写。同分类并列不等于冲突。`;
  $('pins-list').replaceChildren();
  const cats={current_goal:'当前目标',user_constraint:'用户约束',confirmed_decision:'已确认决定',open_question:'未决事项',pending_work:'待完成工作'};
  for(const p of allPins){
    const evidence=current.decisions?.items.find(d=>d.pin_id===p.id);
    const past=evidence?.ever_effective === false?'无稳定生效区间':evidence?.ever_effective === null?'历史生效边界未知':'历史曾有效';
    const status=p.status==='active'?'当前有效':`${past}，${p.status==='superseded'?'已被替换':'已撤销'}`;
    const row=node('div',undefined,'pin-row');row.append(node('p',`${cats[p.category]} · ${status}`),node('p',p.content),node('small',`来源消息 ${p.source_message_id.slice(0,8)} · 字符 ${p.source_span[0]}–${p.source_span[1]}`));
    if(evidence?.ever_effective === false)row.append(node('p','同一提交内已失效，无可观察的稳定生效区间。'));
    if(evidence?.ever_effective === null)row.append(node('p','旧记录缺少完整提交边界；无法精确还原更早生效区间。'));
    if(evidence && !evidence.source_verified)row.append(node('p','来源不完整：这条记录未列入宿主可信原文，不得视为已核验决定。'));
    if(evidence){
      const details=node('details'), summary=node('summary','来源与历史生效区间');
      details.append(summary,node('p',`用户明确固定的原文；生效顺序 ${evidence.valid_from ?? '旧边界未知'}；失效顺序 ${evidence.valid_until ?? (evidence.ended_sequence === null?'未失效':'旧边界未知')}。`),node('p','后来失效不代表当时错误；本视图不恢复任何执行授权。'),node('small',`确认事件 ${evidence.confirmation_event_id.slice(0,8)} · 顺序 ${evidence.confirmation_event_sequence}`));row.append(details);
    }
    const budget=current.resources?.context || {};
    if(budget.pins_included?.includes(p.id))row.append(node('p','最近一次请求：已进入模型预算。'));
    if(budget.pins_omitted?.includes(p.id) || current.pin_budget?.omitted?.includes(p.id))row.append(node('p','最近一次尝试：未进入，预算不足。'));
    if(p.multiple_same_category && p.status==='active')row.append(node('p','同分类多项并列；不是已确认的语义冲突。'));
    if(p.status==='active'){const revoke=node('button','撤销固定','secondary-button');revoke.disabled=!!boot.busy;revoke.addEventListener('click',()=>confirmData('撤销后，此事项不再作为有效固定要求；历史参考会筛选或标注，审计原文仍保留。',async()=>{await api(`conversations/${selected}/pins/${p.id}/revoke`,'POST',{confirmed:true,revision:p.revision});await refresh();}));row.append(revoke);}
    $('pins-list').append(row);
  }
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
    (context.pins_included ? ` 固定事项进入 ${context.pins_included.length} / 遗漏 ${context.pins_omitted.length}；${context.pins_omitted.length?'部分固定要求未进入请求。':'已纳入本次实际请求预算。'}` : '') +
    (r.request_budget_exhausted ? '请求预算不足，本轮未完整完成。' : '') +
    (context.compaction_evidence ? ` 引用有效 ${context.compaction_evidence.valid_entries ?? 0} / 无效 ${context.compaction_evidence.invalid_entries ?? 0} / 已删除 ${context.compaction_evidence.removed_entries ?? 0}。` : '') +
    (context.history_projection_incomplete ? `历史投影已筛选：遮蔽 ${context.redacted_source_spans ?? 0} 个来源跨度，保留 ${context.preserved_independent_user_spans ?? 0} 个独立原文片段；省略协议轮 ${context.omitted_protocol_turns ?? 0}，来源关联失败 ${context.source_mapping_failures ?? 0}。` : '') +
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
  $('send').disabled = !$('message-input').value.trim() || !!boot.busy || boot.cleanup_uncertain || ['execution_uncertain','pending','running'].includes(current?.status);
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
  renderHistory(); renderMessages(); renderActivity(); renderApproval(); controls();renderPreview();renderSteer();
}
async function select(id) {
  selected = id; olderMessages=[]; stream?.close(); $('sidebar').parentElement.classList.remove('nav-open'); nearBottom = true;
  await refresh();
  if (selected !== id) return;
  stream = new EventSource(`/api/conversations/${id}/events`);
  stream.addEventListener('activity',streamActivity);
  stream.addEventListener('reset', () => refresh().catch(e=>notice(e.message)));
  stream.onopen = () => {scheduleRefresh(); $('connection').replaceChildren(node('i'), document.createTextNode('本地连接')); };
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
  for(const [label,value] of [['会话ID',current.id],['模型',`${boot.provider || '未配置'} / ${boot.model}`],['工作区',boot.workspace],['执行模式',boot.command_mode],['Patch 协议',boot.receipt?'Preview Receipt':'Legacy'],['历史存储',boot.persistence?'本地SQLite明文':'仅本次进程内存']]) details.append(node('dt',label),node('dd',value));
  $('storage-notice').textContent=boot.storage_notice+' CLI/Web默认隔离。清除上下文不会删除SQLite历史或固定事项；删除记录也不能保证备份或底层介质无残留。';
  $('review-chat').hidden=current.status!=='execution_uncertain';
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

function openPin(message){
  pinSource=message;$('pin-quote').value=[...message.content].slice(0,512).join('');$('pin-error').textContent='';
  const replace=$('pin-replace');replace.replaceChildren();const none=node('option','不替换，新增一项');none.value='';replace.append(none);
  for(const p of current.pins || [])if(p.status==='active'){const option=node('option',`${p.content.slice(0,70)}（状态修订${p.revision}）`);option.value=p.id;replace.append(option);}
  $('pin-dialog').showModal();
}
$('pin-cancel').addEventListener('click',()=>$('pin-dialog').close());
$('pin-confirm').addEventListener('click',async()=>{
  const quote=$('pin-quote').value,raw=pinSource?.content || '',offset=raw.indexOf(quote);
  if(!quote || offset<0){$('pin-error').textContent='片段必须精确存在于原用户消息。';return;}
  const start=[...raw.slice(0,offset)].length,end=start+[...quote].length;
  const old=(current.pins || []).find(p=>p.id===$('pin-replace').value);
  const value={message_id:pinSource.id,start,end,category:$('pin-category').value,confirmed:true};
  if(old){value.replace_id=old.id;value.expected_revision=old.revision;}
  $('pin-confirm').disabled=true;
  try{await api(`conversations/${selected}/pins`,'POST',value);$('pin-dialog').close();await refresh();}catch(e){$('pin-error').textContent=e.message;}finally{$('pin-confirm').disabled=false;}
});
function confirmData(text,action){pendingDataAction=action;$('data-confirm-text').textContent=text;$('data-confirm').showModal();}
$('data-cancel').addEventListener('click',()=>{$('data-confirm').close();pendingDataAction=null;});
$('data-approve').addEventListener('click',async()=>{const action=pendingDataAction;pendingDataAction=null;$('data-confirm').close();try{if(action)await action();}catch(e){notice(e.message);}});
$('delete-chat').addEventListener('click',()=>{const id=selected;$('settings-dialog').close();confirmData('确认删除此会话、固定事项和对应数据库记录？删除后应用不可恢复；备份、SQLite日志和底层存储可能有残留。',async()=>{await api(`conversations/${id}/delete`,'POST',{confirmed:true});stream?.close();boot=await api('bootstrap');if(boot.conversations.length)await select(boot.conversations.at(-1).id);else await newChat();renderHistory();});});
$('review-chat').addEventListener('click',()=>{$('settings-dialog').close();confirmData('仅当你已人工检查工作区和所有残留子进程后确认。此操作只解除中断状态的执行阻止，不恢复审批、Receipt或verified，也不会重放工具。',async()=>{await api(`conversations/${selected}/review`,'POST',{confirmed:true,workspace_and_processes_checked:true});boot=await api('bootstrap');await refresh();});});
$('load-older').addEventListener('click',async()=>{try{const first=(olderMessages.length?olderMessages:current.messages)[0];if(!first?.sequence)return;const page=await api(`conversations/${selected}/history?before=${first.sequence}`);if(!page.messages.length){notice('没有更早的已存消息。');return;}olderMessages=page.messages;$('show-recent').hidden=false;nearBottom=false;renderMessages();}catch(e){notice(e.message);}});
$('show-recent').addEventListener('click',()=>{olderMessages=[];$('show-recent').hidden=true;nearBottom=true;renderMessages();});

$('steer-form').addEventListener('submit',async event=>{
  event.preventDefault();const text=$('steer-input').value.trim();if(!text)return;
  $('steer-send').disabled=true;
  try{await api(`conversations/${selected}/steer`,'POST',{expected_turn_id:current.active_turn_id,client_request_id:crypto.randomUUID(),text});$('steer-input').value='';await refresh();}
  catch(e){notice(e.message);}
  finally{renderSteer();}
});
