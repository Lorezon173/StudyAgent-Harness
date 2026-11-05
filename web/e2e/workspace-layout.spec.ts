import { writeFile } from 'node:fs/promises';
import { test, expect, type Page, type BrowserContext, type APIRequestContext, type Request, type Response, type Frame } from '@playwright/test';

// These tests exercise the actual React page over loopback HTTP. API responses in
// the first group are controlled in the browser and are not persistence evidence.
const profile = { id: 'p1', user_id: 1, name: '概率论与极长中文主题名称用于检查换行', scope_description: '', kind: 'manual', revision: 1, created_at: '', updated_at: '' };
const node = { id: 'n1', profile_id: 'p1', title: '条件概率', description: '', mastery: 0, last_practiced_at: 0, practice_count: 1, rationale: '', revision: 1, archived: false };
const summary = { profile_revision: 1, nodes: [node], edges: [], recent_evidence: [], assessed_count: 1, total_count: 1, mastery_score: 0, metric_kind: 'assessed_mean', assessment_coverage: 1 };
const session = { session_id: 's1', user_id: 1, title: '中文学习会话', profile_id: 'p1', active_node_id: 'n1', state_version: 0, next_turn_index: 0, active_request_id: null, created_at: null, updated_at: null };
const snapshot = { session, profile, profile_summary: summary, teaching_state: null, teaching_state_source: 'stored', view_state: { draft: '保留草稿', reading_anchor: null, version: 0, updated_at: null }, pending_requests: [], messages: { items: [{ id: 1, turn_index: 0, role: 'assistant', content: `长链接 https://example.com/${'unbroken'.repeat(20)}`, created_at: null }], next_cursor: null } };
const groups = { groups: [{ group_key: 'p1', profile, summary, sessions: [session], next_session_cursor: null }], next_group_cursor: null };
async function controlled(page: Page, multi = false, representative: 'long' | 'fail-save' | null = null) {
  const longProfile = { ...profile, name: '长中文主题'.repeat(16) };
  const longNodes = Array.from({ length: 3 }, (_, i) => ({ ...node, id: `n${i + 1}`, title: `长知识点${i + 1}${'学习内容'.repeat(18)}` }));
  const longSummary = { ...summary, nodes: longNodes, total_count: 3 };
  const longSession = { ...session, title: `长会话${'学习内容'.repeat(12)}` };
  const longSessions = Array.from({ length: 24 }, (_, i) => ({ ...longSession, session_id: i === 0 ? 's1' : `long${i}`, title: `${longSession.title}${i}` }));

  let state = { last_session_id: 's1', sidebar_pinned: true, sidebar_collapsed: false, progress_y_ratio: .5, version: 0, updated_at: null as string | null };
  const s2 = { ...session, session_id: 's2', title: '第二学习会话' };
  const views: Record<string, { draft: string; reading_anchor: { message_id: number; offset_ratio: number } | null; version: number; updated_at: null }> = {
    s1: { ...snapshot.view_state }, s2: { draft: '第二会话草稿', reading_anchor: null, version: 0, updated_at: null },
  };
  const messages = Array.from({ length: 30 }, (_, index) => ({ id: index + 1, turn_index: index, role: 'assistant', content: `第一会话历史 ${index + 1} ${'学习内容 '.repeat(35)}`, created_at: null }));
  const calls: { url: string; method: string; body: Record<string, unknown> | null }[] = [];
  await page.addInitScript(() => { localStorage.setItem('studyagent_user_id', '1'); localStorage.setItem('studyagent_username', '测试账号'); localStorage.setItem('studyagent_token', 'controlled-token'); });
  await page.route('**/api/**', async route => {
    const request = route.request(); const url = new URL(request.url());
    if (!url.pathname.startsWith('/api/')) return route.continue();
    const method = request.method();
    const body = request.postDataJSON() as Record<string, unknown> | null; calls.push({ url: url.pathname, method, body });
    if (url.pathname === '/api/workspace-state') {
      if (method === 'PATCH') { if (body?.expected_version !== state.version) return route.fulfill({ status: 409, json: { detail: 'conflict' } }); state = { ...state, ...body, version: state.version + 1 }; }
      return route.fulfill({ json: state });
    }
    if (url.pathname === '/api/sessions' && representative === 'long') return route.fulfill({ json: { ...groups, groups: [{ ...groups.groups[0], profile: longProfile, summary: longSummary, sessions: longSessions }] } });
    if (url.pathname === '/api/sessions') return route.fulfill({ json: multi ? { ...groups, groups: [{ ...groups.groups[0], sessions: [session, s2] }] } : groups });
    const match = url.pathname.match(/^\/api\/sessions\/(s1|s2)\/(snapshot|view-state)$/);
    if (match && (match[1] === 's1' || multi)) {
      const id = match[1];
      if (match[2] === 'snapshot' && representative === 'long') return route.fulfill({ json: { ...snapshot, session: longSession, profile: longProfile, profile_summary: longSummary, messages: { items: messages.map(m => ({ ...m, content: `${m.content} https://example.com/${'unbroken'.repeat(30)}${m.id === 1 ? `\n\n\`\`\`\n${'code'.repeat(80)}\n\`\`\`` : ''}` })), next_cursor: null } } });
      if (match[2] === 'snapshot') return route.fulfill({ json: multi ? { ...snapshot, session: id === 's1' ? session : s2, view_state: views[id], messages: { items: id === 's1' ? messages : [{ id: 101, turn_index: 0, role: 'assistant', content: '第二会话历史', created_at: null }], next_cursor: null } } : snapshot });
      if (method === 'PATCH') {
        if (representative === 'fail-save' && id === 's1') return route.fulfill({ status: 503, json: { detail: 'controlled failure' } });
        if ((multi || representative === 'long') && body?.expected_version !== views[id].version) return route.fulfill({ status: 409, json: { detail: 'conflict' } });
        views[id] = { draft: String(body?.draft ?? ''), reading_anchor: (body?.reading_anchor ?? null) as typeof views[string]['reading_anchor'], version: Number(body?.expected_version) + 1, updated_at: null };
        return route.fulfill({ json: views[id] });
      }
    }
    if (url.pathname === '/api/topic-profiles') return route.fulfill({ json: { items: [representative === 'long' ? longProfile : profile], next_cursor: null } });
    if (url.pathname === '/api/topic-profiles/p1') return route.fulfill({ json: { profile: representative === 'long' ? longProfile : profile, profile_revision: 1, nodes: representative === 'long' ? longNodes : [node], edges: [] } });
    if (url.pathname === '/api/topic-profiles/p1/summary') return route.fulfill({ json: representative === 'long' ? longSummary : summary });
    if (url.pathname === '/api/knowledge') return route.fulfill({ json: [] });
    return route.fulfill({ status: 404, json: { detail: `unhandled controlled endpoint: ${url.pathname}` } });
  });
  return { calls, getState: () => state, getViewState: (id: string) => views[id] };
}
async function openControlled(page: Page) { const api = await controlled(page); await page.goto('/chat/s1'); await expect(page.getByPlaceholder('输入学习问题…')).toHaveValue('保留草稿'); return api; }
const trigger = (page: Page) => page.getByRole('button', { name: '学习画像' });
const handle = (page: Page) => page.getByRole('button', { name: '调整画像位置' });
async function rect(page: Page, selector: string) { const value = await page.locator(selector).boundingBox(); expect(value, selector).not.toBeNull(); return value!; }
async function checkBounds(page: Page) {
  const card = await rect(page, '.floating-profile'), host = await rect(page, '.legacy-chat'), nav = await rect(page, '[data-workspace-topbar]'), composer = await rect(page, '.legacy-chat > div:has(> form)');
  expect(card.y).toBeGreaterThanOrEqual(Math.max(host.y, nav.y + nav.height) + 7);
  expect(card.y + card.height).toBeLessThanOrEqual(Math.min(host.y + host.height, composer.y) - 7);
  expect(card.x).toBeGreaterThanOrEqual(host.x - 1); expect(card.x + card.width).toBeLessThanOrEqual(host.x + host.width + 1);
}

async function prepareFloatingDrag(page: Page) {
  const before = await rect(page, '.floating-profile');
  await trigger(page).hover(); await expect(trigger(page)).toHaveAttribute('aria-expanded', 'true');
  await expect(page.getByLabel('画像详情')).toBeVisible();
  const trail: { x: number; y: number; width: number; height: number }[] = [];
  await expect.poll(async () => {
    const current = await handle(page).boundingBox(); if (!current) return false;
    const previous = trail.at(-1); trail.push(current);
    return !!previous && (['x', 'y', 'width', 'height'] as const).every(key => Math.abs(current[key] - previous[key]) <= 1);
  }, { message: `手柄位置未稳定；采样轨迹见 ${JSON.stringify(trail)}` }).toBe(true);
  let box = (await handle(page).boundingBox())!;
  for (let attempt = 0; attempt < 3; attempt++) {
    const point = { x: box.x + box.width / 2, y: box.y + box.height / 2 };
    await page.mouse.move(point.x, point.y);
    const hit = await handle(page).evaluate((el, p) => { const target = document.elementFromPoint(p.x, p.y); return target === el || el.contains(target); }, point);
    const current = await handle(page).boundingBox();
    if (hit && current && Math.abs(current.x - box.x) <= 1 && Math.abs(current.y - box.y) <= 1) return { ...point, before, box: current, after: await rect(page, '.floating-profile'), trail };
    expect(current).not.toBeNull(); box = current!;
  }
  throw new Error(`手柄中心未命中或位置变化：${JSON.stringify(trail)}`);
}

async function mouseDownCaptured(page: Page) {
  await page.mouse.down();
  await expect.poll(() => handle(page).evaluate(el => el.hasPointerCapture(1))).toBe(true);
}

async function readWorkspace(request: APIRequestContext, headers: Record<string, string>) {
  const response = await request.get('/api/workspace-state', { headers });
  expect(response.status(), 'workspace GET').toBe(200);
  const value = await response.json();
  expect(typeof value.sidebar_pinned).toBe('boolean'); expect(typeof value.sidebar_collapsed).toBe('boolean');
  expect(Number.isFinite(value.progress_y_ratio) && value.progress_y_ratio >= 0 && value.progress_y_ratio <= 1).toBe(true);
  expect(Number.isInteger(value.version)).toBe(true); return value;
}
function preferences(value: { sidebar_pinned: boolean; sidebar_collapsed: boolean; progress_y_ratio: number }) {
  return { sidebar_pinned: value.sidebar_pinned, sidebar_collapsed: value.sidebar_collapsed, progress_y_ratio: value.progress_y_ratio };
}
function observeReloadWorkspace(page: Page, expectedPath: string) {
  const mainFrame = page.mainFrame(); const requests = new Set<Request>(); const events: string[] = []; const methods: string[] = [];
  let committed = false, navigations = 0;
  let bodyResult: { status: number; value?: { sidebar_pinned: boolean; sidebar_collapsed: boolean; progress_y_ratio: number }; error?: string } | undefined;
  let reading = false; const record = (message: string) => events.push(`${events.length + 1} ${Date.now()} ${message}`);
  const navigation = (frame: Frame) => { if (frame !== mainFrame) return; navigations++; record(`navigation ${navigations} ${new URL(frame.url()).pathname}`); if (navigations === 1 && new URL(frame.url()).pathname === expectedPath) committed = true; };
  const request = (req: Request) => {
    if (new URL(req.url()).pathname !== '/api/workspace-state') return;
    methods.push(req.method());
    if (committed && req.frame() === mainFrame && req.method() === 'GET') { requests.add(req); record(`request ${requests.size} GET ${new URL(req.frame().url()).pathname}`); }
  };
  const response = (res: Response) => {
    if (!requests.has(res.request()) || reading) return; reading = true;
    record(`response ${[...requests].indexOf(res.request()) + 1} ${res.status()}`);
    void res.json().then(value => { bodyResult = { status: res.status(), value }; }, error => { bodyResult = { status: res.status(), error: String(error) }; });
  };
  page.on('framenavigated', navigation); page.on('request', request); page.on('response', response);
  return { events, methods, get result() { return bodyResult; }, get navigations() { return navigations; }, cleanup() { page.off('framenavigated', navigation); page.off('request', request); page.off('response', response); } };
}
async function assertFloatingRatio(page: Page, ratio: number) {
  await page.mouse.move(5, 5); await page.locator('h1').first().click();
  await expect(trigger(page)).toHaveAttribute('aria-expanded', 'false');
  const card = await rect(page, '.floating-profile'), host = await rect(page, '.legacy-chat'), nav = await rect(page, '[data-workspace-topbar]'), composer = await rect(page, '.legacy-chat > div:has(> form)');
  const top = Math.max(host.y, nav.y + nav.height) + 8, bottom = Math.min(host.y + host.height, composer.y) - 8;
  const travel = Math.max(0, bottom - top - card.height); expect(travel).toBeGreaterThan(0);
  expect(Math.abs(card.y - (top + ratio * travel))).toBeLessThanOrEqual(2); await checkBounds(page);
  return { card, host, nav, composer, travel };
}

test.describe('受控 API · 正式 React HTTP 页面', () => {
  for (const width of [1440, 1024, 760, 600, 481, 480, 390]) for (const height of [900, 450]) {
    test(`视口 ${width}×${height}：导航、输入与浮卡边界`, async ({ page }, testInfo) => {
      await page.setViewportSize({ width, height }); await openControlled(page);
      await expect(trigger(page)).toBeVisible(); await checkBounds(page);
      await trigger(page).hover(); await expect(trigger(page)).toHaveAttribute('aria-expanded', 'true'); await checkBounds(page);
      await expect(page.getByPlaceholder('输入学习问题…')).toBeVisible();
      await testInfo.attach('viewport.png', { body: await page.screenshot(), contentType: 'image/png' });
      await testInfo.attach('rectangles.json', { body: JSON.stringify({ width, height, card: await rect(page, '.floating-profile'), host: await rect(page, '.legacy-chat'), navigation: await rect(page, '[data-workspace-topbar]'), composer: await rect(page, '.legacy-chat > div:has(> form)') }), contentType: 'application/json' });
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth)).toBe(true);
      if (width > 480) {
        const sidebar = page.getByRole('complementary', { name: '会话导航' }); await expect(sidebar).toBeVisible();
        await expect(page.getByRole('button', { name: '取消固定侧栏，保持当前展示' })).toHaveAttribute('aria-pressed', 'true');
        if (width <= 760) expect((await sidebar.boundingBox())!.width).toBeCloseTo(170, 0);
        const before = await rect(page, '.workspace-main'); await page.getByRole('button', { name: '收起会话导航' }).click();
        expect((await rect(page, '.workspace-main')).width).toBeGreaterThan(before.width);
        await page.getByRole('button', { name: '展开会话导航' }).click(); await expect(page.getByRole('button', { name: '固定侧栏，保持展开' })).toBeVisible();
        await expect(page.getByRole('button', { name: /账号：/ })).toBeVisible();
      } else { await page.getByRole('button', { name: '打开会话导航' }).click(); await expect(page.getByRole('complementary', { name: '会话导航' })).toBeVisible(); }
    });
  }
  test('鼠标连续进入卡片、Escape 后保持关闭并重新进入', async ({ page }) => {
    await openControlled(page); await trigger(page).hover(); await expect(trigger(page)).toHaveAttribute('aria-expanded', 'true');
    await page.getByLabel('画像详情').hover(); await expect(trigger(page)).toHaveAttribute('aria-expanded', 'true');
    await page.keyboard.press('Escape'); await expect(trigger(page)).toHaveAttribute('aria-expanded', 'false'); await expect(trigger(page)).toBeFocused();
    await page.mouse.move(5, 5); await trigger(page).hover(); await expect(trigger(page)).toHaveAttribute('aria-expanded', 'true');
  });
  test('指针阈值、捕获、取消、键盘及请求计数', async ({ page }) => {
    const api = await openControlled(page);
    const initial = api.calls.filter(c => c.url.includes('/snapshot') || c.url.includes('/messages')).length;
    const initialSummary = api.calls.filter(c => c.url.includes('/summary')).length;
    let point = await prepareFloatingDrag(page);
    expect(api.calls.filter(c => c.url.includes('/snapshot') || c.url.includes('/messages'))).toHaveLength(initial);
    expect(api.calls.filter(c => c.url.includes('/summary'))).toHaveLength(initialSummary);
    await mouseDownCaptured(page); await page.mouse.move(point.x, point.y + 4); await page.mouse.up();
    expect(await handle(page).evaluate(el => el.hasPointerCapture(1))).toBe(false);
    expect(api.calls.filter(c => c.method === 'PATCH' && c.body && 'progress_y_ratio' in c.body)).toHaveLength(0);
    point = await prepareFloatingDrag(page); await mouseDownCaptured(page); await page.mouse.move(point.x, point.y + 30);
    await expect.poll(async () => (await rect(page, '.floating-profile')).y - point.after.y).toBeGreaterThan(4);
    await page.mouse.move(point.x, point.y + 70); await page.mouse.up();
    expect(await handle(page).evaluate(el => el.hasPointerCapture(1))).toBe(false);
    const completedAt = await page.evaluate(() => performance.now()); const stateAfterDrag = await trigger(page).getAttribute('aria-expanded'); await trigger(page).click(); await expect(trigger(page)).toHaveAttribute('aria-expanded', stateAfterDrag!);
    await expect.poll(() => page.evaluate(start => performance.now() - start, completedAt)).toBeGreaterThanOrEqual(350); await trigger(page).click(); await expect(trigger(page)).not.toHaveAttribute('aria-expanded', stateAfterDrag!);
    await expect.poll(() => api.calls.filter(c => c.method === 'PATCH' && c.body && 'progress_y_ratio' in c.body).length).toBe(1);
    point = await prepareFloatingDrag(page); await mouseDownCaptured(page); await page.mouse.move(point.x, point.y + 20);
    await handle(page).evaluate(el => el.dispatchEvent(new PointerEvent('pointercancel', { bubbles: true, pointerId: 1, isPrimary: true }))); await page.mouse.up();
    expect(api.calls.filter(c => c.method === 'PATCH' && c.body && 'progress_y_ratio' in c.body)).toHaveLength(1);
    await handle(page).focus(); const boundary = await rect(page, '.floating-profile'); const host = await rect(page, '.legacy-chat'); const composer = await rect(page, '.legacy-chat > div:has(> form)');
    expect(Math.abs(boundary.y + boundary.height - (Math.min(host.y + host.height, composer.y) - 8))).toBeLessThanOrEqual(1);
    const baselineRatio = api.getState().progress_y_ratio; const patchCount = () => api.calls.filter(c => c.method === 'PATCH' && c.body && 'progress_y_ratio' in c.body).length;
    expect(baselineRatio).toBe(1); const baselinePatches = patchCount(); await page.keyboard.press('ArrowDown');
    expect(Math.abs((await rect(page, '.floating-profile')).y - boundary.y)).toBeLessThanOrEqual(1); expect(patchCount()).toBe(baselinePatches);
    const nav = await rect(page, '[data-workspace-topbar]'); expect(boundary.y - (Math.max(host.y, nav.y + nav.height) + 8)).toBeGreaterThanOrEqual(12);
    await page.keyboard.press('ArrowUp'); await expect.poll(async () => (await rect(page, '.floating-profile')).y).toBeCloseTo(boundary.y - 12, 0);
    await expect.poll(patchCount).toBe(baselinePatches + 1); await expect.poll(() => api.getState().progress_y_ratio).toBeLessThan(baselineRatio);
    await page.keyboard.press('ArrowDown'); await expect.poll(async () => (await rect(page, '.floating-profile')).y).toBeCloseTo(boundary.y, 0);
    await expect.poll(patchCount).toBe(baselinePatches + 2); await expect.poll(() => api.getState().progress_y_ratio).toBe(baselineRatio);
    expect(api.calls.filter(c => c.url.includes('/snapshot') || c.url.includes('/messages'))).toHaveLength(initial);
    expect(api.calls.filter(c => c.url.includes('/summary'))).toHaveLength(initialSummary);
    await expect(page.getByPlaceholder('输入学习问题…')).toHaveValue('保留草稿');
  });
  test('触屏显式开关', async ({ browser }) => {
    const context: BrowserContext = await browser.newContext({ viewport: { width: 390, height: 844 }, hasTouch: true, isMobile: true }); const page = await context.newPage();
    try { await openControlled(page); await trigger(page).tap(); await expect(trigger(page)).toHaveAttribute('aria-expanded', 'true'); await trigger(page).tap(); await expect(trigger(page)).toHaveAttribute('aria-expanded', 'false'); } finally { await context.close(); }
  });
  test('短高内容滚动、缩放与弹窗层级', async ({ page }) => {
    await page.setViewportSize({ width: 600, height: 450 }); await page.emulateMedia({ reducedMotion: 'reduce' }); await openControlled(page);
    await page.evaluate(() => { document.documentElement.style.fontSize = '200%'; }); await trigger(page).hover(); await checkBounds(page);
    const details = page.locator('.floating-profile-content'); expect(await details.evaluate(el => getComputedStyle(el).overflowY)).toBe('auto');
    await page.getByRole('button', { name: '开启一段新的探索' }).click(); const dialog = page.getByRole('dialog'); await expect(dialog).toBeVisible();
    expect(await dialog.evaluate(el => el.matches(':modal'))).toBe(true);
    await page.keyboard.press('Escape'); await expect(dialog).not.toBeVisible(); await expect(trigger(page)).not.toBeFocused();
  });
});


// Opt-in only: start a disposable backend and database before setting this value.
test.describe('真实 HTTP · 显式配置的隔离后端', () => {
  test.skip(!process.env.TASK12_ISOLATED_API, '未指定 TASK12_ISOLATED_API 隔离后端；真实持久化未验。');
  test('A 保存并重登、B 隔离和深链恢复', async ({ page, request }, testInfo) => {
    const suffix = `${Date.now()}${Math.floor(Math.random() * 1e6)}`; const password = `test-${suffix}`;
    async function createAccount(name: string) {
      const auth = await request.post('/api/auth/register', { data: { username: name, password } }); expect(auth.ok()).toBeTruthy(); const identity = await auth.json();
      const headers = { Authorization: `Bearer ${identity.token}` };
      const created = await request.post('/api/topic-profiles', { headers, data: { name: `隔离主题${name}` } }); expect(created.ok()).toBeTruthy(); const detail = await created.json();
      const result = await request.post('/api/sessions', { headers, data: { profile_id: detail.profile.id, title: `隔离会话${name}`, active_node_id: null } }); expect(result.ok()).toBeTruthy();
      return { ...identity, headers, session: await result.json() };
    }
    const a = await createAccount(`a${suffix}`), b = await createAccount(`b${suffix}`);
    async function login(name: string) {
      await page.goto('/login'); await page.getByLabel('用户名').fill(name); await page.getByLabel('密码').fill(password); await page.locator('form').getByRole('button', { name: '登录' }).click();
      await expect(page).toHaveURL(/\/chat/);
    }
    await page.setViewportSize({ width: 1440, height: 900 });
    await login(a.username); await page.goto(`/chat/${encodeURIComponent(a.session.session_id)}`); await expect(trigger(page)).toBeVisible();
    async function dragReal(headers: Record<string, string>, delta: number) {
      const before = await readWorkspace(request, headers);
      const point = await prepareFloatingDrag(page);
      const host = await rect(page, '.legacy-chat'), composer = await rect(page, '.legacy-chat > div:has(> form)'), nav = await rect(page, '[data-workspace-topbar]');
      expect(Math.min(host.y + host.height, composer.y) - 8 - (point.after.y + point.after.height)).toBeGreaterThanOrEqual(delta);
      const responsePromise = page.waitForResponse(response => new URL(response.url()).pathname === '/api/workspace-state' && response.request().method() === 'PATCH');
      await mouseDownCaptured(page); await page.mouse.move(point.x, point.y + delta);
      await expect.poll(async () => (await rect(page, '.floating-profile')).y - point.after.y).toBeCloseTo(delta, 0);
      await page.mouse.up(); expect(await handle(page).evaluate(el => el.hasPointerCapture(1))).toBe(false);
      const response = await responsePromise; expect(response.status()).toBe(200);
      await expect.poll(async () => (await readWorkspace(request, headers)).progress_y_ratio).not.toBe(before.progress_y_ratio);
      const saved = await readWorkspace(request, headers);
      const travel = Math.min(host.y + host.height, composer.y) - 8 - Math.max(host.y, nav.y + nav.height) - 8 - point.after.height;
      expect(Math.abs(saved.progress_y_ratio - (point.after.y + delta - Math.max(host.y, nav.y + nav.height) - 8) / travel)).toBeLessThan(.01);
      await testInfo.attach(`drag-${delta}.json`, { body: JSON.stringify({ before: preferences(before), after: preferences(saved), point, delta, status: response.status(), host, nav, composer }), contentType: 'application/json' });
      return saved;
    }
    const saved = await dragReal(a.headers, 60); expect(saved.progress_y_ratio).not.toBe(.5);
    await page.getByRole('button', { name: '收起会话导航' }).click();
    await expect.poll(async () => (await readWorkspace(request, a.headers)).sidebar_collapsed).toBe(true);
    let baseline = await readWorkspace(request, a.headers);
    expect(preferences(baseline)).toEqual({ sidebar_pinned: false, sidebar_collapsed: true, progress_y_ratio: saved.progress_y_ratio });
    await page.setViewportSize({ width: 390, height: 844 });
    await page.getByRole('button', { name: '打开会话导航' }).click();
    expect(preferences(await readWorkspace(request, a.headers))).toEqual(preferences(baseline));
    await page.getByRole('button', { name: /账号：/ }).click();
    expect(preferences(await readWorkspace(request, a.headers))).toEqual(preferences(baseline));
    await page.getByRole('button', { name: '退出登录' }).click(); await expect(page).toHaveURL(/\/login/);
    expect(preferences(await readWorkspace(request, a.headers))).toEqual(preferences(baseline));
    await page.setViewportSize({ width: 1024, height: 900 }); await login(a.username);
    await page.goto(`/chat/${encodeURIComponent(a.session.session_id)}`); await expect(trigger(page)).toBeVisible();
    await expect(page.getByRole('button', { name: '展开会话导航' })).toBeVisible();
    expect((await readWorkspace(request, a.headers)).progress_y_ratio).toBe(saved.progress_y_ratio);
    await assertFloatingRatio(page, baseline.progress_y_ratio);
    for (const path of ['/profile', '/knowledge']) {
      const gotoRequests: string[] = [];
      const recordGoto = (req: { method(): string; url(): string }) => { if (new URL(req.url()).pathname === '/api/workspace-state') gotoRequests.push(req.method()); };
      page.on('request', recordGoto);
      try {
        const gotoGet = page.waitForResponse(response => new URL(response.url()).pathname === '/api/workspace-state' && response.request().method() === 'GET');
        await page.goto(path); expect((await gotoGet).status()).toBe(200); await expect(page.getByRole('button', { name: '展开会话导航' })).toBeVisible();
        await expect(page).toHaveURL(new RegExp(`${path}$`)); expect(gotoRequests.filter(method => method === 'PATCH')).toHaveLength(0);
      } finally { page.off('request', recordGoto); }
      const observation = observeReloadWorkspace(page, path);
      try {
        await page.reload();
        try { await expect.poll(() => observation.result).toBeDefined(); } catch (error) { throw new Error(`reload workspace GET ${path}: ${JSON.stringify(observation.events)}; ${String(error)}`); }
        expect(observation.result?.error, JSON.stringify(observation.events)).toBeUndefined(); expect(observation.result?.status, JSON.stringify(observation.events)).toBe(200);
        expect(preferences(observation.result!.value!)).toEqual(preferences(baseline));
        await expect(page).toHaveURL(new RegExp(`${path}$`)); await expect(page.getByRole('button', { name: '展开会话导航' })).toBeVisible();
        expect(observation.navigations, JSON.stringify(observation.events)).toBe(1); expect(observation.methods.filter(method => method === 'PATCH')).toHaveLength(0); expect(observation.methods).toContain('GET');
      } finally { observation.cleanup(); }
      await page.goto(`/chat/${encodeURIComponent(a.session.session_id)}`); await expect(trigger(page)).toBeVisible(); await assertFloatingRatio(page, baseline.progress_y_ratio);
    }
    await page.getByRole('button', { name: '展开会话导航' }).click();
    await expect.poll(async () => (await readWorkspace(request, a.headers)).sidebar_collapsed).toBe(false);
    baseline = await readWorkspace(request, a.headers);
    await page.getByRole('button', { name: /账号：/ }).click(); await page.getByRole('button', { name: '退出登录' }).click();
    await login(b.username); await page.goto(`/chat/${encodeURIComponent(b.session.session_id)}`); await expect(trigger(page)).toBeVisible();
    expect(preferences(await readWorkspace(request, b.headers))).toEqual({ sidebar_pinned: true, sidebar_collapsed: false, progress_y_ratio: .5 });
    expect((await request.get(`/api/sessions/${encodeURIComponent(a.session.session_id)}/snapshot`, { headers: b.headers })).status()).toBe(403);
    await expect(page.getByRole('heading', { name: `隔离会话${b.username}` })).toBeVisible();
    const bSaved = await dragReal(b.headers, 90); expect(Math.abs(bSaved.progress_y_ratio - baseline.progress_y_ratio)).toBeGreaterThan(.01);
    await page.getByRole('button', { name: /账号：/ }).click(); await page.getByRole('button', { name: '退出登录' }).click();
    await login(a.username); await page.goto(`/chat/${encodeURIComponent(a.session.session_id)}`); await expect(trigger(page)).toBeVisible();
    await expect(page.getByRole('heading', { name: `隔离会话${a.username}` })).toBeVisible();
    expect(preferences(await readWorkspace(request, a.headers))).toEqual(preferences(baseline)); await assertFloatingRatio(page, baseline.progress_y_ratio);
  });
});



test('受控 API · 触屏手柄拖动不滚动页面', async ({ browser }) => {
  const context = await browser.newContext({ viewport: { width: 390, height: 844 }, hasTouch: true, isMobile: true }); const page = await context.newPage();
  try {
    const api = await openControlled(page); const client = await context.newCDPSession(page);
    const initial = api.calls.filter(c => c.url.includes('/snapshot') || c.url.includes('/messages') || c.url.includes('/summary')).length;
    const point = await prepareFloatingDrag(page); const { x, y } = point; const before = await page.evaluate(() => window.scrollY);
    expect(api.calls.filter(c => c.url.includes('/snapshot') || c.url.includes('/messages') || c.url.includes('/summary'))).toHaveLength(initial);
    expect(api.calls.filter(c => c.method === 'PATCH' && c.body && 'progress_y_ratio' in c.body)).toHaveLength(0);
    await handle(page).evaluate(el => el.addEventListener('pointerdown', e => { (el as HTMLElement).dataset.testPointerId = String((e as PointerEvent).pointerId); }, { once: true }));
    await client.send('Input.dispatchTouchEvent', { type: 'touchStart', touchPoints: [{ x, y }] });
    const pointerId = Number(await handle(page).getAttribute('data-test-pointer-id'));
    expect(pointerId).toBeGreaterThan(0); await expect.poll(() => handle(page).evaluate((el, id) => el.hasPointerCapture(id), pointerId)).toBe(true);
    await client.send('Input.dispatchTouchEvent', { type: 'touchMove', touchPoints: [{ x, y: y + 50 }] });
    await expect.poll(async () => (await rect(page, '.floating-profile')).y - point.after.y).toBeGreaterThan(4);
    await client.send('Input.dispatchTouchEvent', { type: 'touchEnd', touchPoints: [] });
    expect(await handle(page).evaluate((el, id) => el.hasPointerCapture(id), pointerId)).toBe(false);
    await expect.poll(() => api.calls.filter(c => c.method === 'PATCH' && c.body && 'progress_y_ratio' in c.body).length).toBe(1);
    expect(await page.evaluate(() => window.scrollY)).toBe(before); await client.detach();
  } finally { await context.close(); }
});

test('受控 API · 展开后调整短高仍遵守边界', async ({ page }) => {
  await page.setViewportSize({ width: 760, height: 900 }); const api = await openControlled(page); await trigger(page).hover(); await expect(trigger(page)).toHaveAttribute('aria-expanded', 'true');
  const old = api.getState().progress_y_ratio; await page.setViewportSize({ width: 760, height: 450 }); await checkBounds(page);
  expect(api.getState().progress_y_ratio).toBe(old); expect(api.calls.filter(c => c.method === 'PATCH' && c.body && 'progress_y_ratio' in c.body)).toHaveLength(0);
});

test('受控 API · 同账号切会话保留比例草稿与阅读位置，浮卡交互不重取消息', async ({ page }, testInfo) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  const api = await controlled(page, true); await page.goto('/chat/s1');
  const draft = page.getByPlaceholder('输入学习问题…'); await expect(draft).toHaveValue('保留草稿');
  await draft.fill('第一会话独有的新草稿');
  const scroller = page.locator('[data-message-id]').first().locator('..');
  await scroller.evaluate(el => { el.scrollTop = el.scrollHeight * .45; el.dispatchEvent(new Event('scroll')); });
  await expect.poll(() => api.getViewState('s1').reading_anchor?.message_id ?? null).not.toBeNull();
  await expect.poll(() => api.getViewState('s1').draft).toBe('第一会话独有的新草稿');
  const anchor = api.getViewState('s1').reading_anchor!;
  const capture = () => scroller.evaluate(el => {
    const top = el.getBoundingClientRect().top;
    const visible = [...el.querySelectorAll<HTMLElement>('[data-message-id]')].find(item => item.getBoundingClientRect().bottom > top)!;
    return { scrollTop: el.scrollTop, height: el.clientHeight, scrollHeight: el.scrollHeight, id: Number(visible.dataset.messageId), offset: visible.getBoundingClientRect().top - top };
  });
  const position = await capture(); expect(position.scrollTop).toBeGreaterThan(0); expect(position.scrollTop + position.height).toBeLessThan(position.scrollHeight - 10);
  const counts = () => api.calls.filter(c => c.method === 'GET' && (c.url.includes('/snapshot') || c.url.includes('/messages'))).length;
  const phases: Record<string, number> = { s1Ready: counts() }; const summaryCount = api.calls.filter(c => c.url.includes('/summary')).length;
  const point = await prepareFloatingDrag(page);
  expect(counts()).toBe(phases.s1Ready); expect(api.calls.filter(c => c.url.includes('/summary'))).toHaveLength(summaryCount);
  expect(api.calls.filter(c => c.method === 'PATCH' && c.body && 'progress_y_ratio' in c.body)).toHaveLength(0);
  await mouseDownCaptured(page); await page.mouse.move(point.x, point.y + 40);
  await expect.poll(async () => (await rect(page, '.floating-profile')).y - point.after.y).toBeGreaterThan(4); await page.mouse.up();
  await expect.poll(() => api.getState().progress_y_ratio).not.toBe(.5);
  await handle(page).focus(); await page.keyboard.press('ArrowUp');
  await expect.poll(() => api.calls.filter(c => c.method === 'PATCH' && c.body && 'progress_y_ratio' in c.body).length).toBeGreaterThanOrEqual(2);
  phases.s1Interaction = counts(); expect(phases.s1Interaction).toBe(phases.s1Ready); await expect(draft).toHaveValue('第一会话独有的新草稿');
  expect(api.getViewState('s1').reading_anchor?.message_id).toBe(anchor.message_id);
  expect(Math.abs(api.getViewState('s1').reading_anchor!.offset_ratio - anchor.offset_ratio)).toBeLessThanOrEqual(.02);
  const ratio = api.getState().progress_y_ratio; await assertFloatingRatio(page, ratio);
  await page.getByRole('button', { name: '第二学习会话' }).click(); await expect(draft).toHaveValue('第二会话草稿');
  await expect(page.getByText('第二会话历史')).toBeVisible(); phases.s2Ready = counts(); await assertFloatingRatio(page, ratio);
  await trigger(page).hover(); await expect(trigger(page)).toHaveAttribute('aria-expanded', 'true'); await page.mouse.move(5, 5);
  phases.s2Interaction = counts(); expect(phases.s2Interaction).toBe(phases.s2Ready);
  await page.getByRole('button', { name: '中文学习会话' }).click(); await expect(draft).toHaveValue('第一会话独有的新草稿');
  phases.s1Return = counts(); await expect.poll(async () => (await capture()).id).toBe(position.id);
  expect(Math.abs((await capture()).offset - position.offset)).toBeLessThanOrEqual(2);
  expect(api.getViewState('s1').reading_anchor?.message_id).toBe(anchor.message_id); await assertFloatingRatio(page, ratio);
  await expect(page.getByRole('button', { name: '取消固定侧栏，保持当前展示' })).toHaveAttribute('aria-pressed', 'true');
  expect(api.calls.filter(c => c.method === 'POST')).toHaveLength(0);
  await testInfo.attach('session-observations.json', { body: JSON.stringify({ phases, position, restored: await capture(), anchor, ratio, s1View: api.getViewState('s1'), s2View: api.getViewState('s2') }), contentType: 'application/json' });
});



test('受控 API · 代表性键盘焦点与关闭详情', async ({ page }, testInfo) => {
  await page.setViewportSize({ width: 1024, height: 900 }); await openControlled(page); await page.mouse.move(1, 1);
  const trace: unknown[] = [];
  const press = async (key: 'Tab' | 'Shift+Tab' | 'Escape') => { await page.keyboard.press(key); trace.push({ key, ...await page.evaluate(() => ({ tag: document.activeElement?.tagName, label: document.activeElement?.getAttribute('aria-label'), text: document.activeElement?.textContent?.trim().slice(0, 100), expanded: document.querySelector('.floating-profile-trigger')?.getAttribute('aria-expanded') })) }); };
  const step = async (key: 'Tab' | 'Shift+Tab', target: ReturnType<Page['locator']>, closed = false) => {
    for (let i = 0; i < 40; i++) {
      await press(key);
      const state = await page.evaluate(() => ({ tag: document.activeElement?.tagName, label: document.activeElement?.getAttribute('aria-label'), text: document.activeElement?.textContent?.trim().slice(0, 100), expanded: document.querySelector('.floating-profile-trigger')?.getAttribute('aria-expanded'), inDetails: !!document.activeElement?.closest('.floating-profile-content') }));
      trace.push({ key, ...state });
      const reached = await target.evaluate(el => el === document.activeElement);
      if (closed) { expect(state.inDetails, JSON.stringify(trace)).toBe(false); if (!reached) expect(state.expanded, JSON.stringify(trace)).toBe('false'); }
      if (reached) return;
    }
    throw new Error(`焦点在40步内未到达目标：${JSON.stringify(trace)}`);
  };
  const link = page.getByRole('link', { name: '查看完整画像' });
  try {
    await step('Tab', trigger(page)); await expect(trigger(page)).toHaveAttribute('aria-expanded', 'true');
    const focus = await trigger(page).evaluate(el => { const style = getComputedStyle(el); return { visible: el.matches(':focus-visible'), style: style.outlineStyle, width: style.outlineWidth, color: style.outlineColor }; });
    expect(focus.visible).toBe(true); expect(focus.style).not.toBe('none'); expect(parseFloat(focus.width)).toBeGreaterThan(0); expect(focus.color).not.toBe('transparent');
    await page.screenshot({ path: testInfo.outputPath('keyboard-focus.png') }); await testInfo.attach('keyboard-focus.png', { path: testInfo.outputPath('keyboard-focus.png'), contentType: 'image/png' });
    await press('Tab'); await expect(handle(page)).toBeFocused(); await expect(trigger(page)).toHaveAttribute('aria-expanded', 'true');
    await press('Tab'); await expect(link).toBeFocused(); await expect(trigger(page)).toHaveAttribute('aria-expanded', 'true');
    await press('Shift+Tab'); await expect(handle(page)).toBeFocused(); await expect(trigger(page)).toHaveAttribute('aria-expanded', 'true');
    await press('Shift+Tab'); await expect(trigger(page)).toBeFocused(); await expect(trigger(page)).toHaveAttribute('aria-expanded', 'true');
    await press('Shift+Tab'); await expect(trigger(page)).toHaveAttribute('aria-expanded', 'false');
    await press('Tab'); await expect(trigger(page)).toBeFocused(); await expect(trigger(page)).toHaveAttribute('aria-expanded', 'true');
    await press('Escape'); await expect(trigger(page)).toBeFocused(); await expect(trigger(page)).toHaveAttribute('aria-expanded', 'false');
    await press('Tab'); await expect(handle(page)).toBeFocused(); await expect(trigger(page)).toHaveAttribute('aria-expanded', 'false');
    await press('Tab'); await expect(trigger(page)).toHaveAttribute('aria-expanded', 'false'); await expect(link).toHaveCount(0);
    await step('Shift+Tab', handle(page), true); await expect(handle(page)).toBeFocused(); await expect(trigger(page)).toHaveAttribute('aria-expanded', 'true'); await press('Shift+Tab'); await expect(trigger(page)).toBeFocused(); await expect(trigger(page)).toHaveAttribute('aria-expanded', 'true');
    await press('Shift+Tab'); await expect(trigger(page)).toHaveAttribute('aria-expanded', 'false');
    await trigger(page).hover(); await expect(trigger(page)).toHaveAttribute('aria-expanded', 'true'); await page.mouse.move(1, 1); await expect(trigger(page)).toHaveAttribute('aria-expanded', 'false');
  } finally {
    await writeFile(testInfo.outputPath('keyboard-trace.json'), JSON.stringify({ viewport: { width: 1024, height: 900 }, trace })); await testInfo.attach('keyboard-trace.json', { path: testInfo.outputPath('keyboard-trace.json'), contentType: 'application/json' });
  }
});

test('受控 API · 代表性短高长内容与两倍实际字号', async ({ page }, testInfo) => {
  await page.setViewportSize({ width: 600, height: 450 }); await page.emulateMedia({ reducedMotion: 'reduce' });
  const api = await controlled(page, false, 'long'); await page.goto('/chat/s1'); await expect(trigger(page)).toBeVisible(); await trigger(page).hover();
  const scale = () => page.evaluate(() => {
    const elements = [...document.querySelectorAll<HTMLElement>('.workspace-shell, .workspace-shell *')];
    for (const el of elements) if (el.dataset.testFontBaseline) el.style.fontSize = el.dataset.testFontOriginal || '';
    const values = elements.map(el => ({ el, baseline: parseFloat(getComputedStyle(el).fontSize), original: el.style.fontSize }));
    for (const item of values) { item.el.dataset.testFontBaseline = String(item.baseline); item.el.dataset.testFontOriginal = item.original; item.el.style.fontSize = `${item.baseline * 2}px`; }
    return values.map(item => ({ tag: item.el.tagName, className: item.el.className, label: item.el.getAttribute('aria-label'), text: item.el.textContent?.trim().slice(0, 40), baseline: item.baseline, actual: parseFloat(getComputedStyle(item.el).fontSize) }));
  });
  const observations: Record<string, unknown> = {};
  try {
    observations.normal = await page.locator('.floating-profile, .workspace-main, .sidebar-groups').evaluateAll(els => els.map(el => { const r = el.getBoundingClientRect(); return { x: r.x, y: r.y, width: r.width, height: r.height, top: el.scrollTop, heightTotal: el.scrollHeight, client: el.clientHeight }; }));
    observations.fonts = await scale();
    for (const sample of observations.fonts as { baseline: number; actual: number }[]) expect(Math.abs(sample.actual - sample.baseline * 2)).toBeLessThanOrEqual(1);
    const details = page.locator('.floating-profile-content'), sidebar = page.locator('.sidebar-groups'), messages = page.locator('[data-message-id]').first().locator('..');
    const read = (selector: string) => page.locator(selector).evaluate(el => { const r = el.getBoundingClientRect(); return { x: r.x, y: r.y, width: r.width, height: r.height, top: el.scrollTop, sw: el.scrollWidth, cw: el.clientWidth, sh: el.scrollHeight, ch: el.clientHeight }; });
    const regions = async () => ({ document: await read('html'), main: await read('.workspace-main'), sidebar: await read('.sidebar-groups'), messages: await messages.evaluate(el => ({ top: el.scrollTop, sw: el.scrollWidth, cw: el.clientWidth, sh: el.scrollHeight, ch: el.clientHeight })), details: await read('.floating-profile-content'), footer: await read('.sidebar-account'), composer: await read('.legacy-chat > div:has(> form)') });
    observations.before = await regions(); const before = observations.before as Awaited<ReturnType<typeof regions>>;
    expect(before.details.sh).toBeGreaterThan(before.details.ch); expect(before.sidebar.sh).toBeGreaterThan(before.sidebar.ch); expect(before.messages.sh).toBeGreaterThan(before.messages.ch);
    await details.hover(); await page.mouse.wheel(0, 1200); await expect.poll(() => details.evaluate(el => el.scrollTop)).toBeGreaterThan(0);
    await page.mouse.wheel(0, 10000); await expect.poll(() => details.evaluate(el => el.scrollTop + el.clientHeight >= el.scrollHeight - 1)).toBe(true);
    const draft = page.getByPlaceholder('输入学习问题…'); await draft.fill('短高字号压力草稿'); await expect(draft).toHaveValue('短高字号压力草稿'); await expect.poll(() => api.getViewState('s1').draft).toBe('短高字号压力草稿');
    const send = page.locator('.legacy-chat form button[type="submit"]'); await expect(send).toBeEnabled();
    const hit = async (locator: ReturnType<Page['locator']>) => { const box = await locator.boundingBox(); expect(box).not.toBeNull(); const point = { x: box!.x + box!.width / 2, y: box!.y + box!.height / 2 }; expect(await locator.evaluate((el, p) => { const hit = document.elementFromPoint(p.x, p.y); return hit === el || el.contains(hit); }, point)).toBe(true); };
    observations.afterFill = { ...await regions(), send: await read('.chat-composer-area button'), title: await read('.chat-session-title'), top: await read('.sidebar-top-controls') };
    const filled = observations.afterFill as Awaited<ReturnType<typeof regions>> & { send: Awaited<ReturnType<typeof read>>; title: Awaited<ReturnType<typeof read>>; top: Awaited<ReturnType<typeof read>> };
    expect(filled.sidebar.ch).toBeGreaterThanOrEqual(48); expect(filled.messages.ch).toBeGreaterThan(0);
    for (const area of [filled.footer, filled.composer, filled.send]) { expect(area.y).toBeGreaterThanOrEqual(0); expect(area.y + area.height).toBeLessThanOrEqual(450); }
    expect(filled.title.height).toBeLessThanOrEqual(Math.min(96, (await read('.legacy-chat')).height * .25) + 1);
    const title = page.locator('.chat-session-title'), topControls = page.locator('.sidebar-top-controls');
    await title.focus(); await page.keyboard.press('End'); await expect.poll(() => title.evaluate(el => el.scrollTop + el.clientHeight >= el.scrollHeight - 1)).toBe(true);
    await expect(title).toHaveText(`长会话${'学习内容'.repeat(12)}`);
    const titlePoint = await title.evaluate(el => {
      const r = el.getBoundingClientRect(), left = Math.max(0, r.left), right = Math.min(innerWidth, r.right), top = Math.max(0, r.top), bottom = Math.min(innerHeight, r.bottom);
      const points = [{ x: left + 4, y: top + 4 }, { x: right - 4, y: top + 4 }, { x: left + 4, y: bottom - 4 }, { x: right - 4, y: bottom - 4 }, { x: left + 4, y: (top + bottom) / 2 }];
      const candidates = points.filter(p => p.x >= left && p.x < right && p.y >= top && p.y < bottom).map(p => { const hit = document.elementFromPoint(p.x, p.y); return { ...p, matches: hit === el || el.contains(hit), tag: hit?.tagName, text: hit?.textContent?.trim().slice(0, 80) }; });
      return { rect: { left, right, top, bottom }, candidates, point: candidates.find(p => p.matches) };
    });
    const titleScrollBefore = await title.evaluate(el => el.scrollTop), expandedBefore = await trigger(page).getAttribute('aria-expanded');
    observations.titlePoint = { ...titlePoint, scrollBefore: titleScrollBefore, expandedBefore };
    expect(titlePoint.point, JSON.stringify(titlePoint)).toBeTruthy();
    await page.mouse.move(titlePoint.point!.x, titlePoint.point!.y);
    const expandedAfter = await trigger(page).getAttribute('aria-expanded');
    await page.mouse.wheel(0, -10000); await expect.poll(() => title.evaluate(el => el.scrollTop)).toBe(0);
    observations.titleScroll = { before: titleScrollBefore, after: await title.evaluate(el => el.scrollTop), expandedBefore, expandedAfter };
    await expect(title).toHaveText(`长会话${'学习内容'.repeat(12)}`);
    await topControls.focus(); await page.keyboard.press('End'); await expect.poll(() => topControls.evaluate(el => el.scrollTop + el.clientHeight >= el.scrollHeight - 1)).toBe(true);
    await topControls.hover(); await page.mouse.wheel(0, -10000); await expect.poll(() => topControls.evaluate(el => el.scrollTop)).toBe(0);
    observations.sendHit = await send.evaluate(el => { const r = el.getBoundingClientRect(), x = r.x + r.width / 2, y = r.y + r.height / 2, hit = document.elementFromPoint(x, y); return { x, y, matches: hit === el || el.contains(hit) }; });
    await hit(send); await hit(page.getByRole('button', { name: /账号：/ })); await page.getByRole('button', { name: '收起会话导航' }).click(); await checkBounds(page); await page.getByRole('button', { name: '展开会话导航' }).click(); await checkBounds(page);
    await page.getByRole('button', { name: /账号：/ }).click(); observations.menuFonts = await scale(); for (const sample of observations.menuFonts as { baseline: number; actual: number }[]) expect(Math.abs(sample.actual - sample.baseline * 2)).toBeLessThanOrEqual(1); await expect(page.getByRole('button', { name: '退出登录' })).toBeVisible(); await page.getByRole('button', { name: /账号：/ }).click();
    const pre = messages.locator('pre').first(); const code = await pre.evaluate(el => ({ sw: el.scrollWidth, cw: el.clientWidth, whiteSpace: getComputedStyle(el).whiteSpace })); observations.code = code; expect(code.sw).toBeGreaterThan(code.cw); expect(code.whiteSpace).toBe('pre');
    await trigger(page).hover(); await expect(trigger(page)).toHaveAttribute('aria-expanded', 'true'); await expect(details).toBeVisible();
    observations.baselineFonts = await scale(); for (const sample of observations.baselineFonts as { baseline: number; actual: number }[]) expect(Math.abs(sample.actual - sample.baseline * 2)).toBeLessThanOrEqual(1);
    const baseline = await regions();
    const priorMessage = await messages.evaluate(el => el.scrollTop); await sidebar.hover(); await page.mouse.wheel(0, 500); await expect.poll(() => sidebar.evaluate(el => el.scrollTop)).toBeGreaterThan(0); expect(await messages.evaluate(el => el.scrollTop)).toBe(priorMessage);
    const priorSidebar = await sidebar.evaluate(el => el.scrollTop); await messages.hover(); await page.mouse.wheel(0, -10000); await expect.poll(() => messages.evaluate(el => el.scrollTop)).toBe(0); await page.mouse.wheel(0, 500); await expect.poll(() => messages.evaluate(el => el.scrollTop)).toBeGreaterThan(0); expect(await sidebar.evaluate(el => el.scrollTop)).toBe(priorSidebar);
    await trigger(page).hover(); observations.reopenedFonts = await scale(); for (const sample of observations.reopenedFonts as { baseline: number; actual: number }[]) expect(Math.abs(sample.actual - sample.baseline * 2)).toBeLessThanOrEqual(1); observations.after = await regions(); const after = observations.after as Awaited<ReturnType<typeof regions>>;
    for (const region of [after.document, after.main, after.sidebar, after.messages, after.details]) expect(region.sw).toBeLessThanOrEqual(region.cw + 1);
    expect(Math.abs(after.footer.y - baseline.footer.y)).toBeLessThanOrEqual(1); expect(Math.abs(after.composer.y - baseline.composer.y)).toBeLessThanOrEqual(1);
    observations.motion = await page.locator('.floating-profile, .floating-profile *').evaluateAll(elements => elements.map(el => { const s = getComputedStyle(el); return { name: s.animationName, animation: s.animationDuration, transition: s.transitionDuration }; }));
    for (const motion of observations.motion as { name: string; animation: string; transition: string }[]) { expect(motion.name === 'none' || motion.animation.split(',').every(x => parseFloat(x) === 0)).toBe(true); expect(motion.transition.split(',').every(x => parseFloat(x) === 0)).toBe(true); }
    await page.screenshot({ path: testInfo.outputPath('long-content.png') }); await testInfo.attach('long-content.png', { path: testInfo.outputPath('long-content.png'), contentType: 'image/png' });
    const link = page.getByRole('link', { name: '查看完整画像' }); await expect(link).toHaveAttribute('href', '/profile?profile_id=p1&session_id=s1');
    for (let i = 0; i < 40 && !(await link.evaluate(el => el === document.activeElement)); i++) await page.keyboard.press('Tab');
    await expect(link).toBeFocused(); await hit(link); expect(await link.evaluate(el => el.matches(':focus-visible'))).toBe(true); await page.keyboard.press('Enter'); await expect(page).toHaveURL(/\/profile\?profile_id=p1&session_id=s1/); const profilePage = page.locator('.profile-page'), profileGrid = profilePage.locator('.profile-grid'), detailPanel = profileGrid.locator('.profile-panel');
    await expect(profileGrid).toBeVisible(); await expect(profilePage.getByText('正在读取画像…', { exact: true })).toHaveCount(0); await expect(profilePage.getByRole('alert')).toHaveCount(0);
    await expect(detailPanel.locator('header h2')).toHaveText('长中文主题'.repeat(16));
    const nodeTitle = `长知识点1${'学习内容'.repeat(18)}`;
    await expect(detailPanel.getByText(`当前知识点：${nodeTitle}`, { exact: true })).toBeVisible(); await expect(detailPanel.locator('.profile-node-list h4').getByText(nodeTitle, { exact: true })).toBeVisible(); await expect(profilePage.locator('#profile-select')).toHaveValue('p1');
  } finally { await writeFile(testInfo.outputPath('long-observations.json'), JSON.stringify(observations)); await testInfo.attach('long-observations.json', { path: testInfo.outputPath('long-observations.json'), contentType: 'application/json' }); }
});

test('受控 API · 代表性移动抽屉菜单与退出提示', async ({ browser }, testInfo) => {
  const context = await browser.newContext({ viewport: { width: 390, height: 844 }, hasTouch: true, isMobile: true });
  const log: unknown[] = []; let api: Awaited<ReturnType<typeof controlled>> | undefined;
  try {
    const page = await context.newPage(); api = await controlled(page, false, 'fail-save'); await page.goto('/chat/s1'); await expect(trigger(page)).toBeVisible(); await trigger(page).tap();
    const phase = async (name: string) => {
      log.push({ phase: name, expanded: await trigger(page).getAttribute('aria-expanded'), detailsVisible: await page.getByLabel('画像详情').isVisible(), drawerVisible: await page.getByRole('complementary', { name: '会话导航' }).isVisible(), stayFocused: await page.evaluate(() => document.activeElement?.textContent?.trim() === '留在页面'), active: await page.evaluate(() => ({ tag: document.activeElement?.tagName, label: document.activeElement?.getAttribute('aria-label'), text: document.activeElement?.textContent?.trim() })) });
      await expect(trigger(page)).toHaveAttribute('aria-expanded', 'true'); await expect(page.getByLabel('画像详情')).toBeVisible();
    };
    const hit = async (locator: ReturnType<Page['locator']>) => {
      const box = await locator.boundingBox(), card = await page.locator('.floating-profile').boundingBox(); expect(box).not.toBeNull(); expect(card).not.toBeNull();
      const left = Math.max(box!.x, card!.x), right = Math.min(box!.x + box!.width, card!.x + card!.width), top = Math.max(box!.y, card!.y), bottom = Math.min(box!.y + box!.height, card!.y + card!.height);
      const overlap = right > left && bottom > top; const point = overlap ? { x: (left + right) / 2, y: (top + bottom) / 2 } : { x: box!.x + box!.width / 2, y: box!.y + box!.height / 2 };
      const result = await locator.evaluate((el, p) => { const target = document.elementFromPoint(p.x, p.y); return { matches: target === el || el.contains(target), tag: target?.tagName, label: target?.getAttribute('aria-label') }; }, point);
      log.push({ box, card, overlap, point, result }); expect(result.matches).toBe(true); return point;
    };
    const tapHit = async (locator: ReturnType<Page['locator']>) => { const point = await hit(locator); await page.touchscreen.tap(point.x, point.y); };
    await phase('trigger tap'); await page.getByRole('button', { name: '打开会话导航' }).tap(); await phase('drawer open');
    const account = page.getByRole('button', { name: /账号：/ }); await tapHit(account); await phase('menu open');
    const logout = page.getByRole('button', { name: '退出登录' }); await hit(logout); await expect(logout).toBeVisible(); await account.tap(); await expect(logout).not.toBeVisible(); await phase('menu closed'); await account.tap(); await expect(logout).toBeVisible(); await phase('menu reopened');
    await page.getByRole('button', { name: '关闭会话导航', exact: true }).tap(); await expect(page.getByRole('complementary', { name: '会话导航' })).not.toBeVisible(); await phase('drawer closed');
    const draft = page.getByPlaceholder('输入学习问题…'); await draft.fill('受控503仍保留的草稿');
    await expect.poll(() => api!.calls.filter(c => c.method === 'PATCH' && c.url === '/api/sessions/s1/view-state').length).toBeGreaterThan(0);
    await page.getByRole('button', { name: '打开会话导航' }).tap(); await expect(logout).toBeVisible(); await phase('drawer reopened before logout');
    const mainBefore = await page.locator('.workspace-main').boundingBox(); await tapHit(logout);
    const dialog = page.getByRole('dialog', { name: '退出登录' }); await expect(dialog).toBeVisible(); await phase('dialog open'); const stay = dialog.getByRole('button', { name: '留在页面' });
    const mainAfter = await page.locator('.workspace-main').boundingBox(), roleRect = await dialog.boundingBox(), stayRect = await stay.boundingBox();
    log.push({ mainBefore, mainAfter, roleRect, stayRect }); expect(mainBefore).not.toBeNull(); expect(mainAfter).not.toBeNull(); expect(Math.abs(mainAfter!.width - mainBefore!.width)).toBeLessThanOrEqual(1);
    for (const box of [roleRect, stayRect]) { expect(box).not.toBeNull(); expect(box!.x).toBeGreaterThanOrEqual(0); expect(box!.y).toBeGreaterThanOrEqual(0); expect(box!.x + box!.width).toBeLessThanOrEqual(390); expect(box!.y + box!.height).toBeLessThanOrEqual(844); }
    await expect(stay).toBeFocused(); await hit(stay);
    for (let i = 0; i < 40 && !(await stay.evaluate(el => el === document.activeElement)); i++) { await page.keyboard.press('Tab'); log.push(await page.evaluate(() => ({ tag: document.activeElement?.tagName, text: document.activeElement?.textContent?.trim() }))); }
    await expect(stay).toBeFocused(); await expect(page.getByRole('complementary', { name: '会话导航' })).toBeVisible(); await phase('before escape'); await page.screenshot({ path: testInfo.outputPath('overlay.png') }); await testInfo.attach('overlay.png', { path: testInfo.outputPath('overlay.png'), contentType: 'image/png' }); await page.keyboard.press('Escape'); await expect(dialog).toBeVisible(); await expect(trigger(page)).not.toBeFocused(); await expect(stay).toBeFocused(); await expect(page.getByRole('complementary', { name: '会话导航' })).toBeVisible(); await phase('after escape'); await tapHit(stay);
    await expect(dialog).not.toBeVisible(); await expect(page).toHaveURL(/\/chat\/s1$/); if (await page.getByRole('button', { name: '关闭会话导航', exact: true }).isVisible()) await page.getByRole('button', { name: '关闭会话导航', exact: true }).tap(); await expect(draft).toHaveValue('受控503仍保留的草稿');
  } finally {
    try { await writeFile(testInfo.outputPath('overlay-observations.json'), JSON.stringify({ fixture: 'controlled s1 view-state PATCH 503', calls: api?.calls.filter(c => c.url.endsWith('/view-state')).map(c => ({ url: c.url, method: c.method })), log })); await testInfo.attach('overlay-observations.json', { path: testInfo.outputPath('overlay-observations.json'), contentType: 'application/json' }); }
    finally { await context.close(); }
  }
});
