import React from "react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { discoveredDevices } from "../data/discoveredDevices";
import { fetchDevices } from "../services/deviceService";

const filters = ["All", "Routers", "Switches", "Hosts", "Servers"];
const filterTypes = {
  Routers: "Router",
  Switches: "Switch",
  Hosts: "Host",
  Servers: "Server",
};

function DeviceManagement({ onViewDevice }) {
  const [devices, setDevices] = useState(discoveredDevices);
  const [manualDevices, setManualDevices] = useState([]);
  const [isLive, setIsLive] = useState(false);
  const [isLoading, setIsLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [activeFilter, setActiveFilter] = useState("All");
  const [search, setSearch] = useState("");
  const [newDevice, setNewDevice] = useState({
    hostname: "",
    ipAddress: "",
    deviceType: "Switch",
    os: "",
    site: "Main Site",
    status: "Online",
  });

  const refreshDevices = useCallback(async () => {
    setIsLoading(true);
    const result = await fetchDevices();
    setDevices(result.devices);
    setIsLive(result.isLive);
    setIsLoading(false);
  }, []);

  useEffect(() => {
    void refreshDevices();
    const intervalId = window.setInterval(refreshDevices, 15000);
    return () => window.clearInterval(intervalId);
  }, [refreshDevices]);

  const allDevices = useMemo(() => [...devices, ...manualDevices], [devices, manualDevices]);
  const visibleDevices = useMemo(() => {
    const query = search.trim().toLowerCase();
    return allDevices.filter((device) => {
      const matchesType = activeFilter === "All" || device.deviceType === filterTypes[activeFilter];
      const matchesSearch = !query || [
        device.hostname,
        device.ipAddress,
        device.deviceType,
        device.site,
        device.status,
      ].some((value) => value?.toLowerCase().includes(query));
      return matchesType && matchesSearch;
    });
  }, [activeFilter, allDevices, search]);

  const handleAdd = (event) => {
    event.preventDefault();
    if (!newDevice.hostname.trim() || !newDevice.ipAddress.trim()) return;

    const device = {
      ...newDevice,
      id: newDevice.hostname.trim(),
      hostname: newDevice.hostname.trim(),
      ipAddress: newDevice.ipAddress.trim(),
      latencyMs: 0,
      packetLoss: 0,
      discoveredMethod: "Manually Added",
      lastChecked: "Not checked",
      configurationPending: true,
    };

    setManualDevices((current) => [...current, device]);
    setNewDevice({
      hostname: "",
      ipAddress: "",
      deviceType: "Switch",
      os: "",
      site: "Main Site",
      status: "Online",
    });
    setShowForm(false);
  };

  return (
    <div className="page-stack">
      <section className="page-header-row">
        <div>
          <h2>Device Inventory</h2>
          <p>Manage network assets and monitor operational health. {isLive ? "Live GNS3 telemetry." : "Showing fallback inventory."}</p>
        </div>
        <div className="header-button-group">
          {isLive && <span className="status-badge neutral">Live GNS3 Telemetry</span>}
          <button type="button" className="secondary-button" onClick={refreshDevices} disabled={isLoading}>
            {isLoading ? "Refreshing..." : "Refresh Poll"}
          </button>
          <button type="button" className="primary-button" onClick={() => setShowForm((value) => !value)}>
            {showForm ? "Close" : "+ Add Device"}
          </button>
        </div>
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
                required
              />
            </label>
            <label>
              <span>IP Address</span>
              <input
                type="text"
                value={newDevice.ipAddress}
                onChange={(event) => setNewDevice((current) => ({ ...current, ipAddress: event.target.value }))}
                required
              />
            </label>
            <label>
              <span>Device Type</span>
              <select
                value={newDevice.deviceType}
                onChange={(event) => setNewDevice((current) => ({ ...current, deviceType: event.target.value }))}
              >
                <option>Switch</option>
                <option>Router</option>
                <option>Host</option>
                <option>Server</option>
              </select>
            </label>
            <label>
              <span>OS</span>
              <input
                type="text"
                value={newDevice.os}
                onChange={(event) => setNewDevice((current) => ({ ...current, os: event.target.value }))}
              />
            </label>
            <label>
              <span>Site</span>
              <select
                value={newDevice.site}
                onChange={(event) => setNewDevice((current) => ({ ...current, site: event.target.value }))}
              >
                <option>Management</option>
                <option>Main Site</option>
                <option>Branch Site</option>
              </select>
            </label>
            <label>
              <span>Status</span>
              <select
                value={newDevice.status}
                onChange={(event) => setNewDevice((current) => ({ ...current, status: event.target.value }))}
              >
                <option>Online</option>
                <option>Warning</option>
                <option>Offline</option>
              </select>
            </label>
            <button type="submit" className="primary-button">Save device</button>
          </form>
        </section>
      )}

      <section className="panel-card">
        <div className="inventory-toolbar">
          <div className="device-filters" role="group" aria-label="Filter devices by type">
            {filters.map((filter) => (
              <button
                key={filter}
                type="button"
                className={`filter-chip ${activeFilter === filter ? "active" : ""}`}
                onClick={() => setActiveFilter(filter)}
              >
                {filter}
              </button>
            ))}
          </div>
          <input
            className="device-search"
            type="search"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder="Search hostname, IP, site, or status"
            aria-label="Search devices"
          />
        </div>

        <div className="table-scroll">
          <table className="data-table device-table">
            <thead>
              <tr>
                <th>Hostname</th>
                <th>IP Address</th>
                <th>Device Type</th>
                <th>Site</th>
                <th>Status</th>
                <th>Latency</th>
                <th>Packet Loss</th>
                <th>Discovery</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {visibleDevices.map((device) => (
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
                    <span className="discovered-tag">
                      {device.discoveredMethod === "Manually Added" ? "Manual" : "Discovered"}
                    </span>
                  </td>
                  <td className="action-cell">
                    <button type="button" className="secondary-button small-button" onClick={() => onViewDevice(device)}>
                      View Details
                    </button>
                  </td>
                </tr>
              ))}
              {visibleDevices.length === 0 && (
                <tr>
                  <td colSpan="9" className="empty-table-message">
                    {isLoading ? "Loading devices..." : "No devices match this search."}
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}

export default DeviceManagement;
