import React from 'react';
import {render,screen,fireEvent,waitFor} from '@testing-library/react';
import {beforeEach,expect,test,vi} from 'vitest';
import {ClientImageUpload} from '../src/components/settings/ClientImageUpload';
import {fetchApi} from '../src/api/client';
vi.mock('../src/context/AuthContext',()=>({useAuth:()=>({tenant:null,reloadBootstrap:vi.fn()})}));
vi.mock('../src/api/client',()=>({fetchApi:vi.fn()}));
beforeEach(()=>vi.clearAllMocks());
test('uploads the actual selected file and shows confirmed provider success',async()=>{
 vi.mocked(fetchApi).mockResolvedValueOnce({configured:true,url:''}).mockResolvedValueOnce({url:'https://images.example/photo.png',message:'Photo updated on Meta',meta_synced:true});
 render(<ClientImageUpload kind="whatsapp_profile" label="WhatsApp profile photo"/>);
 const file=new File(['image bytes'],'logo.png',{type:'image/png'});
 fireEvent.change(await screen.findByLabelText('WhatsApp profile photo'),{target:{files:[file]}});
 fireEvent.click(screen.getByRole('button',{name:'Update WhatsApp photo'}));
 expect(await screen.findByRole('status')).toHaveTextContent('Photo updated on Meta');
 const body=vi.mocked(fetchApi).mock.calls[1][1]?.body as FormData;
 expect(body.get('file')).toBe(file);expect(body.get('kind')).toBe('whatsapp_profile');
});
test('does not claim success on provider rejection',async()=>{
 vi.mocked(fetchApi).mockResolvedValueOnce({configured:true,url:''}).mockRejectedValueOnce({error:'Meta rejected the image'});
 render(<ClientImageUpload kind="whatsapp_profile" label="WhatsApp profile photo"/>);
 fireEvent.change(await screen.findByLabelText('WhatsApp profile photo'),{target:{files:[new File(['x'],'photo.png',{type:'image/png'})]}});
 fireEvent.click(screen.getByRole('button',{name:'Update WhatsApp photo'}));
 expect(await screen.findByRole('alert')).toHaveTextContent('Meta rejected');expect(screen.queryByRole('status')).toBeNull();
});
import {SettingsPage} from '../src/pages/SettingsPage';
test('client Meta settings submit app identity without echoing the saved app secret',async()=>{
 vi.mocked(fetchApi).mockImplementation(async(path:any,options:any)=>{
  if(options?.method==='POST')return {status:'saved'};
  if(path==='/api/settings/workspace/')return {name:'Client',logo_url:'',timezone:'Asia/Kolkata'};
  if(path==='/api/settings/whatsapp/')return {phone_number_id:'12345',app_id:'123',app_secret_present:true,is_enabled:true};
  if(String(path).includes('/media/'))return {configured:true,url:''};
  return {profile:{},meta_info:{},vertical_choices:[]};
 });
 render(<SettingsPage/>);
 fireEvent.click(await screen.findByRole('button',{name:'Meta API & Connection'}));
 fireEvent.change(screen.getByLabelText('Meta App ID'),{target:{value:'999'}});
 fireEvent.change(screen.getByLabelText('Meta App Secret'),{target:{value:'new-secret'}});
 fireEvent.click(screen.getByRole('checkbox',{name:'Enable WhatsApp messaging for this workspace'}));
 fireEvent.submit(screen.getByLabelText('Meta App ID').closest('form')!);
 await waitFor(()=>expect(vi.mocked(fetchApi).mock.calls.some(([path,options])=>path==='/api/settings/whatsapp/'&&options?.method==='POST'&&JSON.parse(String(options.body)).app_id==='999'&&JSON.parse(String(options.body)).is_enabled===false)).toBe(true));
});
