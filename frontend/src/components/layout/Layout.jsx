import NetOps360Logo from "../common/NetOps360Logo";
import { useAuth } from "../../context/AuthContext";

const navItems = [
  { id: "dashboard", label: "Dashboard" }, { id: "devices", label: "Devices", permission: "devices.read" },
  { id: "alerts", label: "Alerts & Incidents", permission: "incidents.read" }, { id: "monitoring", label: "Monitoring Rules", permission: "rules.read" },
  { id: "automation", label: "Automation", permission: "automation.read" }, { id: "users", label: "User management", permission: "users.read" },
];

export default function Layout({ activePage, onNavigate, onLogout, title, children }) {
  const { user, roles, hasPermission } = useAuth();
  return <div className="app-shell"><aside className="sidebar"><div><div className="brand-block"><NetOps360Logo size={38} variant="sidebar" /></div><div className="nav-section-label">Network Core</div><nav className="sidebar-nav" aria-label="Sidebar navigation">{navItems.filter((item) => !item.permission || hasPermission(item.permission)).map((item) => <button key={item.id} type="button" className={`nav-button ${activePage === item.id ? "active" : ""}`} onClick={() => onNavigate(item.id)}><span className="nav-swatch" />{item.label}</button>)}</nav></div>
    <div className="sidebar-footer"><div className="user-pill"><span className="user-avatar">{(user?.full_name || user?.email || "U").slice(0, 1).toUpperCase()}</span><span><strong>{user?.full_name || user?.email}</strong><small>{roles.join(", ") || "NetOps360 user"}</small></span></div><button type="button" className="logout-button" onClick={onLogout}>Log out</button></div></aside>
    <main className="workspace-panel"><header className="workspace-header"><div className="crumbs-row"><span className="crumb-label">NetOps360</span><span className="crumb-separator">›</span><span>{title}</span></div><div className="header-actions-right"><span className="header-pill muted">{user?.email}</span></div></header><div className="content-surface">{children}</div></main></div>;
}
