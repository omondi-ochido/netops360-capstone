import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { assignUserRole, fetchCompanyAudit, fetchRoles, fetchUserAudit, fetchUsers, inviteUser, removeUserRole, setUserStatus, updateUser } from "../services/operationsService.js";
import { useAuth } from "../context/AuthContext";

export default function UserManagement() {
  const { hasPermission, roles: currentRoles } = useAuth();
  const [users, setUsers] = useState([]);
  const [roles, setRoles] = useState([]);
  const [selected, setSelected] = useState(null);
  const [auditRows, setAuditRows] = useState(null);
  const [companyAuditRows, setCompanyAuditRows] = useState(null);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  const [stepUpRequired, setStepUpRequired] = useState(false);
  const [search, setSearch] = useState("");
  const canInvite = hasPermission("users.create");
  const canUpdate = hasPermission("users.update");
  const canAssign = hasPermission("roles.assign");
  const canSuspend = hasPermission("users.suspend");
  const isCompanyAdmin = currentRoles.includes("company_admin");
  const refresh = useCallback(async () => {
    try {
      const [people, roleRows] = await Promise.all([
        fetchUsers({ search: search || undefined, limit: 100 }),
        fetchRoles(),
      ]);
      setUsers(people);
      setRoles(roleRows);
      setSelected((current) => current ? people.find((u) => u.id === current.id) || null : null);
      setError("");
    } catch (e) { setError(e.message); }
  }, [search, isCompanyAdmin]);
  useEffect(() => { void refresh(); }, [refresh]);
  async function run(action, message) { setBusy(true); setError(""); setNotice(""); try { await action(); await refresh(); setNotice(message); setStepUpRequired(false); return true; } catch (e) { setError(e.message); setStepUpRequired(["step_up_required", "mfa_required"].includes(e.code)); return false; } finally { setBusy(false); } }
  async function invite(event) {
    event.preventDefault();
    const formElement = event.currentTarget;
    const form = new FormData(formElement);
    const succeeded = await run(() => inviteUser({
      email: form.get("email"),
      full_name: form.get("full_name"),
      phone_number: form.get("phone_number") || null,
      role_id: form.get("role_id"),
    }), "Invitation sent.");
    if (succeeded) formElement.reset();
  }
  return <div className="page-stack"><section className="page-header-row"><div><h2>User management</h2><p>Invite staff and manage account access.</p></div><div className="page-header-actions"><button className="secondary-button" onClick={() => void refresh()}>Refresh</button>{isCompanyAdmin && hasPermission("audit.read") && <button className="secondary-button" disabled={busy} onClick={async () => { setBusy(true); setError(""); try { setCompanyAuditRows(await fetchCompanyAudit({ limit: 100 })); } catch (e) { setError(e.message); } finally { setBusy(false); } }}>Company activity</button>}</div></section>
    {error && <p role="alert">{error}{stepUpRequired && <> <Link to="/security">Verify your authenticator, then retry this action.</Link></>}</p>}{notice && <p role="status">{notice}</p>}
    {companyAuditRows && <section className="panel-card"><h3>Company activity and audit history</h3><ul>{companyAuditRows.map((row) => <li key={row.id}>{row.occurred_at} — {row.action} {row.resource_type} {row.resource_id || ""}</li>)}{!companyAuditRows.length && <li>No company audit events recorded.</li>}</ul></section>}
    {canInvite && <form className="panel-card login-form" onSubmit={invite}>
      <div className="panel-header-row">
        <h3>Invite a user</h3>
        {isCompanyAdmin && <span className="status-badge neutral">Invitations are limited to members of your company.</span>}
      </div>
      <label><span>Name</span><input name="full_name" required maxLength="120" /></label>
      <label><span>Email</span><input type="email" name="email" required /></label>
      <label><span>Phone (optional)</span><input name="phone_number" maxLength="32" /></label>
      <label><span>Initial role</span><select name="role_id" required>{roles.filter((r) => isCompanyAdmin
        ? ["network_operator", "viewer"].includes(r.name)
        : r.name !== "super_admin" || hasPermission("system.manage")).map((r) => <option key={r.id} value={r.id}>{r.name}</option>)}</select></label>
      <button className="primary-button" disabled={busy}>Send invitation</button>
    </form>}
    <section className="panel-card"><label><span>Search users</span><input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Name or email" /></label><div className="table-scroll"><table><thead><tr><th>User</th><th>Status</th><th>Roles</th><th>Last sign in</th></tr></thead><tbody>{users.map((u) => <tr key={u.id} role="button" aria-pressed={selected?.id === u.id} onClick={() => setSelected(u)} tabIndex="0" onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); setSelected(u); } }}><td>{u.full_name}<br /><small>{u.email}</small></td><td>{u.account_status}</td><td>{(u.roles || []).map((r) => r.name).join(", ") || "—"}</td><td>{u.last_login_at ? new Date(u.last_login_at).toLocaleString() : "Never"}</td></tr>)}{!users.length && <tr><td colSpan="4">No users found.</td></tr>}</tbody></table></div></section>
    {selected && <section className="panel-card"><h3>{selected.full_name}</h3><p>{selected.email} · {selected.account_status}</p>{canUpdate && <form className="login-form" onSubmit={(e) => { e.preventDefault(); const d = new FormData(e.currentTarget); void run(() => updateUser(selected.id, { full_name: d.get("name"), phone_number: d.get("phone") || null }), "User profile updated."); }}><label><span>Name</span><input name="name" defaultValue={selected.full_name} required /></label><label><span>Phone</span><input name="phone" defaultValue={selected.phone_number || ""} /></label><button className="secondary-button" disabled={busy}>Save profile</button></form>}
      {canAssign && <div><h4>Role assignments</h4>{(selected.roles || []).map((r) => <div key={r.id}>{r.name} {(r.name !== "super_admin" || hasPermission("system.manage")) && <button className="secondary-button" disabled={busy} onClick={() => void run(() => removeUserRole(selected.id, r.id), "Role removed.")}>Remove</button>}</div>)}<label><span>Add role</span><select id="assign-role" defaultValue="">{roles.filter((r) => !(selected.roles || []).some((assigned) => assigned.id === r.id) && (r.name !== "super_admin" || hasPermission("system.manage"))).map((r) => <option key={r.id} value={r.id}>{r.name}</option>)}</select></label><button className="secondary-button" disabled={busy} onClick={() => { const roleId = document.getElementById("assign-role")?.value; if (roleId) void run(() => assignUserRole(selected.id, roleId), "Role assigned."); }}>Assign role</button></div>}
      {canSuspend && <button className="secondary-button" disabled={busy} onClick={() => void run(() => setUserStatus(selected.id, selected.account_status === "suspended" ? "active" : "suspended"), "Account status updated.")}>{selected.account_status === "suspended" ? "Reactivate account" : "Suspend account"}</button>}
      {hasPermission("audit.read") && <div><h4>Account audit history</h4><button className="secondary-button" disabled={busy} onClick={async () => { setBusy(true); setError(""); try { setAuditRows(await fetchUserAudit(selected.id)); } catch (e) { setError(e.message); } finally { setBusy(false); } }}>Load audit history</button>{auditRows && <ul>{auditRows.map((row) => <li key={row.id}>{row.occurred_at} — {row.action} {row.resource_type}</li>)}{!auditRows.length && <li>No audit events recorded.</li>}</ul>}</div>}
    </section>}
  </div>;
}
