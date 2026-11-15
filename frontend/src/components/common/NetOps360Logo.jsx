import React from 'react';

export default function NetOps360Logo({ size = 44, variant = 'sidebar' }) {
  const isStacked = variant === 'banner';

  return (
    <div
      style={{
        display: 'inline-flex',
        flexDirection: isStacked ? 'column' : 'row',
        alignItems: 'center',
        gap: '12px',
        textAlign: isStacked ? 'center' : 'left',
      }}
    >
      <svg
        width={size}
        height={size}
        viewBox="0 0 120 120"
        fill="none"
        xmlns="http://www.w3.org/2000/svg"
      >
        <defs>
          <linearGradient id="netops360Grad" x1="15" y1="15" x2="105" y2="105" gradientUnits="userSpaceOnUse">
            <stop offset="0%" stopColor="#22D3EE" />
            <stop offset="55%" stopColor="#06B6D4" />
            <stop offset="100%" stopColor="#2563EB" />
          </linearGradient>
        </defs>

        {/* Outer Thin Orbit Ring */}
        <circle
          cx="60"
          cy="60"
          r="50"
          stroke="url(#netops360Grad)"
          strokeWidth="3"
        />

        {/* Segmented Left-Bottom Gauge Arc */}
        <path
          d="M 33 18 A 50 50 0 0 0 85 103 L 78 90 A 35 35 0 0 1 41 30 Z"
          fill="url(#netops360Grad)"
        />

        {/* Dark Segment Cutouts */}
        <line x1="25" y1="32" x2="38" y2="40" stroke="#0B1120" strokeWidth="3" />
        <line x1="15" y1="48" x2="31" y2="52" stroke="#0B1120" strokeWidth="3" />
        <line x1="12" y1="66" x2="29" y2="65" stroke="#0B1120" strokeWidth="3" />
        <line x1="18" y1="84" x2="34" y2="78" stroke="#0B1120" strokeWidth="3" />
        <line x1="31" y1="99" x2="44" y2="88" stroke="#0B1120" strokeWidth="3" />
        <line x1="49" y1="108" x2="56" y2="93" stroke="#0B1120" strokeWidth="3" />
        <line x1="68" y1="109" x2="69" y2="93" stroke="#0B1120" strokeWidth="3" />

        {/* Three Connected Nodes on the Orbit */}
        <circle cx="36" cy="17" r="4.5" fill="#0B1120" stroke="#22D3EE" strokeWidth="3" />
        <circle cx="96" cy="26" r="6" fill="#0B1120" stroke="#06B6D4" strokeWidth="3" />
        <circle cx="101" cy="88" r="8" fill="#0B1120" stroke="#2563EB" strokeWidth="3" />

        {/* Center 360° Text */}
        <text
          x="62"
          y="68"
          textAnchor="middle"
          fill="url(#netops360Grad)"
          fontFamily="Inter, system-ui, sans-serif"
          fontWeight="800"
          fontSize="27"
          letterSpacing="-1"
        >
          360°
        </text>
      </svg>

      <div>
        <div
          style={{
            fontWeight: 800,
            fontSize: isStacked ? '1.6rem' : '1.15rem',
            letterSpacing: '0.04em',
            color: '#F8FAFC',
            lineHeight: 1.1,
          }}
        >
          NETOPS<span style={{ color: '#22D3EE' }}>360</span>
        </div>
        {isStacked && (
          <div
            style={{
              fontSize: '0.8rem',
              fontStyle: 'italic',
              color: '#94A3B8',
              marginTop: '4px',
              letterSpacing: '0.03em',
            }}
          >
            Rule-Based Network Monitoring &amp; Automation
          </div>
        )}
      </div>
    </div>
  );
}
