import { apiRequest, listData, resourceData, queryString } from "./api.js";

export async function fetchRules(params) {
  return listData(await apiRequest(`/api/rules${queryString(params)}`));
}
export async function createRule(body) {
  return resourceData(await apiRequest("/api/rules", { method: "POST", body: JSON.stringify(body) }));
}
export async function updateRule(id, body) {
  return resourceData(await apiRequest(`/api/rules/${encodeURIComponent(id)}`, { method: "PATCH", body: JSON.stringify(body) }));
}
export async function deleteRule(id) {
  return apiRequest(`/api/rules/${encodeURIComponent(id)}`, { method: "DELETE" });
}
export async function fetchIncidents(params) {
  return listData(await apiRequest(`/api/incidents${queryString(params)}`));
}
export async function acknowledgeIncident(id) {
  return resourceData(await apiRequest(`/api/incidents/${encodeURIComponent(id)}/acknowledge`, { method: "POST" }));
}
export async function resolveIncident(id) {
  return resourceData(await apiRequest(`/api/incidents/${encodeURIComponent(id)}/resolve`, { method: "POST" }));
}
export async function fetchAutomationLogs(params) {
  return listData(await apiRequest(`/api/automation/logs${queryString(params)}`));
}
export async function retryAutomation(id) {
  return resourceData(await apiRequest(`/api/automation/retry/${encodeURIComponent(id)}`, { method: "POST" }));
}
export async function fetchMonitoringHistory(params) {
  return listData(await apiRequest(`/api/monitoring/history${queryString(params)}`));
}

export async function fetchUsers(params) { return listData(await apiRequest(`/api/users${queryString(params)}`)); }
export async function inviteUser(body) { return resourceData(await apiRequest("/api/users", { method: "POST", body: JSON.stringify(body) })); }
export async function updateUser(id, body) { return resourceData(await apiRequest(`/api/users/${encodeURIComponent(id)}`, { method: "PATCH", body: JSON.stringify(body) })); }
export async function setUserStatus(id, status) { return resourceData(await apiRequest(`/api/users/${encodeURIComponent(id)}/status`, { method: "PATCH", body: JSON.stringify({ status }) })); }
export async function fetchRoles() { return resourceData(await apiRequest("/api/roles")); }
export async function assignUserRole(id, role_id) { return resourceData(await apiRequest(`/api/users/${encodeURIComponent(id)}/roles`, { method: "POST", body: JSON.stringify({ role_id }) })); }
export async function removeUserRole(id, roleId) { return apiRequest(`/api/users/${encodeURIComponent(id)}/roles/${encodeURIComponent(roleId)}`, { method: "DELETE" }); }
export async function fetchUserAudit(id) { return listData(await apiRequest(`/api/users/${encodeURIComponent(id)}/audit-logs`)); }
