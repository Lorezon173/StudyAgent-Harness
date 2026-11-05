import { test, expect, type Page, type Request, type Response } from '@playwright/test';
import { createHash } from 'node:crypto';
import { mkdir, rename, writeFile } from 'node:fs/promises';
import { dirname, resolve, sep } from 'node:path';

test.use({ screenshot: 'off', trace: 'off', video: 'off' });

// The browser is the sole producer of the acceptance scenario. No routes are mocked.
const required = (key: string) => { const value = process.env[key]; if (!value) throw new Error(`缺少 ${key}`); return value; };
const hash = (value: string) => createHash('sha256').update(value, 'utf8').digest('hex');
const jsonHash = (value: unknown) => hash(JSON.stringify(value));
const pathIs = (response: Response, path: string, method = 'GET') => new URL(response.url()).pathname === path && response.request().method() === method;
async function body(response: Response) { expect(response.ok(), `${response.request().method()} ${new URL(response.url()).pathname}`).toBeTruthy(); return response.json(); }
async function fillCredentials(page: Page, username: string, password: string) {
  try { await page.getByLabel('用户名').fill(username, { timeout: 3000 }); await page.getByLabel('密码').fill(password, { timeout: 3000 }); }
  catch { throw new Error('TASK13_AUTH_INPUT_FAILED'); }
}
async function login(page: Page, username: string, password: string, register: boolean) {
  await page.goto('/');
  if (register) await page.getByRole('button', { name: '注册', exact: true }).click();
  await fillCredentials(page, username, password);
  const response = page.waitForResponse(r => pathIs(r, `/api/auth/${register ? 'register' : 'login'}`, 'POST'));
  await page.locator('form').getByRole('button', { name: register ? '注册' : '登录' }).click();
  const result = await body(await response); expect(result.token).toBeTruthy();
  await expect(page).toHaveURL(/\/chat(?:\/|$)/); return result;
}
async function api(page: Page, token: string, path: string) {
  let response;
  try { response = await page.request.get(path, { headers: { Authorization: `Bearer ${token}` } }); }
  catch { throw new Error('权威读取连接失败'); }
  expect(response.ok(), `GET ${path}`).toBeTruthy(); return response.json();
}
async function createSession(page: Page, title: string, profileName: string, isNew: boolean) {
  await page.getByRole('button', { name: '开启一段新的探索' }).click();
  const dialog = page.getByRole('dialog'); await dialog.getByLabel('会话标题').fill(title);
  if (isNew) { await dialog.getByLabel('所属主题画像').selectOption('__new'); await dialog.getByLabel('新主题名称').fill(profileName); }
  else { await expect(dialog.getByRole('option', { name: profileName, exact: true })).toBeAttached(); await dialog.getByLabel('所属主题画像').selectOption({ label: profileName }); }
  const response = page.waitForResponse(r => pathIs(r, '/api/sessions', 'POST'));
  await dialog.getByRole('button', { name: '进入书房 →' }).click();
  const session = await body(await response); await expect(page.getByRole('heading', { name: title })).toBeVisible(); return session;
}
async function selectSession(page: Page, profile: string, title: string) {
  const group = page.getByRole('region', { name: `主题：${profile}` });
  const toggle = group.getByRole('button', { name: `切换主题：${profile}` });
  if (await toggle.getAttribute('aria-expanded') !== 'true') await toggle.click();
  await group.getByRole('button', { name: title, exact: true }).click();
  await expect(page.getByRole('heading', { name: title })).toBeVisible();
}
async function createLibrary(page: Page, name: string, content: string, profile: string) {
  await page.getByRole('link', { name: '知识库' }).click();
  await page.getByRole('button', { name: '＋ 新建文本资料' }).click();
  const dialog = page.getByRole('dialog'); await dialog.getByLabel('名称').fill(name); await dialog.getByLabel('正文').fill(content);
  await expect(dialog.getByRole('option', { name: profile, exact: true })).toBeAttached(); await dialog.getByLabel('关联主题').selectOption({ label: profile });
  const response = page.waitForResponse(r => pathIs(r, '/api/knowledge', 'POST'));
  await dialog.getByRole('button', { name: '保存', exact: true }).click();
  const item = await body(await response); await expect(dialog.getByText(content, { exact: true })).toBeVisible();
  await dialog.getByRole('button', { name: '关闭' }).click(); return item;
}
type TurnMessage = { id: number; turn_index: number; role: string; content: string };
function matchTurn(items: TurnMessage[], turnIndex: number, userText: string, reply: string) {
  const messages = items.filter(item => item.turn_index === turnIndex);
  expect(messages).toHaveLength(2); const users = messages.filter(item => item.role === 'user'); const assistants = messages.filter(item => item.role === 'assistant');
  expect(users).toHaveLength(1); expect(assistants).toHaveLength(1);
  expect(users[0].content).toBe(userText); expect(assistants[0].content).toBe(reply);
  return { user: users[0], assistant: assistants[0] };
}
async function send(page: Page, token: string, sessionId: string, text: string) {
  const before = await api(page, token, `/api/sessions/${sessionId}/snapshot`);
  expect(before.session.session_id).toBe(sessionId); expect(before.session.active_request_id).toBeNull();
  expect(before.pending_requests.some((item: {status:string}) => item.status === 'running')).toBe(false);
  const response = page.waitForResponse(r => pathIs(r, '/api/chat', 'POST') && r.request().postDataJSON()?.session_id === sessionId, { timeout: 240_000 });
  await page.getByPlaceholder('输入学习问题…').fill(text); await page.getByRole('button', { name: '发送', exact: true }).click();
  const http = await response; const sent = http.request().postDataJSON(); const result = await body(http);
  expect(sent.session_id).toBe(sessionId); expect(sent.message).toBe(text); expect(sent.request_id).toBeTruthy();
  expect(sent.expected_state_version).toBe(before.session.state_version);
  expect(result.session_id).toBe(sessionId); expect(result.request_id).toBe(sent.request_id); expect(result.persisted).toBe(true);
  expect(result.status).toBe('completed'); expect(result.reply).toBeTruthy(); expect(result.state_version).toBe(before.session.state_version + 1);
  const request = await api(page, token, `/api/sessions/${sessionId}/requests/${sent.request_id}`);
  expect(request.session_id).toBe(sessionId); expect(request.request_id).toBe(sent.request_id); expect(request.status).toBe('completed');
  expect(request.attempt).toBe(result.attempt); expect(request.base_state_version).toBe(before.session.state_version);
  expect(request.response_json.persisted).toBe(true); expect(request.response_json.state_version).toBe(result.state_version);
  const snapshot = await api(page, token, `/api/sessions/${sessionId}/snapshot`);
  expect(snapshot.session.next_turn_index).toBe(before.session.next_turn_index + 1);
  expect(snapshot.session.state_version).toBe(before.session.state_version + 1);
  const matched = matchTurn(snapshot.messages.items, before.session.next_turn_index, text, result.reply);
  await expect(page.locator(`[data-message-id="${matched.assistant.id}"]`)).toBeVisible();
  return { request_id: sent.request_id, attempt: result.attempt, user_message_id: matched.user.id, assistant_message_id: matched.assistant.id, reply_sha256: hash(result.reply), persisted: result.persisted, status: request.status };
}

