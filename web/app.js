const $ = (id) => document.getElementById(id);
const API_TOKEN = document.querySelector('meta[name="awe-api-token"]')?.content || '';
async function campusAPI(path, options = {}) {
  const response = await fetch('/api/v1/' + path, {...options, headers:{Authorization:'Bearer ' + API_TOKEN, ...(options.headers || {})}});
  const data = await response.json();
  if (!response.ok) throw new Error(data.error?.message || '接口请求失败');
  return data;
}
const escapeHTML = (value) => String(value ?? '').replace(/[&<>"']/g, (c) => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const safeURL = (value) => { try { const url = new URL(value); return ['http:', 'https:'].includes(url.protocol) ? escapeHTML(url.href) : '#'; } catch { return '#'; } };
function restore(key, fallback) { try { return JSON.parse(localStorage.getItem(key)) ?? fallback; } catch { return fallback; } }
let saved = restore('awe-saved-v1', []);
if (!Array.isArray(saved)) saved = [];
saved = new Set(saved.filter((id) => typeof id === 'string'));
let tasks = restore('awe-tasks-v1', []);
if (!Array.isArray(tasks)) tasks = [];
tasks = tasks.filter((t) => t && typeof t.id === 'string' && typeof t.title === 'string');
let feed = {items: []}, view = 'all', category = '全部', limit = 12, toastTimer;
function persist() {
  try { localStorage.setItem('awe-saved-v1', JSON.stringify([...saved])); localStorage.setItem('awe-tasks-v1', JSON.stringify(tasks)); }
  catch { toast('浏览器存储不可用，本次更改只在当前页面保留。'); }
}
function toast(message) { $('toast').textContent = message; $('toast').hidden = false; clearTimeout(toastTimer); toastTimer = setTimeout(() => $('toast').hidden = true, 5500); }
function dateText(value) {
  if (!value) return '时间未提供';
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? '时间未提供' : date.toLocaleString('zh-CN', {timeZone:'Asia/Shanghai',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hour12:false});
}
function group(item) {
  const name = item.category || '';
  if (/讲座/.test(name)) return '讲座';
  if (/文体/.test(name)) return '文体';
  if (/社团/.test(name)) return '社团';
  if (/就业|招聘|实习/.test(name)) return '就业';
  if (/学习|学业/.test(name)) return '学业';
  return '通知';
}
function renderFilters() {
  const categories = ['全部', ...new Set(feed.items.map(group))];
  $('filters').innerHTML = categories.map((name) => `<button data-category="${name}" class="${category === name ? 'active' : ''}" aria-pressed="${category === name}">${name}</button>`).join('');
}
function renderFeed() {
  const query = $('search').value.trim().toLocaleLowerCase();
  const items = feed.items.filter((item) => (view !== 'saved' || saved.has(item.id)) && (category === '全部' || group(item) === category) && (!$('registration').checked || item.registration) && `${item.title} ${item.source} ${item.category}`.toLocaleLowerCase().includes(query)).sort((a,b) => (Date.parse(b.publishedAt) || 0) - (Date.parse(a.publishedAt) || 0));
  $('result-count').textContent = `${items.length} 条信息`;
  $('save-count').textContent = saved.size;
  $('feed').innerHTML = items.slice(0, limit).map((item) => `<article><span class="item-category">${group(item)}</span><div class="item-main"><div class="item-meta"><span>${escapeHTML(item.source)}</span>${item.registration ? '<span class="badge">需报名</span>' : ''}</div><h3><a href="${safeURL(item.url)}" target="_blank" rel="noreferrer">${escapeHTML(item.title)}</a></h3><div class="item-footer"><span>发布于 ${dateText(item.publishedAt)} · <a href="${safeURL(item.url)}" target="_blank" rel="noreferrer">原文 ↗</a></span><button class="save ${saved.has(item.id) ? 'selected' : ''}" data-save="${escapeHTML(item.id)}" aria-label="${saved.has(item.id) ? '取消收藏' : '收藏'}：${escapeHTML(item.title)}" aria-pressed="${saved.has(item.id)}">${saved.has(item.id) ? '★' : '☆'}</button></div></div></article>`).join('') || `<div class="empty-feed">${view === 'saved' ? '还没有符合条件的收藏。点击信息旁的 ☆，留到稍后再看。' : '没有匹配的信息，试试其他关键词或分类。'}</div>`;
  $('load-more').hidden = items.length <= limit;
}
function renderTasks() {
  $('tasks').innerHTML = tasks.length ? tasks.map((task) => `<div class="task ${task.done ? 'done' : ''}"><input type="checkbox" data-task="${escapeHTML(task.id)}" aria-label="完成：${escapeHTML(task.title)}" ${task.done ? 'checked' : ''}><label>${escapeHTML(task.title)}<small>${task.due ? `截止 ${dateText(task.due)}` : '手动待办 · 未设截止时间'}</small></label><button data-delete="${escapeHTML(task.id)}" aria-label="删除：${escapeHTML(task.title)}">×</button></div>`).join('') : '<div class="empty-tasks"><strong>给今天安排一件小事。</strong>添加个人待办，或前往教学网查看课程任务。</div>';
}
const views = {
  all: ['燕园的事，<br>在这一处。', '课程里的下一步，校园里的新鲜事。'],
  activities: ['走出课表，<br>发现校园。', '每一次讲座、演出和相遇，都从一条信息开始。'],
  saved: ['感兴趣的，<br>留在这里。', '你收藏的校园信息，随时回来看看。'],
  teaching: ['学业有序，<br>心里有底。', '课程、作业与公告，由你的本机连接器读取。'],
  treehole: ['有些问题，<br>问问同学。', '为课程经验、校园生活留下一个检索入口。'],
};
function changeView(next) {
  view = next; category = '全部'; limit = 12; $('search').value = ''; $('registration').checked = false;
  document.querySelectorAll('nav button').forEach((button) => {button.classList.toggle('active', button.dataset.view === next); button.setAttribute('aria-current', button.dataset.view === next ? 'page' : 'false');});
  $('page-title').innerHTML = views[next][0]; $('page-description').textContent = views[next][1];
  $('overview').hidden = !['all','teaching'].includes(next);
  $('feed-section').hidden = ['teaching','treehole'].includes(next);
  $('private-panel').hidden = !['teaching','treehole'].includes(next);
  $('search').disabled = ['teaching','treehole'].includes(next);
  $('feed-title').textContent = next === 'saved' ? '留给稍后的信息' : '校园正在发生';
  if (['teaching','treehole'].includes(next)) renderConnector(next);
  renderFilters(); renderFeed();
}
function applyFeed(data) {
  if (!Array.isArray(data.items)) throw new Error('数据格式不正确');
  feed = data;
  $('status').parentElement.classList.remove('error');
  $('status').textContent = `${data.mode === 'live' ? '同步于' : '公开页面快照 · 采集于'} ${dateText(data.fetchedAt)} · 发布日期非活动日期`;
  renderFilters(); renderFeed();
}
$('today').textContent = new Date().toLocaleDateString('zh-CN', {timeZone:'Asia/Shanghai', year:'numeric', month:'long', day:'numeric', weekday:'long'});
document.querySelector('nav').addEventListener('click', (event) => {const button = event.target.closest('[data-view]'); if (button) changeView(button.dataset.view);});
$('discover').addEventListener('click', () => {changeView('activities'); $('feed-section').scrollIntoView({behavior:'smooth'});});
$('filters').addEventListener('click', (event) => { const button = event.target.closest('[data-category]'); if (button) {category = button.dataset.category; limit = 12; renderFilters(); renderFeed();} });
$('search').addEventListener('input', () => {limit = 12; renderFeed();});
$('registration').addEventListener('change', () => {limit = 12; renderFeed();});
$('load-more').addEventListener('click', () => {limit += 12; renderFeed();});
$('feed').addEventListener('click', (event) => {const button = event.target.closest('[data-save]'); if (!button) return; const id = button.dataset.save; saved.has(id) ? saved.delete(id) : saved.add(id); persist(); renderFeed();});
$('sources-button').addEventListener('click', () => $('sources-dialog').showModal());
$('close-sources').addEventListener('click', () => $('sources-dialog').close());
$('add-task').addEventListener('click', () => {$('task-dialog').showModal(); $('task-title').focus();});
$('cancel-task').addEventListener('click', () => $('task-dialog').close());
$('task-form').addEventListener('submit', (event) => {event.preventDefault(); const title = $('task-title').value.trim(); if (!title) return; const due = $('task-date').value; tasks.push({id:crypto.randomUUID(),title,due:due ? new Date(due).toISOString() : '',done:false}); persist(); renderTasks(); $('task-dialog').close(); $('task-form').reset();});
$('tasks').addEventListener('change', (event) => {if (!event.target.dataset.task) return; const task = tasks.find((t) => t.id === event.target.dataset.task); if (task) {task.done = event.target.checked; persist(); renderTasks();}});
$('tasks').addEventListener('click', (event) => {const button = event.target.closest('[data-delete]'); if (button) {tasks = tasks.filter((task) => task.id !== button.dataset.delete); persist(); renderTasks();}});
$('refresh').addEventListener('click', async () => {
  const button = $('refresh'); button.disabled = true; button.textContent = '正在同步…';
  try {const response = await fetch('/api/refresh', {method:'POST'}); const data = await response.json(); if (!response.ok) throw new Error(data.error); applyFeed(data); toast('公开信息已同步');}
  catch (error) {$('status').textContent = error.message; $('status').parentElement.classList.add('error'); toast(error.message);}
  finally {button.disabled = false; button.textContent = '↻ 同步公开信息';}
});
function renderConnector(next) {
  const isTree = next === 'treehole';
  $('private-panel').innerHTML = `<div class="private-card"><div class="eyebrow">${isTree ? 'TREEHOLE · 关键词检索' : 'BLACKBOARD · 作业 / 公告 / 课表'}</div><div class="section-top"><h2>${isTree ? '让经验有出处，让回答有依据。' : '你的课程，集中在这里。'}</h2>${isTree ? '' : '<button id="sync-teaching">↻ 同步教学网</button>'}</div><p id="connector-status" role="status">正在检查连接状态…</p><div class="login-actions"><button data-browser-login="${isTree ? 'treehole' : 'blackboard'}">在官方页面登录 ↗</button>${isTree ? '' : '<button data-browser-login="portal">登录课表门户 ↗</button>'}<button id="finish-browser-login" hidden>完成登录并保存会话</button></div><p id="browser-login-status" class="connector-hint" role="status"></p><form id="connector-form"><label class="search"><input id="connector-query" type="search" maxlength="200" aria-label="${isTree ? '搜索树洞' : '搜索教学网缓存'}" placeholder="${isTree ? '输入课程名称或校园关键词' : '搜索作业、公告、课表；留空查看已同步内容'}" ${isTree ? 'required' : ''}><button type="submit">检索 ↗</button></label></form><p class="connector-hint">${isTree ? '按需联网检索，评论仅提供有限预览；可打开详情继续阅读。' : '检索本机缓存；精确截止时间以教学网原文为准。'} 数据会提供给你主动连接的 agent。</p><div id="connector-warnings" role="status"></div><div id="connector-results" class="connector-results"></div><div class="connector-paging" hidden><button id="connector-prev">← 上一页</button><span id="connector-page"></span><button id="connector-next">下一页 →</button></div></div>`;
  connectorPage = 1;
  campusAPI('status').then((data) => {
    if (view !== next) return;
    const item = data.sources.find((item) => item.source === (isTree ? 'treehole' : 'blackboard'));
    $('connector-status').textContent = `${item.message} · 已缓存 ${item.cachedCount} 条`;
  }).catch((error) => {if (view === next) $('connector-status').textContent = error.message;});
}
let connectorPage = 1;
async function searchConnector() {
  const source = view === 'treehole' ? 'treehole' : 'blackboard';
  const query = $('connector-query').value.trim();
  if (source === 'treehole' && !query) {toast('请输入树洞检索关键词'); return;}
  $('connector-results').textContent = '正在检索…';
  $('connector-warnings').textContent = '';
  const currentView = view;
  try {
    const params = new URLSearchParams({q:query,sources:source,limit:'10',offset:String(source === 'blackboard' ? (connectorPage - 1) * 10 : 0),page:String(connectorPage)});
    const data = await campusAPI('search?' + params);
    if (view !== currentView) return;
    $('connector-warnings').textContent = data.warnings.map((warning) => warning.message).join(' ');
    $('connector-results').innerHTML = data.items.map((doc) => `<article><div class="item-meta">${escapeHTML(doc.course || doc.source)} · ${escapeHTML(doc.kind)} · 采集 ${dateText(doc.fetchedAt)}</div><h3>${escapeHTML(doc.title)}</h3><p>${escapeHTML(doc.text?.slice(0,350) || '打开详情查看内容')}</p><div class="section-top"><a href="${safeURL(doc.url)}" target="_blank" rel="noreferrer">来源 ↗</a><button data-document="${escapeHTML(doc.id)}">阅读详情 →</button></div></article>`).join('') || '<p>没有可显示的结果。若尚未配置账号，请先完成本地配置与登录。</p>';
    const paging = document.querySelector('.connector-paging');
    paging.hidden = false;
    $('connector-page').textContent = `第 ${connectorPage} 页`;
    $('connector-prev').disabled = connectorPage === 1;
    $('connector-next').disabled = source === 'treehole' ? data.treeholeRemoteTotal === null || connectorPage * 10 >= data.treeholeRemoteTotal : connectorPage * 10 >= data.cachedMatches;
  } catch (error) {if (view === currentView) $('connector-results').textContent = error.message;}
}
$('private-panel').addEventListener('submit', (event) => {if (event.target.id === 'connector-form') {event.preventDefault();connectorPage=1;searchConnector();}});
$('private-panel').addEventListener('click', async (event) => {
  const loginButton=event.target.closest('[data-browser-login]');
  if (loginButton) {
    try {
      const data=await campusAPI('login/browser/'+loginButton.dataset.browserLogin,{method:'POST'});
      toast(data.message);pollBrowserLogin();
    } catch(error){toast(error.message);}
    return;
  }
  if(event.target.id==='finish-browser-login') {
    try {await campusAPI('login/browser/finish',{method:'POST'});pollBrowserLogin();}
    catch(error){toast(error.message);}
    return;
  }
  if (event.target.id === 'connector-prev' || event.target.id === 'connector-next') {connectorPage += event.target.id === 'connector-next' ? 1 : -1; searchConnector(); return;}
  if (event.target.id === 'sync-teaching') {
    const button = event.target;button.disabled=true;button.textContent='正在同步…';
    try {
      const data = await campusAPI('sync/blackboard',{method:'POST'});
      toast(data.ok ? '教学网已同步' : '部分同步失败，原有缓存已保留');
      if (view === 'teaching') {
        $('connector-status').textContent = data.results.map((item) => `${item.kind}：${item.ok ? item.count + ' 条' : item.error.message}`).join(' / ');
        connectorPage = 1; await searchConnector();
      }
    } catch (error) {toast(error.message); if (view === 'teaching') $('connector-status').textContent=error.message;}
    finally {button.disabled=false;button.textContent='↻ 同步教学网';}
  }
  const documentButton = event.target.closest('[data-document]');
  if (documentButton) openDocument(documentButton.dataset.document);
});
let loginPollTimer;
async function pollBrowserLogin() {
  clearTimeout(loginPollTimer);
  try {
    const data=await campusAPI('login/browser');
    const status=$('browser-login-status'),finish=$('finish-browser-login');
    if(status) status.textContent=data.message || '';
    if(finish) finish.hidden=!['waiting','verifying','starting'].includes(data.state);
    if(['waiting','verifying','starting'].includes(data.state)) loginPollTimer=setTimeout(pollBrowserLogin,2000);
    else if(data.state==='ready') {
      toast('官方登录已验证，会话已保存，可以开始检索。');
      if($('connector-status')) $('connector-status').textContent='浏览器登录会话已保存；请检索或同步验证数据读取。';
    }
  }catch(error){if($('browser-login-status')) $('browser-login-status').textContent=error.message;}
}
let detailIdentity = '', detailPage = 1;
async function openDocument(identity,page=1) {
  detailIdentity=identity;detailPage=page;
  if (!$('document-dialog').open) $('document-dialog').showModal();
  $('document-body').textContent='正在读取详情…';
  $('document-next').hidden=true;
  try {
    const data=await campusAPI('document?' + new URLSearchParams({id:identity,page:String(page),limit:'20'}));
    const doc=data.document;
    $('document-body').textContent = `${doc.title}\n\n来源：${doc.source} · 采集于 ${dateText(doc.fetchedAt)}\n${doc.deadlineText ? '采集时状态：' + doc.deadlineText + '\n' : ''}\n${doc.text || ''}` + (doc.comments ? `\n\n评论（第 ${page} 页，非完整讨论）：\n` + doc.comments.map((c) => c.text).join('\n\n') : '');
    $('document-next').hidden = doc.source !== 'treehole' || (typeof doc.commentTotal === 'number' && page*20 >= doc.commentTotal) || (doc.comments?.length || 0) < 20;
  } catch (error) {$('document-body').textContent=error.message;}
}
$('document-next').addEventListener('click',()=>openDocument(detailIdentity,detailPage+1));
$('close-document').addEventListener('click',()=>$('document-dialog').close());
document.addEventListener('keydown', (event) => {if (event.key === '/' && !['INPUT','TEXTAREA'].includes(document.activeElement.tagName) && !document.querySelector('dialog[open]') && !$('search').disabled) {event.preventDefault(); $('search').focus();}});
renderTasks();
fetch('/api/feed').then((response) => {if (!response.ok) throw new Error('无法读取公开快照'); return response.json();}).then(applyFeed).catch(() => {$('status').textContent = '读取失败，请检查本机服务后刷新页面。'; $('status').parentElement.classList.add('error');});
