import React from 'react';
import {render,screen,fireEvent,waitFor} from '@testing-library/react';
import {test,expect,vi,beforeEach} from 'vitest';
import {AuthProvider} from '../src/context/AuthContext';
import {App} from '../src/App';
import {fetchApi} from '../src/api/client';
vi.mock('../src/api/client',()=>({fetchApi:vi.fn()}));
vi.mock('../src/components/Layout/WorkspaceSwitcher',()=>({WorkspaceSwitcher:()=>null}));
vi.mock('../src/components/Layout/InspectionBanner',()=>({InspectionBanner:()=>null}));
const api=vi.mocked(fetchApi);
beforeEach(()=>{api.mockReset();window.history.replaceState({},'', '/app/settings?tab=whatsapp');});
for(const action of ['save','verify rejection','verify failed response']) test(action+' invalidates verified bootstrap and locks business deep links',async()=>{
 let ready=true;
 api.mockImplementation(async(url:any,options:any)=>{
  if(url==='/api/auth/bootstrap/') return {user:{id:1,username:'owner',is_superuser:false,email_verified:true},tenant:{id:1,name:'Client',meta_setup_required:true,meta_setup_ready:ready},membership:{is_owner:true},capabilities:{dashboard:{allowed:true},inbox:{allowed:true},whatsapp_settings:{allowed:true}},user_tenants:[]} as any;
  if(options?.method==='POST'){ready=false;if(action==='verify rejection')throw {error:'Meta rejected credentials'};return {status:'error',provider_status:'FAILED',message:'Meta rejected credentials'} as any;}
  if(String(url).includes('/whatsapp/profile/'))return {profile:{},meta_info:{},vertical_choices:[]} as any;
  if(url==='/api/settings/whatsapp/')return {credentials_present:true,is_enabled:true,expected_number:'+919876543210'} as any;
  return {} as any;
 });
 render(<AuthProvider><App/></AuthProvider>);
 expect(await screen.findByRole('button',{name:'Overview'})).toBeInTheDocument();
 await screen.findByRole('heading',{name:'Meta Cloud API Credentials'});
 if(action==='save')fireEvent.submit(screen.getByLabelText('Meta App ID').closest('form')!);else fireEvent.click(screen.getByRole('button',{name:'Verify and Unlock'}));
 expect(await screen.findByRole('button',{name:'Meta Setup'})).toBeInTheDocument();
 expect(screen.queryByRole('button',{name:'Overview'})).not.toBeInTheDocument();
 window.history.pushState({},'', '/app/inbox');fireEvent.popState(window);
 await waitFor(()=>expect(window.location.pathname).toBe('/app/settings'));
 expect(api.mock.calls.some(([url])=>String(url).includes('/api/inbox/'))).toBe(false);
});
