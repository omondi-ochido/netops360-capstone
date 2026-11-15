import React from 'react';
const kpis = [
  { label: "Total Devices", value: "148", delta: "+4 this week" },
  { label: "Online", value: "141", delta: "95.3% healthy" },
  { label: "Offline", value: "3", delta: "1 action required" },
  { label: "Active Incidents", value: "4", delta: "2 warn / 1 critical" },
];

const statusRows = [
  { hostname: "core-sw-01", ip: "10.1.0.1", type: "Switch", status: "Healthy", uptime: "99.9%" },
  { hostname: "edge-rt-01", ip: "192.168.1.10", type: "Router", status: "Warning", uptime: "96.2%" },
  { hostname: "db-cluster-01", ip: "10.20.0.12", type: "Database", status: "Healthy", uptime: "99.8%" },
  { hostname: "ap-west-3rdfloor", ip: "10.15.0.8", type: "Access Point", status: "Offline", uptime: "92.1%" },
];

const recentAlerts = [
  { severity: "Critical", message: "Packet loss > 25% on Edge-RT-01", time: "4 minutes ago" },
  { severity: "Warning", message: "CPU spike detected on Core-SW-04", time: "11 minutes ago" },
  { severity: "Critical", message: "AP-West-3rdFloor unreachable via SSH", time: "18 minutes ago" },
  { severity: "Info", message: "BGP peer flapping on ASN 56402", time: "29 minutes ago" },
];

function Dashboard() {
  return (
    <div className="page-stack dashboard-page">
      <section className="page-header-row">
        <div>
          <h2>Welcome back, Marcus</h2>
          <p>Friday, Nov 15, 2026 • 10:27 UTC • Fleet status synchronized</p>
        </div>
        <div className="header-button-group">
          <button type="button" className="secondary-button">Run Ping Sweep</button>
          <button type="button" className="secondary-button">View Active Alerts</button>
          <button type="button" className="primary-button">+ Add Device</button>
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
            <span className="status-badge neutral">Last 24h</span>
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
            <div className="donut-chart">
              <span>148</span>
            </div>
            <ul className="legend-list">
              <li><span className="legend-dot green" /> Healthy 141</li>
              <li><span className="legend-dot amber" /> Warning 4</li>
              <li><span className="legend-dot red" /> Critical 3</li>
            </ul>
          </div>
        </div>
      </section>

      <section className="content-row split-row">
        <div className="panel-card table-panel">
          <div className="panel-header-row">
            <div>
              <span className="eyebrow-text">Status</span>
              <h3>Device status summary</h3>
            </div>
          </div>

          <table className="data-table">
            <thead>
              <tr>
                <th>Hostname</th>
                <th>IP</th>
                <th>Type</th>
                <th>Status</th>
                <th>Uptime</th>
              </tr>
            </thead>
            <tbody>
              {statusRows.map((row) => (
                <tr key={row.hostname}>
                  <td>{row.hostname}</td>
                  <td>{row.ip}</td>
                  <td>{row.type}</td>
                  <td>
                    <span className={`status-tag ${row.status.toLowerCase()}`}>{row.status}</span>
                  </td>
                  <td>{row.uptime}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <div className="panel-card alerts-panel">
          <div className="panel-header-row">
            <div>
              <span className="eyebrow-text">Alerts</span>
              <h3>Recent alerts</h3>
            </div>
          </div>

          <ul className="alert-list">
            {recentAlerts.map((alert) => (
              <li key={`${alert.message}-${alert.time}`}>
                <div className={`alert-severity ${alert.severity.toLowerCase()}`}>{alert.severity}</div>
                <div>
                  <strong>{alert.message}</strong>
                  <small>{alert.time}</small>
                </div>
              </li>
            ))}
          </ul>
        </div>
      </section>
    </div>
  );
}

export default Dashboard;
