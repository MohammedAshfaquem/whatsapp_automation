import React from 'react';
import {render,screen,fireEvent,waitFor} from '@testing-library/react';
import {test,expect,vi,beforeEach} from 'vitest';
import {SettingsPage} from '../src/pages/SettingsPage';
import {PlatformTenantsPage} from '../src/pages/PlatformTenantsPage';
import {fetchApi} from '../src/api/client';
const reload=vi.hoisted(()=>vi.fn());
vi.mock('../src/context/AuthContext',()=>({useAuth:()=>({tenant:{meta_setup_required:true,meta_setup_ready:false,whatsapp_number:'+919876543210'},membership:{is_owner:true},reloadBootstrap:reload})}));
vi.mock('../src/api/client',()=>({fetchApi:vi.fn()}));
const api=vi.mocked(fetchApi);
beforeEach(()=>{vi.clearAllMocks();api.mockImplementation(async (url:any)=>url.includes('/verify/')?{status:'ok',provider_status:'VERIFIED',message:'Connected'}:url.includes('/tenants/')?{tenants:[]}:url.includes('/whatsapp/profile/')?{profile:{},meta_info:{},vertical_choices:[]}:url.includes('/whatsapp/')?{configured:false,credentials_present:true,is_enabled:true,expected_number:'+919876543210'}:{} as any);});
test('starts new clients with credentials and refreshes bootstrap only after actual provider verification',async()=>{
 render(<SettingsPage/>);expect(await screen.findByRole('heading',{name:'Meta Cloud API Credentials'})).toBeInTheDocument();
 expect(screen.getByLabelText('Business WhatsApp number *')).toHaveValue('+919876543210');
 fireEvent.click(screen.getByRole('button',{name:'Verify and Unlock'}));await waitFor(()=>expect(reload).toHaveBeenCalledTimes(1));
});
test('client provisioning requires a separate business WhatsApp number',async()=>{
 render(<PlatformTenantsPage onNavigate={()=>{}}/>);fireEvent.click(await screen.findByRole('button',{name:/Provision Client Workspace/}));
 const input=screen.getByLabelText('Business WhatsApp number *');expect(input).toBeRequired();
 fireEvent.change(screen.getByPlaceholderText('e.g. Apex Hospital or Horizon Retail'),{target:{value:'Example'}});fireEvent.click(screen.getByRole('button',{name:/Next Step/}));expect(screen.getByText(/valid business WhatsApp number/)).toBeInTheDocument();
});

test('provisioning posts business number separately from contact phone',async()=>{
 api.mockImplementation(async(url:any,options:any)=>options?.method==='POST'?{tenant:{name:'Example',owner_username:'owner'}}:{tenants:[]} as any);
 render(<PlatformTenantsPage onNavigate={()=>{}}/>);fireEvent.click(await screen.findByRole('button',{name:'Provision Client Workspace'}));fireEvent.change(screen.getByPlaceholderText('e.g. Apex Hospital or Horizon Retail'),{target:{value:'Example'}});fireEvent.change(screen.getByLabelText('Business WhatsApp number *'),{target:{value:'+919876543210'}});fireEvent.change(screen.getByPlaceholderText('+91 98765 43210'),{target:{value:'+919999999999'}});fireEvent.click(screen.getByRole('button',{name:/Next Step/}));fireEvent.change(screen.getByPlaceholderText('sarah@client.com'),{target:{value:'owner@example.com'}});fireEvent.click(screen.getByRole('button',{name:/Next Step/}));fireEvent.click(screen.getByRole('button',{name:/Next Step/}));fireEvent.click(screen.getByRole('button',{name:'Confirm & Provision Workspace'}));await waitFor(()=>expect(api).toHaveBeenCalledWith('/api/platform/tenants/',expect.objectContaining({method:'POST',body:expect.stringContaining('"whatsapp_number":"+919876543210"')})));const payload=JSON.parse(String(api.mock.calls.find(([,options])=>options?.method==='POST')?.[1]?.body));expect(payload.contact_phone).toBe('+919999999999');
});
