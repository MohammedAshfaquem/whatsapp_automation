import React from 'react';
import {act,render,screen,fireEvent,cleanup} from '@testing-library/react';
import {beforeEach,afterEach,test,expect,vi} from 'vitest';
import {HelpSupportPage} from '../src/pages/HelpSupportPage';
import {PlatformSupportPage} from '../src/pages/PlatformSupportPage';
import {fetchApi} from '../src/api/client';
vi.mock('../src/api/client',()=>({fetchApi:vi.fn()}));
const ticket=(id='a')=>({id,ticket_number:'SUP-'+id,subject:'Issue '+id,tenant_name:'Client',status:'OPEN',status_display:'Open',priority:'NORMAL',priority_display:'Normal',category_display:'Help',assigned_to:null,created_at:'2026-11-25T12:00:00Z',updated_at:'2026-11-25T12:00:00Z'});
let body='Original message';
let pending:Promise<any>|null=null;
let fail=false;
beforeEach(()=>{
 vi.useFakeTimers();vi.mocked(fetchApi).mockReset();body='Original message';pending=null;fail=false;
 Object.defineProperty(document,'hidden',{configurable:true,value:false});
 vi.mocked(fetchApi).mockImplementation(async(url:string)=>{
  if(fail)throw {error:'Offline'};
  if(/\/tickets\/(a|b)\/$/.test(url)){
   if(pending&&url.endsWith('/a/'))return pending;
   const id=url.endsWith('/a/')?'a':'b';
   return {ticket:ticket(id),messages:[{id:'m-'+id,sender_name:'User',sender_type:'CLIENT',body:id==='a'?body:'Other thread',created_at:'2026-11-25T12:00:00Z'}],escalations:[]};
  }
  return {tickets:[ticket('a'),ticket('b')],categories:[],priorities:[],operators:[],counts:{total:2}};
 });
});
afterEach(()=>{cleanup();vi.useRealTimers();});
const flush=()=>act(async()=>{await Promise.resolve();});
async function boot(platform:boolean){
 render(platform?<PlatformSupportPage/>:<HelpSupportPage/>);await flush();
 fireEvent.click(screen.getByText(platform?'SUP-a • Client':'SUP-a: Issue a'));await flush();
 expect(screen.getByText('Original message')).toBeInTheDocument();
}
for(const platform of [false,true]){
 const label=platform?'platform':'client';
 test(`${label}: polling updates open thread and preserves draft`,async()=>{
  await boot(platform);const input=screen.getByPlaceholderText(platform?'Reply directly to the client...':'Write a reply to Neoriz Support...');
  fireEvent.change(input,{target:{value:'Unsent draft'}});body='New remote reply';
  await act(()=>vi.advanceTimersByTimeAsync(2500));
  expect(screen.getByText('New remote reply')).toBeInTheDocument();expect(input).toHaveValue('Unsent draft');
  expect(vi.mocked(fetchApi).mock.calls.some(([,options])=>options?.method==='POST')).toBe(false);
 });
 test(`${label}: Refresh reloads selected thread, not just list`,async()=>{
  await boot(platform);body='Refresh response';fireEvent.click(screen.getByRole('button',{name:'Refresh'}));await flush();
  expect(screen.getByText('Refresh response')).toBeInTheDocument();
 });
 test(`${label}: focus and visibility resume immediately; hidden timers do not fetch`,async()=>{
  await boot(platform);Object.defineProperty(document,'hidden',{configurable:true,value:true});
  const before=vi.mocked(fetchApi).mock.calls.length;
  await act(()=>vi.advanceTimersByTimeAsync(10000));expect(fetchApi).toHaveBeenCalledTimes(before);
  body='Returned reply';Object.defineProperty(document,'hidden',{configurable:true,value:false});
  fireEvent(document,new Event('visibilitychange'));await flush();expect(screen.getByText('Returned reply')).toBeInTheDocument();
  body='Focus reply';fireEvent(window,new Event('focus'));await flush();expect(screen.getByText('Focus reply')).toBeInTheDocument();
 });
 test(`${label}: slow polling stays single-flight and stale detail cannot replace another ticket`,async()=>{
  await boot(platform);let resolve!:(v:any)=>void;pending=new Promise(r=>{resolve=r;});
  await act(()=>vi.advanceTimersByTimeAsync(2500));const calls=vi.mocked(fetchApi).mock.calls.length;
  await act(()=>vi.advanceTimersByTimeAsync(10000));expect(fetchApi).toHaveBeenCalledTimes(calls);
  fireEvent.click(screen.getByText(platform?'SUP-b • Client':'SUP-b: Issue b'));await flush();
  expect(screen.getByText('Other thread')).toBeInTheDocument();
  await act(async()=>resolve({ticket:ticket('a'),messages:[{id:'late',body:'Stale reply'}],escalations:[]}));
  expect(screen.queryByText('Stale reply')).not.toBeInTheDocument();expect(screen.getByText('Other thread')).toBeInTheDocument();
 });
 test(`${label}: transient sync failures recover without removing thread or draft`,async()=>{
  await boot(platform);fail=true;await act(()=>vi.advanceTimersByTimeAsync(2500));
  expect(screen.getByText(/Connection interrupted/)).toBeInTheDocument();expect(screen.getByText('Original message')).toBeInTheDocument();
  fail=false;body='Recovered';await act(()=>vi.advanceTimersByTimeAsync(2500));expect(screen.getByText('Recovered')).toBeInTheDocument();
  expect(screen.queryByText(/Connection interrupted/)).not.toBeInTheDocument();
 });
}
test('unmount removes timers and wake listeners',async()=>{
 await boot(true);cleanup();const calls=vi.mocked(fetchApi).mock.calls.length;
 fireEvent(window,new Event('focus'));await act(()=>vi.advanceTimersByTimeAsync(10000));expect(fetchApi).toHaveBeenCalledTimes(calls);
});
