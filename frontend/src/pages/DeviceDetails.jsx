import React, { useEffect, useState } from "react";
import { discoveredDevices } from "../data/discoveredDevices";
import { backupDeviceConfig, fetchDevices } from "../services/deviceService";

function DeviceDetails({ deviceId, device: selectedDevice, onBack }) {
  const [liveDevice, setLiveDevice] = useState(null);
  const [isLive, setIsLive] = useState(false);
  const [backup, setBackup] = useState(null);
  const [backupError, setBackupError] = useState("");
  const [isBackingUp, setIsBackingUp] = useState(false);

  useEffect(() => {
    let isMounted = true;
    const refreshDevice = async () => {
      const result = await fetchDevices();
      if (!isMounted) return;
      const matchingDevice = result.devices.find((item) => item.id === deviceId)
        || result.devices.find((item) => item.hostname === selectedDevice?.hostname);
      if (matchingDevice) setLiveDevice(matchingDevice);
      setIsLive(result.isLive);
    };

    void refreshDevice();
    const intervalId = window.setInterval(refreshDevice, 15000);
    return () => {
      isMounted = false;
      window.clearInterval(intervalId);
    };
  }, [deviceId, selectedDevice?.hostname]);

  const device = liveDevice || selectedDevice || discoveredDevices.find((item) => item.id === deviceId);
  const canBackup = device?.sshEnabled || device?.hostname === "main-rtr";

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
          <h2>Device not found</h2>
          <p>The selected device is not in the discovered topology inventory.</p>
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
          <p>{device.deviceType} • {device.ipAddress} • {device.site} • {isLive ? "Live GNS3 telemetry" : "Fallback inventory"}</p>
        </div>
        <div className="header-button-group">
          <button type="button" className="secondary-button" onClick={onBack}>Back to inventory</button>
          <button type="button" className="primary-button">Restart Device</button>
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
            <div><label>Discovery Method</label><strong>{device.discoveredMethod || "GNS3 inventory"}</strong></div>
            <div><label>Last Checked</label><strong>{device.lastChecked}</strong></div>
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
            <span>{backup ? `Retrieved ${new Date(backup.backedUpAt).toLocaleString()}` : "No backup retrieved"}</span>
          </div>
          {canBackup && (
            <button type="button" className="primary-button" onClick={handleBackup} disabled={isBackingUp}>
              {isBackingUp ? "Retrieving..." : "Pull Live Config Backup (Netmiko)"}
            </button>
          )}
        </div>
        {device.configurationPending && !canBackup && (
          <p className="configuration-pending">Configuration pending console boot</p>
        )}
        {backupError && <p className="configuration-pending" role="alert">{backupError}</p>}
        {backup && (
          <div className="config-backup-output">
            <h4>VyOS running configuration</h4>
            <pre>{backup.config}</pre>
            <h4>Interface status</h4>
            <pre>{backup.interfaces}</pre>
          </div>
        )}
      </section>

      <section className="action-grid">
        <button type="button" className="secondary-button">Reboot</button>
        <button type="button" className="secondary-button">Run Diagnostics</button>
        <button type="button" className="secondary-button">Push Policy</button>
        <button type="button" className="secondary-button">Assign Tier</button>
      </section>
    </div>
  );
}

export default DeviceDetails;
