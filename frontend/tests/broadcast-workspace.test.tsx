import {cleanup,fireEvent,render,screen,waitFor} from '@testing-library/react';
import {afterEach,beforeEach,expect,it,vi} from 'vitest';
import {GrowthPage} from '../src/pages/GrowthPage';
import {fetchApi} from '../src/api/client';
vi.mock('../src/api/client',()=>({fetchApi:vi.fn()}));
const templates=[{id:1,name:'order_update',language:'en',category:'UTILITY',body_text:'Order {{1}} ready',variables:['Order'],meta_status:'APPROVED'},{id:2,name:'draft_offer',language:'en',category:'MARKETING',body_text:'Offer',variables:[],meta_status:'DRAFT'}];
const campaign={id:7,name:'Orders',status:'DRAFT',template_name:'order_update',audience_count:2};
beforeEach(()=>vi.mocked(fetchApi).mockImplementation(async(url)=>String(url)==='/api/crm/campaigns/7/'?{campaign,eligible_now:2,recipients:[]}:{campaigns:[campaign],templates}));
afterEach(()=>{cleanup();vi.clearAllMocks();});
it('uses real draft component, disables unapproved templates and posts rendered inputs',async()=>{
 render(<GrowthPage/>);await screen.findByText('Orders');fireEvent.click(screen.getByRole('button',{name:'New broadcast'}));
 fireEvent.change(screen.getByLabelText('Campaign name'),{target:{value:'Order reminders'}});
 expect((screen.getByRole('option',{name:/draft_offer/}) as HTMLOptionElement).disabled).toBe(true);
 fireEvent.change(screen.getByLabelText('Campaign template'),{target:{value:'1'}});
 fireEvent.change(screen.getByLabelText('Variable 1'),{target:{value:'AB12'}});
 expect(screen.getByText('Order AB12 ready')).toBeTruthy();fireEvent.click(screen.getByRole('button',{name:'Save draft'}));
 await waitFor(()=>expect(fetchApi).toHaveBeenCalledWith('/api/crm/campaigns/',expect.objectContaining({method:'POST',body:JSON.stringify({name:'Order reminders',template_id:'1',template_parameters:['AB12'],target_lifecycle_status:''})})));
});
it('launch requires audience review and explicit confirmation; opening it sends nothing',async()=>{
 render(<GrowthPage/>);fireEvent.click(await screen.findByRole('button',{name:'Review & launch'}));await screen.findByRole('dialog');
 expect(screen.getByRole('button',{name:'Launch broadcast now'})).toBeDisabled();expect(vi.mocked(fetchApi).mock.calls.filter(c=>c[1]?.method==='POST')).toHaveLength(0);
 fireEvent.click(screen.getByRole('checkbox'));fireEvent.click(screen.getByRole('button',{name:'Launch broadcast now'}));
 await waitFor(()=>expect(fetchApi).toHaveBeenCalledWith('/api/crm/campaigns/7/',expect.objectContaining({body:JSON.stringify({action:'launch',confirm_send:true,scheduled_at:null})})));
});
it('creates a local template through the application API and closes with Escape without submitting',async()=>{
 render(<GrowthPage/>);await screen.findByText('Orders');fireEvent.click(screen.getByRole('button',{name:'Templates'}));fireEvent.click(screen.getByRole('button',{name:'New template'}));
 fireEvent.change(screen.getByLabelText('Template name'),{target:{value:'delivery_update'}});fireEvent.change(screen.getByLabelText('Template body'),{target:{value:'Your order is ready'}});fireEvent.click(screen.getByRole('button',{name:'Save template draft'}));
 await waitFor(()=>expect(fetchApi).toHaveBeenCalledWith('/api/whatsapp/templates/manage/',expect.objectContaining({method:'POST',body:JSON.stringify({name:'delivery_update',category:'UTILITY',language:'en',body_text:'Your order is ready'})})));
 await waitFor(()=>expect(screen.queryByRole('dialog')).toBeNull());fireEvent.click(screen.getByRole('button',{name:'New template'}));const calls=vi.mocked(fetchApi).mock.calls.length;fireEvent.keyDown(document,{key:'Escape'});expect(screen.queryByRole('dialog')).toBeNull();expect(fetchApi).toHaveBeenCalledTimes(calls);
});
