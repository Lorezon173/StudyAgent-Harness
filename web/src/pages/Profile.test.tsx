// @vitest-environment jsdom
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { expect, it, vi } from 'vitest';
import Profile from './Profile';
import { AuthProvider } from '../store/auth';
import { response, storeIdentity, profile } from '../test/setup';

it('renders a verified profile and its real assessed summary', async () => {
  storeIdentity();
  const p = profile('p1', '物理');
  const summary = { profile_revision: p.revision, nodes: [], edges: [], recent_evidence: [], assessed_count: 1, total_count: 2, mastery_score: 80, metric_kind: 'assessed_mean', assessment_coverage: 0.5 };
  vi.stubGlobal('fetch', vi.fn((url: RequestInfo | URL) => Promise.resolve(response(String(url).endsWith('/summary') ? summary : String(url).includes('/p1') ? { profile: p, profile_revision: p.revision, nodes: [], edges: [] } : { items: [p], next_cursor: null }))));
  render(<AuthProvider><MemoryRouter initialEntries={['/profile?profile_id=p1']}><Profile /></MemoryRouter></AuthProvider>);
  expect((await screen.findAllByText('物理')).length).toBeGreaterThan(0);
  expect(screen.getAllByText(/80%/).length).toBeGreaterThan(0);
  expect(screen.getAllByText(/1\s*\/\s*2/).length).toBeGreaterThan(0);
});



it('retries mismatched revisions and keeps the previous matching pair when both retries mismatch', async () => {
  storeIdentity(); const p = profile('p1', '物理'); let summaryCalls = 0;
  const summary = (revision: number, score: number) => ({ profile_revision: revision, nodes: [], edges: [], recent_evidence: [], assessed_count: 1, total_count: 1, mastery_score: score, metric_kind: 'assessed_mean', assessment_coverage: 1 });
  vi.stubGlobal('fetch', vi.fn((url: RequestInfo | URL) => { const path = String(url); if (path.endsWith('/summary')) { summaryCalls++; return Promise.resolve(response(summary(summaryCalls === 1 || summaryCalls > 2 ? 1 : 0, summaryCalls === 2 ? 80 : 10))); } if (path.endsWith('/p1')) return Promise.resolve(response({ profile: p, profile_revision: 0, nodes: [], edges: [] })); return Promise.resolve(response({ items: [p], next_cursor: null })); }));
  const { fireEvent } = await import('@testing-library/react');
  render(<AuthProvider><MemoryRouter initialEntries={['/profile?profile_id=p1']}><Profile /></MemoryRouter></AuthProvider>);
  expect((await screen.findAllByText(/80%/)).length).toBeGreaterThan(0);
  expect(summaryCalls).toBe(2);
  // Trigger a same-target reload through a failed first request on the next run.
  fireEvent.change(screen.getByLabelText('查看主题'), { target: { value: '' } });
  fireEvent.change(screen.getByLabelText('查看主题'), { target: { value: 'p1' } });
  expect((await screen.findByRole('alert')).textContent).toContain('画像已更新');
  expect(screen.getAllByText(/80%/).length).toBeGreaterThan(0);
});


