import React, { useCallback, useEffect, useMemo, useState } from "react";
import { fetchDevices } from "../services/deviceService";
import { acknowledgeIncident, fetchIncidents, resolveIncident } from "../services/operationsService";

function AlertsAndIncidents() {
  const [incidents, setIncidents] = useState([]); const [devices, setDevices] = useState([]);
  const [filter, setFilter] = useState("All"); const [deviceFilter, setDeviceFilter] = useState("All");
  const [error, setError] = useState(""); const [busyId, setBusyId] = useState(""); const [loading, setLoading] = useState(true);
  const refresh = useCallback(async () => { setLoading(true); setError(""); try {
    const [rows, deviceResult] = await Promise.all([fetchIncidents({ limit: 200 }), fetchDevices()]);
    setIncidents(rows); setDevices(deviceResult.devices);
  } catch (err) { setError(err.message); } finally { setLoading(false); } }, []);
  useEffect(() => { void refresh(); }, [refresh]);
  const list = useMemo(() => incidents.filter((item) => (filter === "All" || item.status === filter || item.severity === filter)
    && (deviceFilter === "All" || item.device_id === deviceFilter)), [deviceFilter, filter, incidents]);
  const act = async (incident, action) => { setBusyId(incident.id); setError(""); try {
    if (action === "acknowledge") await acknowledgeIncident(incident.id); else await resolveIncident(incident.id);
    await refresh();
  } catch (err) { setError(err.message); } finally { setBusyId(""); } };
  return <div className="page-stack">
    <section className="page-header-row"><div><h2>Alerts &amp; Incidents</h2><p>Incident state and severity are loaded from persisted backend records.</p></div><button type="button" className="secondary-button" onClick={refresh}>Refresh</button></section>
    {error && <p className="configuration-pending" role="alert">{error} <button type="button" className="secondary-button small-button" onClick={refresh}>Retry</button></p>}
    <section className="panel-card"><div className="filter-row">
      {["All", "open", "acknowledged", "resolved", "critical", "warning", "info"].map((item) => <button key={item} type="button" className={`filter-chip ${filter === item ? "active" : ""}`} onClick={() => setFilter(item)}>{item[0].toUpperCase() + item.slice(1)}</button>)}
      <select className="device-select-filter" value={deviceFilter} onChange={(e) => setDeviceFilter(e.target.value)} aria-label="Filter by device"><option value="All">All devices</option>{devices.map((d) => <option key={d.id} value={d.id}>{d.hostname}</option>)}</select>
    </div><div className="table-scroll"><table className="data-table incident-table"><thead><tr><th>Incident</th><th>Device</th><th>Trigger</th><th>Severity</th><th>Status</th><th>Triggered</th><th>Actions</th></tr></thead><tbody>
      {list.map((incident) => <tr key={incident.id}><td>{incident.title || incident.id}</td><td>{devices.find((d) => d.id === incident.device_id)?.hostname || incident.device_id}</td><td>{incident.description || incident.trigger_metric || "—"}</td><td><span className={`severity-pill ${incident.severity}`}>{incident.severity}</span></td><td>{incident.status}</td><td>{incident.triggered_at ? new Date(incident.triggered_at).toLocaleString() : "—"}</td><td className="action-cell">{incident.status === "open" && <button type="button" className="secondary-button small-button" disabled={busyId === incident.id} onClick={() => act(incident, "acknowledge")}>Acknowledge</button>}{incident.status !== "resolved" && <button type="button" className="primary-button small-button" disabled={busyId === incident.id} onClick={() => act(incident, "resolve")}>Resolve</button>}</td></tr>)}
      {loading && !list.length && <tr><td colSpan="7">Loading incidents...</td></tr>}{!loading && !error && !list.length && <tr><td colSpan="7">No incidents found.</td></tr>}
    </tbody></table></div></section>
  </div>;
}
export default AlertsAndIncidents;
