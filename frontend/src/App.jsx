import { useState } from "react";
import { BrowserRouter, Navigate, Route, Routes, useNavigate } from "react-router-dom";
import Layout from "./components/layout/Layout";
import Login from "./pages/Login";
import SignUp from "./pages/SignUp";
import AuthCallback from "./pages/AuthCallback";
import ForgotPassword from "./pages/ForgotPassword";
import ResetPassword from "./pages/ResetPassword";
import AcceptInvite from "./pages/AcceptInvite";
import Dashboard from "./pages/Dashboard";
import DeviceManagement from "./pages/DeviceManagement";
import DeviceDetails from "./pages/DeviceDetails";
import AlertsAndIncidents from "./pages/AlertsAndIncidents";
import MonitoringRules from "./pages/MonitoringRules";
import AutomationManagement from "./pages/AutomationManagement";
import UserManagement from "./pages/UserManagement";
import { AuthProvider, useAuth } from "./context/AuthContext";

function ProtectedApp() {
  const { user, loading, hasPermission, logout } = useAuth();
  const [activePage, setActivePage] = useState("dashboard"); const [selectedDevice, setSelectedDevice] = useState(null); const navigate = useNavigate();
  if (loading) return <div className="login-page" role="status">Loading your account…</div>;
  if (!user) return <Navigate to="/login" replace />;
  const openDevice = (device) => { setSelectedDevice(device); setActivePage("device-details"); };
  const titleMap = { dashboard: "Dashboard", devices: "Device Management", "device-details": "Device Details", alerts: "Alerts & Incidents", monitoring: "Monitoring Rules", automation: "Automation Management", users: "User Management" };
  const allowed = { devices: "devices.read", alerts: "incidents.read", monitoring: "rules.read", automation: "automation.read", users: "users.read" };
  const visiblePage = allowed[activePage] && !hasPermission(allowed[activePage]) ? "dashboard" : activePage;
  const render = () => {
    if (visiblePage === "dashboard") return <Dashboard onViewDevice={openDevice} onNavigate={(page) => { if (!allowed[page] || hasPermission(allowed[page])) setActivePage(page); }} />;
    if (visiblePage === "devices") return <DeviceManagement onViewDevice={openDevice} />;
    if (visiblePage === "device-details") return <DeviceDetails deviceId={selectedDevice?.id} device={selectedDevice} onBack={() => setActivePage("devices")} />;
    if (visiblePage === "alerts") return <AlertsAndIncidents />;
    if (visiblePage === "monitoring") return <MonitoringRules />;
    if (visiblePage === "automation") return <AutomationManagement />;
    if (visiblePage === "users") return <UserManagement />;
    return <Dashboard onViewDevice={openDevice} onNavigate={setActivePage} />;
  };
  return <Layout title={titleMap[visiblePage] || "Dashboard"} activePage={visiblePage === "device-details" ? "devices" : visiblePage} onNavigate={(page) => { if (!allowed[page] || hasPermission(allowed[page])) setActivePage(page); }} onLogout={async () => { await logout(); navigate("/login", { replace: true }); }}>{render()}</Layout>;
}

function AppRoutes() {
  const { user, loading } = useAuth();
  return <Routes>
    <Route path="/login" element={user ? <Navigate to="/" replace /> : <Login />} />
    <Route path="/signup" element={user ? <Navigate to="/" replace /> : <SignUp />} />
    <Route path="/auth/callback" element={<AuthCallback />} />
    <Route path="/forgot-password" element={<ForgotPassword />} />
    <Route path="/reset-password" element={<ResetPassword />} />
    <Route path="/accept-invite" element={<AcceptInvite />} />
    <Route path="/*" element={loading ? <div className="login-page" role="status">Loading your account…</div> : user ? <ProtectedApp /> : <Navigate to="/login" replace />} />
  </Routes>;
}

export default function App() { return <BrowserRouter><AuthProvider><AppRoutes /></AuthProvider></BrowserRouter>; }
