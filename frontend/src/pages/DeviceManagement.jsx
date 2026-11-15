import React from 'react';
import { useState } from "react";

const deviceInventory = [
  { id: 1, hostname: "core-sw-01", ip: "10.1.0.1", type: "Core Switch", status: "Healthy" },
  { id: 2, hostname: "edge-rt-01", ip: "192.168.1.10", type: "Router", status: "Warning" },
  { id: 3, hostname: "db-cluster-01", ip: "10.20.0.12", type: "Database", status: "Healthy" },
  { id: 4, hostname: "ap-west-3rdfloor", ip: "10.15.0.8", type: "Access Point", status: "Offline" },
];

function DeviceManagement({ onViewDevice }) {
  const [devices, setDevices] = useState(deviceInventory);
  const [showForm, setShowForm] = useState(false);
  const [newDevice, setNewDevice] = useState({ hostname: "", ip: "", type: "Switch", status: "Healthy" });

  const handleAdd = (event) => {
    event.preventDefault();

    if (!newDevice.hostname || !newDevice.ip) {
      return;
    }

    setDevices((current) => [
      ...current,
      {
        id: Date.now(),
        hostname: newDevice.hostname,
        ip: newDevice.ip,
        type: newDevice.type,
        status: newDevice.status,
      },
    ]);

    setNewDevice({ hostname: "", ip: "", type: "Switch", status: "Healthy" });
    setShowForm(false);
  };

  return (
    <div className="page-stack">
      <section className="page-header-row">
        <div>
          <h2>Device Inventory</h2>
          <p>Manage network assets and monitor operational health.</p>
        </div>
        <button type="button" className="primary-button" onClick={() => setShowForm((value) => !value)}>
          {showForm ? "Close" : "+ Add Device"}
        </button>
      </section>

      {showForm && (
        <section className="panel-card compact-panel">
          <h3>Add new device</h3>

          <form className="inline-form" onSubmit={handleAdd}>
            <label>
              <span>Hostname</span>
              <input
                type="text"
                value={newDevice.hostname}
                onChange={(event) => setNewDevice((current) => ({ ...current, hostname: event.target.value }))}
              />
            </label>
            <label>
              <span>IP Address</span>
              <input
                type="text"
                value={newDevice.ip}
                onChange={(event) => setNewDevice((current) => ({ ...current, ip: event.target.value }))}
              />
            </label>
            <label>
              <span>Device Type</span>
              <select
                value={newDevice.type}
                onChange={(event) => setNewDevice((current) => ({ ...current, type: event.target.value }))}
              >
                <option>Switch</option>
                <option>Router</option>
                <option>Access Point</option>
                <option>Firewall</option>
                <option>Database</option>
              </select>
            </label>
            <label>
              <span>Status</span>
              <select
                value={newDevice.status}
                onChange={(event) => setNewDevice((current) => ({ ...current, status: event.target.value }))}
              >
                <option>Healthy</option>
                <option>Warning</option>
                <option>Offline</option>
              </select>
            </label>
            <button type="submit" className="primary-button">Save device</button>
          </form>
        </section>
      )}

      <section className="panel-card">
        <table className="data-table device-table">
          <thead>
            <tr>
              <th>Hostname</th>
              <th>IP Address</th>
              <th>Device Type</th>
              <th>Status</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {devices.map((device) => (
              <tr key={device.id}>
                <td>{device.hostname}</td>
                <td>{device.ip}</td>
                <td>{device.type}</td>
                <td>
                  <span className={`status-tag ${device.status.toLowerCase()}`}>{device.status}</span>
                </td>
                <td className="action-cell">
                  <button type="button" className="secondary-button small-button" onClick={() => onViewDevice(device)}>
                    View Details
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
    </div>
  );
}

export default DeviceManagement;
