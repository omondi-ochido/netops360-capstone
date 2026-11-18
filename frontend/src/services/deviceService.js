import { discoveredDevices } from "../data/discoveredDevices";

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:5050").replace(/\/+$/, "");

export async function fetchDevices() {
  try {
    const response = await fetch(`${API_BASE_URL}/api/devices`);
    if (!response.ok) {
      throw new Error(`Device request failed (${response.status})`);
    }

    const payload = await response.json();
    if (!Array.isArray(payload.devices)) {
      throw new Error("Device response did not contain a device list");
    }

    return {
      devices: payload.devices.map((device) => ({
        ...device,
        discoveredMethod: device.discoveredMethod || "GNS3 Live API",
        lastChecked: device.lastChecked || payload.timestamp || "Just now",
      })),
      isLive: true,
    };
  } catch {
    return { devices: discoveredDevices, isLive: false };
  }
}

export async function backupDeviceConfig(deviceId) {
  const response = await fetch(`${API_BASE_URL}/api/devices/${encodeURIComponent(deviceId)}/backup`, {
    method: "POST",
  });
  const payload = await response.json();

  if (!response.ok) {
    throw new Error(payload.error || `Configuration backup failed (${response.status})`);
  }

  return payload;
}
