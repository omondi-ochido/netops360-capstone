import React from 'react';
import { useMemo, useState } from "react";
import { discoveredDevices } from "../data/discoveredDevices";

const incidentSeed = [
  { id: "INC-2049", deviceId: "main-rtr", trigger: "Packet loss above threshold", severity: "Critical", status: "Open", time: "4m ago" },
  { id: "INC-2048", deviceId: "branch-rtr", trigger: "Router configuration pending", severity: "Warning", status: "Investigating", time: "8m ago" },
  { id: "INC-2047", deviceId: "SW1", trigger: "Switch reachability check", severity: "Info", status: "Open", time: "12m ago" },
  { id: "INC-2046", deviceId: "MAIN-SERVER", trigger: "Server health check", severity: "Info", status: "Open", time: "16m ago" },
  { id: "INC-2045", deviceId: "PC4", trigger: "Host response time monitor", severity: "Info", status: "Resolved", time: "30m ago" },
];

function AlertsAndIncidents() {
  const [filter, setFilter] = useState("All");
  const [deviceFilter, setDeviceFilter] = useState("All");

  const list = useMemo(() => {
    return incidentSeed.filter((item) => {
      const matchesFilter = filter === "All" || item.status === filter || item.severity === filter;
      const matchesDevice = deviceFilter === "All" || item.deviceId === deviceFilter;
      return matchesFilter && matchesDevice;
    });
  }, [deviceFilter, filter]);

  return (
    <div className="page-stack">
      <section className="page-header-row">
        <div>
          <h2>Alerts &amp; Incidents</h2>
          <p>Correlate telemetry, triage events, and resolve operational impact.</p>
        </div>
        <button type="button" className="primary-button">+ Create alert</button>
      </section>

      <section className="panel-card">
        <div className="filter-row">
          {['All', 'Open', 'Investigating', 'Resolved', 'Critical', 'Warning', 'Info'].map((item) => (
            <button
              key={item}
              type="button"
              className={`filter-chip ${filter === item ? "active" : ""}`}
              onClick={() => setFilter(item)}
            >
              {item}
            </button>
          ))}
          <select
            className="device-select-filter"
            value={deviceFilter}
            onChange={(event) => setDeviceFilter(event.target.value)}
            aria-label="Filter incidents by device"
          >
            <option value="All">All devices</option>
            {discoveredDevices.map((device) => (
              <option key={device.id} value={device.id}>{device.hostname}</option>
            ))}
          </select>
        </div>

        <table className="data-table incident-table">
          <thead>
            <tr>
              <th>ID</th>
              <th>Device</th>
              <th>Rule Triggered</th>
              <th>Severity</th>
              <th>Status</th>
              <th>Timestamp</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {list.map((incident) => (
              <tr key={incident.id}>
                <td>{incident.id}</td>
                <td>{discoveredDevices.find((device) => device.id === incident.deviceId)?.hostname || incident.deviceId}</td>
                <td>{incident.trigger}</td>
                <td>
                  <span className={`severity-pill ${incident.severity.toLowerCase()}`}>{incident.severity}</span>
                </td>
                <td>{incident.status}</td>
                <td>{incident.time}</td>
                <td className="action-cell">
                  <button type="button" className="secondary-button small-button">Acknowledge</button>
                  <button type="button" className="primary-button small-button">Resolve</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
    </div>
  );
}

export default AlertsAndIncidents;
