import React from 'react';
import { useState } from "react";
import { discoveredDevices } from "../data/discoveredDevices";

const workflowSeed = [
  { id: 1, name: "Device Down Alert", trigger: "Webhook: device-down", deviceId: "branch-rtr", status: "Healthy" },
  { id: 2, name: "Device Recovery", trigger: "Webhook: device-up", deviceId: "SW1", status: "Healthy" },
  { id: 3, name: "Latency Escalation", trigger: "Webhook: latency-threshold", deviceId: "main-rtr", status: "Paused" },
];

const activitySeed = [
  { time: "07:42 UTC", workflow: "Device Down Alert", deviceId: "branch-rtr", result: "Triggered successfully" },
  { time: "08:10 UTC", workflow: "Device Recovery", deviceId: "SW1", result: "Recovery check completed" },
  { time: "09:03 UTC", workflow: "Latency Escalation", deviceId: "main-rtr", result: "Escalated to NOC queue" },
];

function AutomationManagement() {
  const [workflows, setWorkflows] = useState(workflowSeed);

  const triggerWorkflow = (id) => {
    setWorkflows((current) => current.map((workflow) => (
      workflow.id === id ? { ...workflow, status: "Executed" } : workflow
    )));
  };

  const updateWorkflowDevice = (id, deviceId) => {
    setWorkflows((current) => current.map((workflow) => (
      workflow.id === id ? { ...workflow, deviceId } : workflow
    )));
  };

  return (
    <div className="page-stack">
      <section className="page-header-row">
        <div>
          <h2>Automation Management</h2>
          <p>Review workflow health and trigger operational automations on demand.</p>
        </div>
      </section>

      <section className="panel-card">
        <div className="automation-list">
          {workflows.map((workflow) => (
            <div key={workflow.id} className="automation-row">
              <div>
                <strong>{workflow.name}</strong>
                <small>{workflow.trigger}</small>
              </div>
              <div className="automation-actions">
                <select
                  className="automation-device-select"
                  value={workflow.deviceId}
                  onChange={(event) => updateWorkflowDevice(workflow.id, event.target.value)}
                  aria-label={`Device for ${workflow.name}`}
                >
                  {discoveredDevices.map((device) => (
                    <option key={device.id} value={device.id}>{device.hostname}</option>
                  ))}
                </select>
                <span className={`status-tag ${workflow.status.toLowerCase()}`}>{workflow.status}</span>
                <button type="button" className="primary-button small-button" onClick={() => triggerWorkflow(workflow.id)}>
                  Test Trigger
                </button>
              </div>
            </div>
          ))}
        </div>
      </section>

      <section className="panel-card">
        <div className="panel-header-row">
          <div>
            <span className="eyebrow-text">Log</span>
            <h3>Automated activity</h3>
          </div>
        </div>

        <table className="data-table log-table">
          <thead>
            <tr>
              <th>Time</th>
              <th>Workflow</th>
              <th>Device</th>
              <th>Result</th>
            </tr>
          </thead>
          <tbody>
            {activitySeed.map((item, index) => (
              <tr key={`${item.workflow}-${index}`}>
                <td>{item.time}</td>
                <td>{item.workflow}</td>
                <td>{discoveredDevices.find((device) => device.id === item.deviceId)?.hostname || item.deviceId}</td>
                <td>{item.result}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
    </div>
  );
}

export default AutomationManagement;
