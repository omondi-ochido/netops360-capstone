import { apiRequest, listData, resourceData, queryString } from "./api.js";

export function mapDevice(row) {
  const type = row.device_type || row.type || row.deviceType || "other";
  return {
    ...row,
    id: row.id,
    hostname: row.hostname || row.name,
    ipAddress: row.ip_address || row.ipAddress || row.ip,
    deviceType: type.replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase()),
    os: row.operating_system || row.os || "",
    site: row.site || "",
    status: row.current_status || row.status || "Unknown",
    latencyMs: row.last_latency_ms == null ? null : Number(row.last_latency_ms),
    packetLoss: row.last_packet_loss == null ? null : Number(row.last_packet_loss),
    lastChecked: row.last_checked_at || row.last_checked || "Never",
    sshEnabled: Boolean(row.ssh_enabled ?? row.sshEnabled),
    monitoringEnabled: Boolean(row.monitoring_enabled ?? row.monitoringEnabled),
    monitoringMethod: row.monitoring_method || row.monitoringMethod,
    monitorIntervalSeconds: row.monitor_interval_seconds || row.monitorIntervalSeconds,
  };
}

export async function fetchDevices({ limit = 200, offset = 0 } = {}) {
  const payload = await apiRequest(`/api/devices${queryString({ limit, offset, refresh: true })}`);
  return { devices: listData(payload).map(mapDevice), pagination: payload.pagination, isLive: true };
}

export async function getDevice(deviceId) {
  const payload = await apiRequest(`/api/devices/${encodeURIComponent(deviceId)}`);
  return mapDevice(resourceData(payload));
}

export async function createDevice(device) {
  const payload = await apiRequest("/api/devices", { method: "POST", body: JSON.stringify(device) });
  return mapDevice(resourceData(payload));
}

export async function updateDevice(deviceId, changes) {
  const payload = await apiRequest(`/api/devices/${encodeURIComponent(deviceId)}`, {
    method: "PATCH", body: JSON.stringify(changes),
  });
  return mapDevice(resourceData(payload));
}

export async function deactivateDevice(deviceId) {
  return apiRequest(`/api/devices/${encodeURIComponent(deviceId)}`, { method: "DELETE" });
}

export async function fetchDeviceHistory(deviceId, params = {}) {
  const payload = await apiRequest(`/api/monitoring/history${queryString({ ...params, device_id: deviceId })}`);
  return listData(payload);
}

export async function backupDeviceConfig(deviceId) {
  const payload = await apiRequest(`/api/devices/${encodeURIComponent(deviceId)}/backup`, { method: "POST" });
  return resourceData(payload);
}
