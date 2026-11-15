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

const ADMIN_PATHS = [
  '/settings/providers',
  '/settings/api-keys',
  '/settings/suppressions',
];

export default function SettingsLayout() {
  const { isAdmin } = useAuth();
  const location = useLocation();

  // Redirect admin-only routes for non-admins
  const isAdminOnlyPath = ADMIN_PATHS.some((p) => location.pathname.startsWith(p));
  if (isAdminOnlyPath && !isAdmin) {
    return (
      <Navigate
        to="/settings/general"
        replace
        state={{
          flash: 'Not allowed: this section requires admin or owner role.',
        }}
      />
    );
  }

  return (
    <div className="space-y-6">
      {/* Settings Header */}
      <div>
        <h1 className="text-xl sm:text-2xl font-semibold text-[#1C1917] tracking-tight">
          Settings
        </h1>
        <p className="text-xs sm:text-sm text-[#78716C] mt-0.5">
          Manage workspace configuration, notification delivery providers, and team access.
        </p>
      </div>

      {/* Horizontal underline tab bar */}
      <div className="border-b border-[#E7E5E4] overflow-x-auto">
        <nav className="flex gap-6 min-w-max -mb-px">
          {TABS.map((tab) => {
            if (tab.adminOnly && !isAdmin) return null;
            return (
              <NavLink
                key={tab.to}
                to={tab.to}
                className={({ isActive }) =>
                  `pb-3 text-xs sm:text-sm font-medium border-b-2 transition-colors cursor-pointer inline-flex items-center gap-1.5 ${
                    isActive
                      ? 'border-[#4F46E5] text-[#1C1917]'
                      : 'border-transparent text-[#78716C] hover:text-[#1C1917] hover:border-[#D6D3D1]'
                  }`
                }
              >
                {tab.label}
              </NavLink>
            );
          })}
        </nav>
      </div>

      {/* Tab Page Content */}
      <div className="max-w-[760px]">
        <Outlet />
      </div>
    </div>
  );
}
