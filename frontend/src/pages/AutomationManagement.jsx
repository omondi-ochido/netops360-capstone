import React, { useCallback, useEffect, useState } from "react";
import { fetchDevices } from "../services/deviceService";
import { fetchAutomationLogs, retryAutomation } from "../services/operationsService";

function AutomationManagement() {
  const [logs, setLogs] = useState([]); const [devices, setDevices] = useState([]);
  const [error, setError] = useState(""); const [busyId, setBusyId] = useState(""); const [loading, setLoading] = useState(true);
  const refresh = useCallback(async () => { setLoading(true); setError(""); try {
    const [rows, deviceResult] = await Promise.all([fetchAutomationLogs({ limit: 200 }), fetchDevices()]);
    setLogs(rows); setDevices(deviceResult.devices);
  } catch (err) { setError(err.message); } finally { setLoading(false); } }, []);
  useEffect(() => { void refresh(); }, [refresh]);
  const retry = async (log) => { setBusyId(log.id); setError(""); try { await retryAutomation(log.id); await refresh(); } catch (err) { setError(err.message); } finally { setBusyId(""); } };
  return <div className="page-stack">
    <section className="page-header-row"><div><h2>Automation Management</h2><p>Delivery state comes from persisted webhook execution records.</p></div><button type="button" className="secondary-button" onClick={refresh}>Refresh</button></section>
    {error && <p className="configuration-pending" role="alert">{error} <button type="button" className="secondary-button small-button" onClick={refresh}>Retry loading</button></p>}
    <section className="panel-card"><div className="panel-header-row"><div><span className="eyebrow-text">n8n delivery history</span><h3>Automation executions</h3></div></div><div className="table-scroll"><table className="data-table log-table"><thead><tr><th>Created</th><th>Workflow</th><th>Trigger</th><th>Device</th><th>Status</th><th>Retries</th><th>Result</th><th>Action</th></tr></thead><tbody>
      {logs.map((log) => <tr key={log.id}><td>{log.created_at ? new Date(log.created_at).toLocaleString() : "—"}</td><td>{log.workflow_name}</td><td>{log.trigger_type}</td><td>{devices.find((d) => d.id === log.device_id)?.hostname || log.device_id || "—"}</td><td><span className={`status-tag ${log.status}`}>{log.status}</span></td><td>{log.retry_count}</td><td>{log.error_message || log.execution_id || (log.status === "success" ? "Delivered" : "Awaiting result")}</td><td>{["failed", "pending"].includes(log.status) && <button type="button" className="primary-button small-button" disabled={busyId === log.id} onClick={() => retry(log)}>{busyId === log.id ? "Retrying..." : "Retry"}</button>}</td></tr>)}
      {loading && !logs.length && <tr><td colSpan="8">Loading automation logs...</td></tr>}{!loading && !error && !logs.length && <tr><td colSpan="8">No automation executions recorded. Webhook delivery requires N8N_WEBHOOK_URL.</td></tr>}
    </tbody></table></div></section>
  </div>;
}
export default AutomationManagement;
