import React from 'react';
import { AlertTriangle, ArrowLeft } from 'lucide-react';

interface NotFoundPageProps {
  onNavigate: (path: string) => void;
}

export const NotFoundPage: React.FC<NotFoundPageProps> = ({ onNavigate }) => {
  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        padding: '4rem 1.5rem',
        textAlign: 'center',
        maxWidth: '32rem',
        margin: '0 auto',
      }}
    >
      <div
        style={{
          width: '4rem',
          height: '4rem',
          borderRadius: '50%',
          backgroundColor: 'rgba(239, 68, 68, 0.1)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          marginBottom: '1.5rem',
          color: "var(--danger)",
        }}
      >
        <AlertTriangle size={32} />
      </div>
      <h1 style={{ fontSize: '1.75rem', fontWeight: 700, color: "var(--text-main)", marginBottom: '0.75rem' }}>
        Page Not Found
      </h1>
      <p style={{ fontSize: '0.9rem', color: "var(--text-muted)", lineHeight: 1.6, marginBottom: '2rem' }}>
        The requested application page does not exist or you do not have permission to access it in the current workspace.
      </p>
      <button
        onClick={() => onNavigate('/app/dashboard')}
        className="btn-primary"
        style={{ display: 'inline-flex', alignItems: 'center', gap: '0.5rem' }}
      >
        <ArrowLeft size={16} />
        Back to Dashboard
      </button>
    </div>
  );
};