it('resolves the most recent session read-only and links evidence to its real session', async () => {
  storeIdentity(); const p = profile('p1', '物理'); const { session } = await import('../test/setup');
  const node = { id: 'n1', profile_id: 'p1', title: '力学', description: '', mastery: null, last_practiced_at: 0, practice_count: 0, rationale: '', revision: 0, archived: false };
  const summary = { profile_revision: 0, nodes: [node], edges: [], recent_evidence: [{ id: 'e1', node_id: 'old', session_id: 'source 1', request_id: 'r1', message_id: 9, score: 80, rationale: '来源说明', created_at: '2026-01-01' }], assessed_count: 0, total_count: 1, mastery_score: null, metric_kind: 'assessed_mean', assessment_coverage: 0 };
  const fetcher = vi.fn((url: RequestInfo | URL, _init?: RequestInit) => { const path = String(url); if (path.includes('/snapshot')) return Promise.resolve(response({ session: { ...session('s1'), active_node_id: 'n1' }, profile: p })); if (path.endsWith('/workspace-state')) return Promise.resolve(response({ last_session_id: 's1' })); if (path.endsWith('/summary')) return Promise.resolve(response(summary)); if (path.endsWith('/p1')) return Promise.resolve(response({ profile: p, profile_revision: 0, nodes: [], edges: [] })); return Promise.resolve(response({ items: [p], next_cursor: null })); }); vi.stubGlobal('fetch', fetcher);
  render(<AuthProvider><MemoryRouter initialEntries={['/profile']}><Profile /></MemoryRouter></AuthProvider>);
  expect((await screen.findAllByText(/当前知识点：力学/)).length).toBeGreaterThan(0);
  expect(screen.getByText(/已归档知识点（old）/)).toBeTruthy();
  expect(screen.getByRole('link', { name: '查看来源会话' }).getAttribute('href')).toBe('/chat/source%201');
  expect(screen.getByText('暂无已记录关系')).toBeTruthy();
  expect(fetcher.mock.calls.every(([, init]) => !init || (init as RequestInit).method === 'GET')).toBe(true);
});

it('rejects a session linked to another profile without showing either profile as a successful result', async () => {
  storeIdentity(); const p = profile('p1', '物理'); const other = profile('p2', '化学'); const { session } = await import('../test/setup');
  vi.stubGlobal('fetch', vi.fn((url: RequestInfo | URL) => { const path = String(url); if (path.includes('/snapshot')) return Promise.resolve(response({ session: session('s1', 'p2'), profile: other })); return Promise.resolve(response({ items: [p, other], next_cursor: null })); }));
  render(<AuthProvider><MemoryRouter initialEntries={['/profile?profile_id=p1&session_id=s1']}><Profile /></MemoryRouter></AuthProvider>);
  expect((await screen.findByRole('alert')).textContent).toContain('不一致');
  expect(screen.queryByLabelText('画像摘要')).toBeNull();
});

it('ignores an older profile response after selecting another profile', async () => {
  storeIdentity(); const p1 = profile('p1', '物理'); const p2 = profile('p2', '化学'); const { deferred } = await import('../test/setup'); const slow = deferred<Response>();
  const summary = { profile_revision: 0, nodes: [], edges: [], recent_evidence: [], assessed_count: 0, total_count: 0, mastery_score: null, metric_kind: 'assessed_mean', assessment_coverage: null };
  vi.stubGlobal('fetch', vi.fn((url: RequestInfo | URL) => { const path = String(url); if (path.endsWith('/p1')) return slow.promise; if (path.endsWith('/p2')) return Promise.resolve(response({ profile: p2, profile_revision: 0, nodes: [], edges: [] })); if (path.endsWith('/summary')) return Promise.resolve(response(summary)); return Promise.resolve(response({ items: [p1, p2], next_cursor: null })); }));
  const { fireEvent, act } = await import('@testing-library/react');
  render(<AuthProvider><MemoryRouter initialEntries={['/profile?profile_id=p1']}><Profile /></MemoryRouter></AuthProvider>);
  await screen.findByRole('option', { name: '化学' }); fireEvent.change(screen.getByLabelText('查看主题'), { target: { value: 'p2' } });
  expect((await screen.findByLabelText('画像摘要')).textContent).toContain('化学');
  await act(async () => slow.resolve(response({ profile: p1, profile_revision: 0, nodes: [], edges: [] })));
  expect(screen.getByLabelText('画像摘要').textContent).toContain('化学');
});

