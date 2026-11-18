import { NavLink, Link, useLocation } from 'react-router-dom';
import React, { useState, useEffect, useRef } from 'react';
import {
  LayoutDashboard,
  Bell,
  LayoutTemplate,
  Send,
  Layers,
  Mail,
  BookOpen,
  Settings,
  ShieldAlert,
  ChevronsUpDown,
  Plus,
  Check,
  LogOut,
  Menu,
  X,
} from 'lucide-react';
import { useAuth } from '../lib/auth';
import { apiFetch } from '../lib/api';
import { describeError } from '../lib/errors';
import Button from './ui/Button';
import Input from './ui/Input';

const NAV_GROUPS = [
  {
    title: 'MONITOR',
    items: [
      { to: '/', label: 'Overview', exact: true, icon: LayoutDashboard },
      { to: '/notifications', label: 'Notifications', exact: false, icon: Bell },
    ],
  },
  {
    title: 'CHANNELS & TEMPLATES',
    items: [
      { to: '/templates', label: 'Templates', exact: false, icon: LayoutTemplate },
      { to: '/send', label: 'Send', exact: false, icon: Send, adminOnly: true },
      { to: '/bulk', label: 'Bulk', exact: false, icon: Layers, adminOnly: true },
      {
        to: '/invitations',
        label: 'Invitations',
        exact: false,
        icon: Mail,
        badgeKey: 'invitations',
      },
    ],
  },
  {
    title: 'DEVELOPERS',
    items: [
      { to: '/docs', label: 'Documentation', exact: false, icon: BookOpen },
      { to: '/settings', label: 'Settings', exact: false, icon: Settings },
      {
        to: '/platform',
        label: 'Platform',
        exact: false,
        icon: ShieldAlert,
        superadminOnly: true,
      },
    ],
  },
];

function RoleBadge({ role }) {
  if (!role) return null;
  return (
    <span className="text-[11px] font-medium text-[#78716C] bg-[#F5F5F4] px-1.5 py-0.5 rounded-[4px] border border-[#E7E5E4] capitalize">
      {role}
    </span>
  );
}

