// Task10 controlled-network browser acceptance. No real backend is contacted.
const fs = require('node:fs');
const path = require('node:path');
const http = require('node:http');
const crypto = require('node:crypto');
const assert = require('node:assert/strict');

function argumentsOf(argv) {
  const opts = {};
  for (let i = 0; i < argv.length; i++) {
    const key = argv[i];
    if (key === '--probe-only') { opts.probe = true; continue; }
    if (!['--project-root', '--tool-root', '--browser-path', '--run-id', '--output-root', '--scenario'].includes(key) || !argv[i + 1] || argv[i + 1].startsWith('--')) throw Error(`Invalid argument: ${key}`);
    if (opts[key]) throw Error(`Duplicate argument: ${key}`);
    opts[key] = argv[++i];
  }
  for (const key of ['--project-root', '--tool-root', '--browser-path', '--run-id', '--output-root']) if (!opts[key]) throw Error(`Missing ${key}`);
  if (!/^[a-zA-Z0-9_-]+$/.test(opts['--run-id'])) throw Error('Invalid run id');
  if (!['conflict', 'network', 'cursor-loop', 'source-change', 'all'].includes(opts['--scenario'] || 'all')) throw Error('Invalid scenario');
  return opts;
}
function inside(base, target) {
  const rel = path.relative(base, target);
  return rel !== '' && !rel.startsWith('..' + path.sep) && rel !== '..' && !path.isAbsolute(rel);
}
function hash(file) { return crypto.createHash('sha256').update(fs.readFileSync(file)).digest('hex'); }
function prepareRun(opts) {
  for (const key of ['--project-root', '--tool-root', '--browser-path', '--output-root']) if (!path.isAbsolute(opts[key])) throw Error(`${key} must be absolute`);
  const root = fs.realpathSync(opts['--project-root']);
  const tool = fs.realpathSync(opts['--tool-root']);
  const browser = fs.realpathSync(opts['--browser-path']);
  const outputRoot = fs.realpathSync(opts['--output-root']);
  const runtime = fs.realpathSync(path.join(root, '.superpowers/runtime/task10-browser'));
  const allowedOutput = fs.realpathSync(path.join(root, 'docs/delivery/study-workspace-goal/evidence/Task10/goal-recovery-minimal/browser-controlled'));
  if (!inside(runtime, tool) || outputRoot !== allowedOutput) throw Error('Directory outside approved scope');
  const dist = fs.realpathSync(path.join(root, 'web/dist'));
  if (!fs.existsSync(path.join(dist, 'index.html'))) throw Error('Missing dist/index.html');
  const output = path.join(outputRoot, opts['--run-id']);
  fs.mkdirSync(output); // exclusive: never overwrite a prior run
  const pkgPath = require.resolve('playwright-core/package.json', { paths: [tool] });
  if (!inside(tool, fs.realpathSync(pkgPath))) throw Error('playwright-core resolved outside tool directory');
  const pkg = require(pkgPath);
  if (pkg.version !== '1.64.1') throw Error(`Unexpected playwright-core ${pkg.version}`);
  const files = ['web/src/pages/Chat.tsx', 'web/src/pages/Chat.test.tsx', 'web/src/store/workspace.ts', 'web/src/store/workspaceController.ts', 'web/src/store/localRecovery.ts', 'web/src/api/client.ts'];
  const hashes = Object.fromEntries(files.map(f => [f, hash(path.join(root, f))]));
  return { root, tool, browser, dist, output, pkgPath, hashes };
}
async function startStaticServer(dist) {
  const mime = { '.html': 'text/html; charset=utf-8', '.js': 'text/javascript; charset=utf-8', '.css': 'text/css; charset=utf-8', '.svg': 'image/svg+xml', '.png': 'image/png', '.ico': 'image/x-icon' };
  const server = http.createServer((req, res) => {
    try {
      const url = new URL(req.url, 'http://localhost');
      const decoded = decodeURIComponent(url.pathname);
      if (!['GET', 'HEAD'].includes(req.method) || decoded === '/api' || decoded.startsWith('/api/') || decoded.includes('\\') || decoded.split('/').includes('..')) { res.writeHead(404).end(); return; }
      let file = path.resolve(dist, '.' + decoded);
      if (!inside(dist, file)) { res.writeHead(404).end(); return; }
      if (!fs.existsSync(file) || !fs.statSync(file).isFile()) {
        if (path.extname(decoded)) { res.writeHead(404).end(); return; }
        file = path.join(dist, 'index.html');
      }
      if (!inside(dist, fs.realpathSync(file))) { res.writeHead(404).end(); return; }
      res.writeHead(200, { 'content-type': mime[path.extname(file)] || 'application/octet-stream', 'cache-control': 'no-store' });
      if (req.method === 'HEAD') res.end(); else fs.createReadStream(file).pipe(res);
    } catch { res.writeHead(400).end(); }
  });
  await new Promise((resolve, reject) => { server.once('error', reject); server.listen(0, '127.0.0.1', resolve); });
  return { server, origin: `http://127.0.0.1:${server.address().port}`, port: server.address().port };
}
async function probe(browser, origin) {
  const context = await browser.newContext({ serviceWorkers: 'block' });
  const page = await context.newPage();
  let unknownBlocked = false;
  try {
    await context.route('**/*', async route => {
      const url = new URL(route.request().url());
      if (url.origin !== origin) return route.abort();
      if (url.pathname === '/api/probe') return route.fulfill({ json: { probe: 'controlled' } });
      if (url.pathname.startsWith('/api/')) { unknownBlocked = true; return route.abort(); }
      return route.continue();
    });
    await page.goto(origin + '/probe-spa');
    assert.equal(await page.evaluate(async () => (await (await fetch('/api/probe')).json()).probe), 'controlled');
    await page.evaluate(() => fetch('/api/unknown').catch(() => null));
    assert.equal(unknownBlocked, true);
  } finally { await context.close(); }
}

