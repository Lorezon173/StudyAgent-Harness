// @vitest-environment jsdom
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { expect, it, vi } from 'vitest';
import Knowledge from './Knowledge';
import { AuthProvider, useAuth } from '../store/auth';
import { deferred, response, storeIdentity } from '../test/setup';

it('searches private text and opens its full content', async () => {
  storeIdentity();
  const item = { id: 7, name: '学习笔记', description: '说明', content_text: '真实正文\n第二行', profile_id: null, user_id: 1, source_type: 'manual', created_at: '', updated_at: '' };
  vi.stubGlobal('fetch', vi.fn((url: RequestInfo | URL) => Promise.resolve(response(String(url).includes('topic-profiles') ? { items: [], next_cursor: null } : String(url).includes('/7') ? item : [item]))));
  render(<AuthProvider><Knowledge /></AuthProvider>);
  fireEvent.change(screen.getByRole('searchbox'), { target: { value: '笔记' } });
  fireEvent.click(screen.getByRole('button', { name: '搜索' }));
  await waitFor(() => expect(vi.mocked(fetch).mock.calls.some(([url]) => String(url).includes('q=%E7%AC%94%E8%AE%B0'))).toBe(true));
  fireEvent.click(await screen.findByRole('button', { name: '查看 学习笔记' }));
  expect(await screen.findByText(/真实正文/)).toBeTruthy();
});



it('keeps the form when creating fails and warns before an explicit retry', async () => {
  storeIdentity();
  vi.stubGlobal('fetch', vi.fn((url: RequestInfo | URL, init?: RequestInit) => {
    if (init?.method === 'POST') return Promise.reject(new TypeError('offline'));
    return Promise.resolve(response(String(url).includes('topic-profiles') ? { items: [], next_cursor: null } : []));
  }));
  render(<AuthProvider><Knowledge /></AuthProvider>);
  fireEvent.click(screen.getByRole('button', { name: '＋ 新建文本资料' }));
  fireEvent.change(screen.getByLabelText('名称'), { target: { value: '待保存笔记' } });
  fireEvent.change(screen.getByLabelText('正文'), { target: { value: '不能丢失的正文' } });
  fireEvent.click(screen.getByRole('button', { name: '保存' }));
  expect(await screen.findByText(/再次提交可能重复创建/)).toBeTruthy();
  expect((screen.getByLabelText('名称') as HTMLInputElement).value).toBe('待保存笔记');
  expect((screen.getByLabelText('正文') as HTMLTextAreaElement).value).toBe('不能丢失的正文');
});

it('does not repeat a confirmed create when the following detail read fails', async () => {
  storeIdentity(); let posts = 0;
  const item = { id: 7, name: '已保存', description: '', content_text: '正文', profile_id: null, user_id: 1, source_type: 'manual', created_at: '', updated_at: '' };
  vi.stubGlobal('fetch', vi.fn((url: RequestInfo | URL, init?: RequestInit) => {
    const path = String(url);
    if (init?.method === 'POST') { posts++; return Promise.resolve(response(item)); }
    if (path.includes('topic-profiles')) return Promise.resolve(response({ items: [], next_cursor: null }));
    if (path.endsWith('/7')) return Promise.resolve(response({ detail: '暂时不可读' }, 503));
    return Promise.resolve(response([]));
  }));
  render(<AuthProvider><Knowledge /></AuthProvider>);
  fireEvent.click(screen.getByRole('button', { name: '＋ 新建文本资料' }));
  fireEvent.change(screen.getByLabelText('名称'), { target: { value: '已保存' } });
  fireEvent.change(screen.getByLabelText('正文'), { target: { value: '正文' } });
  fireEvent.click(screen.getByRole('button', { name: '保存' }));
  expect(await screen.findByText(/已保存，刷新失败/)).toBeTruthy();
  fireEvent.click(screen.getByRole('button', { name: '重试读取' }));
  await waitFor(() => expect(screen.getByText(/已保存，刷新失败/)).toBeTruthy());
  expect(posts).toBe(1);
});

