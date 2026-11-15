import NetOps360Logo from "../common/NetOps360Logo";

const navItems = [
  { id: "dashboard", label: "Dashboard" },
  { id: "devices", label: "Devices" },
  { id: "alerts", label: "Alerts & Incidents" },
  { id: "monitoring", label: "Monitoring Rules" },
  { id: "automation", label: "Automation" },
];

function Layout({ activePage, onNavigate, onLogout, title, children }) {
  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div>
          <div className="brand-block">
            <NetOps360Logo size={38} variant="sidebar" />
          </div>

          <div className="nav-section-label">Network Core</div>

          <nav className="sidebar-nav" aria-label="Sidebar navigation">
            {navItems.map((item) => (
              <button
                key={item.id}
                type="button"
                className={`nav-button ${activePage === item.id ? "active" : ""}`}
                onClick={() => onNavigate(item.id)}
              >
                <span className="nav-swatch" />
                {item.label}
              </button>
            ))}
          </nav>
        </div>

        <div className="sidebar-footer">
          <div className="status-row">
            <span className="status-dot success" />
            <span>Normal</span>
          </div>
          <div className="sidebar-kpis">
            <span>99.4% uptime</span>
            <span>All nodes reporting</span>
          </div>
          <button type="button" className="logout-button" onClick={onLogout}>Log out</button>
        </div>
      </aside>

      <main className="workspace-panel">
        <header className="workspace-header">
          <div className="crumbs-row">
            <span className="crumb-label">NetOps360</span>
            <span className="crumb-separator">›</span>
            <span>{title}</span>
          </div>

          <div className="header-actions-right">
            <div className="header-search">Search IP, hostname, MAC, or alert...</div>
            <div className="header-pill warning">3 Active Incidents</div>
            <div className="header-pill muted">Live Sync: 30s</div>
            <div className="user-pill">
              <span className="user-avatar">M</span>
              <span>
                <strong>Marcus Vance</strong>
                <small>Lead Network Admin</small>
              </span>
            </div>
          </div>
        </header>

        <div className="content-surface">{children}</div>
      </main>
    </div>
  );
}

export default Layout;
