import React from "react";
import { discoveredDevices } from "../data/discoveredDevices";

const onlineCount = discoveredDevices.filter((device) => device.status === "Online").length;
const warningCount = discoveredDevices.filter((device) => device.status === "Warning").length;
const offlineCount = discoveredDevices.filter((device) => device.status === "Offline").length;
const needsAttentionCount = warningCount + offlineCount;
const onlinePercentage = (onlineCount / discoveredDevices.length) * 100;
const warningEndPercentage = ((onlineCount + warningCount) / discoveredDevices.length) * 100;
const kpis = [
  { label: "Total Devices", value: discoveredDevices.length, delta: "Discovered in GNS3 topology" },
  { label: "Online", value: onlineCount, delta: "Responding devices" },
  { label: "Warning / Offline", value: needsAttentionCount, delta: "Require attention" },
  { label: "Active Incidents", value: needsAttentionCount, delta: "Based on device status" },
];

const recentAlerts = discoveredDevices
  .filter((device) => device.status !== "Online")
  .map((device) => ({
    severity: device.status === "Warning" ? "Warning" : "Critical",
    message: `${device.hostname} is ${device.status.toLowerCase()}`,
    time: device.configurationPending ? "Pending console boot" : device.lastChecked,
  }));

function Dashboard({ onViewDevice, onNavigate }) {
  return (
    <div className="page-stack dashboard-page">
      <section className="page-header-row">
        <div>
          <h2>Welcome back, Marcus</h2>
          <p>GNS3 topology inventory • Fleet status synchronized</p>
        </div>
        <div className="header-button-group">
          <button type="button" className="secondary-button">Run Ping Sweep</button>
          <button type="button" className="secondary-button" onClick={() => onNavigate("alerts")}>
            View Active Alerts
          </button>
          <button type="button" className="primary-button" onClick={() => onNavigate("devices")}>
            View Devices
          </button>
        </div>
      </section>

      <section className="kpi-grid">
        {kpis.map((item) => (
          <article key={item.label} className="kpi-card">
            <span className="kpi-label">{item.label}</span>
            <strong>{item.value}</strong>
            <small>{item.delta}</small>
          </article>
        ))}
      </section>

      <section className="content-row split-row">
        <div className="panel-card large-panel">
          <div className="panel-header-row">
            <div>
              <span className="eyebrow-text">SLA</span>
              <h3>Network health overview</h3>
            </div>
            <span className="status-badge neutral">Topology scan</span>
          </div>

          <div className="chart-box">
            <div className="chart-bars">
              {Array.from({ length: 24 }).map((_, index) => (
                <span key={index} style={{ height: 30 + ((index * 11) % 55) }} />
              ))}
            </div>
          </div>
        </div>

        <div className="panel-card small-panel">
          <div className="panel-header-row">
            <div>
              <span className="eyebrow-text">Health</span>
              <h3>Topology status</h3>
            </div>
          </div>

          <div className="donut-wrap">
            <div
              className="donut-chart"
              style={{
                background: `conic-gradient(#16a34a 0 ${onlinePercentage}%, #f59e0b ${onlinePercentage}% ${warningEndPercentage}%, #ef4444 ${warningEndPercentage}% 100%)`,
              }}
            >
              <span>{discoveredDevices.length}</span>
            </div>
            <ul className="legend-list">
              <li><span className="legend-dot green" /> Online {onlineCount}</li>
              <li><span className="legend-dot amber" /> Warning {warningCount}</li>
              <li><span className="legend-dot red" /> Offline {offlineCount}</li>
            </ul>
          </div>
        </div>
      </section>

      <section className="panel-card table-panel">
        <div className="panel-header-row">
          <div>
            <span className="eyebrow-text">Inventory</span>
            <h3>Discovered Network Devices</h3>
          </div>
          <button type="button" className="secondary-button small-button" onClick={() => onNavigate("devices")}>
            Full inventory
          </button>
        </div>

        <div className="table-scroll">
          <table className="data-table">
            <thead>
              <tr>
                <th>Hostname</th>
                <th>IP Address</th>
                <th>Type</th>
                <th>Site</th>
                <th>Status</th>
                <th>Details</th>
              </tr>
            </thead>
            <tbody>
              {discoveredDevices.map((device) => (
                <tr key={device.id}>
                  <td>{device.hostname}</td>
                  <td>{device.ipAddress}</td>
                  <td>{device.deviceType}</td>
                  <td>{device.site}</td>
                  <td>
                    <span className={`status-tag ${device.status.toLowerCase()}`}>{device.status}</span>
                  </td>
                  <td>
                    <button type="button" className="secondary-button small-button" onClick={() => onViewDevice(device)}>
                      View details
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className="panel-card alerts-panel">
        <div className="panel-header-row">
          <div>
            <span className="eyebrow-text">Alerts</span>
            <h3>Recent alerts</h3>
          </div>
        </div>
        {recentAlerts.length ? (
          <ul className="alert-list">
            {recentAlerts.map((alert) => (
              <li key={alert.message}>
                <div className={`alert-severity ${alert.severity.toLowerCase()}`}>{alert.severity}</div>
                <div>
                  <strong>{alert.message}</strong>
                  <small>{alert.time}</small>
                </div>
              </li>
            ))}
          </ul>
        ) : (
          <p>No devices currently need attention.</p>
        )}
      </section>
    </div>
  );
}

export default Dashboard;