type ViewAck = { draft: string; reading_anchor: unknown; version: number };
function observeViews(page: Page, sessionId: string, initial: ViewAck) {
  const pending = new Set<Request>(); const tasks = new Set<Promise<void>>(); const acks: ViewAck[] = [initial]; let failed = false;
  const matches = (request: Request) => request.method() === 'PATCH' && new URL(request.url()).pathname === `/api/sessions/${sessionId}/view-state`;
  page.on('request', request => { if (matches(request)) pending.add(request); });
  page.on('requestfailed', request => { if (matches(request)) { failed = true; pending.delete(request); } });
  page.on('response', response => {
    if (!matches(response.request())) return;
    const task = (async () => { if (!response.ok()) { failed = true; return; } const value = await response.json(); acks.push({ draft: value.draft, reading_anchor: value.reading_anchor, version: value.version }); })().catch(() => { failed = true; });
    tasks.add(task); void task.finally(() => tasks.delete(task));
  });
  page.on('requestfinished', request => { if (matches(request)) pending.delete(request); });
  return {
    async settledEmpty() { await expect.poll(() => !failed && pending.size === 0 && tasks.size === 0 && acks.some(ack => ack.draft === ''), { timeout: 30_000 }).toBe(true); },
    async final() { await expect.poll(() => pending.size === 0 && tasks.size === 0, { timeout: 30_000 }).toBe(true); expect(failed).toBe(false); return [...acks].sort((a, b) => b.version - a.version)[0]; },
  };
}

