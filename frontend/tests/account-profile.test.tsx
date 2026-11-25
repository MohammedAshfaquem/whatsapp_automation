import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { expect, test, vi } from 'vitest';
import { AccountProfile } from '../src/components/settings/AccountProfile';
import { fetchApi } from '../src/api/client';
vi.mock('../src/api/client',()=>({fetchApi:vi.fn()}));
test('updates own name and email and opens native password change',async()=>{
 const api=vi.mocked(fetchApi);
 api.mockResolvedValue({username:'alice',full_name:'Alice',email:'a@example.com',password_change_supported:true});
 render(<AccountProfile />);
 expect(await screen.findByDisplayValue('alice')).toHaveAttribute('readonly');
 fireEvent.change(screen.getByLabelText('Your full name'),{target:{value:'Alice Smith'}});
 fireEvent.change(screen.getByLabelText('Your email'),{target:{value:'alice@example.com'}});
 fireEvent.click(screen.getByRole('button',{name:'Save profile'}));
 await waitFor(()=>expect(api).toHaveBeenCalledWith('/api/auth/profile/',{method:'POST',body:JSON.stringify({full_name:'Alice Smith',email:'alice@example.com'})}));
 fireEvent.click(screen.getByRole('button',{name:'Change password'}));
 expect(screen.getByRole('dialog',{name:'Change password'})).toBeInTheDocument();
 expect(screen.queryByRole('link',{name:'Change password'})).not.toBeInTheDocument();
});
test('shows new email verification handoff after profile changes',async()=>{
 const api=vi.mocked(fetchApi);
 api.mockResolvedValueOnce({username:'alice',full_name:'Alice',email:'a@example.com'}).mockResolvedValueOnce({username:'alice',full_name:'Alice',email:'new@example.com',email_verification_required:true});
 render(<AccountProfile />);
 await screen.findByDisplayValue('a@example.com');
 fireEvent.change(screen.getByLabelText('Your email'),{target:{value:'new@example.com'}});
 fireEvent.click(screen.getByRole('button',{name:'Save profile'}));
 expect(await screen.findByText('Verify your new email before reopening your workspace')).toBeInTheDocument();
 expect(screen.getByRole('link',{name:'Resend verification email'})).toHaveAttribute('href','/resend-verification/');
});
