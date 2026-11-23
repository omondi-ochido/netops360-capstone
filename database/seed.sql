-- =====================================================================
-- NetOps360 seed data. Idempotent: re-running never duplicates rows and
-- never overwrites changes made after the first seed (ON CONFLICT DO NOTHING).
-- Run AFTER schema.sql.
-- =====================================================================

-- Main Site devices (9)
-- The three GNS3 Ethernet Switches are Layer 2 devices with no IP stack, so
-- they cannot answer ICMP. They are seeded as 'Unmonitored' (monitoring off,
-- method 'none') instead of being falsely reported Online.
INSERT INTO devices
    (hostname, ip_address, device_type, operating_system, site, description,
     ssh_enabled, monitoring_enabled, monitoring_method, monitor_interval_seconds, current_status)
VALUES
    ('main-rtr',      '192.168.100.10', 'router', 'VyOS 1.5',              'main-site', 'Main Site VyOS router',               true,  true,  'icmp', 30, 'Unknown'),
    ('MAIN-SERVER',   '192.168.10.100', 'server', 'Linux',                 'main-site', 'Main Site Linux server',              false, true,  'icmp', 30, 'Unknown'),
    ('PC1',           '192.168.10.11',  'host',   'VPCS',                  'main-site', 'Main Site VPCS host 1',               false, true,  'icmp', 30, 'Unknown'),
    ('PC2',           '192.168.10.12',  'host',   'VPCS',                  'main-site', 'Main Site VPCS host 2',               false, true,  'icmp', 30, 'Unknown'),
    ('PC3',           '192.168.10.13',  'host',   'VPCS',                  'main-site', 'Main Site VPCS host 3',               false, true,  'icmp', 30, 'Unknown'),
    ('PC4',           '192.168.10.14',  'host',   'VPCS',                  'main-site', 'Main Site VPCS host 4',               false, true,  'icmp', 30, 'Unknown'),
    ('MANAGEMENT-SW', '192.168.100.2',  'switch', 'GNS3 Ethernet Switch',  'main-site', 'Management switch (Layer 2, no ICMP)', false, false, 'none', 30, 'Unmonitored'),
    ('SW1',           '192.168.10.2',   'switch', 'GNS3 Ethernet Switch',  'main-site', 'Access switch 1 (Layer 2, no ICMP)',   false, false, 'none', 30, 'Unmonitored'),
    ('SW2',           '192.168.10.3',   'switch', 'GNS3 Ethernet Switch',  'main-site', 'Access switch 2 (Layer 2, no ICMP)',   false, false, 'none', 30, 'Unmonitored')
ON CONFLICT (hostname) DO NOTHING;

-- Default global rules (3)
INSERT INTO rules (name, description, metric, operator, threshold, severity, enabled, scope)
VALUES
    ('Device Offline',   'Raised when a monitored device stops responding to ICMP.',
        'device_status', 'eq',  '"Offline"'::jsonb, 'critical', true, 'global'),
    ('High Latency',     'Raised when average round-trip latency exceeds 100 ms.',
        'latency_ms',    'gt',  '100'::jsonb,       'warning',  true, 'global'),
    ('High Packet Loss', 'Raised when packet loss is 50% or more.',
        'packet_loss',   'gte', '50'::jsonb,        'warning',  true, 'global')
ON CONFLICT (name) DO NOTHING;
