import React, { useState, useRef, useEffect } from 'react';
import { useAuth } from '../../context/AuthContext';
import { Building2, ChevronDown, Check, Shield } from 'lucide-react';

export const WorkspaceSwitcher: React.FC = () => {
  const { tenant, userTenants, switchTenant, user } = useAuth();
  const [isOpen, setIsOpen] = useState(false);
  const dropdownRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
        setIsOpen(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  if (!tenant && !user?.is_superuser) return null;

  return (
    <div style={{ position: 'relative' }} ref={dropdownRef}>
      <button
        onClick={() => setIsOpen(!isOpen)}
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: '0.625rem',
          padding: '0.4rem 0.75rem',
          backgroundColor: "var(--bg-card)",
          border: "1px solid var(--border)",
          borderRadius: '0.5rem',
          color: "var(--text-main)",
          cursor: 'pointer',
          fontSize: '0.875rem',
          fontWeight: 500,
        }}
      >
        <div
          style={{
            width: '1.75rem',
            height: '1.75rem',
            borderRadius: '0.375rem',
            backgroundColor: 'rgba(17, 183, 109, 0.15)',
            border: '1px solid rgba(17, 183, 109, 0.3)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            color: "var(--primary)",
          }}
        >
          <Building2 size={15} />
        </div>
        <div style={{ textAlign: 'left', lineHeight: 1.2 }}>
          <div style={{ fontSize: '0.85rem', fontWeight: 600 }}>
            {tenant ? tenant.name : 'Platform Management'}
          </div>
          <div style={{ fontSize: '0.7rem', color: "var(--text-muted)" }}>
            {tenant ? tenant.plan_name : 'Superadmin'}
          </div>
        </div>
        <ChevronDown size={14} style={{ color: "var(--text-muted)", marginLeft: '0.25rem' }} />
      </button>

      {isOpen && (
        <div
          style={{
            position: 'absolute',
            top: 'calc(100% + 0.5rem)',
            left: 0,
            width: '16rem',
            backgroundColor: "var(--bg-card)",
            border: "1px solid var(--border)",
            borderRadius: '0.5rem',
            boxShadow: '0 10px 25px -5px rgba(0, 0, 0, 0.5)',
            zIndex: 50,
            overflow: 'hidden',
          }}
        >
          <div style={{ padding: '0.6rem 0.85rem', borderBottom: "1px solid var(--border)", fontSize: '0.75rem', color: "var(--text-muted)", fontWeight: 600, textTransform: 'uppercase' }}>
            Switch Workspace
          </div>

          <div style={{ maxHeight: '14rem', overflowY: 'auto' }}>
            {userTenants.map((ut) => {
              const isSelected = tenant?.id === ut.id;
              return (
                <button
                  key={ut.id}
                  onClick={() => {
                    switchTenant(ut.id);
                    setIsOpen(false);
                  }}
                  style={{
                    width: '100%',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    padding: '0.625rem 0.85rem',
                    backgroundColor: isSelected ? 'rgba(17, 183, 109, 0.1)' : 'transparent',
                    border: 'none',
                    borderBottom: "1px solid var(--border)",
                    color: isSelected ? "var(--primary)" : "var(--text-main)",
                    cursor: 'pointer',
                    textAlign: 'left',
                    fontSize: '0.85rem',
                  }}
                >
                  <div>
                    <div style={{ fontWeight: isSelected ? 600 : 400 }}>{ut.name}</div>
                    <div style={{ fontSize: '0.7rem', color: "var(--text-muted)" }}>{ut.role_display}</div>
                  </div>
                  {isSelected && <Check size={16} style={{ color: "var(--primary)" }} />}
                </button>
              );
            })}
          </div>

          {user?.is_superuser && (
            <div style={{ padding: '0.5rem', backgroundColor: "var(--bg-card)", borderTop: "1px solid var(--border)" }}>
              <a
                href="/app/platform/dashboard"
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '0.5rem',
                  padding: '0.4rem 0.6rem',
                  color: "var(--text-muted)",
                  fontSize: '0.75rem',
                  textDecoration: 'none',
                  borderRadius: '0.375rem',
                }}
              >
                <Shield size={14} style={{ color: "var(--primary)" }} />
                Super Admin
              </a>
            </div>
          )}
        </div>
      )}
    </div>
  );
};
