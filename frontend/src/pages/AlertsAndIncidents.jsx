import React from 'react';
import { useMemo, useState } from "react";

const incidentSeed = [
  { id: "INC-2049", device: "Edge-RT-01", trigger: "Packet loss > 25%", severity: "Critical", status: "Open", time: "4m ago" },
  { id: "INC-2048", device: "AP-West-3rdFloor", trigger: "SSH unreachable", severity: "Critical", status: "Open", time: "8m ago" },
  { id: "INC-2047", device: "DB-Cluster-01", trigger: "ICMP health check failed", severity: "Critical", status: "Investigating", time: "12m ago" },
  { id: "INC-2046", device: "Core-SW-04", trigger: "CPU spike", severity: "Warning", status: "Open", time: "16m ago" },
  { id: "INC-2045", device: "BGP Peer", trigger: "Route instability", severity: "Info", status: "Resolved", time: "30m ago" },
];

function AlertsAndIncidents() {
  const [filter, setFilter] = useState("All");

  const list = useMemo(() => {
    if (filter === "All") return incidentSeed;
    return incidentSeed.filter((item) => item.status === filter || item.severity === filter);
  }, [filter]);

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
                <td>{incident.device}</td>
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
