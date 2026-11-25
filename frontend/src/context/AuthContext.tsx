import React, { createContext, useContext, useEffect, useState } from 'react';
import { BootstrapResponse, User, Tenant, Membership, UserTenant, CapabilitiesMap, UsageData } from '../types';
import { fetchApi } from '../api/client';

interface AuthContextType {
  user: User | null;
  tenant: Tenant | null;
  membership: Membership | null;
  userTenants: UserTenant[];
  isInspecting: boolean;
  capabilities: CapabilitiesMap;
  usage: UsageData | null;
  isLoading: boolean;
  error: string | null;
  reloadBootstrap: () => Promise<void>;
  switchTenant: (tenantId: number) => Promise<void>;
  inspectTenant: (tenantId: number) => Promise<void>;
  exitInspection: () => Promise<void>;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [user, setUser] = useState<User | null>(null);
  const [tenant, setTenant] = useState<Tenant | null>(null);
  const [membership, setMembership] = useState<Membership | null>(null);
  const [userTenants, setUserTenants] = useState<UserTenant[]>([]);
  const [isInspecting, setIsInspecting] = useState(false);
  const [capabilities, setCapabilities] = useState<CapabilitiesMap>({});
  const [usage, setUsage] = useState<UsageData | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const reloadBootstrap = async () => {
    try {
      setIsLoading(true);
      setError(null);
      const data = await fetchApi<BootstrapResponse>('/api/auth/bootstrap/');
      setUser(data.user);
      setTenant(data.tenant);
      setMembership(data.membership);
      setUserTenants(data.user_tenants || []);
      setIsInspecting(data.is_inspecting || false);
      setCapabilities(data.capabilities || {});
      setUsage(data.usage || null);
    } catch (err: any) {
      setError(err?.error || 'Failed to initialize session context');
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    reloadBootstrap();
  }, []);

  const switchTenant = async (tenantId: number) => {
    try {
      await fetchApi('/api/auth/switch-tenant/', {
        method: 'POST',
        body: JSON.stringify({ tenant_id: tenantId }),
      });
      await reloadBootstrap();
    } catch (err: any) {
      alert(err?.error || 'Could not switch active workspace');
    }
  };

  const inspectTenant = async (tenantId: number) => {
    try {
      await fetchApi(`/api/platform/inspect/${tenantId}/`, {
        method: 'POST',
      });
      await reloadBootstrap();
    } catch (err: any) {
      alert(err?.error || 'Could not inspect workspace');
    }
  };

  const exitInspection = async () => {
    try {
      await fetchApi('/api/platform/inspect/exit/', {
        method: 'POST',
      });
      await reloadBootstrap();
    } catch (err: any) {
      alert(err?.error || 'Could not exit inspection mode');
    }
  };

  return (
    <AuthContext.Provider
      value={{
        user,
        tenant,
        membership,
        userTenants,
        isInspecting,
        capabilities,
        usage,
        isLoading,
        error,
        reloadBootstrap,
        switchTenant,
        inspectTenant,
        exitInspection,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
};

export const useAuth = () => {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
};
