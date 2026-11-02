import { NavLink, Outlet, Navigate, useLocation } from 'react-router-dom';
import { useAuth } from '../../lib/auth';

const TABS = [
  { to: '/settings/general', label: 'General', adminOnly: false },
  { to: '/settings/providers', label: 'Providers', adminOnly: true },
  { to: '/settings/api-keys', label: 'API Keys', adminOnly: true },
  { to: '/settings/team', label: 'Team', adminOnly: false },
  { to: '/settings/suppressions', label: 'Suppressions', adminOnly: true },
  { to: '/settings/account', label: 'Account', adminOnly: false },
];

const ADMIN_PATHS = ['/settings/providers', '/settings/api-keys', '/settings/suppressions'];

export default function SettingsLayout() {
  const { isAdmin } = useAuth();
  const location = useLocation();

  // Redirect admin-only routes for non-admins
  const isAdminOnlyPath = ADMIN_PATHS.some(p => location.pathname.startsWith(p));
  if (isAdminOnlyPath && !isAdmin) {
    return (
      <Navigate
        to="/settings/general"
        replace
        state={{ flash: 'Not allowed: this section requires admin or owner role.' }}
      />
    );
  }

  return (
    <div className="space-y-6">
      <h1 className="text-xl font-bold text-white">Settings</h1>

      {/* Tab bar */}
      <div className="border-b border-gray-800 overflow-x-auto whitespace-nowrap">
        <nav className="flex gap-1 min-w-max">
          {TABS.map((tab) => {
            if (tab.adminOnly && !isAdmin) return null;
            return (
              <NavLink
                key={tab.to}
                to={tab.to}
                className={({ isActive }) =>
                  `px-4 py-2.5 text-sm font-medium border-b-2 transition-colors inline-block ${
                    isActive
                      ? 'border-blue-500 text-white'
                      : 'border-transparent text-gray-400 hover:text-gray-200 hover:border-gray-600'
                  }`
                }
              >
                {tab.label}
              </NavLink>
            );
          })}
        </nav>
      </div>

      {/* Page content */}
      <Outlet />
    </div>
  );
}
