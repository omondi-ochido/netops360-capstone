import React from 'react';
import { useState } from "react";
import Layout from "./components/layout/Layout";
import Login from "./pages/Login";
import Dashboard from "./pages/Dashboard";
import DeviceManagement from "./pages/DeviceManagement";
import DeviceDetails from "./pages/DeviceDetails";
import AlertsAndIncidents from "./pages/AlertsAndIncidents";
import MonitoringRules from "./pages/MonitoringRules";
import AutomationManagement from "./pages/AutomationManagement";

const pageTitles = {
  dashboard: "Dashboard",
  devices: "Device Management",
  "device-details": "Device Details",
  alerts: "Alerts & Incidents",
  monitoring: "Monitoring Rules",
  automation: "Automation Management",
};

function App() {
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [activePage, setActivePage] = useState("dashboard");
  const [selectedDevice, setSelectedDevice] = useState(null);

  const handleNavigate = (page) => {
    setActivePage(page);
  };

  const handleViewDevice = (device) => {
    setSelectedDevice(device);
    setActivePage("device-details");
  };

  const handleBackToDevices = () => {
    setSelectedDevice(null);
    setActivePage("devices");
  };

  const handleLogout = () => {
    setIsAuthenticated(false);
    setActivePage("dashboard");
    setSelectedDevice(null);
  };

  const renderPage = () => {
    switch (activePage) {
      case "dashboard":
        return <Dashboard />;
      case "devices":
        return <DeviceManagement onViewDevice={handleViewDevice} />;
      case "device-details":
        return <DeviceDetails device={selectedDevice} onBack={handleBackToDevices} />;
      case "alerts":
        return <AlertsAndIncidents />;
      case "monitoring":
        return <MonitoringRules />;
      case "automation":
        return <AutomationManagement />;
      default:
        return <Dashboard />;
    }
  };

  if (!isAuthenticated) {
    return <Login onLogin={() => setIsAuthenticated(true)} />;
  }

  const activeTitle = pageTitles[activePage] || "Dashboard";

  return (
    <Layout
      title={activeTitle}
      activePage={activePage === "device-details" ? "devices" : activePage}
      onNavigate={handleNavigate}
      onLogout={handleLogout}
    >
      {renderPage()}
    </Layout>
  );
}

export default App;