async function scenarioRoutes(context, origin, scenario, events) {
  const profile = { id: 'p1', name: '概率论', user_id: 1, scope_description: '学习范围', kind: 'manual', revision: 0, created_at: '2026-10-27T00:00:00Z', updated_at: '2026-10-27T00:00:00Z' };
  const session = { session_id: 'A', title: '会话 A', user_id: 1, profile_id: 'p1', active_node_id: null, state_version: 0, next_turn_index: 0, active_request_id: null, created_at: null, updated_at: null };
  const workspace = { last_session_id: 'A', sidebar_pinned: true, sidebar_collapsed: false, progress_y_ratio: 0.5, version: 0, updated_at: null };
  const user = { id: 10, turn_index: 0, role: 'user', content: scenario === 'source-change' ? '来源问题' : '双重查问题', created_at: null };
  const answer = { id: 11, turn_index: 0, role: 'assistant', content: scenario === 'source-change' ? '答案' : '正确回答', created_at: null };
  const state = { phase: 'init', sent: scenario === 'source-change' ? { request_id: 'r-source', message: user.content } : null, postCount: 0, held: {}, waiters: {}, failures: [] };
  const record = (event, details = {}) => events.push({ seq: events.length + 1, phase: state.phase, event, ...details });
  const reply = (route, data, status = 200) => route.fulfill({ status, json: data });
  const baseSnapshot = messages => ({ session: state.phase === 'init' ? session : { ...session, state_version: 1, next_turn_index: 1 }, teaching_state: null, teaching_state_source: 'stored', profile, profile_summary: null, view_state: { draft: '', reading_anchor: null, version: 0, updated_at: null }, pending_requests: [], messages });
  await context.route('**/*', async route => {
    const req = route.request(); const url = new URL(req.url()); const method = req.method();
    if (url.origin !== origin) { state.failures.push(`external ${url.origin}`); record('blocked-external'); return route.abort(); }
    if (!url.pathname.startsWith('/api/')) return route.continue();
    record('request', { method, path: url.pathname + url.search });
    if (url.pathname === '/api/workspace-state' && method === 'GET') return reply(route, workspace);
    if (url.pathname === '/api/workspace-state' && method === 'PATCH') { const body = req.postDataJSON(); return reply(route, { ...workspace, last_session_id: body.last_session_id, version: body.expected_version + 1 }); }
    if (url.pathname === '/api/sessions' && method === 'GET') return reply(route, { groups: [{ group_key: 'p1', profile, summary: null, sessions: [session], next_session_cursor: null }], next_group_cursor: null });
    if (url.pathname === '/api/sessions/A/view-state' && method === 'PATCH') { const body = req.postDataJSON(); return reply(route, { draft: body.draft, reading_anchor: body.reading_anchor, version: body.expected_version + 1, updated_at: null }); }
    if (url.pathname === '/api/chat' && method === 'POST' && state.phase === 'init' && !state.sent) {
      state.sent = req.postDataJSON(); state.postCount++; state.phase = 'initial-conflict';
      assert.equal(state.sent.message, user.content); assert.equal(state.sent.session_id, 'A'); assert.equal(state.sent.profile_id, 'p1');
      return reply(route, { session_id: 'A', request_id: state.sent.request_id, status: 'completed', attempt: 1, persisted: true, state_version: 1, reply: answer.content });
    }
    if (url.pathname === '/api/sessions/A/snapshot' && method === 'GET') {
      if (state.phase === 'activity' && !state.held.C) { state.held.C = route; record('held', { slot: 'C', purpose: 'activity-recheck' }); state.waiters.C?.(); return; }
      const messages = state.phase === 'init' ? { items: [], next_cursor: null } : state.phase === 'A' || state.phase === 'source' ? { items: [], next_cursor: 'old' } : state.phase === 'B' ? { items: [], next_cursor: 'new' } : { items: [user, state.phase === 'recover' ? answer : { ...answer, content: '矛盾回答' }], next_cursor: null };
      return reply(route, baseSnapshot(messages));
    }
    if (method === 'GET' && state.sent && url.pathname === `/api/sessions/A/requests/${encodeURIComponent(state.sent.request_id)}`) return reply(route, { user_id: 1, session_id: 'A', request_id: state.sent.request_id, profile_id: 'p1', active_node_id: null, request_payload: { message: user.content, profile_id: 'p1', active_node_id: null, base_state_version: 0 }, base_state_version: 0, attempt: 1, status: 'completed', lease_until: null, lease_expired: false, error_code: null, response_json: { session_id: 'A', request_id: state.sent.request_id, status: 'completed', attempt: 1, persisted: true, state_version: 1, reply: answer.content }, created_at: '', updated_at: '' });
    if (method === 'GET' && url.pathname === '/api/sessions/A/messages') {
      const cursor = url.searchParams.get('cursor'); const slot = cursor === 'old' ? 'A' : cursor === 'new' ? 'B' : null;
      if (slot && (state.phase === slot || (state.phase === 'source' && slot === 'A')) && !state.held[slot]) { state.held[slot] = route; record('held', { slot, cursor }); state.waiters[slot]?.(); return; }
    }
    state.failures.push(`unexpected ${method} ${url.pathname}${url.search}`); record('blocked-unexpected', { method, path: url.pathname + url.search }); return route.abort();
  });
  return {
    state,
    phase(value) { state.phase = value; record('phase'); },
    record,
    expected(outcome) {
      if (outcome === 'activity') return { status: 200, body: baseSnapshot({ items: [user, answer], next_cursor: null }) };
      if (outcome === 'network') return { status: 503, body: {} };
      if (outcome === 'cursor-loop') return { status: 200, body: { items: [], next_cursor: 'new' } };
      return { status: 200, body: { items: [user, outcome === 'conflict' ? { ...answer, content: '矛盾回答' } : answer], next_cursor: null } };
    },
    async release(slot, outcome) {
      const route = state.held[slot]; if (!route) throw Error(`Missing held route ${slot}`); delete state.held[slot];
      record('release', { slot, outcome });
      const expected = this.expected(outcome); await reply(route, expected.body, expected.status);
    },
  };
}
function watchRequest(page, request) {
  let cleanup;
  const done = new Promise((resolve, reject) => {
    let response; let finished = false;
    const timer = setTimeout(() => fail(Error('Timeout waiting for exact request response and finish')), 15000);
    function stop() { clearTimeout(timer); page.off('response', onResponse); page.off('requestfinished', onFinished); page.off('requestfailed', onFailed); }
    function fail(error) { stop(); reject(error); }
    function complete() { if (response && finished) { stop(); resolve(response); } }
    function onResponse(value) { if (value.request() === request) { response = value; complete(); } }
    function onFinished(value) { if (value === request) { finished = true; complete(); } }
    function onFailed(value) { if (value === request) fail(Error('Exact request failed')); }
    cleanup = stop;
    page.on('response', onResponse); page.on('requestfinished', onFinished); page.on('requestfailed', onFailed);
  });
  return { done, cleanup: () => cleanup() };
}
async function releaseAndObserve(page, control, slot, outcome) {
  const route = control.state.held[slot]; if (!route) throw Error(`Missing held route ${slot}`);
  const request = route.request(); const watcher = watchRequest(page, request);
  const completion = watcher.done.then(value => ({ value }), error => ({ error }));
  try {
    const expected = control.expected(outcome);
    await control.release(slot, outcome);
    const observed = await completion; if (observed.error) throw observed.error;
    const response = observed.value;
    assert.equal(response.request(), request); assert.equal(response.status(), expected.status);
    assert.deepEqual(JSON.parse(await response.text()), expected.body);
    control.record('network-finished', { slot, status: response.status(), fixture: outcome });
    await page.evaluate(() => new Promise((resolve, reject) => {
      const channel = new MessageChannel();
      const timeout = setTimeout(() => { channel.port1.close(); channel.port2.close(); reject(Error('Timeout waiting for task and render frames')); }, 15000);
      channel.port1.onmessage = () => { channel.port1.close(); channel.port2.close(); requestAnimationFrame(() => requestAnimationFrame(() => { clearTimeout(timeout); resolve(); })); };
      channel.port2.postMessage(null);
    }));
    control.record('render-observed', { slot });
  } finally { watcher.cleanup(); }
}
async function waitForHeld(control, slot) {
  if (control.state.held[slot]) return;
  await new Promise((resolve, reject) => {
    const timeout = setTimeout(() => reject(Error(`Timeout awaiting route ${slot}, phase ${control.state.phase}`)), 15000);
    control.state.waiters[slot] = () => { clearTimeout(timeout); resolve(); };
  });
}
async function capture(page, output, label) {
  await page.screenshot({ path: path.join(output, label + '.png'), fullPage: true });
  const snapshot = await page.evaluate(() => ({ text: document.body.innerText, sendDisabled: document.querySelector('button[type=submit]')?.disabled ?? null, recovery: Object.fromEntries(Object.keys(localStorage).filter(k => k.startsWith('studyagent:recovery:v1:')).map(k => [k, localStorage.getItem(k)])) }));
  fs.writeFileSync(path.join(output, label + '.json'), JSON.stringify(snapshot, null, 2));
  return snapshot;
}
function exactCopies(snapshot, copies) { for (const [key, value] of Object.entries(copies)) assert.equal(snapshot.recovery[key], value, `Recovery copy changed: ${key}`); }
async function runScenario(browser, origin, run, name) {
  const output = path.join(run.output, name); fs.mkdirSync(output);
  const context = await browser.newContext({ serviceWorkers: 'block', viewport: { width: 1280, height: 900 } });
  const events = []; const control = await scenarioRoutes(context, origin, name, events);
  const page = await context.newPage(); page.setDefaultTimeout(15000); const errors = [];
  const deadline = setTimeout(() => { errors.push('scenario exceeded 90 seconds'); void context.close(); }, 90000);
  page.on('pageerror', error => errors.push(String(error)));
  let result = 'failed'; let error;
  try {
    await context.addInitScript(() => { localStorage.setItem('studyagent_user_id', '1'); localStorage.setItem('studyagent_username', '测试用户'); localStorage.setItem('studyagent_token', 'synthetic-token'); });
    if (name === 'source-change') {
      await context.addInitScript(() => {
        const payload = { message: '来源问题', session_id: 'A', profile_id: 'p1', request_id: 'r-source', expected_state_version: 0 };
        const baseline = { owner_user_id: 1, session_id: 'A', request_id: 'r-source', profile_id: 'p1', active_node_id: null, base_state_version: 0, expected_turn_index: 0, provenance: 'before_submit', snapshot_sequence: 1 };
        const candidate = { text: payload.message, sequence: 1, phase: 'linked', requestId: payload.request_id, payload, baseline, schema: 2, kind: 'prepared', userId: 1, sessionId: 'A', writerId: 'source-writer', writeId: 'source-write', itemId: 'source', savedAt: 1 };
        localStorage.setItem('studyagent:recovery:v1:prepared:1:A:source-writer:source', JSON.stringify(candidate));
        const other = { text: '另一份原文', sequence: 1, phase: 'prepared', schema: 2, kind: 'prepared', userId: 1, sessionId: 'A', writerId: 'other-source-writer', writeId: 'other-source-write', itemId: 'other-source', savedAt: 1 };
        localStorage.setItem('studyagent:recovery:v1:prepared:1:A:other-source-writer:other-source', JSON.stringify(other));
      });
      await page.goto(origin + '/chat/A'); await page.getByText('来源问题').waitFor();
      const before = await capture(page, output, 'source-before');
      control.phase('source'); await page.getByRole('button', { name: '查询原请求', exact: true }).click(); await waitForHeld(control, 'A');
      await page.evaluate(() => { const key = 'studyagent:recovery:v1:prepared:1:A:source-writer:source'; const candidate = JSON.parse(localStorage.getItem(key)); candidate.sequence = 2; candidate.writeId = 'source-write-2'; localStorage.setItem(key, JSON.stringify(candidate)); });
      const changed = await capture(page, output, 'source-changed');
      assert.notEqual(before.recovery['studyagent:recovery:v1:prepared:1:A:source-writer:source'], changed.recovery['studyagent:recovery:v1:prepared:1:A:source-writer:source']);
      await control.release('A', 'conflict'); await page.getByText('本机内容已变化或无法读取，请重新检查').waitFor();
      const warning = await capture(page, output, 'source-warning');
      assert.equal(warning.recovery['studyagent:recovery:v1:prepared:1:A:source-writer:source'], changed.recovery['studyagent:recovery:v1:prepared:1:A:source-writer:source']);
      assert.equal(warning.recovery['studyagent:recovery:v1:prepared:1:A:other-source-writer:other-source'], before.recovery['studyagent:recovery:v1:prepared:1:A:other-source-writer:other-source']);
      assert.equal(control.state.postCount, 0); assert.deepEqual(control.state.failures, []); assert.deepEqual(errors, []);
      result = 'blocked'; error = '来源候选入口已验证，但已有 inconsistent 起点的双重查组合未证实可达'; return { name, result, error };
    }
    await page.goto(origin + '/chat/A');
    await page.getByPlaceholder('输入学习问题…').fill('双重查问题');
    await page.getByRole('button', { name: '发送', exact: true }).click();
    await page.getByText('已保存的消息与请求不一致，请检查').waitFor();
    const copies = await page.evaluate(requestId => {
      const entries = Object.entries(localStorage).filter(([key, value]) => key.startsWith('studyagent:recovery:v1:request:1:A:') && JSON.parse(value).itemId === requestId);
      if (!entries.length) throw Error('No own request recovery copy');
      const candidate = JSON.parse(entries[0][1]); candidate.writerId = 'goal-recovery-other-writer'; candidate.writeId = crypto.randomUUID();
      const key = 'studyagent:recovery:v1:' + ['request', 1, 'A', candidate.writerId, requestId].map(x => encodeURIComponent(String(x))).join(':');
      const value = JSON.stringify(candidate); localStorage.setItem(key, value); return Object.fromEntries([...entries, [key, value]]);
    }, control.state.sent.request_id);
    let snapshot = await capture(page, output, 'initial-conflict'); exactCopies(snapshot, copies);
    control.phase('A'); await page.getByRole('button', { name: '重新查询', exact: true }).click(); await waitForHeld(control, 'A');
    snapshot = await capture(page, output, 'A-held'); exactCopies(snapshot, copies); assert.equal(await page.getByRole('button', { name: '发送', exact: true }).isDisabled(), true);
    control.phase('B'); await page.getByRole('button', { name: '重新查询', exact: true }).click(); await waitForHeld(control, 'B');
    await releaseAndObserve(page, control, 'B', name);
    await page.getByText(name === 'conflict' ? '已保存的消息与请求不一致，请检查' : '回复复核失败，请重新查询').waitFor();
    snapshot = await capture(page, output, 'B-returned'); exactCopies(snapshot, copies); assert.equal(await page.getByRole('button', { name: '发送', exact: true }).isDisabled(), true); assert.equal(control.state.postCount, 1); assert.deepEqual(control.state.failures, []);
    await releaseAndObserve(page, control, 'A', 'success');
    if (name === 'conflict') {
      await page.getByText('已保存的消息与请求不一致，请检查').waitFor();
      snapshot = await capture(page, output, 'A-returned'); exactCopies(snapshot, copies); assert.equal(await page.getByRole('button', { name: '发送', exact: true }).isDisabled(), true); assert.equal(control.state.postCount, 1); assert.deepEqual(control.state.failures, []);
      control.phase('recover'); await page.getByRole('button', { name: '重新查询', exact: true }).click();
    }
    await page.getByText('正确回答').waitFor();
    snapshot = await capture(page, output, 'recovered');
    const other = Object.fromEntries(Object.entries(copies).filter(([key]) => key.includes('goal-recovery-other-writer'))); exactCopies(snapshot, other);
    assert.equal(control.state.postCount, 1); assert.deepEqual(control.state.failures, []); assert.deepEqual(errors, []);
    if (name !== 'conflict') {
      await page.getByText('会话状态待确认').waitFor();
      assert.equal(await page.getByRole('button', { name: '发送', exact: true }).isDisabled(), true);
      snapshot = await capture(page, output, 'activity-pending'); exactCopies(snapshot, other);
      control.phase('activity');
      await page.getByRole('button', { name: '重新查询会话状态', exact: true }).click(); await waitForHeld(control, 'C');
      await releaseAndObserve(page, control, 'C', 'activity');
      await page.getByText('会话状态待确认').waitFor({ state: 'hidden' });
      snapshot = await capture(page, output, 'activity-recovered'); exactCopies(snapshot, other);
      await page.getByText('正确回答').waitFor();
      assert.equal(control.state.postCount, 1); assert.deepEqual(control.state.failures, []); assert.deepEqual(errors, []);
    }
    assert.equal(await page.getByRole('button', { name: '发送', exact: true }).isEnabled(), true);
    result = 'pass';
  } catch (e) { error = String(e.stack || e); await capture(page, output, 'failure').catch(() => {}); }
  finally { clearTimeout(deadline); fs.writeFileSync(path.join(output, 'events.json'), JSON.stringify({ events, errors, failures: control.state.failures, postCount: control.state.postCount }, null, 2)); await context.close(); }
  return { name, result, error };
}
async function main() {
  const opts = argumentsOf(process.argv.slice(2));
  const run = prepareRun(opts);
  const report = { mode: 'real browser / synthetic controlled network', node: process.version, tool: 'playwright-core@1.64.1', browserPath: run.browser, arguments: process.argv.slice(2), hashesBefore: run.hashes, distIndexHash: hash(path.join(run.dist, 'index.html')), scenario: opts['--scenario'] || 'all', status: 'failed' };
  let server, browser;
  try {
    const playwright = require(path.dirname(run.pkgPath));
    server = await startStaticServer(run.dist);
    browser = await playwright.chromium.launch({ executablePath: run.browser, headless: true });
    report.browserVersion = browser.version();
    await probe(browser, server.origin);
    report.probe = 'pass';
    if (!opts.probe) {
      const chosen = opts['--scenario'] || 'all';
      const names = chosen === 'all' ? ['conflict', 'network', 'cursor-loop', 'source-change'] : [chosen];
      report.scenarios = [];
      for (const name of names) report.scenarios.push(await runScenario(browser, server.origin, run, name));
      if (report.scenarios.some(item => item.result !== 'pass')) throw Error('One or more scenarios failed or blocked');
    }
    report.status = 'pass';
  } catch (error) { report.error = String(error.stack || error); process.exitCode = 1; }
  finally {
    if (browser) await browser.close();
    if (server) {
      await new Promise((resolve, reject) => server.server.close(e => e ? reject(e) : resolve()));
      try { await new Promise((resolve, reject) => { const check = http.createServer(); check.once('error', reject); check.listen(server.port, '127.0.0.1', () => check.close(resolve)); }); report.portReleased = true; }
      catch (error) { report.portReleased = false; report.cleanupError = String(error); process.exitCode = 1; }
    }
    report.hashesAfter = Object.fromEntries(Object.keys(run.hashes).map(f => [f, hash(path.join(run.root, f))]));
    fs.writeFileSync(path.join(run.output, 'report.json'), JSON.stringify(report, null, 2));
    fs.writeFileSync(path.join(run.output, '报告.md'), `# 浏览器受控网络验收\n\n结果：${report.status}。工具：playwright-core 1.64.1，浏览器：${report.browserVersion || '未启动'}。\n\n所有 API 响应均为合成数据，不能证明真实登录、模型、保存或数据库持久化。网络结束和页面任务/帧屏障仅是有限观察，不证明业务函数已退出；确定性处理时序由既有 RTL 测试单独验证。\n\n场景：${JSON.stringify(report.scenarios || [])}\n\n错误：${report.error || '无'}\n`);
  }
}
main().catch(error => { console.error(error); process.exitCode = 1; });
