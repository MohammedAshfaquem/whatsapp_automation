import {render,screen,fireEvent,waitFor} from '@testing-library/react';
import {expect,it,vi} from 'vitest';
import {PlatformTenantsPage} from '../src/pages/PlatformTenantsPage';
import {fetchApi} from '../src/api/client';
vi.mock('../src/api/client',()=>({fetchApi:vi.fn()}));
vi.mock('../src/context/AuthContext',()=>({useAuth:()=>({inspectTenant:vi.fn()})}));
it('pending clients expose a fresh full setup URL from the existing client list',async()=>{
 vi.mocked(fetchApi).mockImplementation(async(path)=>String(path).endsWith('/activation/')?{activation_url:'https://example.com/activate/setup-token/',owner_username:'client_owner'}:{tenants:[{id:7,name:'Pending Client',slug:'pending-client',owner_username:'client_owner',owner_email:'client@example.com',owner_activation_pending:true,is_active:true},{id:8,name:'Active Client',slug:'active-client',owner_activation_pending:false,is_active:true}]});
 render(<PlatformTenantsPage onNavigate={vi.fn()}/>);
 fireEvent.click(await screen.findByRole('button',{name:'Generate setup link'}));
 await screen.findByRole('dialog',{name:'Client Access & Activation'});
 expect(screen.getByDisplayValue('https://example.com/activate/setup-token/')).toBeTruthy();
 expect(fetchApi).toHaveBeenCalledWith('/api/platform/tenants/7/activation/',{method:'POST'});
 expect(screen.getByText(/It is not emailed automatically/)).toBeTruthy();
 fireEvent.click(screen.getByRole('button',{name:'Close Client Access & Activation'}));
 await waitFor(()=>expect(screen.queryByRole('dialog')).toBeNull());
});
