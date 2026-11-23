import React, { useCallback, useEffect, useState } from "react";
import { fetchDevices } from "../services/deviceService";
import { createRule, deleteRule, fetchRules, updateRule } from "../services/operationsService";

const initialForm = { name: "", metric: "latency_ms", operator: "gt", threshold: "100", severity: "warning", scope: "global", device_id: "" };
const metricNames = { device_status: "Device status", latency_ms: "Latency (ms)", packet_loss: "Packet loss (%)" };

function MonitoringRules() {
  const [rules, setRules] = useState([]); const [devices, setDevices] = useState([]);
  const [form, setForm] = useState(initialForm); const [error, setError] = useState("");
  const [busy, setBusy] = useState(false); const [loading, setLoading] = useState(true);
  const refresh = useCallback(async () => {
    setLoading(true); setError("");
    try { const [nextRules, nextDevices] = await Promise.all([fetchRules({ limit: 200 }), fetchDevices()]); setRules(nextRules); setDevices(nextDevices.devices); }
    catch (err) { setError(err.message); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => { void refresh(); }, [refresh]);
  const submit = async (event) => {
    event.preventDefault(); setBusy(true); setError("");
    const body = { ...form, threshold: form.metric === "device_status" ? form.threshold : Number(form.threshold),
      device_id: form.scope === "device" ? form.device_id : null };
    try { await createRule(body); setForm(initialForm); await refresh(); }
    catch (err) { setError(err.message); }
    finally { setBusy(false); }
  };
  const toggle = async (rule) => { setBusy(true); setError(""); try { await updateRule(rule.id, { enabled: !rule.enabled }); await refresh(); } catch (err) { setError(err.message); } finally { setBusy(false); } };
  const remove = async (rule) => { setBusy(true); setError(""); try { await deleteRule(rule.id); await refresh(); } catch (err) { setError(err.message); } finally { setBusy(false); } };
  return <div className="page-stack">
    <section className="page-header-row"><div><h2>Monitoring Rules</h2><p>Persisted rules are evaluated by the backend monitoring engine.</p></div><button type="button" className="secondary-button" onClick={refresh}>Refresh</button></section>
    {error && <p className="configuration-pending" role="alert">{error} <button type="button" className="secondary-button small-button" onClick={refresh}>Retry</button></p>}
    <section className="panel-card compact-panel"><h3>Create rule</h3><form className="inline-form" onSubmit={submit}>
      <label><span>Name</span><input required maxLength="120" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} /></label>
      <label><span>Metric</span><select value={form.metric} onChange={(e) => setForm({ ...form, metric: e.target.value, threshold: e.target.value === "device_status" ? "Offline" : "100", operator: e.target.value === "device_status" ? "eq" : "gt" })}><option value="device_status">Device status</option><option value="latency_ms">Latency</option><option value="packet_loss">Packet loss</option></select></label>
      <label><span>Operator</span><select value={form.operator} onChange={(e) => setForm({ ...form, operator: e.target.value })}>{(form.metric === "device_status" ? ["eq", "neq"] : ["gt", "gte", "lt", "lte", "eq", "neq"]).map((op) => <option key={op}>{op}</option>)}</select></label>
      <label><span>Threshold</span>{form.metric === "device_status" ? <select value={form.threshold} onChange={(e) => setForm({ ...form, threshold: e.target.value })}>{["Online", "Offline", "Warning", "Unknown", "Unmonitored"].map((s) => <option key={s}>{s}</option>)}</select> : <input type="number" min="0" max={form.metric === "packet_loss" ? "100" : undefined} step="any" required value={form.threshold} onChange={(e) => setForm({ ...form, threshold: e.target.value })} />}</label>
      <label><span>Severity</span><select value={form.severity} onChange={(e) => setForm({ ...form, severity: e.target.value })}><option value="info">Info</option><option value="warning">Warning</option><option value="critical">Critical</option></select></label>
      <label><span>Scope</span><select value={form.scope} onChange={(e) => setForm({ ...form, scope: e.target.value })}><option value="global">All devices</option><option value="device">One device</option></select></label>
      {form.scope === "device" && <label><span>Device</span><select required value={form.device_id} onChange={(e) => setForm({ ...form, device_id: e.target.value })}><option value="">Select device</option>{devices.map((d) => <option key={d.id} value={d.id}>{d.hostname}</option>)}</select></label>}
      <button className="primary-button" disabled={busy || loading}>Add rule</button>
    </form></section>
    <section className="panel-card"><div className="table-scroll"><table className="data-table rule-table"><thead><tr><th>Name</th><th>Scope</th><th>Condition</th><th>Severity</th><th>Status</th><th>Actions</th></tr></thead><tbody>
      {rules.map((rule) => <tr key={rule.id}><td>{rule.name}</td><td>{rule.scope === "device" ? devices.find((d) => d.id === rule.device_id)?.hostname || "Device" : "All devices"}</td><td>{metricNames[rule.metric]} {rule.operator} {String(rule.threshold)}</td><td>{rule.severity}</td><td>{rule.enabled ? "Enabled" : "Disabled"}</td><td><button type="button" className={`toggle-button ${rule.enabled ? "on" : "off"}`} disabled={busy} onClick={() => toggle(rule)}>{rule.enabled ? "Disable" : "Enable"}</button> <button type="button" className="secondary-button small-button" disabled={busy} onClick={() => remove(rule)}>Delete</button></td></tr>)}
      {loading && !rules.length && <tr><td colSpan="6">Loading rules...</td></tr>}{!loading && !error && !rules.length && <tr><td colSpan="6">No rules configured.</td></tr>}
    </tbody></table></div></section>
  </div>;
}
export default MonitoringRules;
