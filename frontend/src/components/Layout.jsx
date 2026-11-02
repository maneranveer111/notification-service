import { NavLink, Outlet } from 'react-router-dom';
import React, { useState, useEffect, useRef } from 'react';
import { useAuth } from '../lib/auth';
import { apiFetch } from '../lib/api';
import { describeError } from '../lib/errors';

const NAV = [
  { to: '/', label: 'Overview', exact: true },
  { to: '/docs', label: 'Docs', exact: false },
  { to: '/notifications', label: 'Notifications', exact: false },
  { to: '/templates', label: 'Templates', exact: false },
  { to: '/send', label: 'Send', exact: false, adminOnly: true },
  { to: '/bulk', label: 'Bulk', exact: false, adminOnly: true },
  { to: '/settings', label: 'Settings', exact: false },
  { to: '/platform', label: 'Platform', exact: false, superadminOnly: true },
];

function NavItem({ to, label, exact, onClick }) {
  return (
    <NavLink
      to={to}
      end={exact}
      onClick={onClick}
      className={({ isActive }) =>
        `block px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
          isActive
            ? 'bg-blue-600 text-white'
            : 'text-gray-300 hover:bg-gray-700 hover:text-white'
        }`
      }
    >
      {label}
    </NavLink>
  );
}

function RoleBadge({ role }) {
  const styles = {
    owner: 'bg-purple-700 text-purple-100',
    admin: 'bg-blue-700 text-blue-100',
    member: 'bg-gray-700 text-gray-300',
  };
  return (
    <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${styles[role] || styles.member}`}>
      {role}
    </span>
  );
}

export default function Layout({ children }) {
  const { user, logout, isAdmin, isSuperadmin, workspace, workspaces, switchWorkspace } = useAuth();
  const [open, setOpen] = useState(false);

  // Workspace switcher
  const [switcherOpen, setSwitcherOpen] = useState(false);
  const switcherRef = useRef(null);

  // Create workspace modal
  const [createOpen, setCreateOpen] = useState(false);
  const [createName, setCreateName] = useState('');
  const [createError, setCreateError] = useState(null);
  const [createLoading, setCreateLoading] = useState(false);

  const visibleNav = NAV.filter((n) => (!n.adminOnly || isAdmin) && (!n.superadminOnly || isSuperadmin));

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
    <div className="min-h-screen flex flex-col md:flex-row bg-gray-950 text-white">
      {/* Mobile top bar */}
      <div className="md:hidden flex items-center justify-between px-4 py-3 bg-gray-900 border-b border-gray-800">
        <span className="font-bold text-blue-400">Notify</span>
        <button
          onClick={() => setOpen((o) => !o)}
          className="p-2 rounded hover:bg-gray-700"
          aria-label="Toggle menu"
        >
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            {open ? (
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            ) : (
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" />
            )}
          </svg>
        </button>
      </div>

      {/* Sidebar */}
      <aside
        className={`${
          open ? 'block' : 'hidden'
        } md:flex md:flex-col w-full md:w-56 bg-gray-900 border-b md:border-b-0 md:border-r border-gray-800 md:min-h-screen`}
      >
        <div className="px-4 py-5 hidden md:block">
          <span className="font-bold text-blue-400 text-lg">Notify</span>
        </div>

        {/* Workspace Switcher */}
        <div className="px-3 pb-3 relative" ref={switcherRef}>
          <button
            type="button"
            onClick={() => setSwitcherOpen((o) => !o)}
            className="w-full flex items-center justify-between gap-2 px-3 py-2 rounded-lg bg-gray-800 hover:bg-gray-700 border border-gray-700 text-left transition-colors"
          >
            <span className="text-sm font-medium text-white truncate">
              {workspace?.name ?? 'No workspace'}
            </span>
            <div className="flex items-center gap-1.5 shrink-0">
              {workspace?.role && <RoleBadge role={workspace.role} />}
              <svg className="w-3.5 h-3.5 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
              </svg>
            </div>
          </button>

          {switcherOpen && (
            <div className="absolute left-3 right-3 mt-1 bg-gray-800 border border-gray-700 rounded-lg shadow-xl z-40 py-1 overflow-hidden">
              {(workspaces || []).map((ws) => (
                <button
                  key={ws.id}
                  type="button"
                  onClick={() => { switchWorkspace(ws.id); setSwitcherOpen(false); }}
                  className="w-full flex items-center justify-between px-3 py-2 text-sm text-gray-200 hover:bg-gray-700 transition-colors"
                >
                  <span className="truncate">{ws.name}</span>
                  {ws.id === workspace?.id && (
                    <span className="text-blue-400 text-xs ml-2">✓</span>
                  )}
                </button>
              ))}
              <div className="border-t border-gray-700 mt-1 pt-1">
                <button
                  type="button"
                  onClick={() => { setCreateOpen(true); setSwitcherOpen(false); }}
                  className="w-full flex items-center gap-2 px-3 py-2 text-sm text-blue-400 hover:bg-gray-700 transition-colors"
                >
                  <span>+ Create workspace</span>
                </button>
              </div>
            </div>
          )}
        </div>

        <nav className="flex-1 px-3 pb-4 space-y-1">
          {visibleNav.map((n) => (
            <NavItem key={n.to} {...n} onClick={() => setOpen(false)} />
          ))}
        </nav>

        {/* User area */}
        <div className="px-4 py-4 border-t border-gray-800 space-y-1">
          <p className="text-xs text-gray-400 truncate">{user?.email}</p>
          <button
            onClick={logout}
            className="mt-2 block w-full text-left px-3 py-1.5 text-sm text-gray-400 hover:text-white hover:bg-gray-700 rounded-lg transition-colors"
          >
            Log out
          </button>
        </div>
      </aside>

      {/* Main */}
      <main className="flex-1 p-4 md:p-6 overflow-auto">
        <React.Fragment key={workspace?.id}>
          {children}
        </React.Fragment>
      </main>

      {/* Create Workspace Modal */}
      {createOpen && (
        <div className="fixed inset-0 bg-black bg-opacity-40 z-50 flex items-center justify-center p-4">
          <div className="bg-gray-900 border border-gray-700 rounded-xl max-w-sm w-full p-6 space-y-4 shadow-2xl">
            <h2 className="text-lg font-semibold text-white">Create workspace</h2>
            <form onSubmit={handleCreateWorkspace} className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-gray-300 mb-1" htmlFor="ws-name">
                  Workspace name
                </label>
                <input
                  id="ws-name"
                  type="text"
                  required
                  value={createName}
                  onChange={(e) => setCreateName(e.target.value)}
                  placeholder="My workspace"
                  className="w-full px-3 py-2 rounded-lg bg-gray-800 border border-gray-700 text-white placeholder-gray-500 focus:outline-none focus:border-blue-500 text-sm"
                  autoFocus
                />
              </div>
              {createError && (
                <p className="text-sm text-red-400">{createError}</p>
              )}
              <div className="flex gap-3 pt-1">
                <button
                  type="button"
                  onClick={() => { setCreateOpen(false); setCreateName(''); setCreateError(null); }}
                  className="flex-1 px-4 py-2 rounded-lg bg-gray-800 hover:bg-gray-700 text-gray-300 text-sm font-medium transition-colors"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={createLoading || !createName.trim()}
                  className="flex-1 px-4 py-2 rounded-lg bg-blue-600 hover:bg-blue-500 disabled:opacity-50 text-white text-sm font-medium transition-colors"
                >
                  {createLoading ? 'Creating…' : 'Create'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
