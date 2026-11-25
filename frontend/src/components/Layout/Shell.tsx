import React, { useEffect, useState } from 'react';
import { useAuth } from '../../context/AuthContext';
import { InspectionBanner } from './InspectionBanner';
import { WorkspaceSwitcher } from './WorkspaceSwitcher';
import {
  LayoutDashboard,
  MessageSquare,
  Users,
  Building,
  Kanban,
  CheckSquare,
  CalendarCheck,
  Package,
  BookOpen,
  UserCheck,
  Settings,
  ShieldAlert,
  Server,
  Layers,
  FileText,
  LogOut,
  ExternalLink,
  ShieldCheck,
  BarChart2,
  Gauge,
  Compass,
  UserPlus,
  Zap,
  Headphones,
  TrendingUp,
  Plug,
  Clock,
} from 'lucide-react';

interface ShellProps {
  currentPath: string;
  onNavigate: (path: string) => void;
  children: React.ReactNode;
}

export const Shell: React.FC<ShellProps> = ({ currentPath, onNavigate, children }) => {
  const { user, tenant, membership, capabilities, isInspecting } = useAuth();
  const [navigationOpen, setNavigationOpen] = useState(false);
  useEffect(() => { setNavigationOpen(false); }, [currentPath]);
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => { if (event.key === 'Escape') setNavigationOpen(false); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);

  const isCapAllowed = (capKey: string) => capabilities[capKey]?.allowed === true;

  // Determine whether this shell operates in the Super Admin Console or a Client Workspace
  const isPlatformUser = Boolean(user?.is_superuser || (user as any)?.is_platform_operator || (user as any)?.platform_role);
  const isSuperAdminConsole = Boolean(isPlatformUser && !isInspecting);

  const manager=membership?.role==='OWNER'||membership?.role==='ADMIN'||user?.is_superuser;
  const tenantNavItems = [

    { label: 'My Account', path: '/app/account', icon: UserCheck, cap: '' },
    {label:'Consent Directory',path:'/app/consent',icon:ShieldCheck,cap:'growth'},
    {label:'Saved Replies',path:'/app/saved-replies',icon:MessageSquare,cap:'inbox'},
    ...(manager?[{label:'Delivery Activity',path:'/app/delivery-activity',icon:MessageSquare,cap:'inbox'},{label:'Subscription & Payments',path:'/app/subscription',icon:Gauge,cap:''}]:[]),
    { label: 'Overview', path: '/app/dashboard', icon: LayoutDashboard, cap: 'dashboard' },
    { label: 'Work Queue', path: '/app/work-queue', icon: Clock, cap: 'work_queue' },
    { label: 'WhatsApp Inbox', path: '/app/inbox', icon: MessageSquare, cap: 'inbox' },
    { label: 'Contacts', path: '/app/contacts', icon: Users, cap: 'contacts' },
    { label: 'Companies', path: '/app/companies', icon: Building, cap: 'companies' },
    { label: 'Deals Pipeline', path: '/app/deals', icon: Kanban, cap: 'deals' },
    { label: 'Tasks & Activities', path: '/app/tasks', icon: CheckSquare, cap: 'tasks' },
    { label: 'Workflow Automations', path: '/app/automations', icon: Zap, cap: 'automations' },
    { label: 'Support & Onboarding', path: '/app/support', icon: Headphones, cap: 'support' },
    { label: 'Growth & Broadcasts', path: '/app/growth', icon: TrendingUp, cap: 'growth' },
    { label: 'Integration Centre', path: '/app/integrations', icon: Plug, cap: 'integrations' },
    { label: 'Bookings', path: '/app/bookings', icon: CalendarCheck, cap: 'bookings' },
    { label: 'Catalog Services', path: '/app/services', icon: Package, cap: 'services' },
    { label: 'Knowledge Base', path: '/app/knowledge', icon: BookOpen, cap: 'knowledge' },
    { label: 'Team & Staff', path: '/app/team', icon: UserCheck, cap: 'team' },
    { label: 'Reports', path: '/app/reports', icon: BarChart2, cap: 'reports' },
    { label: 'Usage & Quotas', path: '/app/usage', icon: Gauge, cap: 'dashboard' },
    { label: 'Setup Checklist', path: '/app/onboarding', icon: Compass, cap: 'onboarding' },
    { label: 'Connection & Profile', path: '/app/settings', icon: Settings, cap: 'whatsapp_settings' },
    { label: 'Help & Support', path: '/app/help-support', icon: Headphones, cap: 'help_support' },
  ];

  const superAdminNavItems = [
    { label: 'My Account', path: '/app/account', icon: UserCheck },
    { label: 'Software Overview', path: '/app/platform/dashboard', icon: Server },
    { label: 'Client Workspaces', path: '/app/platform/tenants', icon: Layers },
    { label: 'Staff Access Requests', path: '/app/platform/staff-requests', icon: UserPlus },
    { label: 'Plans & Menus', path: '/app/platform/matrix', icon: ShieldAlert },
    { label: 'Users', path: '/app/platform/users', icon: Users },
    {label:'Client Onboarding',path:'/app/platform/onboarding',icon:Compass},
    {label:'Subscriptions & Payments',path:'/app/platform/billing',icon:Gauge},
    {label:'Operations Health',path:'/app/platform/health',icon:Server},
    {label:'Email Delivery',path:'/app/platform/emails',icon:MessageSquare},
    {label:'Email Provider',path:'/app/platform/email-provider',icon:Settings},
    { label: 'Security & Audit', path: '/app/platform/audit', icon: FileText },
    { label: 'Support & Escalations', path: '/app/platform/support', icon: Headphones },
    { label: 'System Settings', path: '/app/platform/system-settings', icon: Settings },
  ];

  const setupLocked = !isSuperAdminConsole && tenant?.meta_setup_required === true && tenant?.meta_setup_ready !== true;
  const filteredTenantNav = tenantNavItems.filter((item) => !item.cap || isCapAllowed(item.cap));
  const navButton = (item: {label:string;path:string;icon?:any}) => <button key={item.path} aria-current={currentPath === item.path ? 'page' : undefined} onClick={() => {setNavigationOpen(false);onNavigate(item.path);}} style={{display:'flex',alignItems:'center',gap:'.65rem',width:'100%',padding:'.65rem .75rem',border:0,borderRadius:'.5rem',background:currentPath === item.path ? "var(--primary-light)" : 'transparent',color:currentPath === item.path ? "var(--primary)" : "var(--text-main)",textAlign:'left',cursor:'pointer'}}>{item.icon && <item.icon size={17}/>}<span>{item.label}</span></button>;
  const group = (name:string, items: typeof tenantNavItems) => {
    const visible=items.filter(item=>filteredTenantNav.includes(item));
    return visible.length ? <details key={name} open={visible.some(item=>currentPath===item.path)} style={{margin:'.3rem 0'}}><summary style={{cursor:'pointer',padding:'.75rem',fontWeight:700,color:"var(--text-main)"}}>{name}</summary><div style={{paddingLeft:'.65rem'}}>{visible.map(navButton)}</div></details> : null;
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100vh', overflow: 'hidden' }}>
      <style>{`
        .workspace-menu-toggle, .workspace-mobile-switcher { display: none; }
        .workspace-sidebar { flex-shrink: 0; }
        @media (max-width: 767px) {
          .workspace-menu-toggle { display: inline-flex; flex-shrink: 0; }
          .workspace-mobile-switcher { display: block; padding: .75rem; }
          .workspace-sidebar { display: none !important; }
          .workspace-sidebar.is-open { display: flex !important; position: absolute; top: 3.75rem; bottom: 0; left: 0; max-width: 85vw; overflow-y: auto; box-shadow: 8px 0 30px #0008; }
          .workspace-header { padding: 0 .5rem !important; gap: .5rem; }
          .workspace-header > div { min-width: 0; }
          .workspace-header > div:last-child { display: none !important; }
          .workspace-header > div > div { min-width: 0; }
          .workspace-header > div > div > div:first-child { display: none !important; }
          .workspace-header > div > div > div:nth-child(2) { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
          .workspace-header > div > div > div:last-child { display: none !important; }
          .workspace-main { padding: .5rem !important; }
        }
      `}</style>
      <InspectionBanner />

      <div style={{ display: 'flex', flex: 1, overflow: 'hidden' }}>
        {/* Left Sidebar */}
        <aside id="workspace-navigation" className={`workspace-sidebar ${navigationOpen ? 'is-open' : ''}`}
          style={{
            width: '16.5rem',
            backgroundColor: isSuperAdminConsole ? "var(--bg-card)" : "var(--bg-card)",
            borderRight: isSuperAdminConsole ? "1px solid var(--border)" : "1px solid var(--border)",
            display: 'flex',
            flexDirection: 'column',
            zIndex: 30,
          }}
        >
          <div className="workspace-mobile-switcher"><WorkspaceSwitcher /></div>
          {/* Brand Header */}
          <div
            style={{
              padding: '1.15rem 1.25rem',
              borderBottom: isSuperAdminConsole ? "1px solid var(--border)" : "1px solid var(--border)",
              display: 'flex',
              alignItems: 'center',
              gap: '0.75rem',
              backgroundColor: isSuperAdminConsole ? "var(--bg-card)" : 'transparent',
            }}
          >
            <img
              src="/static/logo.png"
              alt="Neoriz Mascot Logo"
              style={{ width: '2.25rem', height: '2.25rem', borderRadius: '0.5rem', objectFit: 'contain' }}
              onError={(e) => {
                (e.target as HTMLElement).style.display = 'none';
              }}
            />
            <div>
              <div style={{ fontSize: '0.88rem', fontWeight: 800, color: "var(--text-main)", lineHeight: 1.2 }}>
                Neoriz Automation
              </div>
              {isSuperAdminConsole ? (
                <div
                  style={{
                    display: 'inline-flex',
                    alignItems: 'center',
                    gap: '0.25rem',
                    fontSize: '0.7rem',
                    color: "var(--primary)",
                    fontWeight: 700,
                    textTransform: 'uppercase',
                    letterSpacing: '0.04em',
                    marginTop: '2px',
                  }}
                >
                  <ShieldCheck size={12} /> Super Admin Console
                </div>
              ) : (
                <div style={{ fontSize: '0.725rem', color: "var(--primary)", fontWeight: 600 }}>
                  Client Workspace
                </div>
              )}
            </div>
          </div>

          {/* Navigation Links */}
          <div style={{ flex: 1, overflowY: 'auto', padding: '1rem 0.75rem' }}>
            {isSuperAdminConsole ? <nav aria-label="Software management">
              {navButton(superAdminNavItems[1])}
              <details open={currentPath.includes('tenants') || currentPath.includes('staff-requests') || currentPath.includes('/platform/onboarding')}><summary style={{padding:'.75rem',cursor:'pointer',fontWeight:700}}>Clients</summary>{navButton(superAdminNavItems[2])}{navButton(superAdminNavItems[6])}{navButton(superAdminNavItems[3])}</details>
              <details open={currentPath.includes('/billing') || currentPath.includes('/matrix')}><summary style={{padding:'.75rem',cursor:'pointer',fontWeight:700}}>Billing &amp; Plans</summary>{navButton(superAdminNavItems[7])}{navButton(superAdminNavItems[4])}</details>
              <details open={currentPath.includes('/health')||currentPath.includes('/email')}><summary style={{padding:'.75rem',cursor:'pointer',fontWeight:700}}>Operations &amp; Email</summary>{superAdminNavItems.slice(8,11).map(navButton)}</details>
              <details open><summary style={{padding:'.75rem',cursor:'pointer',fontWeight:700}}>Platform Administration</summary>{navButton(superAdminNavItems[5])}{navButton(superAdminNavItems[12])}{navButton(superAdminNavItems[11])}{navButton(superAdminNavItems[13])}</details>
              {navButton(superAdminNavItems[0])}
            </nav> : <nav aria-label="Client workspace">
              {setupLocked ? <>{navButton({label:'Meta Setup',path:'/app/settings',icon:Settings})}{navButton({label:'Setup Checklist',path:'/app/onboarding',icon:Compass})}{navButton({label:'Help & Support',path:'/app/help-support',icon:Headphones})}{navButton(tenantNavItems[0])}</> : <>
                {filteredTenantNav.filter(item=>item.path==='/app/dashboard').map(navButton)}
                {group('WhatsApp',tenantNavItems.filter(item=>['/app/inbox','/app/consent','/app/saved-replies','/app/delivery-activity','/app/settings','/app/automations','/app/growth','/app/integrations'].includes(item.path)))}
                {group('CRM',tenantNavItems.filter(item=>['/app/work-queue','/app/contacts','/app/companies','/app/deals','/app/tasks'].includes(item.path)))}
                {group('Business',tenantNavItems.filter(item=>['/app/bookings','/app/services','/app/knowledge'].includes(item.path)))}
                {group('Administration',tenantNavItems.filter(item=>['/app/team','/app/subscription','/app/onboarding','/app/reports','/app/usage','/app/account','/app/support','/app/help-support'].includes(item.path)))}
              </>}
            </nav>}
          </div>

          {/* User Profile Footer */}
          <div
            style={{
              padding: '0.875rem',
              borderTop: isSuperAdminConsole ? "1px solid var(--border)" : "1px solid var(--border)",
              backgroundColor: isSuperAdminConsole ? "var(--bg-card)" : "var(--bg-card)",
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
            }}
          >
            <div style={{ overflow: 'hidden' }}>
              <div style={{ fontSize: '0.825rem', fontWeight: 600, color: "var(--text-main)", whiteSpace: 'nowrap', textOverflow: 'ellipsis', overflow: 'hidden' }}>
                {user?.full_name}
              </div>
              <div style={{ fontSize: '0.7rem', color: isSuperAdminConsole ? "var(--primary)" : "var(--text-muted)" }}>
                @{user?.username} • {isSuperAdminConsole ? 'Super Admin' : (membership?.role_display || 'Client Staff')}
              </div>
            </div>
            <a
              href="/logout/"
              title="Sign Out"
              style={{
                color: "var(--text-muted)",
                padding: '0.4rem',
                borderRadius: '0.375rem',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                textDecoration: 'none',
              }}
            >
              <LogOut size={16} />
            </a>
          </div>
        </aside>

        {/* Main Content Area */}
        <div style={{ flex: 1, minWidth: 0, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
          {/* Top Bar Header */}
          <header className="workspace-header"
            style={{
              height: '3.75rem',
              backgroundColor: isSuperAdminConsole ? "var(--bg-card)" : "var(--bg-card)",
              borderBottom: isSuperAdminConsole ? "1px solid var(--border)" : "1px solid var(--border)",
              padding: '0 1.5rem',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              zIndex: 20,
            }}
          >
            <button className="btn btn-secondary workspace-menu-toggle" aria-label={navigationOpen ? 'Close navigation' : 'Open navigation'} aria-expanded={navigationOpen} aria-controls="workspace-navigation" onClick={() => setNavigationOpen(open => !open)}>Menu</button>
            {/* Left Context & Branding */}
            <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
              {isSuperAdminConsole ? (
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                  <span
                    style={{
                      background: 'var(--primary-light)',
                      color: "var(--primary)",
                      border: '1px solid var(--primary-border)',
                      padding: '0.3rem 0.75rem',
                      borderRadius: '6px',
                      fontSize: '0.825rem',
                      fontWeight: 700,
                      display: 'flex',
                      alignItems: 'center',
                      gap: '0.4rem',
                    }}
                  >
                    <ShieldCheck size={14} /> Super Admin Console
                  </span>
                  <span style={{ fontSize: '0.8rem', color: "var(--text-muted)" }}>
                    Software Management
                  </span>
                </div>
              ) : (
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
                  {/* Client Logo & Product UI Logo */}
                  <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                    <img
                      src="/static/logo.png"
                      alt="Neoriz Product"
                      style={{ width: '1.75rem', height: '1.75rem', borderRadius: '5px', objectFit: 'contain' }}
                      title="Neoriz WhatsApp Automation"
                    />
                    <span style={{ color: "var(--text-muted)", fontSize: '1rem', fontWeight: 300 }}>/</span>
                    {tenant?.logo_url ? (
                      <img
                        src={tenant.logo_url}
                        alt={`${tenant.name} Logo`}
                        style={{
                          width: '1.75rem',
                          height: '1.75rem',
                          borderRadius: '5px',
                          objectFit: 'contain',
                          border: "1px solid var(--border)",
                          background: '#ffffff',
                          padding: '2px',
                        }}
                        onError={(e) => {
                          (e.target as HTMLElement).style.display = 'none';
                        }}
                      />
                    ) : (
                      <div
                        style={{
                          width: '1.75rem',
                          height: '1.75rem',
                          borderRadius: '5px',
                          backgroundColor: "var(--primary-light)",
                          color: "var(--primary)",
                          fontWeight: 700,
                          fontSize: '0.75rem',
                          display: 'flex',
                          alignItems: 'center',
                          justifyContent: 'center',
                          border: '1px solid #059669',
                        }}
                      >
                        {(tenant?.name || 'W').substring(0, 2).toUpperCase()}
                      </div>
                    )}
                  </div>

                  {/* Header Title with Business Name */}
                  <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                    <span style={{ fontSize: '0.925rem', fontWeight: 700, color: "var(--text-main)" }}>
                      Client Workspace: {tenant?.name || 'Workspace'}
                    </span>
                    {tenant && (
                      <span className={`badge ${tenant.is_active ? 'badge-green' : 'badge-red'}`} style={{ fontSize: '0.7rem' }}>
                        {tenant.is_active ? 'Active' : 'Suspended'}
                      </span>
                    )}
                  </div>

                  <WorkspaceSwitcher />
                </div>
              )}
            </div>

            {/* Right Quick Links */}
            <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
              {user && !user.email_verified && (
                <a
                  href="/verification-notice"
                  className="badge badge-amber"
                  style={{ textDecoration: 'none', cursor: 'pointer' }}
                >
                  Verify Email
                </a>
              )}

              <a
                href="/"
                target="_blank"
                rel="noreferrer"
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '0.35rem',
                  color: "var(--text-muted)",
                  fontSize: '0.8rem',
                  textDecoration: 'none',
                }}
              >
                Marketing Site <ExternalLink size={13} />
              </a>


            </div>
          </header>

          {/* Page Body */}
          <main className="workspace-main" style={{ flex: 1, overflowY: 'auto', padding: '1.5rem', backgroundColor: "var(--bg-card)" }}>
            {children}
          </main>
        </div>
      </div>
    </div>
  );
};

