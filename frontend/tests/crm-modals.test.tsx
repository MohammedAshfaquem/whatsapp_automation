import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, expect, it, vi } from 'vitest';
import { ContactsPage } from '../src/pages/ContactsPage';
import { DealsPage } from '../src/pages/DealsPage';
import { fetchApi } from '../src/api/client';
vi.mock('../src/api/client', () => ({ fetchApi: vi.fn() }));
const contact = { id: 1, name: 'Alice', phone_number: '12345', lifecycle_status: 'LEAD', created_at: '2026-01-01' };
beforeEach(() => { vi.mocked(fetchApi).mockReset(); vi.mocked(fetchApi).mockImplementation(async (path) => {
 if (path === '/api/crm/contacts/1/') return { contact, timeline: [], notes: [], deals: [] };
 if (String(path).includes('/contacts/')) return { contacts: [contact] };
 if (path === '/api/crm/companies/') return { companies: [] };
 if (path === '/api/crm/deals/') return { stages: [{ id: 1, name: 'New', deals: [{ id: 1, title: 'Example deal', value: 10 }], deal_count: 1, total_value: 10 }] };
 return { quotes: [] };
}); });
it('Contacts closes merge independently and restores the details dialog and its opener', async () => {
 render(<ContactsPage />); fireEvent.click(await screen.findByRole('button', { name: 'View Details' }));
 expect(await screen.findByRole('dialog', { name: 'Alice' })).toBeTruthy();
 const merge = screen.getByRole('button', { name: 'Merge Duplicate' }); merge.focus(); fireEvent.click(merge);
 fireEvent.click(screen.getByRole('button', { name: 'Close Merge Duplicate Contact' }));
 expect(screen.queryByRole('dialog', { name: 'Merge Duplicate Contact' })).toBeNull(); expect(screen.getByRole('dialog', { name: 'Alice' })).toBeTruthy(); expect(document.activeElement).toBe(merge);
 fireEvent.keyDown(document, { key: 'Escape' }); expect(screen.queryByRole('dialog')).toBeNull();
 fireEvent.click(screen.getByRole('button', { name: 'Add Contact' })); fireEvent.click(screen.getByRole('button', { name: 'Close Add New Contact' })); expect(screen.queryByRole('dialog')).toBeNull();
});
it('Deals closes the quote editor only, then the quote list, without writing data', async () => {
 render(<DealsPage />); fireEvent.click(await screen.findByRole('button', { name: 'View / Create Quotes' }));
 await screen.findByText('No quotes issued for this deal yet.');
 fireEvent.click(screen.getByRole('button', { name: 'New Quote' }));
 fireEvent.keyDown(document, { key: 'Escape' }); expect(screen.queryByRole('dialog', { name: 'New Versioned Quotation' })).toBeNull(); expect(screen.getByRole('dialog', { name: 'Quotations & Proposals' })).toBeTruthy();
 fireEvent.click(screen.getByRole('button', { name: 'New Quote' })); fireEvent.click(screen.getByRole('button', { name: 'Close New Versioned Quotation' })); expect(screen.getByRole('dialog', { name: 'Quotations & Proposals' })).toBeTruthy();
 fireEvent.click(screen.getByRole('button', { name: 'Close Quotations & Proposals' })); expect(screen.queryByRole('dialog')).toBeNull();
 fireEvent.click(screen.getByRole('button', { name: 'New Deal' })); fireEvent.click(screen.getByRole('button', { name: 'Close Create New Deal' })); expect(screen.queryByRole('dialog')).toBeNull();
 await waitFor(() => expect(vi.mocked(fetchApi).mock.calls.every(([,options]) => !options?.method || options.method === 'GET')).toBe(true));
});
