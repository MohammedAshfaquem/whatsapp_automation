import React, { useState, useEffect } from 'react';
import { useAuth } from './context/AuthContext';
import { Shell } from './components/Layout/Shell';
import { WorkspaceToolsPage } from './pages/WorkspaceToolsPage';
import { DashboardPage } from './pages/DashboardPage';
import { InboxPage } from './pages/InboxPage';
import { ContactsPage } from './pages/ContactsPage';
import { CompaniesPage } from './pages/CompaniesPage';
import { DealsPage } from './pages/DealsPage';
import { TasksPage } from './pages/TasksPage';
import { BookingsPage } from './pages/BookingsPage';
import { ServicesPage } from './pages/ServicesPage';
import { KnowledgePage } from './pages/KnowledgePage';
import { TeamPage } from './pages/TeamPage';
import { AccountProfile } from './components/settings/AccountProfile';
import { SettingsPage } from './pages/SettingsPage';
import { PlatformDashboardPage } from './pages/PlatformDashboardPage';
import { PlatformTenantsPage } from './pages/PlatformTenantsPage';
import { PlatformOnboardingPage } from './pages/PlatformOnboardingPage';
import { PlatformStaffRequestsPage } from './pages/PlatformStaffRequestsPage';
import { PlatformMatrixPage } from './pages/PlatformMatrixPage';
import { PlatformOperationsPage } from './pages/PlatformOperationsPage';
import { PlatformAuditPage } from './pages/PlatformAuditPage';
import { ReportsPage } from './pages/ReportsPage';
import { UsagePage } from './pages/UsagePage';
import { OnboardingPage } from './pages/OnboardingPage';
import { WorkQueuePage } from './pages/WorkQueuePage';
import { AutomationsPage } from './pages/AutomationsPage';
import { SupportPage } from './pages/SupportPage';
import { HelpSupportPage } from './pages/HelpSupportPage';
import { PlatformSupportPage } from './pages/PlatformSupportPage';
import { GrowthPage } from './pages/GrowthPage';
import { IntegrationsPage } from './pages/IntegrationsPage';
import { PlatformSystemSettingsPage } from './pages/PlatformSystemSettingsPage';
import { NotFoundPage } from './pages/NotFoundPage';
import { AlertCircle } from 'lucide-react';

