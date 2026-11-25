import {fireEvent,render,screen,cleanup} from '@testing-library/react';
import {afterEach,expect,it,vi} from 'vitest';
import {readFileSync} from 'node:fs';
import {PasswordInput} from '../src/components/PasswordInput';
afterEach(cleanup);
it('React eye toggles only its field, preserves values and never submits',()=>{
 const submit=vi.fn(e=>e.preventDefault());render(<form onSubmit={submit}><label>New password<PasswordInput visibilityLabel="new password" name="password" defaultValue="SecretExample123!"/></label><label>Confirm password<PasswordInput visibilityLabel="confirm password"/></label></form>);
 const input=screen.getByLabelText('New password') as HTMLInputElement;
 expect(input.type).toBe('password');fireEvent.click(screen.getByRole('button',{name:'Show new password'}));expect(input.type).toBe('text');expect(input.value).toBe('SecretExample123!');expect((screen.getByLabelText('Confirm password') as HTMLInputElement).type).toBe('password');expect(submit).not.toHaveBeenCalled();fireEvent.click(screen.getByRole('button',{name:'Hide new password'}));expect(input.type).toBe('password');
});
it('server-rendered password helper enhances real inputs once and handles later forms',async()=>{
 const Original=globalThis.MutationObserver;const observers:MutationObserver[]=[];vi.stubGlobal('MutationObserver',class extends Original{constructor(cb:MutationCallback){super(cb);observers.push(this);}});
 document.body.innerHTML='<form><label for="new">New password</label><input id="new" type="password" value="Example123!"><label for="confirm">Confirm password</label><input id="confirm" type="password"></form>';
 const script=readFileSync('../templates/tenants/password_visibility.html','utf8').match(/<script>([\s\S]*)<\/script>/)![1];
 window.eval(script);document.dispatchEvent(new Event('DOMContentLoaded'));
 const input=document.getElementById('new') as HTMLInputElement;fireEvent.click(screen.getByRole('button',{name:'Show New password'}));expect(input.type).toBe('text');expect(input.value).toBe('Example123!');expect((document.getElementById('confirm') as HTMLInputElement).type).toBe('password');fireEvent.click(screen.getByRole('button',{name:'Hide New password'}));expect(input.type).toBe('password');
 const later=document.createElement('input');later.type='password';later.setAttribute('aria-label','Later password');document.body.appendChild(later);await new Promise(r=>setTimeout(r,0));expect(screen.getByRole('button',{name:'Show Later password'})).toBeTruthy();expect(document.querySelectorAll('.password-toggle-button').length).toBe(3);observers.forEach(o=>o.disconnect());vi.unstubAllGlobals();
});