async function writeManifest(path: string, manifest: unknown) {
  const root = resolve(process.cwd(), '..', '.superpowers', 'runtime', 'task13'); const target = resolve(path);
  if (!target.startsWith(root + sep)) throw new Error('清单必须位于私有 task13 运行目录');
  await mkdir(dirname(target), { recursive: true }); const temporary = `${target}.${process.pid}.tmp`;
  await writeFile(temporary, JSON.stringify(manifest, null, 2), { encoding: 'utf8', mode: 0o600, flag: 'wx' }); await rename(temporary, target);
}

async function openFloatingProfile(page: Page, profileId: string, sessionId: string) {
  const trigger = page.getByRole('button', { name: '学习画像' });
  await trigger.hover(); await expect(trigger).toHaveAttribute('aria-expanded', 'true');
  const card = page.getByLabel('画像详情'); await expect(card).toBeVisible();
  const link = card.getByRole('link', { name: '查看完整画像' });
  const href = await link.getAttribute('href'); expect(href).toBeTruthy();
  const url = new URL(href!, 'http://127.0.0.1:4178');
  expect(url.pathname).toBe('/profile'); expect(url.searchParams.get('profile_id')).toBe(profileId); expect(url.searchParams.get('session_id')).toBe(sessionId);
  await link.click();
}
async function createNode(page: Page, token: string, profileId: string, title: string, sessionId?: string) {
  if (sessionId) await openFloatingProfile(page, profileId, sessionId);
  else await page.getByRole('link', { name: '学习画像', exact: true }).click();
  const before = await api(page, token, `/api/topic-profiles/${profileId}`);
  await page.getByLabel('知识点名称').fill(title);
  await page.getByLabel('知识点说明').fill(`验收知识点：${title}`);
  const response = page.waitForResponse(r => pathIs(r, `/api/topic-profiles/${profileId}/nodes`, 'POST'));
  await page.getByRole('button', { name: '新建知识点', exact: true }).click();
  const post = await response; const payload = post.request().postDataJSON(); const mutation = await body(post);
  expect(payload.expected_revision).toBe(before.profile_revision); expect(payload.title).toBe(title);
  expect(mutation.node.archived).toBe(false); expect(mutation.node.id).toMatch(/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i); expect(mutation.node.profile_id).toBe(profileId);
  expect(mutation.node.title).toBe(title); expect(mutation.profile_revision).toBe(before.profile_revision + 1);
  await expect(page.getByText('知识点已创建', { exact: true })).toBeVisible();
  const detail = await api(page, token, `/api/topic-profiles/${profileId}`);
  const summary = await api(page, token, `/api/topic-profiles/${profileId}/summary`);
  expect(detail.profile_revision).toBe(mutation.profile_revision); expect(detail.profile.revision).toBe(mutation.profile_revision); expect(summary.profile_revision).toBe(mutation.profile_revision);
  expect(detail.nodes.some((node: { id: string; title: string }) => node.id === mutation.node.id && node.title === title)).toBe(true);
  return mutation.node;
}
async function selectNode(page: Page, token: string, sessionId: string, nodeId: string, title: string) {
  const before = await api(page, token, `/api/sessions/${sessionId}/snapshot`);
  const select = page.getByLabel('当前知识点');
  await expect(select.getByRole('option', { name: title, exact: true })).toHaveAttribute('value', nodeId);
  await select.selectOption(nodeId);
  const response = page.waitForResponse(r => pathIs(r, `/api/sessions/${sessionId}/active-node`, 'PATCH'));
  await page.getByRole('button', { name: '保存当前知识点', exact: true }).click();
  const patch = await response; const payload = patch.request().postDataJSON(); const session = await body(patch);
  expect(payload.node_id).toBe(nodeId); expect(payload.expected_state_version).toBe(before.session.state_version);
  expect(session.session_id).toBe(sessionId); expect(session.active_node_id).toBe(nodeId);
  expect(session.state_version).toBe(before.session.state_version + 1);
  await expect(page.getByText('当前知识点已保存', { exact: true })).toBeVisible();
  const snapshot = await api(page, token, `/api/sessions/${sessionId}/snapshot`);
  expect(snapshot.session.active_node_id).toBe(nodeId); expect(snapshot.session.state_version).toBe(session.state_version);
  const chatRead = page.waitForResponse(r => pathIs(r, `/api/sessions/${sessionId}/snapshot`) && r.ok());
  await page.getByRole('link', { name: '返回当前会话' }).click();
  expect((await body(await chatRead)).session.active_node_id).toBe(nodeId);
  const trigger = page.getByRole('button', { name: '学习画像' }); await trigger.hover();
  await expect(trigger).toHaveAttribute('aria-expanded', 'true'); await expect(page.getByLabel('画像详情')).toContainText(`当前知识点：${title}`);
}

