import React, { useCallback, useEffect, useState } from "react";
import { fetchDevices } from "../services/deviceService";
import { fetchAutomationLogs, fetchBackups, retryAutomation } from "../services/operationsService";

function AutomationManagement() {
  const [logs, setLogs] = useState([]); const [backups, setBackups] = useState([]); const [devices, setDevices] = useState([]);
  const [error, setError] = useState(""); const [busyId, setBusyId] = useState(""); const [loading, setLoading] = useState(true);
  const refresh = useCallback(async () => { setLoading(true); setError(""); try {
    const [rows, backupRows, deviceResult] = await Promise.all([fetchAutomationLogs({ limit: 200 }), fetchBackups({ limit: 200 }), fetchDevices()]);
    setLogs(rows); setBackups(backupRows); setDevices(deviceResult.devices);
  } catch (err) { setError(err.message); } finally { setLoading(false); } }, []);
  useEffect(() => { void refresh(); }, [refresh]);
  const retry = async (log) => { setBusyId(log.id); setError(""); try { await retryAutomation(log.id); await refresh(); } catch (err) { setError(err.message); } finally { setBusyId(""); } };
  return <div className="page-stack">
    <section className="page-header-row"><div><h2>Automation Management</h2><p>Delivery state comes from persisted webhook execution records.</p></div><button type="button" className="secondary-button" onClick={refresh}>Refresh</button></section>
    {error && <p className="configuration-pending" role="alert">{error} <button type="button" className="secondary-button small-button" onClick={refresh}>Retry loading</button></p>}
    <section className="panel-card"><div className="panel-header-row"><div><span className="eyebrow-text">n8n delivery history</span><h3>Automation executions</h3></div></div><div className="table-scroll"><table className="data-table log-table"><thead><tr><th>Created</th><th>Workflow</th><th>Trigger</th><th>Incident</th><th>Device</th><th>Status</th><th>Retries</th><th>Result</th><th>Action</th></tr></thead><tbody>
      {logs.map((log) => { const summary = log.response_payload?.summary; const result = typeof summary === "string" ? summary : summary ? JSON.stringify(summary) : ""; return <tr key={log.id}><td>{log.created_at ? new Date(log.created_at).toLocaleString() : "—"}</td><td>{log.workflow_name}</td><td>{log.trigger_type}</td><td>{log.incident_id || "—"}</td><td>{devices.find((d) => d.id === log.device_id)?.hostname || log.device_id || "—"}</td><td><span className={`status-tag ${log.status}`}>{log.status}</span></td><td>{log.retry_count}</td><td>{log.error_message || result || log.execution_id || (log.status === "success" ? "Completed" : "Awaiting result")}</td><td>{["failed", "pending"].includes(log.status) && <button type="button" className="primary-button small-button" disabled={busyId === log.id} onClick={() => retry(log)}>{busyId === log.id ? "Retrying..." : "Retry"}</button>}</td></tr>; })}
      {loading && !logs.length && <tr><td colSpan="8">Loading automation logs...</td></tr>}{!loading && !error && !logs.length && <tr><td colSpan="8">No automation executions recorded. Webhook delivery requires N8N_WEBHOOK_URL.</td></tr>}
    </tbody></table></div></section>
    <section className="panel-card"><div className="panel-header-row"><div><span className="eyebrow-text">Configuration snapshots</span><h3>Backup history</h3></div><span>{backups.filter((row) => row.status === "success").length} successful · {backups.filter((row) => row.status === "failed").length} failed</span></div><div className="table-scroll"><table className="data-table"><thead><tr><th>Created</th><th>Device</th><th>Type</th><th>Status</th><th>Changed</th><th>Checksum</th><th>Result</th></tr></thead><tbody>
      {backups.map((backup) => <tr key={backup.id}><td>{backup.created_at ? new Date(backup.created_at).toLocaleString() : "—"}</td><td>{devices.find((d) => d.id === backup.device_id)?.hostname || backup.device_id}</td><td>{backup.backup_type}</td><td><span className={`status-tag ${backup.status}`}>{backup.status}</span></td><td>{backup.status === "success" ? (backup.metadata?.changed ? "Yes" : "No") : "—"}</td><td>{backup.checksum || "—"}</td><td>{backup.error_message || "—"}</td></tr>)}
      {loading && !backups.length && <tr><td colSpan="7">Loading backup history...</td></tr>}{!loading && !error && !backups.length && <tr><td colSpan="7">No backups recorded.</td></tr>}
    </tbody></table></div></section>
  </div>;
}
export default AutomationManagement;
