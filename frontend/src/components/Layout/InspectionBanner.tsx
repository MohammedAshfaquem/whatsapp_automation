import React from 'react';
import { useAuth } from '../../context/AuthContext';
import { AlertTriangle, LogOut } from 'lucide-react';

export const InspectionBanner: React.FC = () => {
  const { isInspecting, tenant, exitInspection } = useAuth();

  if (!isInspecting || !tenant) return null;

  return (
    <div
      style={{
        backgroundColor: "#fff3dc",
        borderBottom: '2px solid #f59e0b',
        color: "var(--warning)",
        padding: '0.625rem 1.5rem',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        fontSize: '0.875rem',
        fontWeight: 600,
        zIndex: 50,
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: '0.625rem' }}>
        <AlertTriangle size={19} style={{ color: "var(--warning)" }} />
        <span>
          Super Admin inspecting client: <strong style={{ textDecoration: 'underline' }}>{tenant.name}</strong> (Workspace #{tenant.id})
        </span>
      </div>
      <button
        onClick={exitInspection}
        style={{
          backgroundColor: '#fff3dc',
          border: '1px solid #fde047',
          color: "var(--warning)",
          padding: '0.35rem 0.85rem',
          borderRadius: '6px',
          fontWeight: 700,
          fontSize: '0.8rem',
          cursor: 'pointer',
          display: 'flex',
          alignItems: 'center',
          gap: '0.4rem',
          transition: 'all 0.15s ease',
        }}
      >
        <LogOut size={14} /> Exit Inspection
      </button>
    </div>
  );
};
