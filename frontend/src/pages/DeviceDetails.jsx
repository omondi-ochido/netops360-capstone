import React from 'react';
function DeviceDetails({ device, onBack }) {
  const safeDevice = device || {
    hostname: "edge-rt-01",
    ip: "192.168.1.10",
    type: "Router",
    status: "Warning",
    location: "Rack A1",
    model: "ISR 4351",
  };

  return (
    <div className="page-stack">
      <section className="page-header-row">
        <div>
          <h2>{safeDevice.hostname}</h2>
          <p>{safeDevice.type} • {safeDevice.ip}</p>
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
            <span className={`status-tag ${safeDevice.status.toLowerCase()}`}>{safeDevice.status}</span>
          </div>

          <div className="info-grid">
            <div><label>Hostname</label><strong>{safeDevice.hostname}</strong></div>
            <div><label>IP Address</label><strong>{safeDevice.ip}</strong></div>
            <div><label>Device Type</label><strong>{safeDevice.type}</strong></div>
            <div><label>Location</label><strong>{safeDevice.location || "Rack A1"}</strong></div>
            <div><label>Model</label><strong>{safeDevice.model || "ISR 4351"}</strong></div>
            <div><label>Last Sync</label><strong>2m ago</strong></div>
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
              <strong>18.4 ms</strong>
            </div>
            <div>
              <span>Packet loss</span>
              <strong>0.82%</strong>
            </div>
            <div>
              <span>Throughput</span>
              <strong>2.4 Gbps</strong>
            </div>
            <div>
              <span>Uplink</span>
              <strong>Healthy</strong>
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
            <strong>Last backup</strong>
            <span>Today at 09:42 UTC</span>
          </div>
          <div className="header-button-group">
            <button type="button" className="secondary-button">Retrieve Config</button>
            <button type="button" className="primary-button">Download Backup</button>
          </div>
        </div>
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
