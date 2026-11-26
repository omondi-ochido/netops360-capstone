import React, { useEffect, useState } from "react";
import { backupDeviceConfig, fetchDeviceHistory, getDevice, updateDevice } from "../services/deviceService";

function DeviceDetails({ deviceId, device: selectedDevice, onBack }) {
  const [liveDevice, setLiveDevice] = useState(null);
  const [history, setHistory] = useState([]);
  const [loadError, setLoadError] = useState("");
  const [backup, setBackup] = useState(null);
  const [backupError, setBackupError] = useState("");
  const [isBackingUp, setIsBackingUp] = useState(false);
  const [protocolError, setProtocolError] = useState("");
  const [isUpdatingProtocol, setIsUpdatingProtocol] = useState(false);
  const [copyStatus, setCopyStatus] = useState("");

  useEffect(() => {
    let isMounted = true;
    const refreshDevice = async () => {
      try {
        const [current, rows] = await Promise.all([getDevice(deviceId), fetchDeviceHistory(deviceId, { limit: 30 })]);
        if (!isMounted) return;
        setLiveDevice(current); setHistory(rows); setLoadError("");
      } catch (error) { if (isMounted) setLoadError(error.message); }
    };

    void refreshDevice();
    const intervalId = window.setInterval(refreshDevice, 5000);
    return () => {
      isMounted = false;
      window.clearInterval(intervalId);
    };
  }, [deviceId, selectedDevice?.hostname]);

  const device = liveDevice;
  const deviceType = device?.deviceType?.toLowerCase();
  const canBackup = device?.sshEnabled || deviceType === "router" || deviceType === "switch";
  const monitoringProtocol = device?.monitoringMethod?.toLowerCase() === "tcp" ? "tcp" : "icmp";
  const chronologicalHistory = [...history].sort(
    (left, right) => new Date(left.checked_at) - new Date(right.checked_at),
  );
  const latencySamples = chronologicalHistory
    .map((row) => ({ ...row, latency: row.latency_ms == null ? null : Number(row.latency_ms) }))
    .filter((row) => Number.isFinite(row.latency));
  const latencyValues = latencySamples.map((row) => row.latency);
  const averageLatency = latencyValues.length
    ? latencyValues.reduce((total, latency) => total + latency, 0) / latencyValues.length
    : null;
  const minLatency = latencyValues.length ? Math.min(...latencyValues) : null;
  const maxLatency = latencyValues.length ? Math.max(...latencyValues) : null;
  const availabilityChecks = chronologicalHistory.filter(
    (row) => ["online", "warning", "offline"].includes(String(row.status).toLowerCase()),
  );
  const availableCount = availabilityChecks.filter(
    (row) => ["online", "warning"].includes(String(row.status).toLowerCase()),
  ).length;
  const uptimePercentage = availabilityChecks.length
    ? (availableCount / availabilityChecks.length) * 100
    : null;
  const chartWidth = 720;
  const chartHeight = 220;
  const chartPadding = { top: 16, right: 18, bottom: 30, left: 52 };
  const plotWidth = chartWidth - chartPadding.left - chartPadding.right;
  const plotHeight = chartHeight - chartPadding.top - chartPadding.bottom;
  const latencyPadding = latencyValues.length
    ? Math.max((maxLatency - minLatency) * 0.1, maxLatency * 0.1, 1)
    : 1;
  const scaleMin = latencyValues.length ? Math.max(0, minLatency - latencyPadding) : 0;
  const scaleMax = latencyValues.length ? maxLatency + latencyPadding : 1;
  const chartPoints = latencySamples.map((row, index) => ({
    ...row,
    x: chartPadding.left + (latencySamples.length === 1
      ? plotWidth / 2
      : (index / (latencySamples.length - 1)) * plotWidth),
    y: chartPadding.top + ((scaleMax - row.latency) / (scaleMax - scaleMin)) * plotHeight,
  }));
  const linePath = chartPoints.map((point, index) =>
    `${index === 0 ? "M" : "L"} ${point.x} ${point.y}`).join(" ");
  const areaPath = chartPoints.length > 1
    ? `${linePath} L ${chartPoints[chartPoints.length - 1].x} ${chartHeight - chartPadding.bottom} L ${chartPoints[0].x} ${chartHeight - chartPadding.bottom} Z`
    : "";

  const handleProtocolChange = async (event) => {
    const monitoringMethod = event.target.value;
    setIsUpdatingProtocol(true);
    setProtocolError("");
    try {
      setLiveDevice(await updateDevice(device.id, { monitoring_method: monitoringMethod }));
    } catch (error) {
      setProtocolError(error.message);
    } finally {
      setIsUpdatingProtocol(false);
    }
  };

  const handleBackup = async () => {
    setIsBackingUp(true);
    setBackupError("");
    setCopyStatus("");
    try {
      const result = await backupDeviceConfig(device.id);
      setBackup(result);
    } catch (error) {
      setBackupError(error.message);
    } finally {
      setIsBackingUp(false);
    }
  };

  const handleCopyConfig = async () => {
    try {
      const interfaceSection = deviceType !== "switch" && backup.interfaces
        ? `\n\n=== INTERFACE STATUS ===\n${backup.interfaces}`
        : "";
      await navigator.clipboard.writeText(`${backup.configuration}${interfaceSection}`);
      setCopyStatus("Configuration copied.");
    } catch (error) {
      setCopyStatus(error.message || "Could not copy configuration.");
    }
  };

  if (!device) {
    return (
      <div className="page-stack">
        <section className="panel-card">
          <h2>{loadError ? "Device data unavailable" : "Loading device..."}</h2>
          {loadError && <p role="alert">{loadError}</p>}
          <button type="button" className="secondary-button" onClick={onBack}>Back to inventory</button>
        </section>
      </div>
    );
  }

  return (
    <div className="page-stack">
      <section className="page-header-row">
        <div>
          <h2>{device.hostname}</h2>
          <p>{device.deviceType} • {device.ipAddress} • {device.site} • Persisted backend record</p>
        </div>
        <div className="header-button-group">
          <button type="button" className="secondary-button" onClick={onBack}>Back to inventory</button>
          <button type="button" className="primary-button" disabled title="No device command endpoint is configured">Restart Device</button>
        </div>
      </section>

      <section className="details-grid">
        <div className="panel-card">
          <div className="panel-header-row">
            <div>
              <span className="eyebrow-text">Overview</span>
              <h3>Device info</h3>
            </div>
            <span className={`status-tag ${device.status.toLowerCase()}`}>{device.status}</span>
          </div>

          <div className="info-grid">
            <div><label>Hostname</label><strong>{device.hostname}</strong></div>
            <div><label>IP Address</label><strong>{device.ipAddress}</strong></div>
            <div><label>Device Type</label><strong>{device.deviceType}</strong></div>
            <div><label>Operating System</label><strong>{device.os || "Not specified"}</strong></div>
            <div><label>Site</label><strong>{device.site}</strong></div>
            <div><label>Last Checked</label><strong>{device.lastChecked}</strong></div>
            <div>
              <label htmlFor="device-monitoring-protocol">Monitoring protocol</label>
              <select
                id="device-monitoring-protocol"
                className="device-select-filter"
                value={monitoringProtocol}
                disabled={isUpdatingProtocol}
                onChange={(event) => void handleProtocolChange(event)}
              >
                <option value="icmp">ICMP</option>
                <option value="tcp">TCP</option>
              </select>
              <strong><span className="status-badge neutral">{monitoringProtocol.toUpperCase()}</span></strong>
              {protocolError && <p role="alert">{protocolError}</p>}
            </div>
            <div><label>Monitoring</label><strong>{device.monitoringEnabled ? `Enabled every ${device.monitorIntervalSeconds}s` : "Paused"}</strong></div>
          </div>
        </div>

        <div className="panel-card">
          <div className="panel-header-row">
            <div>
              <span className="eyebrow-text">Metrics</span>
              <h3>Latency &amp; packet loss</h3>
            </div>
          </div>

          <div className="metric-list">
            <div>
              <span>Latency</span>
              <strong>{Number.isFinite(device.latencyMs) ? `${device.latencyMs} ms` : "N/A"}</strong>
            </div>
            <div>
              <span>Packet loss</span>
              <strong>{Number.isFinite(device.packetLoss) ? `${device.packetLoss}%` : "N/A"}</strong>
            </div>
            <div>
              <span>Status</span>
              <strong>{device.status}</strong>
            </div>
            <div>
              <span>Site</span>
              <strong>{device.site}</strong>
            </div>
          </div>
        </div>
      </section>

      <section className="details-grid">
        <div className="panel-card">
          <div className="panel-header-row">
            <div>
              <span className="eyebrow-text">Performance</span>
              <h3>Response latency</h3>
            </div>
            <span className="status-badge neutral">Milliseconds</span>
          </div>
          {latencySamples.length ? (
            <>
              <div className="metric-list">
                <div><span>Average</span><strong>{averageLatency.toFixed(2)} ms</strong></div>
                <div><span>Minimum</span><strong>{minLatency.toFixed(2)} ms</strong></div>
                <div><span>Maximum</span><strong>{maxLatency.toFixed(2)} ms</strong></div>
              </div>
              <svg
                viewBox={`0 0 ${chartWidth} ${chartHeight}`}
                role="img"
                aria-label="Recent response latency trend in milliseconds"
                style={{ display: "block", width: "100%", height: "auto", marginTop: "1rem" }}
              >
                {[0, 0.5, 1].map((fraction) => {
                  const y = chartPadding.top + plotHeight * fraction;
                  const value = scaleMax - (scaleMax - scaleMin) * fraction;
                  return (
                    <g key={fraction}>
                      <line x1={chartPadding.left} x2={chartWidth - chartPadding.right} y1={y} y2={y} stroke="#e2e8f0" />
                      <text x={chartPadding.left - 8} y={y + 4} textAnchor="end" fill="#475569" fontSize="12">
                        {value.toFixed(1)}
                      </text>
                    </g>
                  );
                })}
                {areaPath && <path d={areaPath} fill="#38bdf8" fillOpacity="0.18" />}
                <path d={linePath} fill="none" stroke="#0284c7" strokeWidth="3" strokeLinejoin="round" strokeLinecap="round" />
                {chartPoints.map((point, index) => (
                  <circle key={`${point.checked_at}-${index}`} cx={point.x} cy={point.y} r="3.5" fill="#0369a1">
                    <title>{`${new Date(point.checked_at).toLocaleString()}: ${point.latency} ms`}</title>
                  </circle>
                ))}
                <text x={chartPadding.left} y={chartHeight - 5} fill="#475569" fontSize="11">
                  {new Date(latencySamples[0].checked_at).toLocaleTimeString()}
                </text>
                {latencySamples.length > 1 && (
                  <text x={chartWidth - chartPadding.right} y={chartHeight - 5} textAnchor="end" fill="#475569" fontSize="11">
                    {new Date(latencySamples[latencySamples.length - 1].checked_at).toLocaleTimeString()}
                  </text>
                )}
              </svg>
            </>
          ) : <p>No latency measurements are available in recent monitoring history.</p>}
        </div>

        <div className="panel-card">
          <div className="panel-header-row">
            <div>
              <span className="eyebrow-text">Availability</span>
              <h3>Status history</h3>
            </div>
            <strong>{uptimePercentage == null ? "N/A" : `${uptimePercentage.toFixed(1)}%`}</strong>
          </div>
          <p>Estimated uptime from the latest {availabilityChecks.length} recorded checks.</p>
          {availabilityChecks.length ? (
            <>
              <div
                role="img"
                aria-label={`Status history: ${uptimePercentage.toFixed(1)} percent available`}
                style={{ display: "flex", gap: "3px", width: "100%", minHeight: "24px", margin: "1.25rem 0" }}
              >
                {availabilityChecks.map((row, index) => {
                  const status = String(row.status).toLowerCase();
                  const color = status === "online"
                    ? "#16a34a"
                    : status === "warning"
                      ? "#d97706"
                      : "#dc2626";
                  return (
                    <span
                      key={`${row.id || row.checked_at}-${index}`}
                      title={`${new Date(row.checked_at).toLocaleString()}: ${row.status}`}
                      style={{ backgroundColor: color, borderRadius: "3px", flex: "1 1 0" }}
                    />
                  );
                })}
              </div>
              <div className="metric-list">
                <div><span>Available checks</span><strong>{availableCount} / {availabilityChecks.length}</strong></div>
                <div><span>Latest check</span><strong>{availabilityChecks[availabilityChecks.length - 1].status}</strong></div>
              </div>
              <p style={{ color: "#475569", fontSize: "0.875rem" }}>Online and warning checks count as available.</p>
            </>
          ) : <p>No status history is available yet.</p>}
        </div>
      </section>

      <section className="panel-card"><h3>Monitoring history</h3>{history.length ? <div className="table-scroll"><table className="data-table"><thead><tr><th>Checked</th><th>Status</th><th>Latency</th><th>Packet loss</th><th>Check type</th></tr></thead><tbody>{history.map((row) => <tr key={row.id}><td>{new Date(row.checked_at).toLocaleString()}</td><td>{row.status}</td><td>{row.latency_ms == null ? "N/A" : `${row.latency_ms} ms`}</td><td>{row.packet_loss == null ? "N/A" : `${row.packet_loss}%`}</td><td>{row.check_type}</td></tr>)}</tbody></table></div> : <p>No persisted monitoring checks yet.</p>}</section>

      <section className="panel-card">
        <div className="panel-header-row">
          <div>
            <span className="eyebrow-text">Config</span>
            <h3>Configuration backup</h3>
          </div>
        </div>

        <div className="backup-row">
          <div className="backup-meta">
            <strong>Configuration backup</strong>
            <span>
              {backup
                ? backup.backup?.created_at
                  ? `Latest snapshot: ${new Date(backup.backup.created_at).toLocaleString()}`
                  : "Snapshot retrieved; timestamp unavailable"
                : "No backup retrieved"}
            </span>
          </div>
          {canBackup && (
            <button type="button" className="primary-button" onClick={handleBackup} disabled={isBackingUp}>
              {isBackingUp ? "Retrieving..." : "Fetch / Backup Live Configuration"}
            </button>
          )}
        </div>
        {!canBackup && <p>SSH backup is unavailable because this device type is not supported or SSH is not enabled.</p>}
        {backupError && <p className="configuration-pending" role="alert">{backupError}</p>}
        {backup && (
          <div className="config-backup-output">
            <div className="panel-header-row">
              <h4>{deviceType === "switch" ? "Open vSwitch configuration & diagnostics" : "VyOS running configuration"}</h4>
              <button type="button" className="secondary-button" onClick={() => void handleCopyConfig()}>
                Copy Config
              </button>
            </div>
            <pre>{backup.configuration}</pre>
            {deviceType !== "switch" && backup.interfaces && (
              <>
                <h4>Interface status</h4>
                <pre>{backup.interfaces}</pre>
              </>
            )}
            {copyStatus && <p role="status">{copyStatus}</p>}
          </div>
        )}
      </section>

      <section className="action-grid">
        <button type="button" className="secondary-button" disabled title="No device command endpoint is configured">Reboot</button>
        <button type="button" className="secondary-button" disabled title="No diagnostics endpoint is configured">Run Diagnostics</button>
        <button type="button" className="secondary-button" disabled title="No policy endpoint is configured">Push Policy</button>
        <button type="button" className="secondary-button" disabled title="Tier assignment is not configured">Assign Tier</button>
      </section>
    </div>
  );
}

export default DeviceDetails;