it('loads additional profile options and opens one without issuing writes', async () => {
  storeIdentity(); const p1 = profile('p1', '物理'); const p2 = profile('p2', '化学');
  const summary = { profile_revision: 0, nodes: [], edges: [], recent_evidence: [], assessed_count: 0, total_count: 0, mastery_score: null, metric_kind: 'assessed_mean', assessment_coverage: null };
  const fetcher = vi.fn((url: RequestInfo | URL, _init?: RequestInit) => { const path = String(url); if (path.includes('cursor=next')) return Promise.resolve(response({ items: [p2], next_cursor: null })); if (path.endsWith('/summary')) return Promise.resolve(response(summary)); if (path.endsWith('/p1') || path.endsWith('/p2')) { const p = path.endsWith('/p1') ? p1 : p2; return Promise.resolve(response({ profile: p, profile_revision: 0, nodes: [], edges: [] })); } return Promise.resolve(response({ items: [p1], next_cursor: 'next' })); }); vi.stubGlobal('fetch', fetcher);
  const { fireEvent } = await import('@testing-library/react');
  render(<AuthProvider><MemoryRouter initialEntries={['/profile?profile_id=p1']}><Profile /></MemoryRouter></AuthProvider>);
  await screen.findByLabelText('画像摘要'); fireEvent.click(screen.getByRole('button', { name: '加载更多主题' }));
  await screen.findByRole('option', { name: '化学' }); fireEvent.change(screen.getByLabelText('查看主题'), { target: { value: 'p2' } });
  expect((await screen.findByLabelText('画像摘要')).textContent).toContain('化学');
  expect(fetcher.mock.calls.every(([, init]) => !init || init.method === 'GET')).toBe(true);
});

it('does not display a previous account late response after account transition', async () => {
  storeIdentity(); const p = profile('p1', '物理'); const { deferred } = await import('../test/setup'); const { workspaceStore } = await import('../store/workspace'); const slow = deferred<Response>();
  const summary = { profile_revision: 0, nodes: [], edges: [], recent_evidence: [], assessed_count: 0, total_count: 0, mastery_score: null, metric_kind: 'assessed_mean', assessment_coverage: null };
  vi.stubGlobal('fetch', vi.fn((url: RequestInfo | URL) => { const path = String(url); if (path.endsWith('/p1')) return slow.promise; if (path.endsWith('/summary')) return Promise.resolve(response(summary)); return Promise.resolve(response({ items: [p], next_cursor: null })); }));
  const { act } = await import('@testing-library/react');
  render(<AuthProvider><MemoryRouter initialEntries={['/profile?profile_id=p1']}><Profile /></MemoryRouter></AuthProvider>);
  await screen.findByRole('option', { name: '物理' });
  await act(async () => { workspaceStore.startAccount(2, 'B'); slow.resolve(response({ profile: p, profile_revision: 0, nodes: [], edges: [] })); });
  expect(screen.queryByLabelText('画像摘要')).toBeNull();
});

it('renders only edges returned by the summary', async () => {
  storeIdentity(); const p = profile();
  const summary = { profile_revision: 0, nodes: [], edges: [{ profile_id: 'p1', from_node_id: 'first', to_node_id: 'second', type: 'prerequisite', weight: 1, confidence: 1, source: 'test' }], recent_evidence: [], assessed_count: 0, total_count: 0, mastery_score: null, metric_kind: 'assessed_mean', assessment_coverage: null };
  vi.stubGlobal('fetch', vi.fn((url: RequestInfo | URL) => Promise.resolve(response(String(url).endsWith('/summary') ? summary : String(url).endsWith('/p1') ? { profile: p, profile_revision: 0, nodes: [], edges: [] } : { items: [p], next_cursor: null }))));
  render(<AuthProvider><MemoryRouter initialEntries={['/profile?profile_id=p1']}><Profile /></MemoryRouter></AuthProvider>);
  expect(await screen.findByText('first → second · prerequisite')).toBeTruthy();
  expect(screen.queryByText('暂无已记录关系')).toBeNull();
});