test('Task13 同一真实运行：恢复、续答与画像', async ({ browser }) => {
  test.setTimeout(1_200_000);
  const run = required('TASK13_RUN_ID'), commit = required('TASK13_CANDIDATE_COMMIT'), manifestPath = required('TASK13_MANIFEST_PATH');
  const markers = { initial: required('TASK13_MARKER_INITIAL'), s2: required('TASK13_MARKER_S2'), s3: required('TASK13_MARKER_S3'), resume: required('TASK13_MARKER_RESUME'), draft: required('TASK13_MARKER_DRAFT') };
  expect(new Set(Object.values(markers)).size).toBe(5);
  expect(markers.resume).not.toContain(markers.initial); expect(markers.resume).not.toContain(markers.s2); expect(markers.resume).not.toContain(markers.s3);
  const contextA = await browser.newContext(); const page = await contextA.newPage();
  const a = await login(page, required('TASK13_A_USERNAME'), required('TASK13_A_PASSWORD'), true);
  const names = { t1: `T1-${run}`, t2: `T2-${run}`, s1: `S1-${run}`, s2: `S2-${run}`, s3: `S3-${run}`, node: `节点-${run}`, b: `B-${run}` };
  const s1 = await createSession(page, names.s1, names.t1, true);
  const node = await createNode(page, a.token, s1.profile_id, names.node, s1.session_id); await selectNode(page, a.token, s1.session_id, node.id, names.node);
  let snap = await api(page, a.token, `/api/sessions/${s1.session_id}/snapshot`); expect(snap.session.active_node_id).toBe(node.id);
  const initial = await send(page, a.token, s1.session_id, markers.initial);
  snap = await api(page, a.token, `/api/sessions/${s1.session_id}/snapshot`);
  expect(snap.teaching_state?.stage).toBe('awaiting_response');
  const question = snap.messages.items.find((m: {id:number}) => m.id === initial.assistant_message_id);
  expect(question?.content).toBe(snap.teaching_state.last_question); expect(question.content).toBeTruthy();
  const s2 = await createSession(page, names.s2, names.t1, false); const turn2 = await send(page, a.token, s2.session_id, markers.s2);
  const s3 = await createSession(page, names.s3, names.t2, true); const turn3 = await send(page, a.token, s3.session_id, markers.s3);
  const libraryA = await createLibrary(page, `资料-${run}`, markers.initial, names.t1);
  const before1 = await api(page, a.token, `/api/topic-profiles/${s1.profile_id}`); const before2 = await api(page, a.token, `/api/topic-profiles/${s3.profile_id}`);
  await selectSession(page, names.t1, names.s1);
  await expect.poll(async () => (await api(page, a.token, '/api/workspace-state')).last_session_id).toBe(s1.session_id);
  const patch = page.waitForResponse(async r => { if (!pathIs(r, `/api/sessions/${s1.session_id}/view-state`, 'PATCH') || !r.ok()) return false; return (await r.json()).draft === markers.draft; });
  await page.getByPlaceholder('输入学习问题…').fill(markers.draft); const view = await body(await patch);
  snap = await api(page, a.token, `/api/sessions/${s1.session_id}/snapshot`); expect(snap.view_state.draft).toBe(markers.draft); expect(snap.view_state.version).toBe(view.version);
  const workspace = await api(page, a.token, '/api/workspace-state'); expect(workspace.last_session_id).toBe(s1.session_id);
  await contextA.close();
  const contextReload = await browser.newContext(); const resumedPage = await contextReload.newPage();
  const workspaceRead = resumedPage.waitForResponse(r => pathIs(r, '/api/workspace-state') && r.ok());
  const snapshotRead = resumedPage.waitForResponse(r => pathIs(r, `/api/sessions/${s1.session_id}/snapshot`) && r.ok());
  const a2 = await login(resumedPage, required('TASK13_A_USERNAME'), required('TASK13_A_PASSWORD'), false);
  expect((await body(await workspaceRead)).last_session_id).toBe(s1.session_id); const restored = await body(await snapshotRead);
  expect(restored.session.active_node_id).toBe(node.id); expect(restored.view_state.draft).toBe(markers.draft);
  await expect(resumedPage.getByRole('heading', { name: names.s1 })).toBeVisible();
  await expect(resumedPage.locator(`[data-message-id="${question.id}"]`)).toBeVisible();
  await expect(resumedPage.getByPlaceholder('输入学习问题…')).toHaveValue(markers.draft);
  const views = observeViews(resumedPage, s1.session_id, restored.view_state);
  const resumed = await send(resumedPage, a2.token, s1.session_id, markers.resume);
  await expect(resumedPage.getByPlaceholder('输入学习问题…')).toHaveValue(''); await views.settledEmpty();
  const after1 = await api(resumedPage, a2.token, `/api/topic-profiles/${s1.profile_id}`); const after2 = await api(resumedPage, a2.token, `/api/topic-profiles/${s3.profile_id}`);
  const summary1 = await api(resumedPage, a2.token, `/api/topic-profiles/${s1.profile_id}/summary`);
  const snap1 = await api(resumedPage, a2.token, `/api/sessions/${s1.session_id}/snapshot`); const snap2 = await api(resumedPage, a2.token, `/api/sessions/${s2.session_id}/snapshot`); const snap3 = await api(resumedPage, a2.token, `/api/sessions/${s3.session_id}/snapshot`);
  expect(after1.profile_revision).toBe(summary1.profile_revision); expect(snap1.profile_summary.profile_revision).toBe(after1.profile_revision); expect(snap2.profile_summary.profile_revision).toBe(after1.profile_revision);
  expect(snap3.profile_summary.profile_revision).toBe(after2.profile_revision); expect(jsonHash(after2)).toBe(jsonHash(before2));
  expect(after1.profile_revision).toBeGreaterThan(before1.profile_revision);
  expect(summary1.recent_evidence.some((item: {request_id:string; session_id:string; node_id:string; message_id:number}) => item.request_id === resumed.request_id && item.session_id === s1.session_id && item.node_id === node.id && item.message_id === resumed.user_message_id)).toBe(true);
  await selectSession(resumedPage, names.t1, names.s2);
  const uiSnapshot = resumedPage.waitForResponse(r => pathIs(r, `/api/sessions/${s1.session_id}/snapshot`) && r.ok());
  await selectSession(resumedPage, names.t1, names.s1);
  const compactSource = await body(await uiSnapshot); expect(compactSource.profile.revision).toBe(after1.profile_revision); expect(compactSource.profile_summary.profile_revision).toBe(after1.profile_revision);
  await openFloatingProfile(resumedPage, s1.profile_id, s1.session_id); await expect(resumedPage.getByText(`主题画像 · REV ${after1.profile_revision}`)).toBeVisible();
  await expect.poll(async () => (await api(resumedPage, a2.token, '/api/workspace-state')).last_session_id).toBe(s1.session_id);
  await resumedPage.getByRole('button', { name: /^账号：/ }).click();
  await resumedPage.getByRole('group', { name: '账号操作' }).getByRole('button', { name: '退出登录' }).click();
  await expect(resumedPage.getByLabel('用户名')).toBeVisible();
  const finalAck = await views.final(); const finalSnapshot = await api(resumedPage, a2.token, `/api/sessions/${s1.session_id}/snapshot`);
  expect(finalSnapshot.view_state.draft).toBe(''); expect(finalSnapshot.view_state.draft).toBe(finalAck.draft);
  expect(finalSnapshot.view_state.version).toBe(finalAck.version); expect(finalSnapshot.view_state.reading_anchor).toEqual(finalAck.reading_anchor);
  const finalWorkspace = await api(resumedPage, a2.token, '/api/workspace-state'); expect(finalWorkspace.last_session_id).toBe(s1.session_id);
  const contextB = await browser.newContext(); const pageB = await contextB.newPage(); const b = await login(pageB, required('TASK13_B_USERNAME'), required('TASK13_B_PASSWORD'), true);
  const sb = await createSession(pageB, names.b, names.b, true); const nodeB = await createNode(pageB, b.token, sb.profile_id, `B节点-${run}`); const libraryB = await createLibrary(pageB, `B资料-${run}`, markers.s2, names.b);
  const manifest = { format_version: 1, run_id: run, candidate_commit: commit, users: { a: { id: a.user_id }, b: { id: b.user_id } }, profiles: { t1: { id: s1.profile_id }, t2: { id: s3.profile_id }, b: { id: sb.profile_id } }, sessions: { s1: { id: s1.session_id }, s2: { id: s2.session_id }, s3: { id: s3.session_id }, b: { id: sb.session_id } }, nodes: { s1: { id: node.id }, b: { id: nodeB.id } }, library: { a: { id: libraryA.id }, b: { id: libraryB.id } }, turns: { s1_initial: initial, s2: turn2, s3: turn3, s1_resume: resumed }, markers: { initial_sha256: hash(markers.initial), s2_sha256: hash(markers.s2), s3_sha256: hash(markers.s3), resume_sha256: hash(markers.resume), draft_sha256: hash(markers.draft), question_sha256: hash(question.content) }, versions: { workspace: workspace.version, view: view.version, s1_state: snap1.session.state_version, t1_revision: after1.profile_revision, t2_revision: after2.profile_revision, before_t1_revision: before1.profile_revision, before_t2_revision: before2.profile_revision, before_t1_sha256: jsonHash(before1), before_t2_sha256: jsonHash(before2), final_workspace_version: finalWorkspace.version, final_view_version: finalSnapshot.view_state.version, final_draft_sha256: hash(finalSnapshot.view_state.draft) }, assertions: { automatic_restore: true, view_acknowledged: true, pending_question: true, profile_revisions_match: true, b_retry_control: false } };
  await writeManifest(manifestPath, manifest); await contextReload.close(); await contextB.close();
});


