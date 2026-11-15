import React from 'react';
import { useState } from "react";

const workflowSeed = [
  { id: 1, name: "Device Down Alert", trigger: "Webhook: device-down", status: "Healthy" },
  { id: 2, name: "Device Recovery", trigger: "Webhook: device-up", status: "Healthy" },
  { id: 3, name: "Latency Escalation", trigger: "Webhook: latency-threshold", status: "Paused" },
];

const activitySeed = [
  { time: "07:42 UTC", workflow: "Device Down Alert", result: "Triggered successfully" },
  { time: "08:10 UTC", workflow: "Device Recovery", result: "Recovered node and cleared incident" },
  { time: "09:03 UTC", workflow: "Latency Escalation", result: "Escalated to NOC queue" },
];

function AutomationManagement() {
  const [workflows, setWorkflows] = useState(workflowSeed);

  const triggerWorkflow = (id) => {
    setWorkflows((current) => current.map((workflow) => (
      workflow.id === id ? { ...workflow, status: "Executed" } : workflow
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
              <th>Result</th>
            </tr>
          </thead>
          <tbody>
            {activitySeed.map((item, index) => (
              <tr key={`${item.workflow}-${index}`}>
                <td>{item.time}</td>
                <td>{item.workflow}</td>
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
