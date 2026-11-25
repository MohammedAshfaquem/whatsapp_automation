import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, expect, test, vi } from 'vitest';
import { PlatformSystemSettingsPage } from '../src/pages/PlatformSystemSettingsPage';
import { WorkspaceToolsPage } from '../src/pages/WorkspaceToolsPage';
import { AutomationsPage } from '../src/pages/AutomationsPage';
import { ReportsPage } from '../src/pages/ReportsPage';
import { api, fetchApi } from '../src/api/client';

const authState = vi.hoisted(() => ({
  user: { id: 1, username: 'super', is_superuser: true, platform_role: 'SUPER_ADMIN' },
}));

vi.mock('../src/context/AuthContext', () => ({ useAuth: () => authState }));
vi.mock('../src/api/client', () => ({
  fetchApi: vi.fn(),
  api: { get: vi.fn(), post: vi.fn() },
}));

beforeEach(() => {
  vi.clearAllMocks();
});

test('PlatformSystemSettingsPage renders and persists bounded settings and backup check', async () => {
  vi.mocked(fetchApi).mockResolvedValue({
    verification_expiry_minutes: 30,
    resend_cooldown_seconds: 60,
    resend_max_per_hour: 5,
    support_alert_email: 'support@neorizsolutions.com',
    support_escalation_minutes: 10,
    global_outbound_paused: false,
    global_outbound_pause_reason: '',
    maintenance_mode: false,
    maintenance_message: 'Maintenance',
    last_backup_verified_at: null,
    last_backup_note: '',
  });
  render(<PlatformSystemSettingsPage />);
  expect(await screen.findByRole('heading', { name: /System Settings/i })).toBeInTheDocument();
  fireEvent.click(screen.getByRole('checkbox', { name: /Pause All Outbound WhatsApp/i }));
  fireEvent.click(screen.getByRole('button', { name: /Save System Settings/i }));
  await waitFor(() =>
    expect(fetchApi).toHaveBeenCalledWith(
      '/api/platform/system-settings/',
      expect.objectContaining({ method: 'POST', body: expect.stringContaining('"global_outbound_paused":true') })
    )
  );
});

test('WorkspaceToolsPage health triggers lease release and global outbound pause', async () => {
  vi.mocked(fetchApi).mockResolvedValue({
    expired_processing_leases: 2,
    expired_customer_leases: 1,
    expired_event_leases: 1,
    expired_webhook_leases: 0,
    expired_delivery_leases: 0,
    active_processing_leases: 0,
    global_outbound_paused: false,
    global_outbound_pause_reason: '',
    paused_tenants: [],
    delivery_queue: [],
    email_queue: [],
    smtp_ready: true,
    billing_mode: 'MANUAL',
    meta_onboarding: 'Client-owned',
  });
  render(<WorkspaceToolsPage platform resource="health" />);
  fireEvent.click(await screen.findByRole('button', { name: 'Release Expired Leases' }));
  await waitFor(() =>
    expect(fetchApi).toHaveBeenCalledWith(
      '/api/platform/tools/health/',
      expect.objectContaining({ method: 'POST', body: JSON.stringify({ action: 'release_expired_leases' }) })
    )
  );
});

test('AutomationsPage loads and saves business hours and SLA timer', async () => {
  vi.mocked(api.get).mockImplementation(async (url: string) => {
    if (url.includes('/settings/')) {
      return {
        data: {
          business_hours: { enabled: false, timezone: 'Asia/Kolkata', days: {} },
          currently_open: true,
          after_hours_auto_reply: '',
          greeting_auto_reply: '',
          auto_assign_inbound: false,
          no_response_followup_minutes: 0,
        },
      } as any;
    }
    return { data: { rules: [], recent_logs: [], triggers: [], actions: [] } } as any;
  });
  vi.mocked(api.post).mockResolvedValue({
    data: {
      business_hours: { enabled: true, timezone: 'Asia/Kolkata', days: {} },
      currently_open: false,
      after_hours_auto_reply: 'Offline',
      greeting_auto_reply: '',
      auto_assign_inbound: true,
      no_response_followup_minutes: 15,
    },
  } as any);

  render(<AutomationsPage />);
  fireEvent.click(await screen.findByRole('button', { name: 'Save Operational Settings' }));
  await waitFor(() =>
    expect(api.post).toHaveBeenCalledWith('/api/crm/automations/settings/', expect.any(Object))
  );
});

test('ReportsPage renders unanswered inbound, agent workload, and campaign outcomes', async () => {
  vi.mocked(fetchApi).mockResolvedValue({
    conversations: { total: 10, active: 3, human_takeover: 7, unanswered_inbound: 2, avg_first_response_minutes: 4.5 },
    deals: { open: 1, won: 2, lost: 0, pipeline_value: '5000.00' },
    activities: { pending: 3, overdue: 1, completed: 5 },
    bookings: { total: 4, confirmed: 3 },
    agents: [{ user_id: 9, username: 'asha', full_name: 'Asha', role: 'STAFF', open_chats: 2, replies_sent: 12 }],
    campaigns: { total: 2, completed: 1, sent: 40, delivered: 38, read: 22, failed: 2 },
  });
  render(<ReportsPage />);
  expect(await screen.findByText('Campaign Outcomes')).toBeInTheDocument();
  expect(screen.getByText('Asha (@asha)')).toBeInTheDocument();
  expect(screen.getByText('4.5 min')).toBeInTheDocument();
});