it('creates, edits, unlinks and deletes a real text resource', async () => {
  storeIdentity();
  const p = { id: 'p1', user_id: 1, name: '物理', scope_description: '', kind: 'manual', revision: 0, created_at: '', updated_at: '' };
  let item: { id: number; name: string; description: string; content_text: string; profile_id: string | null; user_id: number; source_type: string; created_at: string; updated_at: string } | null = null;
  vi.stubGlobal('fetch', vi.fn((url: RequestInfo | URL, init?: RequestInit) => {
    const path = String(url);
    if (path.includes('topic-profiles')) return Promise.resolve(response({ items: [p], next_cursor: null }));
    if (init?.method === 'POST') { item = { id: 7, ...JSON.parse(String(init.body)), user_id: 1, source_type: 'manual', created_at: '', updated_at: '' }; return Promise.resolve(response(item)); }
    if (init?.method === 'PATCH' && item) { item = { ...item, ...JSON.parse(String(init.body)) }; return Promise.resolve(response(item)); }
    if (init?.method === 'DELETE') { item = null; return Promise.resolve(response({ status: 'deleted' })); }
    return Promise.resolve(response(path.endsWith('/7') ? item : item ? [item] : []));
  }));
  render(<AuthProvider><Knowledge /></AuthProvider>);
  fireEvent.click(screen.getByRole('button', { name: '＋ 新建文本资料' }));
  fireEvent.change(screen.getByLabelText('名称'), { target: { value: '笔记' } });
  fireEvent.change(screen.getByLabelText('说明'), { target: { value: '旧说明' } });
  fireEvent.change(screen.getByLabelText('正文'), { target: { value: '真实正文' } });
  await screen.findByRole('option', { name: '物理' });
  fireEvent.change(screen.getByLabelText('关联主题'), { target: { value: 'p1' } });
  fireEvent.click(screen.getByRole('button', { name: '保存' }));
  expect(await screen.findByText('真实正文')).toBeTruthy();
  fireEvent.click(screen.getByRole('button', { name: '编辑' }));
  fireEvent.change(screen.getByLabelText('说明'), { target: { value: '' } });
  fireEvent.change(screen.getByLabelText('关联主题'), { target: { value: '' } });
  fireEvent.change(screen.getByLabelText('正文'), { target: { value: '新正文' } });
  fireEvent.click(screen.getByRole('button', { name: '保存' }));
  expect(await screen.findByText('新正文')).toBeTruthy();
  expect(item).toMatchObject({ description: '', profile_id: null, content_text: '新正文' });
  fireEvent.click(screen.getByRole('button', { name: '删除' }));
  fireEvent.click(screen.getByRole('button', { name: '确认删除' }));
  await waitFor(() => expect(screen.queryByRole('button', { name: '查看 笔记' })).toBeNull());
  expect(item).toBeNull();
});

it('marks list refresh failure separately after a confirmed create', async () => {
  storeIdentity(); let lists = 0;
  const item = { id: 7, name: '已保存', description: '', content_text: '正文', profile_id: null, user_id: 1, source_type: 'manual', created_at: '', updated_at: '' };
  vi.stubGlobal('fetch', vi.fn((url: RequestInfo | URL, init?: RequestInit) => {
    if (init?.method === 'POST') return Promise.resolve(response(item));
    if (String(url).includes('topic-profiles')) return Promise.resolve(response({ items: [], next_cursor: null }));
    if (String(url).endsWith('/7')) return Promise.resolve(response(item));
    return Promise.resolve(++lists === 1 ? response([]) : response({ detail: '网络错误' }, 503));
  }));
  render(<AuthProvider><Knowledge /></AuthProvider>);
  await waitFor(() => expect(lists).toBe(1));
  fireEvent.click(screen.getByRole('button', { name: '＋ 新建文本资料' }));
  fireEvent.change(screen.getByLabelText('名称'), { target: { value: '已保存' } });
  fireEvent.click(screen.getByRole('button', { name: '保存' }));
  expect(await screen.findByText(/已保存，列表刷新失败/)).toBeTruthy();
});


