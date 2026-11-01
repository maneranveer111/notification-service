import { NavLink } from 'react-router-dom';
import { useState } from 'react';
import { useAuth } from '../lib/auth';

const NAV = [
  { to: '/', label: 'Overview', exact: true },
  { to: '/notifications', label: 'Notifications', exact: false },
  { to: '/templates', label: 'Templates', exact: false },
  { to: '/send', label: 'Send', exact: false, adminOnly: true },
  { to: '/bulk', label: 'Bulk', exact: false, adminOnly: true },
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

export default function Layout({ children }) {
  const { user, logout, canWrite } = useAuth();
  const [open, setOpen] = useState(false);

  const visibleNav = NAV.filter((n) => !n.adminOnly || canWrite);

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
        <nav className="flex-1 px-3 pb-4 space-y-1">
          {visibleNav.map((n) => (
            <NavItem key={n.to} {...n} onClick={() => setOpen(false)} />
          ))}
        </nav>
        <div className="px-4 py-4 border-t border-gray-800 space-y-1">
          <p className="text-xs text-gray-400 truncate">{user?.email}</p>
          <span
            className={`text-xs px-2 py-0.5 rounded-full font-medium ${
              user?.role === 'admin' ? 'bg-blue-700 text-blue-100' : 'bg-gray-700 text-gray-300'
            }`}
          >
            {user?.role}
          </span>
          <button
            onClick={logout}
            className="mt-2 block w-full text-left px-3 py-1.5 text-sm text-gray-400 hover:text-white hover:bg-gray-700 rounded-lg transition-colors"
          >
            Log out
          </button>
        </div>
      </aside>

      {/* Main */}
      <main className="flex-1 p-4 md:p-6 overflow-auto">{children}</main>
    </div>
  );
}
