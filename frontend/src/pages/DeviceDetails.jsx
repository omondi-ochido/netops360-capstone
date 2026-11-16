import React from "react";
import { discoveredDevices } from "../data/discoveredDevices";

function DeviceDetails({ deviceId, device: selectedDevice, onBack }) {
  const device = discoveredDevices.find((item) => item.id === deviceId) || selectedDevice;

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
          <p>{device.deviceType} • {device.ipAddress} • {device.site}</p>
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
            <div><label>Discovery Method</label><strong>{device.discoveredMethod}</strong></div>
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
              <strong>{device.latencyMs} ms</strong>
            </div>
            <div>
              <span>Packet loss</span>
              <strong>{device.packetLoss}%</strong>
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

        {device.configurationPending ? (
          <p className="configuration-pending">Configuration pending console boot</p>
        ) : (
          <div className="backup-row">
            <div className="backup-meta">
              <strong>Last backup</strong>
              <span>Not yet retrieved</span>
            </div>
            <div className="header-button-group">
              <button type="button" className="secondary-button">Retrieve Config</button>
              <button type="button" className="primary-button">Download Backup</button>
            </div>
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