it('ignores an older search response after a newer query succeeds', async () => {
  storeIdentity(); const slow = deferred<Response>();
  const entry = (id: number, name: string) => ({ id, name, description: '', content_text: '', profile_id: null, user_id: 1, source_type: 'manual', created_at: '', updated_at: '' });
  vi.stubGlobal('fetch', vi.fn((url: RequestInfo | URL) => {
    const path = String(url);
    if (path.includes('q=old')) return slow.promise;
    if (path.includes('q=new')) return Promise.resolve(response([entry(2, '新查询结果')]));
    return Promise.resolve(response([]));
  }));
  render(<AuthProvider><Knowledge /></AuthProvider>);
  fireEvent.change(screen.getByRole('searchbox'), { target: { value: 'old' } });
  fireEvent.click(screen.getByRole('button', { name: '搜索' }));
  fireEvent.change(screen.getByRole('searchbox'), { target: { value: 'new' } });
  fireEvent.click(screen.getByRole('button', { name: '搜索' }));
  await screen.findByRole('button', { name: '查看 新查询结果' });
  await act(async () => { slow.resolve(response([entry(1, '旧查询结果')])); });
  await waitFor(() => expect(screen.queryByRole('button', { name: '查看 旧查询结果' })).toBeNull());
  expect(screen.getByRole('button', { name: '查看 新查询结果' })).toBeTruthy();
});

function AccountSwitch() { const auth = useAuth(); return <button onClick={() => auth.login(2, '用户2', 'B')}>切换账号</button>; }
it('does not expose old account data when a previous list arrives late', async () => {
  storeIdentity(); const slow = deferred<Response>(); let calls = 0;
  const entry = (id: number, name: string, user_id: number) => ({ id, name, description: '', content_text: '', profile_id: null, user_id, source_type: 'manual', created_at: '', updated_at: '' });
  vi.stubGlobal('fetch', vi.fn(() => ++calls === 1 ? slow.promise : Promise.resolve(response([entry(2, '乙的资料', 2)]))));
  render(<AuthProvider><AccountSwitch /><Knowledge /></AuthProvider>);
  fireEvent.click(screen.getByRole('button', { name: '切换账号' }));
  await screen.findByRole('button', { name: '查看 乙的资料' });
  await act(async () => { slow.resolve(response([entry(1, '甲的资料', 1)])); });
  await waitFor(() => expect(screen.queryByRole('button', { name: '查看 甲的资料' })).toBeNull());
  expect(screen.getByRole('button', { name: '查看 乙的资料' })).toBeTruthy();
});

it('paginates by the lowest id and restarts at the first page for a new search', async () => {
  storeIdentity();
  const entry = (id: number) => ({ id, name: `笔记${id}`, description: '', content_text: '', profile_id: null, user_id: 1, source_type: 'manual', created_at: '', updated_at: '' });
  const urls: string[] = [];
  vi.stubGlobal('fetch', vi.fn((url: RequestInfo | URL) => {
    const path = String(url); urls.push(path);
    return Promise.resolve(response(path.includes('before_id=51') ? [entry(50)] : path.includes('q=new') ? [entry(2)] : Array.from({ length: 50 }, (_, i) => entry(100 - i))));
  }));
  render(<AuthProvider><Knowledge /></AuthProvider>);
  fireEvent.click(await screen.findByRole('button', { name: '加载更多' }));
  await screen.findByRole('button', { name: '查看 笔记50' });
  fireEvent.change(screen.getByRole('searchbox'), { target: { value: 'new' } });
  fireEvent.click(screen.getByRole('button', { name: '搜索' }));
  await screen.findByRole('button', { name: '查看 笔记2' });
  expect(screen.queryByRole('button', { name: '查看 笔记100' })).toBeNull();
  expect(urls.some(url => url.includes('before_id=51'))).toBe(true);
  expect(urls.find(url => url.includes('q=new'))).not.toContain('before_id');
});