export const App: React.FC = () => {
  const { user, tenant, isInspecting, isLoading, error } = useAuth();
  const [currentPath, setCurrentPath] = useState(window.location.pathname);

  useEffect(() => {
    const handlePopState = () => {
      setCurrentPath(window.location.pathname);
    };
    window.addEventListener('popstate', handlePopState);
    return () => window.removeEventListener('popstate', handlePopState);
  }, []);

  const navigate = (path: string) => {
    window.history.pushState({}, '', path);
    setCurrentPath(path);
  };

  const isPlatformUser = Boolean(user?.is_superuser || (user as any)?.is_platform_operator || (user as any)?.platform_role);
  const setupLocked = !(isPlatformUser && !isInspecting) && tenant?.meta_setup_required === true && tenant?.meta_setup_ready !== true;
  const setupAllowedPaths = ['/app/settings', '/app/account', '/app/onboarding', '/app/subscription', '/app/usage', '/app/help-support'];

  // Fallback initial redirect
  useEffect(() => {
    if (!isLoading && user) {
      const cleanPath = currentPath.split('?')[0];
      if (setupLocked && !setupAllowedPaths.includes(cleanPath)) { navigate('/app/settings'); } else if (isPlatformUser && !isInspecting && !currentPath.startsWith('/app/platform/') && currentPath !== '/app/account') {
        navigate('/app/platform/dashboard');
      } else if (currentPath === '/app' || currentPath === '/app/') {
        if (isPlatformUser && !isInspecting) {
          navigate('/app/platform/dashboard');
        } else {
          navigate('/app/dashboard');
        }
      }
    }
  }, [isLoading, user, isPlatformUser, tenant, isInspecting, currentPath, setupLocked]);

  if (isLoading) {
    return (
      <div
        style={{
          height: '100vh',
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'center',
          backgroundColor: "var(--bg-card)",
          color: "var(--text-main)",
          gap: '1rem',
        }}
      >
        <div
          style={{
            width: '2.5rem',
            height: '2.5rem',
            borderRadius: '50%',
            border: "3px solid var(--border)",
            borderTopColor: '#11B76D',
            animation: 'spin 0.8s linear infinite',
          }}
        />
        <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
        <div style={{ fontSize: '0.875rem', color: "var(--text-muted)" }}>
          Loading Neoriz WhatsApp Automation...
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div
        style={{
          height: '100vh',
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'center',
          backgroundColor: "var(--bg-card)",
          color: "var(--text-main)",
          padding: '1.5rem',
          textAlign: 'center',
        }}
      >
        <AlertCircle size={40} style={{ color: "var(--danger)", marginBottom: '1rem' }} />
        <h1 style={{ fontSize: '1.25rem', fontWeight: 700, marginBottom: '0.5rem' }}>Workspace Access Error</h1>
        <p style={{ color: "var(--text-muted)", maxWidth: '28rem', marginBottom: '1.5rem' }}>{error}</p>
        <a href="/login/" className="btn btn-primary">
          Back to Login
        </a>
      </div>
    );
  }

  const renderContent = () => {
    const pathname = currentPath.split('?')[0];
    if (pathname.startsWith('/app/platform/') && !isPlatformUser) {
      return <div role="alert"><h1>Platform access denied</h1><p>This console is available to Super Admins.</p></div>;
    }
    if (isPlatformUser && !isInspecting && !pathname.startsWith('/app/platform/') && pathname !== '/app/account') return null;
    if (setupLocked && !setupAllowedPaths.includes(pathname)) return <SettingsPage />;
    const clientTools:Record<string,string>={'/app/consent':'consent','/app/saved-replies':'replies','/app/delivery-activity':'deliveries','/app/subscription':'subscription'};
    const platformTools:Record<string,string>={'/app/platform/health':'health','/app/platform/emails':'emails','/app/platform/email-provider':'smtp','/app/platform/billing':'billing'};
    if(clientTools[pathname])return <WorkspaceToolsPage key={pathname} resource={clientTools[pathname]}/>;
    if(platformTools[pathname])return <WorkspaceToolsPage key={pathname} platform resource={platformTools[pathname]}/>;
    switch (pathname) {
      case '/app/dashboard':
        return <DashboardPage onNavigate={navigate} />;
      case '/app/work-queue':
        return <WorkQueuePage onNavigate={navigate} />;
      case '/app/inbox':
        return <InboxPage onNavigate={navigate} />;
      case '/app/contacts':
        return <ContactsPage onNavigate={navigate} />;
      case '/app/companies':
        return <CompaniesPage />;
      case '/app/deals':
        return <DealsPage onNavigate={navigate} />;
      case '/app/tasks':
        return <TasksPage onNavigate={navigate} />;
      case '/app/automations':
        return <AutomationsPage />;
      case '/app/support':
        return <SupportPage />;
      case '/app/help-support':
        return <HelpSupportPage />;
      case '/app/growth':
        return <GrowthPage />;
      case '/app/integrations':
        return <IntegrationsPage />;
      case '/app/bookings':
        return <BookingsPage />;
      case '/app/services':
        return <ServicesPage />;
      case '/app/knowledge':
        return <KnowledgePage />;
      case '/app/team':
        return <TeamPage />;
      case '/app/reports':
        return <ReportsPage />;
      case '/app/usage':
        return <UsagePage />;
      case '/app/onboarding':
        return <OnboardingPage />;
      case '/app/account':
        return <AccountProfile />;
      case '/app/settings':
        return <SettingsPage />;
      case '/app/platform/dashboard':
        return <PlatformDashboardPage onNavigate={navigate} />;
      case '/app/platform/tenants':
        return <PlatformTenantsPage onNavigate={navigate} />;
      case '/app/platform/onboarding':
        return <PlatformOnboardingPage />;
      case '/app/platform/support':
        return <PlatformSupportPage />;
      case '/app/platform/staff-requests':
        return <PlatformStaffRequestsPage />;
      case '/app/platform/matrix':
        return <PlatformMatrixPage />;
      case '/app/platform/users':
      case '/app/platform/operations':
        return isPlatformUser ? <PlatformOperationsPage /> : <NotFoundPage onNavigate={navigate} />;
      case '/app/platform/system-settings':
        return isPlatformUser ? <PlatformSystemSettingsPage /> : <NotFoundPage onNavigate={navigate} />;
      case '/app/platform/audit':
        return <PlatformAuditPage />;
      default:
        return <NotFoundPage onNavigate={navigate} />;
    }
  };

  return (
    <Shell currentPath={currentPath} onNavigate={navigate}>
      {renderContent()}
    </Shell>
  );
};

