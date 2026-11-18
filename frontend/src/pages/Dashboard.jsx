import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { fetchDevices } from "../services/deviceService";

function Dashboard({ onViewDevice, onNavigate }) {
  const [devices, setDevices] = useState([]);
  const [networkEvents, setNetworkEvents] = useState([]);
  const [isLive, setIsLive] = useState(false);
  const [isLoading, setIsLoading] = useState(true);
  const previousStatuses = useRef(new Map());

  const refreshDevices = useCallback(async () => {
    setIsLoading(true);
    const result = await fetchDevices();
    if (result.isLive) {
      const polledAt = new Date();
      const nextStatuses = new Map();
      const transitions = [];

      result.devices.forEach((device) => {
        const previousStatus = previousStatuses.current.get(device.id);
        if (previousStatus && previousStatus !== device.status) {
          transitions.push({
            id: `${device.id}-${polledAt.getTime()}-${transitions.length}`,
            hostname: device.hostname,
            ipAddress: device.ipAddress,
            previousStatus,
            status: device.status,
            timestamp: polledAt.toLocaleTimeString("en-US", {
              hour: "numeric",
              minute: "2-digit",
              second: "2-digit",
            }),
          });
        }
        nextStatuses.set(device.id, device.status);
      });

      previousStatuses.current = nextStatuses;
      if (transitions.length) {
        setNetworkEvents((events) => [...transitions, ...events]);
      }
    }
    setDevices(result.devices);
    setIsLive(result.isLive);
    setIsLoading(false);
  }, []);

  useEffect(() => {
    void refreshDevices();
    const intervalId = window.setInterval(refreshDevices, 15000);
    return () => window.clearInterval(intervalId);
  }, [refreshDevices]);

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
    { label: "Total Devices", value: devices.length, delta: "GNS3 topology inventory" },
    { label: "Online", value: onlineCount, delta: "Responding devices" },
    { label: "Offline", value: offlineCount, delta: "Unreachable devices" },
    { label: "Avg Latency", value: averageLatency, delta: "Across measured devices" },
  ];
  const recentAlerts = useMemo(() => devices
    .filter((device) => device.status !== "Online")
    .map((device) => ({
      severity: device.status === "Warning" ? "Warning" : "Critical",
      message: `${device.hostname} is ${device.status.toLowerCase()}`,
      time: device.configurationPending ? "Pending console boot" : device.lastChecked,
    })), [devices]);

  return (
    <div className="page-stack dashboard-page">
      <section className="page-header-row">
        <div>
          <h2>Welcome back, Marcus</h2>
          <p>GNS3 topology inventory • {isLive ? "Live telemetry" : "Fallback inventory"}</p>
        </div>
        <div className="header-button-group">
          {isLive && <span className="status-badge neutral">Live GNS3 Telemetry</span>}
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
            <span className="status-badge neutral">{isLive ? "Live poll" : "Fallback data"}</span>
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
            <h3>Live Network Events</h3>
          </div>
          {isLive && <span className="status-badge neutral">Live GNS3 Telemetry</span>}
        </div>
        {networkEvents.length ? (
          <ul className="alert-list">
            {networkEvents.map((event) => (
              <li key={event.id}>
                <span className={`status-tag ${event.previousStatus.toLowerCase()}`}>
                  {event.previousStatus}
                </span>
                <div>
                  <strong>
                    {event.timestamp} — {event.hostname} ({event.ipAddress}) transitioned from{" "}
                    {event.previousStatus} to {event.status}
                  </strong>
                </div>
                <span className={`status-tag ${event.status.toLowerCase()}`}>{event.status}</span>
              </li>
            ))}
          </ul>
        ) : (
          <p>No device status transitions have been detected yet.</p>
        )}
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
