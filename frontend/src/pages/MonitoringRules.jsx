import React from 'react';
import { useState } from "react";
import { discoveredDevices } from "../data/discoveredDevices";

const ruleSeed = [
  { id: 1, name: "Router Reachability", deviceId: "main-rtr", condition: "Device reachable by ICMP", threshold: "3 checks", status: "Enabled" },
  { id: 2, name: "Branch Router Latency", deviceId: "branch-rtr", condition: "Latency above threshold", threshold: "50 ms", status: "Enabled" },
  { id: 3, name: "Switch Packet Loss", deviceId: "SW1", condition: "Packet loss above threshold", threshold: "5%", status: "Disabled" },
  { id: 4, name: "Server Health", deviceId: "MAIN-SERVER", condition: "Server health check", threshold: "2 checks", status: "Enabled" },
];

function MonitoringRules() {
  const [rules, setRules] = useState(ruleSeed);
  const [form, setForm] = useState({ name: "", deviceId: "main-rtr", condition: "", threshold: "", checks: "" });

  const toggleRule = (id) => {
    setRules((current) => current.map((rule) => (
      rule.id === id
        ? { ...rule, status: rule.status === "Enabled" ? "Disabled" : "Enabled" }
        : rule
    )));
  };

  const handleSubmit = (event) => {
    event.preventDefault();
    if (!form.name || !form.condition || !form.threshold) {
      return;
    }

    setRules((current) => [
      ...current,
      {
        id: Date.now(),
        name: form.name,
        deviceId: form.deviceId,
        condition: `${form.condition} ${form.checks ? `for ${form.checks} consecutive checks` : ""}`,
        threshold: form.threshold,
        status: "Enabled",
      },
    ]);

    setForm({ name: "", deviceId: "main-rtr", condition: "", threshold: "", checks: "" });
  };

  return (
    <div className="page-stack">
      <section className="page-header-row">
        <div>
          <h2>Monitoring Rules</h2>
          <p>Define alert triggers and automate detection policies for the fleet.</p>
        </div>
      </section>

      <section className="panel-card compact-panel">
        <h3>Create rule</h3>
        <form className="inline-form" onSubmit={handleSubmit}>
          <label>
            <span>Rule name</span>
            <input
              type="text"
              value={form.name}
              onChange={(event) => setForm((current) => ({ ...current, name: event.target.value }))}
            />
          </label>
          <label>
            <span>Condition type</span>
            <select
              value={form.condition}
              onChange={(event) => setForm((current) => ({ ...current, condition: event.target.value }))}
            >
              <option value="">Select condition</option>
              <option value="CPU usage {'>'} 85%">CPU usage {'>'} 85%</option>
              <option value="Packet loss {'>'} 12%">Packet loss {'>'} 12%</option>
              <option value="Device unreachable">Device unreachable</option>
              <option value="Temperature {'>'} 44°C">Temperature {'>'} 44°C</option>
            </select>
          </label>
          <label>
            <span>Device</span>
            <select
              value={form.deviceId}
              onChange={(event) => setForm((current) => ({ ...current, deviceId: event.target.value }))}
            >
              {discoveredDevices.map((device) => (
                <option key={device.id} value={device.id}>{device.hostname}</option>
              ))}
            </select>
          </label>
          <label>
            <span>Threshold</span>
            <input
              type="text"
              value={form.threshold}
              placeholder="85%, 44°C, etc."
              onChange={(event) => setForm((current) => ({ ...current, threshold: event.target.value }))}
            />
          </label>
          <label>
            <span>Checks</span>
            <input
              type="text"
              value={form.checks}
              placeholder="3"
              onChange={(event) => setForm((current) => ({ ...current, checks: event.target.value }))}
            />
          </label>
          <button type="submit" className="primary-button">Add rule</button>
        </form>
      </section>

      <section className="panel-card">
        <table className="data-table rule-table">
          <thead>
            <tr>
              <th>Rule Name</th>
              <th>Device</th>
              <th>Condition</th>
              <th>Threshold</th>
              <th>Status</th>
              <th>Toggle</th>
            </tr>
          </thead>
          <tbody>
            {rules.map((rule) => (
              <tr key={rule.id}>
                <td>{rule.name}</td>
                <td>{discoveredDevices.find((device) => device.id === rule.deviceId)?.hostname || rule.deviceId}</td>
                <td>{rule.condition}</td>
                <td>{rule.threshold}</td>
                <td>{rule.status}</td>
                <td>
                  <button
                    type="button"
                    className={`toggle-button ${rule.status === "Enabled" ? "on" : "off"}`}
                    onClick={() => toggleRule(rule.id)}
                  >
                    {rule.status === "Enabled" ? "Enabled" : "Disabled"}
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
    </div>
  );
}

export default MonitoringRules;
