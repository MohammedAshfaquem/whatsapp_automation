import React from 'react';
import {render,screen,fireEvent,waitFor} from '@testing-library/react';
import {beforeEach,expect,test,vi} from 'vitest';
import {WorkspaceToolsPage} from '../src/pages/WorkspaceToolsPage';
import {fetchApi} from '../src/api/client';
vi.mock('../src/api/client',()=>({fetchApi:vi.fn()}));
beforeEach(()=>vi.mocked(fetchApi).mockReset());
test('saved replies submit to the real application API and respect management response',async()=>{
 vi.mocked(fetchApi).mockResolvedValue({results:[],can_manage:true});
 render(<WorkspaceToolsPage resource="replies"/>);
 fireEvent.change(await screen.findByLabelText('Title'),{target:{value:'Greeting'}});
 fireEvent.change(screen.getByLabelText('Reply text'),{target:{value:'Hello'}});
 fireEvent.click(screen.getByRole('button',{name:'Add saved reply'}));
 await waitFor(()=>expect(fetchApi).toHaveBeenCalledWith('/api/workspace/tools/replies/',{method:'POST',body:JSON.stringify({title:'Greeting',body:'Hello'})}));
});
test('staff can read replies without management controls',async()=>{
 vi.mocked(fetchApi).mockResolvedValue({results:[{id:1,title:'Greeting',body:'Hello'}],can_manage:false});
 render(<WorkspaceToolsPage resource="replies"/>);
 expect(await screen.findByText('Greeting')).toBeInTheDocument();
 expect(screen.queryByRole('button',{name:'Delete'})).not.toBeInTheDocument();
 expect(screen.queryByLabelText('Title')).not.toBeInTheDocument();
});
test('email queue distinguishes accepted from delivered and refuses uncertain retry controls',async()=>{
 vi.mocked(fetchApi).mockResolvedValue({results:[{id:'job',recipient:'client@example.com',status:'UNKNOWN',attempts:1,purpose:'ACTIVATION'}],smtp_ready:false,count:1});
 render(<WorkspaceToolsPage platform resource="emails"/>);
 expect(await screen.findByText('UNKNOWN')).toBeInTheDocument();
 expect(screen.queryByRole('button',{name:'Retry failed email'})).not.toBeInTheDocument();
 expect(screen.getByText(/ACCEPTED means/)).toBeInTheDocument();
});
test('SMTP password uses visibility control and starts empty',async()=>{
 vi.mocked(fetchApi).mockResolvedValue({enabled:false,host:'',port:587,username:'',from_email:'',security:'TLS',password_present:true});
 render(<WorkspaceToolsPage platform resource="smtp"/>);
 const input=await screen.findByLabelText('Replace password (leave blank to retain)');
 expect(input).toHaveValue('');expect(input).toHaveAttribute('type','password');expect(input).toHaveAttribute('autocomplete','new-password');
 fireEvent.click(screen.getByRole('button',{name:'Show password'}));expect(input).toHaveAttribute('type','text');
});

test('manual billing accepts decimal amounts in the real form',async()=>{
 vi.mocked(fetchApi).mockResolvedValue({results:[],clients:[],count:0});
 render(<WorkspaceToolsPage platform resource="billing"/>);
 expect(await screen.findByLabelText('Amount')).toHaveAttribute('step','0.01');
});
