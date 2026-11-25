import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import { beforeEach, expect, test, vi } from 'vitest';
import { App } from '../src/App';
import { fetchApi } from '../src/api/client';
const state=vi.hoisted(()=>({user:{id:1,username:'alice',is_superuser:false},tenant:null as any,isInspecting:false,capabilities:{},isLoading:false,error:null}));
vi.mock('../src/context/AuthContext',()=>({useAuth:()=>state}));
vi.mock('../src/components/Layout/WorkspaceSwitcher',()=>({WorkspaceSwitcher:()=>null}));
vi.mock('../src/components/Layout/InspectionBanner',()=>({InspectionBanner:()=>null}));
vi.mock('../src/pages/PlatformDashboardPage',()=>({PlatformDashboardPage:()=> <h1>Platform home</h1>}));
vi.mock('../src/api/client',()=>({fetchApi:vi.fn(async()=>({items:[],total:0,page:1,page_size:25}))}));
beforeEach(()=>{vi.mocked(fetchApi).mockClear();state.user.is_superuser=false;state.isInspecting=false;state.tenant=null;});
test('denies client deep links and hides platform navigation',()=>{
 window.history.replaceState({},'', '/app/platform/operations');
 render(<App />);
 expect(screen.getByText('Platform access denied')).toBeInTheDocument();
 expect(screen.queryByRole('button',{name:'WhatsApp Operations'})).not.toBeInTheDocument();
});
test('redirects platform operator out of client routes',async()=>{
 state.user.is_superuser=true;
 window.history.replaceState({},'', '/app/inbox');
 render(<App />);
 await waitFor(()=>expect(window.location.pathname).toBe('/app/platform/dashboard'));
 expect(screen.getByRole('button',{name:'Users'})).toBeInTheDocument();
 expect(screen.queryByRole('link',{name:'Django Admin'})).not.toBeInTheDocument();
});
test('exposes My Account to clients and allows operators to open it',async()=>{
 window.history.replaceState({},'', '/app/account');
 const view=render(<App />);
 expect(screen.getByRole('button',{name:'My Account'})).toBeInTheDocument();
 expect(screen.getByRole('heading',{name:'Your account'})).toBeInTheDocument();
 view.unmount();
 state.user.is_superuser=true;
 render(<App />);
 expect(screen.getByRole('heading',{name:'Your account'})).toBeInTheDocument();
 expect(window.location.pathname).toBe('/app/account');
});

test('groups daily work under collapsible menus',()=>{
 state.capabilities=Object.fromEntries(['dashboard','inbox','contacts','companies','deals','tasks','work_queue','whatsapp_settings','bookings','services','knowledge','team','reports'].map(key=>[key,{allowed:true}])) as any;
 window.history.replaceState({},'', '/app/account');render(<App />);
 for(const name of ['WhatsApp','CRM','Business','Administration']) expect(screen.getByText(name).closest('details')).toBeInTheDocument();
});
test('setup-first client deep links cannot mount business pages',async()=>{
 state.tenant={id:1,name:'New client',meta_setup_required:true,meta_setup_ready:false};window.history.replaceState({},'', '/app/inbox');render(<App />);
 await waitFor(()=>expect(window.location.pathname).toBe('/app/settings'));
 expect(vi.mocked(fetchApi).mock.calls.some(([url])=>String(url).includes('/api/inbox/'))).toBe(false);
 expect(screen.getByRole('button',{name:'Meta Setup'})).toBeInTheDocument();expect(screen.queryByRole('button',{name:'Overview'})).not.toBeInTheDocument();expect(screen.queryByRole('button',{name:'Contacts'})).not.toBeInTheDocument();
});

test('unlocks client navigation after verified bootstrap and keeps legacy clients open',()=>{
 state.capabilities={dashboard:{allowed:true}} as any;state.tenant={meta_setup_required:true,meta_setup_ready:false};window.history.replaceState({},'', '/app/account');const view=render(<App/>);expect(screen.queryByRole('button',{name:'Overview'})).not.toBeInTheDocument();state.tenant={meta_setup_required:true,meta_setup_ready:true};view.rerender(<App/>);expect(screen.getByRole('button',{name:'Overview'})).toBeInTheDocument();state.tenant={id:1};view.rerender(<App/>);expect(screen.getByRole('button',{name:'Overview'})).toBeInTheDocument();
});
