// @vitest-environment jsdom
import { act, fireEvent, render, screen } from '@testing-library/react';
import { expect, it, vi } from 'vitest';
import { MemoryRouter } from 'react-router-dom';
import { useState } from 'react';
import Login from './pages/Login';
import Dialog from './components/workspace/NewSessionDialog';
import { AuthProvider } from './store/auth';
import { apiGet } from './api/client';
import { deferred, response, profile, session, storeIdentity } from './test/setup';
it('review login generation reset releases busy', async () => {
 storeIdentity(); const login = deferred<Response>(); const old = deferred<Response>();
 const fetcher = vi.fn((url: string) => url === '/api/auth/login' ? login.promise : old.promise); vi.stubGlobal('fetch', fetcher);
 render(<AuthProvider><MemoryRouter><Login /></MemoryRouter></AuthProvider>);
 const protectedCall = apiGet('/api/sessions').catch(()=>{});
 fireEvent.change(screen.getByPlaceholderText('用户名'), {target:{value:'B'}}); fireEvent.change(screen.getByPlaceholderText('密码'),{target:{value:'password'}});
 fireEvent.submit(screen.getByPlaceholderText('用户名').closest('form')!);
 await act(async()=>{old.resolve(response({detail:'expired'},401)); await protectedCall;});
 await act(async()=>{login.resolve(response({user_id:2,username:'B',token:'B'}));});
 expect(screen.queryByRole('button',{name:'提交中…'})).toBeNull();
});
it('review same-account close rejects a late profile result', async()=>{
 storeIdentity(); const pending = deferred<Response>(); const created = vi.fn(); let posts = 0;
 vi.stubGlobal('fetch',vi.fn((url:string,init?:RequestInit)=> {if(init?.method === 'POST'){posts++; return url === '/api/topic-profiles' ? pending.promise : Promise.resolve(response(session('late','new')));}return Promise.resolve(response({items:[profile()],next_cursor:null}));}));
 function Host(){const [open,setOpen]=useState(true);return <Dialog open={open} onClose={()=>setOpen(false)} onCreated={created}/>;}
 render(<AuthProvider><MemoryRouter><Host/></MemoryRouter></AuthProvider>);
 await screen.findByRole('option',{name:'概率论'});
 fireEvent.change(screen.getByLabelText('所属主题画像'),{target:{value:'__new'}});fireEvent.change(screen.getByLabelText('新主题名称'),{target:{value:'new'}});fireEvent.submit(screen.getByRole('form',{name:'新建会话'}));
 fireEvent.click(screen.getByRole('button',{name:'关闭'}));
 await act(async()=>{pending.resolve(response({profile:profile('new'),profile_revision:0,nodes:[],edges:[]}));});
 expect(posts).toBe(1);expect(created).not.toHaveBeenCalled();
});
