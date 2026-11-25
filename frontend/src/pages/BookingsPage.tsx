import React, { useEffect, useState } from 'react';
import { Booking } from '../types';
import { fetchApi } from '../api/client';
import { Check, X, CheckCircle } from 'lucide-react';

export const BookingsPage: React.FC = () => {
  const [bookings, setBookings] = useState<Booking[]>([]);
  const [loading, setLoading] = useState(true);

  const loadBookings = async () => {
    try {
      setLoading(true);
      const data = await fetchApi<{ bookings: Booking[] }>('/api/bookings/');
      setBookings(data.bookings || []);
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadBookings();
  }, []);

  const handleBookingAction = async (bookingId: number, action: 'confirm' | 'reject' | 'complete') => {
    try {
      const formData = new FormData();
      formData.append('action', action);
      await fetchApi(`/bookings/${bookingId}/action/`, {
        method: 'POST',
        body: formData,
      });
      await loadBookings();
    } catch (err: any) {
      alert(err?.error || `Could not ${action} booking`);
    }
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem', maxWidth: '80rem', margin: '0 auto' }}>
      <div>
        <h1 style={{ fontSize: '1.5rem', fontWeight: 700, color: "var(--text-main)" }}>Bookings & Consultation Requests</h1>
        <p style={{ fontSize: '0.875rem', color: "var(--text-muted)" }}>
          Customer bookings received through WhatsApp bot automation.
        </p>
      </div>

      <div className="table-container">
        <table className="custom-table">
          <thead>
            <tr>
              <th>Status</th>
              <th>Customer</th>
              <th>Service Requested</th>
              <th>Preferred Date / Time</th>
              <th>Address / Notes</th>
              <th style={{ textAlign: 'right' }}>Actions</th>
            </tr>
          </thead>
          <tbody>
            {bookings.length === 0 ? (
              <tr>
                <td colSpan={6} style={{ textAlign: 'center', padding: '2rem', color: "var(--text-muted)" }}>
                  {loading ? 'Loading bookings...' : 'No bookings recorded.'}
                </td>
              </tr>
            ) : (
              bookings.map((b) => (
                <tr key={b.id}>
                  <td>
                    <span
                      className={`badge ${
                        b.status === 'CONFIRMED'
                          ? 'badge-green'
                          : b.status === 'COMPLETED'
                          ? 'badge-blue'
                          : b.status === 'REJECTED'
                          ? 'badge-red'
                          : 'badge-amber'
                      }`}
                    >
                      {b.status_display}
                    </span>
                  </td>
                  <td>
                    <div style={{ fontWeight: 600 }}>{b.customer_name}</div>
                    <div style={{ fontSize: '0.75rem', color: "var(--text-muted)" }}>{b.customer_phone}</div>
                  </td>
                  <td style={{ fontWeight: 500 }}>{b.service_name}</td>
                  <td style={{ fontSize: '0.85rem', color: "var(--text-main)" }}>
                    {b.preferred_date ? new Date(b.preferred_date).toLocaleDateString() : 'Flexible'}
                    {b.preferred_time ? ` • ${b.preferred_time}` : ''}
                  </td>
                  <td style={{ fontSize: '0.8rem', color: "var(--text-muted)", maxWidth: '14rem' }}>
                    {b.address || '—'}
                  </td>
                  <td style={{ textAlign: 'right' }}>
                    <div style={{ display: 'flex', gap: '0.35rem', justifyContent: 'flex-end' }}>
                      {b.status === 'PENDING' && (
                        <>
                          <button
                            onClick={() => handleBookingAction(b.id, 'confirm')}
                            className="btn btn-sm btn-primary"
                          >
                            <Check size={13} /> Confirm
                          </button>
                          <button
                            onClick={() => handleBookingAction(b.id, 'reject')}
                            className="btn btn-sm btn-danger"
                          >
                            <X size={13} /> Reject
                          </button>
                        </>
                      )}
                      {b.status === 'CONFIRMED' && (
                        <button
                          onClick={() => handleBookingAction(b.id, 'complete')}
                          className="btn btn-sm btn-secondary"
                        >
                          <CheckCircle size={13} /> Mark Done
                        </button>
                      )}
                    </div>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
};