it('does not put a late detail response into a newly opened dialog', async () => {
  storeIdentity(); const slow = deferred<Response>();
  const entry = (id: number) => ({ id, name: `笔记${id}`, description: '', content_text: `正文${id}`, profile_id: null, user_id: 1, source_type: 'manual', created_at: '', updated_at: '' });
  vi.stubGlobal('fetch', vi.fn((url: RequestInfo | URL) => {
    const path = String(url);
    if (path.includes('topic-profiles')) return Promise.resolve(response({ items: [], next_cursor: null }));
    if (path.endsWith('/1')) return slow.promise;
    if (path.endsWith('/2')) return Promise.resolve(response(entry(2)));
    return Promise.resolve(response([entry(1), entry(2)]));
  }));
  render(<AuthProvider><Knowledge /></AuthProvider>);
  fireEvent.click(await screen.findByRole('button', { name: '查看 笔记1' }));
  fireEvent.click(screen.getByRole('button', { name: '关闭' }));
  fireEvent.click(screen.getByRole('button', { name: '查看 笔记2' }));
  await screen.findByText('正文2');
  await act(async () => { slow.resolve(response(entry(1))); });
  await waitFor(() => expect(screen.queryByText('正文1')).toBeNull());
  expect(screen.getByText('正文2')).toBeTruthy();
});

it('rejects oversized input instead of truncating it or sending it', async () => {
  storeIdentity(); let posts = 0;
  vi.stubGlobal('fetch', vi.fn((url: RequestInfo | URL, init?: RequestInit) => {
    if (init?.method === 'POST') posts++;
    return Promise.resolve(response(String(url).includes('topic-profiles') ? { items: [], next_cursor: null } : []));
  }));
  render(<AuthProvider><Knowledge /></AuthProvider>);
  fireEvent.click(screen.getByRole('button', { name: '＋ 新建文本资料' }));
  fireEvent.change(screen.getByLabelText('名称'), { target: { value: '笔记' } });
  fireEvent.change(screen.getByLabelText('正文'), { target: { value: '长'.repeat(100001) } });
  fireEvent.click(screen.getByRole('button', { name: '保存' }));
  expect(screen.getByRole('alert').textContent).toContain('正文最多100000字');
  expect((screen.getByLabelText('正文') as HTMLTextAreaElement).value).toHaveLength(100001);
  expect(posts).toBe(0);
});


it('does not close or unlock a new form when an earlier closed form finishes saving', async () => {
  storeIdentity(); const first = deferred<Response>(); const second = deferred<Response>(); let writes = 0;
  const entry = (id: number, name: string) => ({ id, name, description: '', content_text: '', profile_id: null, user_id: 1, source_type: 'manual', created_at: '', updated_at: '' });
  vi.stubGlobal('fetch', vi.fn((url: RequestInfo | URL, init?: RequestInit) => {
    if (init?.method === 'POST') return ++writes === 1 ? first.promise : second.promise;
    if (String(url).includes('topic-profiles')) return Promise.resolve(response({ items: [], next_cursor: null }));
    return Promise.resolve(response([]));
  }));
  render(<AuthProvider><Knowledge /></AuthProvider>);
  fireEvent.click(screen.getByRole('button', { name: '＋ 新建文本资料' }));
  fireEvent.change(screen.getByLabelText('名称'), { target: { value: '第一个' } });
  fireEvent.click(screen.getByRole('button', { name: '保存' }));
  fireEvent.click(screen.getByRole('button', { name: '关闭' }));
  fireEvent.click(screen.getByRole('button', { name: '＋ 新建文本资料' }));
  fireEvent.change(screen.getByLabelText('名称'), { target: { value: '第二个' } });
  fireEvent.click(screen.getByRole('button', { name: '保存' }));
  await act(async () => { first.resolve(response(entry(1, '第一个'))); });
  expect((screen.getByLabelText('名称') as HTMLInputElement).value).toBe('第二个');
  expect((screen.getByRole('button', { name: '保存' }) as HTMLButtonElement).disabled).toBe(true);
  fireEvent.submit(screen.getByLabelText('名称').closest('form')!);
  expect(writes).toBe(2);
  await act(async () => { second.resolve(response(entry(2, '第二个'))); });
});