it('falls back to the first profile only when no recent session exists', async () => {
  storeIdentity(); const p = profile('p1', '物理');
  const summary = { profile_revision: 0, nodes: [], edges: [], recent_evidence: [], assessed_count: 0, total_count: 0, mastery_score: null, metric_kind: 'assessed_mean', assessment_coverage: null };
  const fetcher = vi.fn((url: RequestInfo | URL) => { const path = String(url); return Promise.resolve(response(path.endsWith('/workspace-state') ? { last_session_id: null } : path.endsWith('/summary') ? summary : path.endsWith('/p1') ? { profile: p, profile_revision: 0, nodes: [], edges: [] } : { items: [p], next_cursor: null })); });
  vi.stubGlobal('fetch', fetcher);
  render(<AuthProvider><MemoryRouter initialEntries={['/profile']}><Profile /></MemoryRouter></AuthProvider>);
  expect((await screen.findByLabelText('画像摘要')).textContent).toContain('物理');
  expect(fetcher.mock.calls.some(([url]) => String(url).includes('/snapshot'))).toBe(false);
});

it('offers a new session when both recent session and profiles are absent', async () => {
  storeIdentity(); vi.stubGlobal('fetch', vi.fn((url: RequestInfo | URL) => Promise.resolve(response(String(url).endsWith('/workspace-state') ? { last_session_id: null } : { items: [], next_cursor: null }))));
  render(<AuthProvider><MemoryRouter initialEntries={['/profile']}><Profile /></MemoryRouter></AuthProvider>);
  expect((await screen.findByRole('link', { name: '新建学习会话' })).getAttribute('href')).toBe('/chat');
  expect(screen.queryByLabelText('画像摘要')).toBeNull();
});

it('opens an explicit profile absent from the first options page', async () => {
  storeIdentity(); const p1 = profile('p1', '物理'); const p2 = profile('p2', '化学');
  const summary = { profile_revision: 0, nodes: [], edges: [], recent_evidence: [], assessed_count: 0, total_count: 0, mastery_score: null, metric_kind: 'assessed_mean', assessment_coverage: null };
  vi.stubGlobal('fetch', vi.fn((url: RequestInfo | URL) => Promise.resolve(response(String(url).endsWith('/summary') ? summary : String(url).endsWith('/p2') ? { profile: p2, profile_revision: 0, nodes: [], edges: [] } : { items: [p1], next_cursor: 'next' }))));
  render(<AuthProvider><MemoryRouter initialEntries={['/profile?profile_id=p2']}><Profile /></MemoryRouter></AuthProvider>);
  expect((await screen.findByLabelText('画像摘要')).textContent).toContain('化学');
  expect((screen.getByLabelText('查看主题') as HTMLSelectElement).value).toBe('p2');
});

it('shows an explicit missing profile error and retries that profile without falling back', async () => {
  storeIdentity(); const p = profile('p1', '物理'); let attempts = 0;
  vi.stubGlobal('fetch', vi.fn((url: RequestInfo | URL) => { const path = String(url); if (path.includes('/missing')) { attempts++; return Promise.resolve(response({ detail: '画像不存在' }, 404)); } return Promise.resolve(response({ items: [p], next_cursor: null })); }));
  const { fireEvent } = await import('@testing-library/react');
  render(<AuthProvider><MemoryRouter initialEntries={['/profile?profile_id=missing']}><Profile /></MemoryRouter></AuthProvider>);
  expect((await screen.findByRole('alert')).textContent).toContain('画像不存在');
  expect(screen.queryByLabelText('画像摘要')).toBeNull(); const first = attempts;
  fireEvent.click(screen.getByRole('button', { name: '重试' }));
  await screen.findByRole('alert'); expect(attempts).toBeGreaterThan(first);
  expect(screen.queryByLabelText('画像摘要')).toBeNull();
});

