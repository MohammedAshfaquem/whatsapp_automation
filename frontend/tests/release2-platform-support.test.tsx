import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { vi, test, expect, beforeEach } from 'vitest';
import { HelpSupportPage } from '../src/pages/HelpSupportPage';
import { PlatformSupportPage } from '../src/pages/PlatformSupportPage';
import { fetchApi } from '../src/api/client';

vi.mock('../src/api/client', () => ({
  fetchApi: vi.fn(),
  APIError: class extends Error {},
}));

beforeEach(() => {
  vi.resetAllMocks();
});

test('HelpSupportPage displays SLA policy, submits new ticket, and renders public messages without internal notes', async () => {
  vi.mocked(fetchApi).mockImplementation(async (url: string, opts?: any) => {
    if (url.startsWith('/api/support/tickets/') && (!opts || !opts.method)) {
      if (url === '/api/support/tickets/') {
        return {
          tickets: [
            {
              id: 'tkt-1',
              ticket_number: 'SUP-101',
              subject: 'Webhook handshake failing',
              category: 'META_SETUP',
              category_display: 'Meta & WhatsApp Setup',
              priority: 'HIGH',
              priority_display: 'High',
              status: 'OPEN',
              status_display: 'Open',
              sla_cycle_started_at: '2026-11-25T10:00:00Z',
              sla_deadline_at: '2026-11-25T10:10:00Z',
              sla_breached: false,
              sla_threshold_minutes: 10,
              created_at: '2026-11-25T10:00:00Z',
              updated_at: '2026-11-25T10:00:00Z',
            },
          ],
          categories: [{ value: 'META_SETUP', label: 'Meta & WhatsApp Setup' }],
          priorities: [{ value: 'HIGH', label: 'High' }],
          sla_config: { threshold_minutes: 10 },
        };
      }
      return {
        ticket: {
          id: 'tkt-1',
          ticket_number: 'SUP-101',
          subject: 'Webhook handshake failing',
          category_display: 'Meta & WhatsApp Setup',
          priority_display: 'High',
          status: 'OPEN',
          status_display: 'Open',
        },
        messages: [
          {
            id: 'msg-1',
            sender_name: 'Owner User',
            sender_type: 'CLIENT',
            body: 'Meta verify token failing with 403.',
            created_at: '2026-11-25T10:00:00Z',
          },
        ],
      };
    }
    return { status: 'ok' };
  });

  render(<HelpSupportPage />);
  expect(await screen.findByText(/10-Minute Urgent Escalation Policy/i)).toBeInTheDocument();
  fireEvent.click(await screen.findByText(/SUP-101: Webhook handshake failing/i));
  expect(await screen.findByText('Meta verify token failing with 403.')).toBeInTheDocument();
});

test('PlatformSupportPage shows SLA breach count, internal notes toggle, and escalation audit history', async () => {
  vi.mocked(fetchApi).mockImplementation(async (url: string, opts?: any) => {
    if (url === '/api/platform/support/tickets/' && !opts?.method) {
      return {
        tickets: [
          {
            id: 'tkt-2',
            ticket_number: 'SUP-202',
            tenant_id: 1,
            tenant_name: 'Neoriz Solutions',
            subject: 'Urgent Billing Help',
            category: 'BILLING',
            category_display: 'Billing & Subscription',
            priority: 'URGENT',
            priority_display: 'Urgent',
            status: 'AWAITING_PLATFORM',
            status_display: 'Awaiting Platform',
            assigned_to: null,
            sla_cycle_started_at: '2026-11-25T10:00:00Z',
            sla_breached: true,
            escalations_count: 1,
            updated_at: '2026-11-25T10:15:00Z',
          },
        ],
        counts: { total: 1, open: 1, breached: 1, escalated: 1, awaiting_client: 0, resolved: 0 },
        operators: [{ id: 2, username: 'superadmin', full_name: 'Super Admin' }],
      };
    }
    if (url === '/api/platform/support/tickets/tkt-2/') {
      return {
        ticket: {
          id: 'tkt-2',
          ticket_number: 'SUP-202',
          tenant_name: 'Neoriz Solutions',
          subject: 'Urgent Billing Help',
          status: 'AWAITING_PLATFORM',
          priority: 'URGENT',
          assigned_to: null,
        },
        messages: [
          { id: 'm1', sender_name: 'Client', sender_type: 'CLIENT', is_internal_note: false, body: 'Invoice issue', created_at: '2026-11-25T10:00:00Z' },
          { id: 'm2', sender_name: 'Super Admin', sender_type: 'PLATFORM', is_internal_note: true, body: 'Internal billing note', created_at: '2026-11-25T10:05:00Z' },
        ],
        escalations: [
          { id: 'e1', cycle_started_at: '2026-11-25T10:00:00Z', escalated_to_email: 'support@neorizsolutions.com', status: 'SENT', email_status: 'ACCEPTED', reason: 'No response within 10 minutes', sent_at: '2026-11-25T10:10:05Z' },
        ],
      };
    }
    if (url === '/api/platform/support/tickets/tkt-2/reply/' && opts?.method === 'POST') {
      return { status: 'replied' };
    }
    return {};
  });

  render(<PlatformSupportPage />);
  fireEvent.click(await screen.findByText(/SUP-202 • Neoriz Solutions/i));
  expect(await screen.findByText('Internal billing note')).toBeInTheDocument();
  expect(screen.getByText(/Emergency SLA Escalation Audit Log/i)).toBeInTheDocument();
  expect(screen.getByText(/support@neorizsolutions.com/)).toBeInTheDocument();

  const noteCheckbox = screen.getByLabelText(/Internal Operator Note/i);
  fireEvent.click(noteCheckbox);
  fireEvent.change(screen.getByPlaceholderText(/Internal engineering/i), { target: { value: 'Assigned L2 review' } });
  fireEvent.click(screen.getByRole('button', { name: /Save Internal Note/i }));

  await waitFor(() =>
    expect(fetchApi).toHaveBeenCalledWith(
      '/api/platform/support/tickets/tkt-2/reply/',
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({ body: 'Assigned L2 review', is_internal_note: true }),
      })
    )
  );
});