it('opens an accessible dialog, focuses its name, and returns focus on Escape', async () => {
  storeIdentity();
  vi.stubGlobal('fetch', vi.fn((url: RequestInfo | URL) => Promise.resolve(response(String(url).includes('topic-profiles') ? { items: [], next_cursor: null } : []))));
  render(<AuthProvider><Knowledge /></AuthProvider>);
  const trigger = screen.getByRole('button', { name: '＋ 新建文本资料' });
  trigger.focus(); fireEvent.click(trigger);
  const dialog = screen.getByRole('dialog', { name: '新建文本资料' });
  expect(document.activeElement).toBe(screen.getByLabelText('名称'));
  fireEvent(dialog, new Event("cancel", { bubbles: false, cancelable: true }));
  await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
  expect(document.activeElement).toBe(trigger);
});

it('rejects an empty name and an overlong search without a request', async () => {
  storeIdentity(); let calls = 0;
  vi.stubGlobal('fetch', vi.fn((url: RequestInfo | URL, init?: RequestInit) => {
    if (!String(url).includes('topic-profiles') || init?.method === 'POST') calls++;
    return Promise.resolve(response(String(url).includes('topic-profiles') ? { items: [], next_cursor: null } : []));
  }));
  render(<AuthProvider><Knowledge /></AuthProvider>);
  await waitFor(() => expect(calls).toBe(1));
  fireEvent.change(screen.getByRole('searchbox'), { target: { value: 'a'.repeat(257) } });
  fireEvent.click(screen.getByRole('button', { name: '搜索' }));
  expect(screen.getByRole('alert').textContent).toContain('256');
  fireEvent.click(screen.getByRole('button', { name: '＋ 新建文本资料' }));
  fireEvent.change(screen.getByLabelText('名称'), { target: { value: '   ' } });
  fireEvent.click(screen.getByRole('button', { name: '保存' }));
  expect(screen.getAllByRole('alert').some(el => el.textContent?.includes('请填写名称'))).toBe(true);
  expect(calls).toBe(1);
});


it('deduplicates overlapping records when a later page contains repeated ids', async () => {
  storeIdentity();
  const entry = (id: number) => ({ id, name: `资料${id}`, description: '', content_text: '', profile_id: null, user_id: 1, source_type: 'manual', created_at: '', updated_at: '' });
  vi.stubGlobal('fetch', vi.fn((url: RequestInfo | URL) => Promise.resolve(response(String(url).includes('before_id') ? [entry(50), entry(50), entry(51)] : Array.from({ length: 50 }, (_, i) => entry(100 - i))))));
  render(<AuthProvider><Knowledge /></AuthProvider>);
  fireEvent.click(await screen.findByRole('button', { name: '加载更多' }));
  await screen.findByRole('button', { name: '查看 资料50' });
  expect(screen.getAllByRole('button', { name: '查看 资料50' })).toHaveLength(1);
  expect(screen.getAllByRole('button', { name: '查看 资料51' })).toHaveLength(1);
});

it('retains prior search results when a new search fails and retries the new search', async () => {
  storeIdentity(); let searched = 0;
  const item = { id: 1, name: '原结果', description: '', content_text: '', profile_id: null, user_id: 1, source_type: 'manual', created_at: '', updated_at: '' };
  vi.stubGlobal('fetch', vi.fn((url: RequestInfo | URL) => {
    if (String(url).includes('q=retry')) return Promise.resolve(++searched === 1 ? response({ detail: '网络错误' }, 503) : response([]));
    return Promise.resolve(response([item]));
  }));
  render(<AuthProvider><Knowledge /></AuthProvider>);
  await screen.findByRole('button', { name: '查看 原结果' });
  fireEvent.change(screen.getByRole('searchbox'), { target: { value: 'retry' } });
  fireEvent.click(screen.getByRole('button', { name: '搜索' }));
  await screen.findByRole('alert');
  expect(screen.getByText('仍显示上次结果')).toBeTruthy();
  expect(screen.getByRole('button', { name: '查看 原结果' })).toBeTruthy();
  fireEvent.click(screen.getByRole('button', { name: '重试加载' }));
  await screen.findByText('暂无文本资料');
  expect(searched).toBe(2);
});

