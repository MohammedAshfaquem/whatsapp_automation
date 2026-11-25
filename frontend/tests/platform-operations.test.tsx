import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { beforeEach, expect, test, vi } from 'vitest';
import { PlatformOperationsPage, ClientDiagnostics } from '../src/pages/PlatformOperationsPage';
import { fetchApi } from '../src/api/client';
vi.mock('../src/api/client', () => ({ fetchApi: vi.fn() }));
const api = vi.mocked(fetchApi);
beforeEach(() => api.mockReset());
test('shows delivery failure details and manual inspection guidance', async () => {
 api.mockImplementation(async url => String(url).includes('/deliveries/9/') ? { item: { id: 9,status:'UNKNOWN',attempts:5,last_error:'Provider timeout',tenant_name:'Acme' } } : { items:[{id:9,status:'UNKNOWN',attempts:5,tenant_name:'Acme'}],total:1,page:1,page_size:25 } as any);
 render(<ClientDiagnostics />);
 fireEvent.click(await screen.findByRole('button',{name:'Inspect 9'}));
 expect(await screen.findByText('Provider timeout')).toBeInTheDocument();
 expect(screen.getByText(/Manual inspection required/)).toBeInTheDocument();
 expect(screen.queryByRole('button',{name:/retry/i})).not.toBeInTheDocument();
});
test('applies client status and search filters without cross-client selectors',async()=>{
 api.mockResolvedValue({items:[],total:0,page:1,page_size:25});
 render(<ClientDiagnostics />);
 expect(screen.queryByLabelText('Tenant ID')).not.toBeInTheDocument();
 fireEvent.change(screen.getByLabelText('Status'),{target:{value:'FAILED'}});
 fireEvent.change(screen.getByLabelText('Search'),{target:{value:'alice'}});
 fireEvent.click(screen.getByRole('button',{name:'Apply filters'}));
 await waitFor(()=>expect(api).toHaveBeenLastCalledWith('/api/client/operations/deliveries/?tenant_id=&status=FAILED&q=alice&page=1'));
 fireEvent.click(screen.getByRole('tab',{name:'Webhooks'}));
 await waitFor(()=>expect(api).toHaveBeenLastCalledWith('/api/client/operations/webhooks/?tenant_id=&status=&q=alice&page=1'));
});
test('shows HTTP failures and refreshes',async()=>{
 api.mockRejectedValue({error:'Service unavailable'});
 render(<ClientDiagnostics />);
 expect(await screen.findByRole('alert')).toHaveTextContent('Service unavailable');
 api.mockResolvedValue({items:[],total:0,page:1,page_size:25});
 fireEvent.click(screen.getByRole('button',{name:'Refresh'}));
 expect(await screen.findByText('No records found.')).toBeInTheDocument();
});
test('edits user name and email through the supported platform endpoint',async()=>{
 api.mockResolvedValue({items:[{id:3,username:'alice',full_name:'Alice',email:'old@example.com'}],total:1,page:1,page_size:25});
 render(<PlatformOperationsPage />);
 fireEvent.click(screen.getByRole('tab',{name:'Users'}));
 fireEvent.click(await screen.findByRole('button',{name:'Edit user 3'}));
 fireEvent.change(screen.getByLabelText('Full name'),{target:{value:'Alice Smith'}});
 fireEvent.change(screen.getByLabelText('Email'),{target:{value:'alice@example.com'}});
 fireEvent.click(screen.getByRole('button',{name:'Save user'}));
 await waitFor(()=>expect(api).toHaveBeenCalledWith('/api/platform/operations/users/3/',{method:'PATCH',body:JSON.stringify({full_name:'Alice Smith',email:'alice@example.com'})}));
});
test('distinguishes exhausted attempts from a delivery with uncertain outcome',async()=>{
 api.mockImplementation(async url=>String(url).includes('/deliveries/4/')?{item:{id:4,status:'FAILED',attempts:3,last_error:'Provider rejected message',attempts_exhausted:true,max_attempts:3}}:{items:[{id:4,status:'FAILED',attempts:3}],total:1,page:1,page_size:25} as any);
 render(<ClientDiagnostics />);
 fireEvent.click(await screen.findByRole('button',{name:'Inspect 4'}));
 expect(await screen.findByText(/Attempts exhausted:/)).toBeInTheDocument();
 expect(screen.queryByText(/Manual inspection required:/)).not.toBeInTheDocument();
});
test('does not label a successful third attempt as exhausted',async()=>{
 api.mockImplementation(async url=>String(url).includes('/deliveries/4/')?{item:{id:4,status:'SENT',attempts:3,attempts_exhausted:true,max_attempts:3}}:{items:[{id:4,status:'SENT',attempts:3}],total:1,page:1,page_size:25} as any);
 render(<ClientDiagnostics />);
 fireEvent.click(await screen.findByRole('button',{name:'Inspect 4'}));
 await screen.findByRole('region',{name:'Delivery details'});
 expect(screen.queryByText(/Attempts exhausted:/)).not.toBeInTheDocument();
});
test('links records to their tenant workspace',async()=>{
 api.mockResolvedValue({items:[{id:4,tenant_id:12,tenant_name:'Acme',tenant_url:'/platform/tenants/12'}],total:1,page:1,page_size:25});
 render(<PlatformOperationsPage />);
 expect(await screen.findByRole('link',{name:'Acme'})).toHaveAttribute('href','/app/platform/tenants?tenant_id=12');
});
test('ignores delivery details returned after switching resources',async()=>{
 let resolveDetail:(value:any)=>void=()=>{};
 api.mockImplementation(async url=>String(url).includes('/deliveries/4/')?new Promise(resolve=>{resolveDetail=resolve;}):{items:[{id:4}],total:1,page:1,page_size:25} as any);
 render(<ClientDiagnostics />);
 fireEvent.click(await screen.findByRole('button',{name:'Inspect 4'}));
 fireEvent.click(screen.getByRole('tab',{name:'Webhooks'}));
 resolveDetail({item:{id:4,last_error:'Stale error'}});
 await waitFor(()=>expect(screen.queryByText('Loading operations...')).not.toBeInTheDocument());
 expect(screen.queryByText('Stale error')).not.toBeInTheDocument();
});


test('software user console exposes no WhatsApp or business resource tabs',async()=>{api.mockResolvedValue({items:[],total:0,page:1,page_size:25});render(<PlatformOperationsPage/>);expect(screen.getAllByRole('tab').map(el=>el.textContent)).toEqual(['Users']);await waitFor(()=>expect(api).toHaveBeenCalledWith(expect.stringContaining('/api/platform/operations/users/')));});