it('retains loaded options and retries a failed next page', async () => {
  storeIdentity(); const p1 = profile('p1', '物理'); const p2 = profile('p2', '化学'); let failed = false;
  const summary = { profile_revision: 0, nodes: [], edges: [], recent_evidence: [], assessed_count: 0, total_count: 0, mastery_score: null, metric_kind: 'assessed_mean', assessment_coverage: null };
  vi.stubGlobal('fetch', vi.fn((url: RequestInfo | URL) => { const path = String(url); if (path.includes('cursor=next')) { if (!failed) { failed = true; return Promise.resolve(response({ detail: '列表不可用' }, 500)); } return Promise.resolve(response({ items: [p2], next_cursor: null })); } return Promise.resolve(response(path.endsWith('/summary') ? summary : path.endsWith('/p1') ? { profile: p1, profile_revision: 0, nodes: [], edges: [] } : { items: [p1], next_cursor: 'next' })); }));
  const { fireEvent } = await import('@testing-library/react'); render(<AuthProvider><MemoryRouter initialEntries={['/profile?profile_id=p1']}><Profile /></MemoryRouter></AuthProvider>);
  await screen.findByLabelText('画像摘要'); fireEvent.click(screen.getByRole('button', { name: '加载更多主题' }));
  expect((await screen.findByRole('alert')).textContent).toContain('列表不可用'); expect(screen.getByRole('option', { name: '物理' })).toBeTruthy();
  fireEvent.click(screen.getByRole('button', { name: '重试加载主题' })); expect(await screen.findByRole('option', { name: '化学' })).toBeTruthy();
});

it('ignores an old account error and finally while the new account is loading', async () => {
  storeIdentity(); const p = profile('p1', '物理'); const { deferred } = await import('../test/setup'); const { workspaceStore } = await import('../store/workspace');
  const old = deferred<Response>(); const current = deferred<Response>(); let listCalls = 0;
  vi.stubGlobal('fetch', vi.fn((url: RequestInfo | URL) => { const path = String(url); if (path.endsWith('/p1')) return old.promise; if (path.endsWith('/summary')) return Promise.resolve(response({ profile_revision: 0, nodes: [], edges: [], recent_evidence: [], assessed_count: 0, total_count: 0, mastery_score: null, metric_kind: 'assessed_mean', assessment_coverage: null })); listCalls++; return listCalls === 1 ? Promise.resolve(response({ items: [p], next_cursor: null })) : current.promise; }));
  const { act, waitFor } = await import('@testing-library/react'); render(<AuthProvider><MemoryRouter initialEntries={['/profile?profile_id=p1']}><Profile /></MemoryRouter></AuthProvider>);
  await screen.findByRole('option', { name: '物理' });
  await act(async () => { storeIdentity(2, 'B'); workspaceStore.startAccount(2, 'B'); });
  await waitFor(() => expect(listCalls).toBe(2));
  await act(async () => old.reject(new Error('旧账号错误')));
  expect(screen.queryByRole('alert')).toBeNull(); expect(screen.getByRole('status').textContent).toContain('正在读取');
  await act(async () => current.resolve(response({ items: [], next_cursor: null })));
});

it('retries an initial profile list failure without presenting it as an empty list', async () => {
  storeIdentity(); const p = profile('p1', '物理'); let calls = 0;
  const summary = { profile_revision: 0, nodes: [], edges: [], recent_evidence: [], assessed_count: 0, total_count: 0, mastery_score: null, metric_kind: 'assessed_mean', assessment_coverage: null };
  vi.stubGlobal('fetch', vi.fn((url: RequestInfo | URL) => { const path = String(url); if (path.endsWith('/summary')) return Promise.resolve(response(summary)); if (path.endsWith('/p1')) return Promise.resolve(response({ profile: p, profile_revision: 0, nodes: [], edges: [] })); calls++; return Promise.resolve(calls === 1 ? response({ detail: '列表读取失败' }, 500) : response({ items: [p], next_cursor: null })); }));
  const { fireEvent } = await import('@testing-library/react'); render(<AuthProvider><MemoryRouter initialEntries={['/profile?profile_id=p1']}><Profile /></MemoryRouter></AuthProvider>);
  expect((await screen.findByRole('alert')).textContent).toContain('列表读取失败'); expect(screen.queryByText(/暂无主题/)).toBeNull();
  fireEvent.click(screen.getByRole('button', { name: '重试' })); expect((await screen.findByLabelText('画像摘要')).textContent).toContain('物理');
});