export default function Layout({ children }) {
  const {
    user,
    logout,
    isAdmin,
    isSuperadmin,
    workspace,
    workspaces,
    switchWorkspace,
  } = useAuth();
  const location = useLocation();
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const [pendingInvitesCount, setPendingInvitesCount] = useState(0);

  // Workspace switcher
  const [switcherOpen, setSwitcherOpen] = useState(false);
  const switcherRef = useRef(null);

  // Create workspace modal
  const [createOpen, setCreateOpen] = useState(false);
  const [createName, setCreateName] = useState('');
  const [createError, setCreateError] = useState(null);
  const [createLoading, setCreateLoading] = useState(false);

  // Poll pending invitations count
  useEffect(() => {
    let mounted = true;
    function fetchInvites() {
      apiFetch('/invitations')
        .then((data) => {
          if (mounted && Array.isArray(data)) {
            setPendingInvitesCount(data.length);
          }
        })
        .catch(() => {});
    }
    fetchInvites();
    const interval = setInterval(fetchInvites, 30000);
    return () => {
      mounted = false;
      clearInterval(interval);
    };
  }, [location.pathname]);

  // Close switcher on outside click
  useEffect(() => {
    if (!switcherOpen) return;
    function handleClick(e) {
      if (switcherRef.current && !switcherRef.current.contains(e.target)) {
        setSwitcherOpen(false);
      }
    }
    document.addEventListener('mousedown', handleClick);
    return () => document.removeEventListener('mousedown', handleClick);
  }, [switcherOpen]);

  async function handleCreateWorkspace(e) {
    e.preventDefault();
    if (!createName.trim()) return;
    setCreateLoading(true);
    setCreateError(null);
    try {
      const response = await apiFetch('/workspaces', {
        method: 'POST',
        body: JSON.stringify({ name: createName.trim() }),
      });
      setCreateOpen(false);
      setCreateName('');
      await switchWorkspace(response.id);
    } catch (err) {
      const desc = describeError(err);
      setCreateError(desc.title + ': ' + desc.message);
    } finally {
      setCreateLoading(false);
    }
  }

  return (
    <div className="min-h-screen flex flex-col md:flex-row bg-[#FAFAF9] text-[#1C1917]">
      {/* Mobile top bar */}
      <div className="md:hidden flex items-center justify-between px-4 py-3 bg-white border-b border-[#E7E5E4] sticky top-0 z-30">
        <div className="flex items-center gap-2">
          <div className="w-6 h-6 rounded-[5px] bg-[#4F46E5] flex items-center justify-center text-white text-xs font-bold">
            N
          </div>
          <span className="font-semibold text-sm tracking-tight text-[#1C1917]">
            Notify
          </span>
        </div>
        <div className="flex items-center gap-2">
          <Link
            to="/invitations"
            className="relative p-2 rounded-[6px] text-[#78716C] hover:text-[#1C1917] hover:bg-[#F5F5F4] transition-colors"
            title="Workspace Invitations"
            aria-label="Workspace Invitations"
          >
            <Mail className="w-4 h-4" strokeWidth={1.5} />
            {pendingInvitesCount > 0 && (
              <span className="absolute top-1 right-1 flex h-4 min-w-[16px] px-1 items-center justify-center rounded-full bg-[#4F46E5] text-[10px] font-semibold text-white">
                {pendingInvitesCount}
              </span>
            )}
          </Link>
          <button
            onClick={() => setMobileMenuOpen((o) => !o)}
            className="p-2 rounded-[6px] text-[#78716C] hover:text-[#1C1917] hover:bg-[#F5F5F4]"
            aria-label="Toggle menu"
          >
            {mobileMenuOpen ? (
              <X className="w-5 h-5" strokeWidth={1.5} />
            ) : (
              <Menu className="w-5 h-5" strokeWidth={1.5} />
            )}
          </button>
        </div>
      </div>

      {/* Sidebar (232px width) */}
      <aside
        className={`${
          mobileMenuOpen ? 'block' : 'hidden'
        } md:flex md:flex-col w-full md:w-[232px] md:min-w-[232px] bg-white border-b md:border-b-0 md:border-r border-[#E7E5E4] md:min-h-screen shrink-0 z-20`}
      >
        {/* Logo and Wordmark */}
        <div className="px-4 py-4.5 hidden md:flex items-center justify-between">
          <div className="flex items-center gap-2.5">
            <div className="w-6 h-6 rounded-[5px] bg-[#4F46E5] flex items-center justify-center text-white text-xs font-bold shadow-xs">
              N
            </div>
            <span className="font-semibold text-[15px] tracking-tight text-[#1C1917]">
              Notify
            </span>
          </div>
        </div>

        {/* Workspace Switcher */}
        <div className="px-3 pb-3 relative" ref={switcherRef}>
          <button
            type="button"
            onClick={() => setSwitcherOpen((o) => !o)}
            className="w-full flex items-center justify-between gap-2 px-2.5 py-2 rounded-[6px] bg-[#FAFAF9] hover:bg-[#F5F5F4] border border-[#E7E5E4] text-left transition-colors cursor-pointer group"
          >
            <div className="flex items-center gap-2 min-w-0">
              <span className="text-xs font-medium text-[#1C1917] truncate">
                {workspace?.name ?? 'No workspace'}
              </span>
              {workspace?.role && <RoleBadge role={workspace.role} />}
            </div>
            <ChevronsUpDown
              className="w-3.5 h-3.5 text-[#78716C] shrink-0 group-hover:text-[#1C1917]"
              strokeWidth={1.5}
            />
          </button>

          {switcherOpen && (
            <div className="absolute left-3 right-3 mt-1.5 bg-white border border-[#E7E5E4] rounded-[8px] shadow-md z-40 py-1 overflow-hidden">
              <div className="px-2.5 py-1 text-[11px] font-semibold text-[#78716C] uppercase tracking-wider">
                Workspaces
              </div>
              <div className="max-h-48 overflow-y-auto">
                {(workspaces || []).map((ws) => (
                  <button
                    key={ws.id}
                    type="button"
                    onClick={() => {
                      switchWorkspace(ws.id);
                      setSwitcherOpen(false);
                    }}
                    className={`w-full flex items-center justify-between px-2.5 py-1.5 text-xs text-left transition-colors cursor-pointer ${
                      ws.id === workspace?.id
                        ? 'bg-[#F5F5F4] text-[#1C1917] font-medium'
                        : 'text-[#57534E] hover:bg-[#FAFAF9] hover:text-[#1C1917]'
                    }`}
                  >
                    <div className="flex items-center gap-1.5 min-w-0">
                      <span className="truncate">{ws.name}</span>
                      {(ws.is_default || ws.slug === 'default') && (
                        <span className="px-1.5 py-0.5 rounded text-[10px] font-medium bg-[#F5F5F4] text-[#78716C] border border-[#E7E5E4] shrink-0">
                          Default
                        </span>
                      )}
                    </div>
                    {ws.id === workspace?.id && (
                      <Check
                        className="w-3.5 h-3.5 text-[#4F46E5] shrink-0"
                        strokeWidth={2}
                      />
                    )}
                  </button>
                ))}
              </div>
              <div className="border-t border-[#E7E5E4] mt-1 pt-1">
                <button
                  type="button"
                  onClick={() => {
                    setCreateOpen(true);
                    setSwitcherOpen(false);
                  }}
                  className="w-full flex items-center gap-1.5 px-2.5 py-1.5 text-xs text-[#4F46E5] hover:bg-[#F5F5F4] font-medium transition-colors cursor-pointer"
                >
                  <Plus className="w-3.5 h-3.5" strokeWidth={1.5} />
                  <span>Create workspace</span>
                </button>
              </div>
            </div>
          )}
        </div>

        {/* Navigation Sections */}
        <nav className="flex-1 px-3 py-2 space-y-4 overflow-y-auto">
          {NAV_GROUPS.map((group) => {
            const visibleItems = group.items.filter(
              (item) =>
                (!item.adminOnly || isAdmin) &&
                (!item.superadminOnly || isSuperadmin)
            );
            if (visibleItems.length === 0) return null;

            return (
              <div key={group.title} className="space-y-1">
                <div className="px-2.5 py-1 text-[11px] font-semibold tracking-wider text-[#A8A29E] uppercase">
                  {group.title}
                </div>
                {visibleItems.map((item) => {
                  const Icon = item.icon;
                  const isInvitations = item.badgeKey === 'invitations';
                  return (
                    <NavLink
                      key={item.to}
                      to={item.to}
                      end={item.exact}
                      onClick={() => setMobileMenuOpen(false)}
                      className={({ isActive }) =>
                        `flex items-center justify-between px-2.5 py-1.5 rounded-[6px] text-xs font-medium transition-colors ${
                          isActive
                            ? 'bg-[#F5F5F4] text-[#1C1917]'
                            : 'text-[#78716C] hover:text-[#1C1917] hover:bg-[#FAFAF9]'
                        }`
                      }
                    >
                      {({ isActive }) => (
                        <>
                          <div className="flex items-center gap-2.5 min-w-0">
                            <Icon
                              className={`w-4 h-4 shrink-0 transition-colors ${
                                isActive ? 'text-[#4F46E5]' : 'text-[#78716C]'
                              }`}
                              strokeWidth={1.5}
                            />
                            <span className="truncate">{item.label}</span>
                          </div>
                          {isInvitations && pendingInvitesCount > 0 && (
                            <span className="ml-2 inline-flex items-center justify-center px-1.5 py-0.2 rounded-full text-[10px] font-semibold leading-none text-white bg-[#4F46E5]">
                              {pendingInvitesCount}
                            </span>
                          )}
                        </>
                      )}
                    </NavLink>
                  );
                })}
              </div>
            );
          })}
        </nav>

        {/* Sidebar Footer User Area */}
        <div className="p-3 border-t border-[#E7E5E4] space-y-2 bg-white">
          <div className="flex items-center justify-between px-1">
            <div className="flex items-center gap-2 min-w-0">
              <span className="w-1.5 h-1.5 rounded-full bg-[#15803D] shrink-0" />
              <p className="text-[11px] text-[#78716C] truncate" title={user?.full_name || user?.email}>
                {user?.full_name || user?.email}
              </p>
            </div>
            <button
              onClick={logout}
              title="Log out"
              className="p-1 rounded-[4px] text-[#78716C] hover:text-[#1C1917] hover:bg-[#F5F5F4] transition-colors cursor-pointer"
            >
              <LogOut className="w-3.5 h-3.5" strokeWidth={1.5} />
            </button>
          </div>
        </div>
      </aside>

      {/* Main Content Area */}
      <main className="flex-1 min-w-0 p-5 sm:p-7 lg:p-8 overflow-auto">
        <div className="max-w-[1120px]">
          <React.Fragment key={workspace?.id}>{children}</React.Fragment>
        </div>
      </main>

      {/* Create Workspace Modal */}
      {createOpen && (
        <div className="fixed inset-0 bg-black/40 z-50 flex items-center justify-center p-4">
          <div className="bg-white border border-[#E7E5E4] rounded-[12px] max-w-sm w-full p-6 space-y-4 shadow-xl">
            <div>
              <h2 className="text-base font-semibold text-[#1C1917]">
                Create workspace
              </h2>
              <p className="text-xs text-[#78716C] mt-0.5">
                Workspaces keep notifications, API keys, and team members isolated.
              </p>
            </div>
            <form onSubmit={handleCreateWorkspace} className="space-y-4">
              <Input
                id="ws-name"
                label="Workspace name"
                type="text"
                required
                value={createName}
                onChange={(e) => setCreateName(e.target.value)}
                placeholder="Acme Corp"
                autoFocus
              />
              {createError && (
                <p className="text-xs text-[#B91C1C]">{createError}</p>
              )}
              <div className="flex gap-2.5 pt-1">
                <Button
                  variant="secondary"
                  size="sm"
                  className="flex-1"
                  onClick={() => {
                    setCreateOpen(false);
                    setCreateName('');
                    setCreateError(null);
                  }}
                >
                  Cancel
                </Button>
                <Button
                  type="submit"
                  variant="primary"
                  size="sm"
                  className="flex-1"
                  loading={createLoading}
                  disabled={!createName.trim()}
                >
                  Create
                </Button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
