import React from 'react';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { NewChatModal } from '../src/components/inbox/NewChatModal';
import { PlatformTenantsPage } from '../src/pages/PlatformTenantsPage';
import { fetchApi } from '../src/api/client';

vi.mock('../src/api/client', () => ({ fetchApi: vi.fn(async () => ({ contacts: [], templates: [], tenants: [] })) }));
vi.mock('../src/context/AuthContext', () => ({ useAuth: () => ({ inspectTenant: vi.fn() }) }));
afterEach(() => { cleanup(); vi.clearAllMocks(); });

describe('inline modal dismissal', () => {
  for (const action of ['close', 'Escape', 'backdrop']) {
    it(`dismisses New Chat using ${action} without submitting`, async () => {
      const onClose = vi.fn();
      render(<NewChatModal isOpen onClose={onClose} onConversationCreated={vi.fn()} />);
      await waitFor(() => expect(fetchApi).toHaveBeenCalledTimes(2));
      const calls = vi.mocked(fetchApi).mock.calls.length;
      if (action === 'close') fireEvent.click(screen.getByRole('button', { name: 'Close New WhatsApp Conversation' }));
      if (action === 'Escape') fireEvent.keyDown(document, { key: 'Escape' });
      if (action === 'backdrop') fireEvent.click(screen.getByRole('dialog').parentElement!);
      expect(onClose).toHaveBeenCalledTimes(1);
      expect(fetchApi).toHaveBeenCalledTimes(calls);
    });
    it(`dismisses workspace provisioning using ${action} and retains its draft`, async () => {
      render(<PlatformTenantsPage onNavigate={vi.fn()} />);
      await waitFor(() => expect(fetchApi).toHaveBeenCalledTimes(1));
      const open = screen.getByRole('button', { name: /Provision Client Workspace/ });
      fireEvent.click(open);
      expect(screen.getByRole('dialog')).toBeTruthy();
      fireEvent.change(screen.getByPlaceholderText('e.g. Apex Hospital or Horizon Retail'), { target: { value: 'Draft business' } });
      if (action === 'close') fireEvent.click(screen.getByRole('button', { name: 'Close Provision Client Workspace (Step 1 of 4)' }));
      if (action === 'Escape') fireEvent.keyDown(document, { key: 'Escape' });
      if (action === 'backdrop') fireEvent.click(screen.getByRole('dialog').parentElement!);
      expect(screen.queryByRole('dialog')).toBeNull();
      expect(fetchApi).toHaveBeenCalledTimes(1);
      fireEvent.click(open);
      expect((screen.getByPlaceholderText('e.g. Apex Hospital or Horizon Retail') as HTMLInputElement).value).toBe('Draft business');
    });
  }
});


