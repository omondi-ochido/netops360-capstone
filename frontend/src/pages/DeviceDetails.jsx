import React, { useEffect, useState } from "react";
import { backupDeviceConfig, fetchDeviceHistory, getDevice } from "../services/deviceService";

function DeviceDetails({ deviceId, device: selectedDevice, onBack }) {
  const [liveDevice, setLiveDevice] = useState(null);
  const [history, setHistory] = useState([]);
  const [loadError, setLoadError] = useState("");
  const [backup, setBackup] = useState(null);
  const [backupError, setBackupError] = useState("");
  const [isBackingUp, setIsBackingUp] = useState(false);

  useEffect(() => {
    let isMounted = true;
    const refreshDevice = async () => {
      try {
        const [current, rows] = await Promise.all([getDevice(deviceId), fetchDeviceHistory(deviceId, { limit: 20 })]);
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
  const canBackup = device?.sshEnabled;

  const handleBackup = async () => {
    setIsBackingUp(true);
    setBackupError("");
    try {
      const result = await backupDeviceConfig(device.id);
      setBackup(result);
    } catch (error) {
      setBackupError(error.message);
    } finally {
      setIsBackingUp(false);
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
            <div><label>Monitoring</label><strong>{device.monitoringEnabled ? `${device.monitoringMethod} every ${device.monitorIntervalSeconds}s` : "Paused"}</strong></div>
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
            <span>{backup ? `Retrieved ${new Date(backup.backup?.created_at || Date.now()).toLocaleString()}` : "No backup retrieved"}</span>
          </div>
          {canBackup && (
            <button type="button" className="primary-button" onClick={handleBackup} disabled={isBackingUp}>
              {isBackingUp ? "Retrieving..." : "Pull Live Config Backup (Netmiko)"}
            </button>
          )}
        </div>
        {!canBackup && <p>SSH backup is unavailable because SSH is not enabled for this device.</p>}
        {backupError && <p className="configuration-pending" role="alert">{backupError}</p>}
        {backup && (
          <div className="config-backup-output">
            <h4>VyOS running configuration</h4>
            <pre>{backup.configuration}</pre>
            <h4>Interface status</h4>
            <pre>{backup.interfaces}</pre>
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