it('offers profile pagination without losing the entered text', async () => {
  storeIdentity();
  const p = (id: string) => ({ id, user_id: 1, name: `主题${id}`, scope_description: '', kind: 'manual', revision: 0, created_at: '', updated_at: '' });
  vi.stubGlobal('fetch', vi.fn((url: RequestInfo | URL) => {
    const path = String(url);
    return Promise.resolve(response(path.includes('topic-profiles') ? path.includes('cursor=next') ? { items: [p('later')], next_cursor: null } : { items: [p('first')], next_cursor: 'next' } : []));
  }));
  render(<AuthProvider><Knowledge /></AuthProvider>);
  fireEvent.click(screen.getByRole('button', { name: '＋ 新建文本资料' }));
  fireEvent.change(screen.getByLabelText('正文'), { target: { value: '保留这段文字' } });
  fireEvent.click(await screen.findByRole('button', { name: '加载更多主题' }));
  await screen.findByRole('option', { name: '主题later' });
  expect((screen.getByLabelText('正文') as HTMLTextAreaElement).value).toBe('保留这段文字');
});

it('keeps failed search retry intact until the new result can be paginated', async () => {
  storeIdentity();
  const urls: string[] = [];
  let bAttempts = 0;
  const entry = (id: number, name: string) => ({ id, name, description: '', content_text: '', profile_id: null, user_id: 1, source_type: 'manual', created_at: '', updated_at: '' });
  vi.stubGlobal('fetch', vi.fn((url: RequestInfo | URL) => {
    const path = String(url); urls.push(path);
    const params = new URL(path, 'http://localhost').searchParams;
    if (params.get('q') === 'B') {
      if (params.has('before_id')) return Promise.resolve(response([entry(150, 'B续页')]));
      if (++bAttempts === 1) return Promise.resolve(response({ detail: 'B 搜索失败' }, 503));
      return Promise.resolve(response(Array.from({ length: 50 }, (_, i) => entry(200 - i, `B结果${200 - i}`))));
    }
    if (params.has('before_id')) return Promise.resolve(response([entry(50, 'A续页')]));
    return Promise.resolve(response(Array.from({ length: 50 }, (_, i) => entry(100 - i, `A结果${100 - i}`))));
  }));
  render(<AuthProvider><Knowledge /></AuthProvider>);
  await screen.findByRole('button', { name: '查看 A结果100' });
  fireEvent.change(screen.getByRole('searchbox'), { target: { value: 'B' } });
  fireEvent.click(screen.getByRole('button', { name: '搜索' }));
  expect((await screen.findByRole('alert')).textContent).toContain('B 搜索失败');
  const more = screen.getByRole('button', { name: '加载更多' }) as HTMLButtonElement;
  expect(more.disabled).toBe(true);
  fireEvent.click(more);
  expect(screen.getByText('仍显示上次结果')).toBeTruthy();
  expect(screen.getByRole('alert').textContent).toContain('B 搜索失败');
  expect(urls.some(path => path.includes('before_id'))).toBe(false);
  fireEvent.click(screen.getByRole('button', { name: '重试加载' }));
  await screen.findByRole('button', { name: '查看 B结果200' });
  expect(screen.queryByText('仍显示上次结果')).toBeNull();
  expect(screen.queryByRole('button', { name: '查看 A结果100' })).toBeNull();
  fireEvent.click(screen.getByRole('button', { name: '加载更多' }));
  await screen.findByRole('button', { name: '查看 B续页' });
  expect(urls.some(path => path.includes('q=B') && path.includes('before_id=151'))).toBe(true);
});

