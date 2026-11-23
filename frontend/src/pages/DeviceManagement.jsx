import React, { useCallback, useEffect, useMemo, useState } from "react";
import { createDevice, deactivateDevice, fetchDevices, updateDevice } from "../services/deviceService";

const filters = ["All", "Routers", "Switches", "Hosts", "Servers"];
const filterTypes = { Routers: "Router", Switches: "Switch", Hosts: "Host", Servers: "Server" };
const emptyForm = { hostname: "", ipAddress: "", deviceType: "switch", os: "", site: "main-site" };

function DeviceManagement({ onViewDevice }) {
  const [devices, setDevices] = useState([]);
  const [isLoading, setIsLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [showForm, setShowForm] = useState(false);
  const [editingDevice, setEditingDevice] = useState(null);
  const [activeFilter, setActiveFilter] = useState("All");
  const [search, setSearch] = useState("");
  const [newDevice, setNewDevice] = useState(emptyForm);
  const [error, setError] = useState("");

  const refreshDevices = useCallback(async () => {
    setIsLoading(true);
    try { setDevices((await fetchDevices()).devices); setError(""); }
    catch (err) { setError(err.message); }
    finally { setIsLoading(false); }
  }, []);

  useEffect(() => {
    void refreshDevices();
    const intervalId = window.setInterval(refreshDevices, 15000);
    return () => window.clearInterval(intervalId);
  }, [refreshDevices]);

  const visibleDevices = useMemo(() => {
    const query = search.trim().toLowerCase();
    return devices.filter((device) => (activeFilter === "All" || device.deviceType === filterTypes[activeFilter])
      && (!query || [device.hostname, device.ipAddress, device.deviceType, device.site, device.status]
        .some((value) => value?.toLowerCase().includes(query))));
  }, [activeFilter, devices, search]);

  const handleAdd = async (event) => {
    event.preventDefault(); setBusy(true); setError("");
    try {
      const body = { hostname: newDevice.hostname.trim(), ip_address: newDevice.ipAddress.trim(),
        device_type: newDevice.deviceType, operating_system: newDevice.os.trim() || null, site: newDevice.site };
      if (editingDevice) await updateDevice(editingDevice.id, body);
      else await createDevice({ ...body, monitoring_method: "icmp", monitoring_enabled: true });
      setNewDevice(emptyForm); setEditingDevice(null); setShowForm(false); await refreshDevices();
    } catch (err) { setError(err.message); }
    finally { setBusy(false); }
  };

  const startEdit = (device) => {
    const deviceType = device.deviceType.toLowerCase().replaceAll(" ", "_");
    setEditingDevice(device);
    setNewDevice({ hostname: device.hostname, ipAddress: device.ipAddress, deviceType,
      os: device.os || "", site: device.site || "main-site" });
    setShowForm(true);
  };

  const handleMonitoringToggle = async (device) => {
    setBusy(true); setError("");
    try {
      const changes = { monitoring_enabled: !device.monitoringEnabled };
      if (!device.monitoringEnabled && device.monitoringMethod === "none") changes.monitoring_method = "icmp";
      await updateDevice(device.id, changes); await refreshDevices();
    } catch (err) { setError(err.message); }
    finally { setBusy(false); }
  };

  const handleDeactivate = async (device) => {
    if (!window.confirm(`Deactivate ${device.hostname}? Its history will be retained.`)) return;
    setBusy(true); setError("");
    try { await deactivateDevice(device.id); await refreshDevices(); }
    catch (err) { setError(err.message); }
    finally { setBusy(false); }
  };

  return (
    <div className="page-stack">
      <section className="page-header-row">
        <div><h2>Device Inventory</h2><p>Manage persisted network assets and monitoring settings.</p></div>
        <div className="header-button-group">
          <button type="button" className="secondary-button" onClick={refreshDevices} disabled={isLoading}>{isLoading ? "Refreshing..." : "Refresh"}</button>
          <button type="button" className="primary-button" onClick={() => { setShowForm((value) => !value); setEditingDevice(null); setNewDevice(emptyForm); }}>{showForm ? "Close" : "+ Add Device"}</button>
        </div>
      </section>
      {error && <p className="configuration-pending" role="alert">{error} <button type="button" className="secondary-button small-button" onClick={refreshDevices}>Retry</button></p>}

      {showForm && <section className="panel-card compact-panel"><h3>{editingDevice ? `Edit ${editingDevice.hostname}` : "Add device"}</h3><form className="inline-form" onSubmit={handleAdd}>
        <label><span>Hostname</span><input value={newDevice.hostname} onChange={(e) => setNewDevice({ ...newDevice, hostname: e.target.value })} required /></label>
        <label><span>IP address</span><input value={newDevice.ipAddress} onChange={(e) => setNewDevice({ ...newDevice, ipAddress: e.target.value })} required /></label>
        <label><span>Device type</span><select value={newDevice.deviceType} onChange={(e) => setNewDevice({ ...newDevice, deviceType: e.target.value })}>{["switch", "router", "host", "server", "firewall", "access_point", "other"].map((t) => <option key={t} value={t}>{t.replace("_", " ")}</option>)}</select></label>
        <label><span>Operating system</span><input value={newDevice.os} onChange={(e) => setNewDevice({ ...newDevice, os: e.target.value })} /></label>
        <label><span>Site</span><input value={newDevice.site} onChange={(e) => setNewDevice({ ...newDevice, site: e.target.value })} required /></label>
        <button type="submit" className="primary-button" disabled={busy}>{busy ? "Saving..." : editingDevice ? "Update device" : "Save device"}</button>
      </form></section>}

      <section className="panel-card">
        <div className="inventory-toolbar">
          <div className="device-filters" role="group" aria-label="Filter devices by type">{filters.map((filter) => <button key={filter} type="button" className={`filter-chip ${activeFilter === filter ? "active" : ""}`} onClick={() => setActiveFilter(filter)}>{filter}</button>)}</div>
          <input className="device-search" type="search" value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Search hostname, IP, site, or status" aria-label="Search devices" />
        </div>
        <div className="table-scroll"><table className="data-table device-table">
          <thead><tr><th>Hostname</th><th>IP Address</th><th>Type</th><th>Site</th><th>Status</th><th>Latency</th><th>Packet loss</th><th>Monitoring</th><th>Actions</th></tr></thead>
          <tbody>{visibleDevices.map((device) => <tr key={device.id}>
            <td>{device.hostname}</td><td>{device.ipAddress}</td><td>{device.deviceType}</td><td>{device.site}</td>
            <td><span className={`status-tag ${device.status.toLowerCase()}`}>{device.status}</span></td>
            <td>{Number.isFinite(device.latencyMs) ? `${device.latencyMs} ms` : "N/A"}</td>
            <td>{Number.isFinite(device.packetLoss) ? `${device.packetLoss}%` : "N/A"}</td>
            <td>{device.monitoringEnabled ? "Enabled" : "Paused"}</td>
            <td className="action-cell"><button type="button" className="secondary-button small-button" onClick={() => onViewDevice(device)}>Details</button>
              <button type="button" className="secondary-button small-button" onClick={() => startEdit(device)}>Edit</button>
              <button type="button" className="secondary-button small-button" disabled={busy} onClick={() => handleMonitoringToggle(device)}>{device.monitoringEnabled ? "Pause" : "Enable"}</button>
              <button type="button" className="secondary-button small-button" disabled={busy} onClick={() => handleDeactivate(device)}>Deactivate</button></td>
          </tr>)}
          {visibleDevices.length === 0 && <tr><td colSpan="9" className="empty-table-message">{isLoading ? "Loading devices..." : error ? "Device data unavailable." : "No devices match this search."}</td></tr>}</tbody>
        </table></div>
      </section>
    </div>
  );
}

export default DeviceManagement;
