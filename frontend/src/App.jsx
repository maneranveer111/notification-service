import { Routes, Route, Navigate } from 'react-router-dom';
import { RequireAuth } from './lib/auth';
import Layout from './components/Layout';
import LoginPage from './pages/LoginPage';
import SignupPage from './pages/SignupPage';
import VerifyEmailPage from './pages/VerifyEmailPage';
import ForgotPasswordPage from './pages/ForgotPasswordPage';
import ResetPasswordPage from './pages/ResetPasswordPage';
import AcceptInvitePage from './pages/AcceptInvitePage';
import OverviewPage from './pages/OverviewPage';
import NotificationsPage from './pages/NotificationsPage';
import NotificationDetailPage from './pages/NotificationDetailPage';
import TemplatesPage from './pages/TemplatesPage';
import SendPage from './pages/SendPage';
import BulkPage from './pages/BulkPage';
import NotFoundPage from './pages/NotFoundPage';
import SettingsLayout from './pages/settings/SettingsLayout';
import GeneralPage from './pages/settings/GeneralPage';
import ProvidersPage from './pages/settings/ProvidersPage';
import ApiKeysPage from './pages/settings/ApiKeysPage';
import TeamPage from './pages/settings/TeamPage';
import SuppressionsPage from './pages/settings/SuppressionsPage';
import AccountPage from './pages/settings/AccountPage';
import PlatformPage from './pages/PlatformPage';

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/signup" element={<SignupPage />} />
      <Route path="/verify-email" element={<VerifyEmailPage />} />
      <Route path="/forgot-password" element={<ForgotPasswordPage />} />
      <Route path="/reset-password" element={<ResetPasswordPage />} />
      <Route path="/accept-invite" element={<AcceptInvitePage />} />
      <Route
        path="/"
        element={
          <RequireAuth>
            <Layout>
              <OverviewPage />
            </Layout>
          </RequireAuth>
        }
      />
      <Route
        path="/notifications"
        element={
          <RequireAuth>
            <Layout>
              <NotificationsPage />
            </Layout>
          </RequireAuth>
        }
      />
      <Route
        path="/notifications/:id"
        element={
          <RequireAuth>
            <Layout>
              <NotificationDetailPage />
            </Layout>
          </RequireAuth>
        }
      />
      <Route
        path="/templates"
        element={
          <RequireAuth>
            <Layout>
              <TemplatesPage />
            </Layout>
          </RequireAuth>
        }
      />
      <Route
        path="/send"
        element={
          <RequireAuth requireWrite>
            <Layout>
              <SendPage />
            </Layout>
          </RequireAuth>
        }
      />
      <Route
        path="/bulk"
        element={
          <RequireAuth requireWrite>
            <Layout>
              <BulkPage />
            </Layout>
          </RequireAuth>
        }
      />
      <Route
        path="/settings"
        element={
          <RequireAuth>
            <Layout>
              <SettingsLayout />
            </Layout>
          </RequireAuth>
        }
      >
        <Route index element={<Navigate to="/settings/general" replace />} />
        <Route path="general" element={<GeneralPage />} />
        <Route path="providers" element={<ProvidersPage />} />
        <Route path="api-keys" element={<ApiKeysPage />} />
        <Route path="team" element={<TeamPage />} />
        <Route path="suppressions" element={<SuppressionsPage />} />
        <Route path="account" element={<AccountPage />} />
      </Route>
      <Route
        path="/platform"
        element={
          <RequireAuth>
            <Layout>
              <PlatformPage />
            </Layout>
          </RequireAuth>
        }
      />
      <Route
        path="*"
        element={
          <RequireAuth>
            <Layout>
              <NotFoundPage />
            </Layout>
          </RequireAuth>
        }
      />
    </Routes>
  );
}
