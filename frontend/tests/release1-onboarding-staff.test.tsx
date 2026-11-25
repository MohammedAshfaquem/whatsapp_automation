import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { vi, test, expect, beforeEach } from 'vitest';
import { TeamPage } from '../src/pages/TeamPage';
import { PlatformOnboardingPage } from '../src/pages/PlatformOnboardingPage';
import { fetchApi } from '../src/api/client';

vi.mock('../src/api/client', () => ({
  fetchApi: vi.fn(),
  APIError: class extends Error {},
}));

beforeEach(() => {
  vi.resetAllMocks();
});

test('TeamPage supports direct staff creation and password reset without old password', async () => {
  vi.mocked(fetchApi).mockImplementation(async (url: string, opts?: any) => {
    if (url === '/api/team/') {
      return {
        members: [
          {
            id: 10,
            user_id: 10,
            username: 'desk_staff',
            full_name: 'Desk Staff',
            email: '',
            internal_identifier: 'risal@neorizsolutions.com',
            is_synthetic_identifier: true,
            recovery_email: '',
            recovery_email_verified: false,
            skip_mailbox_gate: true,
            role: 'STAFF',
            role_display: 'Tenant Staff',
            is_active: true,
            is_shared_account: false,
            can_manage: true,
            joined_at: '2026-11-25T10:00:00Z',
          },
        ],
        invitations: [],
        staff_requests: [],
        audit_logs: [{ id: 1, action: 'STAFF_CREATED', summary: 'Created team member desk_staff', actor: 'owner', created_at: '2026-11-25T10:00:00Z' }],
        actor_role: 'OWNER',
        seat_summary: { allocated: 5, used: 1, can_add: true },
      };
    }
    if (url === '/api/team/members/10/reset-password/' && opts?.method === 'POST') {
      return { status: 'password_reset', message: 'Password updated for @desk_staff and 1 active session(s) revoked.' };
    }
    return { status: 'ok' };
  });

  render(<TeamPage />);
  expect(await screen.findByText('Desk Staff')).toBeInTheDocument();
  expect(screen.getByRole('button', { name: /Add Staff Member/i })).toBeInTheDocument();

  fireEvent.click(screen.getByRole('button', { name: /Reset Password/i }));
  expect(screen.queryByLabelText(/Current password/i)).not.toBeInTheDocument();

  fireEvent.change(screen.getByLabelText('New Password *'), { target: { value: 'StrongResetPass99!' } });
  fireEvent.change(screen.getByLabelText('Confirm New Password *'), { target: { value: 'StrongResetPass99!' } });
  fireEvent.click(screen.getByRole('button', { name: /Reset Password & Revoke Sessions/i }));

  await waitFor(() =>
    expect(fetchApi).toHaveBeenCalledWith(
      '/api/team/members/10/reset-password/',
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({ new_password: 'StrongResetPass99!', confirm_password: 'StrongResetPass99!' }),
      })
    )
  );
});

test('PlatformOnboardingPage lists onboardings without mark-verified bypass', async () => {
  vi.mocked(fetchApi).mockImplementation(async (url: string) => {
    if (url.startsWith('/api/platform/onboarding/')) {
      return {
        onboardings: [
          {
            id: '11111111-1111-1111-1111-111111111111',
            source: 'SELF_REGISTRATION',
            source_display: 'Self Registration / Request Access',
            business_name: 'Sunrise Clinic',
            owner_full_name: 'Dr Anita',
            owner_email: 'anita@sunrise.example',
            desired_username: 'dr_anita',
            whatsapp_number: '+919876543210',
            requested_plan: { id: 1, code: 'basic', name: 'Basic' },
            assigned_plan: null,
            registration_status: 'SUBMITTED',
            registration_status_display: 'Submitted',
            email_verified: false,
            email_verified_at: null,
            approval_status: 'PENDING',
            approved_by: null,
            approved_at: null,
            decision_reason: '',
            password_set: false,
            verification_expires_at: null,
            activation_expires_at: null,
            email_delivery: { purpose: 'VERIFICATION', status: 'ACCEPTED', status_label: 'SMTP Accepted', attempts: 1, last_error: '', updated_at: '2026-11-25T10:00:00Z' },
            next_action: 'Awaiting owner email verification',
            created_at: '2026-11-25T10:00:00Z',
          },
        ],
        counts: { total: 1, pending_approval: 1, awaiting_email: 1, awaiting_password: 0, active: 0, rejected: 0 },
        plans: [{ id: 1, code: 'basic', name: 'Basic', max_staff: 3 }],
      };
    }
    return {};
  });

  render(<PlatformOnboardingPage />);
  expect(await screen.findByText('Sunrise Clinic')).toBeInTheDocument();
  expect(screen.queryByRole('button', { name: /Mark.*verified/i })).not.toBeInTheDocument();
  expect(screen.getByRole('button', { name: /Approve & Assign Plan/i })).toBeInTheDocument();
  expect(screen.getByRole('button', { name: /Resend Verification Email/i })).toBeInTheDocument();
});
