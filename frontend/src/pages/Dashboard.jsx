import React, { useCallback, useEffect, useRef, useState } from "react";
import { fetchDevices } from "../services/deviceService";
import { fetchIncidents, fetchMonitoringHistory } from "../services/operationsService";

function Dashboard({ onViewDevice, onNavigate }) {
  const [devices, setDevices] = useState([]);
  const [networkEvents, setNetworkEvents] = useState([]);
  const [incidents, setIncidents] = useState([]);
  const [error, setError] = useState("");
  const [isLive, setIsLive] = useState(false);
  const [isLoading, setIsLoading] = useState(true);
  const deviceRefreshInProgress = useRef(false);

  const refreshDevices = useCallback(async () => {
    if (deviceRefreshInProgress.current) return;
    deviceRefreshInProgress.current = true;
    try {
      const result = await fetchDevices();
      setDevices(result.devices);
      setIsLive(true);
      setError("");
    } catch (requestError) { setError(requestError.message); }
    finally {
      deviceRefreshInProgress.current = false;
      setIsLoading(false);
    }
  }, []);

  const refreshActivity = useCallback(async () => {
    try {
      const [history, incidentRows] = await Promise.all([
        fetchMonitoringHistory({ limit: 12 }), fetchIncidents({ active: true, limit: 8 }),
      ]);
      setNetworkEvents(history);
      setIncidents(incidentRows);
    } catch (requestError) { setError(requestError.message); }
  }, []);

  useEffect(() => {
    void refreshDevices();
    const intervalId = window.setInterval(refreshDevices, 3000);
    return () => window.clearInterval(intervalId);
  }, [refreshDevices]);

  useEffect(() => {
    void refreshActivity();
    const intervalId = window.setInterval(refreshActivity, 15000);
    return () => window.clearInterval(intervalId);
  }, [refreshActivity]);

  const onlineCount = devices.filter((device) => device.status === "Online").length;
  const warningCount = devices.filter((device) => device.status === "Warning").length;
  const offlineCount = devices.filter((device) => device.status === "Offline").length;
  const measuredLatencies = devices
    .map((device) => device.latencyMs)
    .filter((latency) => Number.isFinite(latency));
  const averageLatency = measuredLatencies.length
    ? `${(measuredLatencies.reduce((total, latency) => total + latency, 0) / measuredLatencies.length).toFixed(2)} ms`
    : "N/A";
  const onlinePercentage = devices.length ? (onlineCount / devices.length) * 100 : 0;
  const warningEndPercentage = devices.length
    ? ((onlineCount + warningCount) / devices.length) * 100
    : 0;
  const kpis = [
    { label: "Total Devices", value: devices.length, delta: "Managed inventory" },
    { label: "Online", value: onlineCount, delta: "Responding devices" },
    { label: "Offline", value: offlineCount, delta: "Unreachable devices" },
    { label: "Avg Latency", value: averageLatency, delta: "Across measured devices" },
  ];
  const deviceName = (deviceId) => devices.find((device) => device.id === deviceId)?.hostname || deviceId;

  return (
    <div className="page-stack dashboard-page">
      <section className="page-header-row">
        <div>
          <h2>Network overview</h2>
          <p>Persisted network inventory • {isLive ? "Backend data" : "Waiting for backend"}</p>
        </div>
        <div className="header-button-group">
          {error && <span className="status-badge neutral">Backend unavailable</span>}
          <button type="button" className="secondary-button" onClick={refreshDevices} disabled={isLoading}>
            {isLoading ? "Refreshing..." : "Refresh Poll"}
          </button>
          <button type="button" className="secondary-button" onClick={() => onNavigate("alerts")}>
            View Active Alerts
          </button>
          <button type="button" className="primary-button" onClick={() => onNavigate("devices")}>
            View Devices
          </button>
        </div>
      </section>

      {error && <p className="configuration-pending" role="alert">{error} <button type="button" className="secondary-button small-button" onClick={refreshDevices}>Retry</button></p>}

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
            <span className="status-badge neutral">Persisted monitoring</span>
          </div>

          <div className="chart-box">
            <p>Historical charts are unavailable because the backend currently collects availability, latency, and packet loss only.</p>
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
              <span>{devices.length}</span>
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
            <h3>Managed Network Devices</h3>
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
                <th>Latency</th>
                <th>Packet Loss</th>
                <th>Details</th>
              </tr>
            </thead>
            <tbody>
              {devices.map((device) => (
                <tr key={device.id}>
                  <td>{device.hostname}</td>
                  <td>{device.ipAddress}</td>
                  <td>{device.deviceType}</td>
                  <td>{device.site}</td>
                  <td>
                    <span className={`status-tag ${device.status.toLowerCase()}`}>{device.status}</span>
                  </td>
                  <td>{Number.isFinite(device.latencyMs) ? `${device.latencyMs} ms` : "N/A"}</td>
                  <td>{Number.isFinite(device.packetLoss) ? `${device.packetLoss}%` : "N/A"}</td>
                  <td>
                    <button type="button" className="secondary-button small-button" onClick={() => onViewDevice(device)}>
                      View details
                    </button>
                  </td>
                </tr>
              ))}
              {devices.length === 0 && (
                <tr><td colSpan="8" className="empty-table-message">{isLoading ? "Loading devices..." : "No devices available."}</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </section>

      <section className="panel-card alerts-panel">
        <div className="panel-header-row">
          <div>
            <span className="eyebrow-text">Telemetry</span>
          <h3>Recent monitoring checks</h3>
          </div>
          {isLive && <span className="status-badge neutral">Backend records</span>}
        </div>
        {networkEvents.length ? (
          <ul className="alert-list">
          {networkEvents.map((event) => (
              <li key={event.id}>
                <span className={`status-tag ${event.status.toLowerCase()}`}>{event.status}</span>
                <div>
                  <strong>
                    {deviceName(event.device_id)} • {event.checked_at ? new Date(event.checked_at).toLocaleString() : ""}
                  </strong>
                </div>
                <span>{event.latency_ms == null ? "N/A" : `${event.latency_ms} ms`} • {event.packet_loss == null ? "N/A" : `${event.packet_loss}% loss`}</span>
              </li>
            ))}
          </ul>
        ) : (
          <p>No monitoring checks have been recorded yet.</p>
        )}
      </section>

      <section className="panel-card alerts-panel">
        <div className="panel-header-row">
          <div>
            <span className="eyebrow-text">Alerts</span>
            <h3>Recent alerts</h3>
          </div>
        </div>
        {incidents.length ? (
          <ul className="alert-list">
            {incidents.map((incident) => (
              <li key={incident.id}>
                <div className={`alert-severity ${incident.severity}`}>{incident.severity}</div>
                <div>
                  <strong>{incident.title} — {deviceName(incident.device_id)}</strong>
                  <small>{incident.triggered_at ? new Date(incident.triggered_at).toLocaleString() : ""}</small>
                </div>
              </li>
            ))}
          </ul>
        ) : (
          <p>No active incidents.</p>
        )}
      </section>
    </div>
  );
}

export default Dashboard;
