import React, { useState } from 'react';

export default function RulesBook() {
  const [openSection, setOpenSection] = useState(0);

  const toggleSection = (index) => {
    setOpenSection(openSection === index ? null : index);
  };

  const sections = [
    {
      title: "1. THE COMBAT DIVISIONS (PIECES)",
      content: (
        <div>
          <p style={{ margin: '0 0 10px 0' }}>
            The game is fought with two armies (North and South), composed of 4 division types. Relays [R] are non-combat units crucial for extending communication lines.
          </p>
          <table style={{ width: '100%', borderCollapse: 'collapse', border: '1px solid #002fa7', fontSize: '10.5px', marginTop: '8px', fontFamily: 'monospace' }}>
            <thead>
              <tr style={{ backgroundColor: '#002fa7', color: '#ffffff' }}>
                <th style={{ padding: '6px', border: '1px solid #002fa7', textAlign: 'left' }}>UNIT TYPE</th>
                <th style={{ padding: '6px', border: '1px solid #002fa7', textAlign: 'center' }}>OFFENSE</th>
                <th style={{ padding: '6px', border: '1px solid #002fa7', textAlign: 'center' }}>DEFENSE</th>
                <th style={{ padding: '6px', border: '1px solid #002fa7', textAlign: 'center' }}>RANGE</th>
                <th style={{ padding: '6px', border: '1px solid #002fa7', textAlign: 'center' }}>MOBILITY</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td style={{ padding: '6px', border: '1px solid #002fa7', fontWeight: 'bold', color: '#002fa7' }}>Infantry [I]</td>
                <td style={{ padding: '6px', border: '1px solid #002fa7', textAlign: 'center' }}>4</td>
                <td style={{ padding: '6px', border: '1px solid #002fa7', textAlign: 'center' }}>6</td>
                <td style={{ padding: '6px', border: '1px solid #002fa7', textAlign: 'center' }}>2 sq</td>
                <td style={{ padding: '6px', border: '1px solid #002fa7', textAlign: 'center' }}>1 sq</td>
              </tr>
              <tr style={{ backgroundColor: '#fcfbf0' }}>
                <td style={{ padding: '6px', border: '1px solid #002fa7', fontWeight: 'bold', color: '#002fa7' }}>Cavalry [C]</td>
                <td style={{ padding: '6px', border: '1px solid #002fa7', textAlign: 'center' }}>5</td>
                <td style={{ padding: '6px', border: '1px solid #002fa7', textAlign: 'center' }}>5</td>
                <td style={{ padding: '6px', border: '1px solid #002fa7', textAlign: 'center' }}>2 sq</td>
                <td style={{ padding: '6px', border: '1px solid #002fa7', textAlign: 'center' }}>2 sq</td>
              </tr>
              <tr>
                <td style={{ padding: '6px', border: '1px solid #002fa7', fontWeight: 'bold', color: '#002fa7' }}>Artillery [A]</td>
                <td style={{ padding: '6px', border: '1px solid #002fa7', textAlign: 'center' }}>5</td>
                <td style={{ padding: '6px', border: '1px solid #002fa7', textAlign: 'center' }}>8</td>
                <td style={{ padding: '6px', border: '1px solid #002fa7', textAlign: 'center' }}>3 sq</td>
                <td style={{ padding: '6px', border: '1px solid #002fa7', textAlign: 'center' }}>1 sq</td>
              </tr>
              <tr style={{ backgroundColor: '#fcfbf0' }}>
                <td style={{ padding: '6px', border: '1px solid #002fa7', fontWeight: 'bold', color: '#002fa7' }}>Relay [R]</td>
                <td style={{ padding: '6px', border: '1px solid #002fa7', textAlign: 'center' }}>-</td>
                <td style={{ padding: '6px', border: '1px solid #002fa7', textAlign: 'center' }}>1</td>
                <td style={{ padding: '6px', border: '1px solid #002fa7', textAlign: 'center' }}>-</td>
                <td style={{ padding: '6px', border: '1px solid #002fa7', textAlign: 'center' }}>1 sq</td>
              </tr>
            </tbody>
          </table>

          <div style={{ marginTop: '10px', fontSize: '10px', color: '#475569' }}>
            <strong style={{ color: '#002fa7' }}>Conditional Stat Adjustments:</strong>
            <ul style={{ margin: '4px 0 0 12px', padding: 0, listStyleType: 'disc' }}>
              <li style={{ marginBottom: '2px' }}>
                <strong>Cavalry Charge:</strong> Cavalry offense increases from 5 to <strong>7</strong> when attacking an adjacent enemy that is not on a mountain pass or fortress.
              </li>
              <li style={{ marginBottom: '2px' }}>
                <strong>Mountain Pass Defenses:</strong> Units on mountain passes gain a <strong>+2</strong> base defense rating (Infantry becomes 8, Artillery becomes 10).
              </li>
              <li>
                <strong>Fortress Defenses:</strong> Units on fortresses or arsenals gain a <strong>+4</strong> base defense rating (Infantry becomes 10, Artillery becomes 12).
              </li>
            </ul>
          </div>
        </div>
      )
    },
    {
      title: "2. LINES OF COMMUNICATION (LoC)",
      content: (
        <div>
          <p style={{ margin: '0 0 8px 0' }}>
            All combat divisions must maintain a connection back to one of their home arsenals, either directly or through a contiguous chain of Relays [R]. Relays project straight grid lines of connection.
          </p>
          <strong style={{ color: '#002fa7' }}>Isolation (Disconnected) Penalties:</strong>
          <ul style={{ margin: '6px 0 0 16px', padding: 0, listStyleType: 'disc' }}>
            <li style={{ marginBottom: '4px' }}><strong>Operational Paralysis:</strong> Disconnected units are completely disabled and cannot move, attack, or be selected.</li>
            <li><strong>Zero Combat Rating:</strong> Disconnected units have both their Offense and Defense reduced to <strong>0</strong>, leaving them extremely vulnerable to destruction.</li>
          </ul>
        </div>
      )
    },
    {
      title: "3. COMBAT RESOLUTION & STACKING",
      content: (
        <div>
          <p style={{ margin: '0 0 8px 0' }}>
            <strong>Aligned Stacking (Combined Fire):</strong> Lining up 2 or more friendly units along a straight line (horizontal, vertical, or diagonal) forms an offensive stack. The attack's range is limited solely by the unit closest to the enemy (the attacker head). All units contiguously aligned directly behind it add their combat power to the attack, preventing long-range sniping while rewarding coordination.
          </p>
          <p style={{ margin: '0 0 10px 0' }}>
            <strong>Defensive Stacking:</strong> Friendly units can also stack defensively. If a unit is attacked, any friendly units aligned in a contiguous stack directly behind it (along the axis of attack) add their defense ratings to support and protect the defender.
          </p>
          <strong style={{ color: '#002fa7' }}>Combat Outcomes (Net Force = Total Offense - Total Defense):</strong>
          <ul style={{ margin: '6px 0 0 16px', padding: 0, listStyleType: 'disc' }}>
            <li style={{ marginBottom: '4px' }}><strong>DESTROY (Net Force &ge; 2):</strong> The enemy unit is permanently eliminated from the board.</li>
            <li style={{ marginBottom: '4px' }}><strong>RETREAT (Net Force == 1):</strong> The enemy unit is pushed back to an adjacent empty square.</li>
            <li><strong>REPELLED (Net Force &le; 0):</strong> The attack fails and the defender stands firm.</li>
          </ul>
        </div>
      )
    },
    {
      title: "4. DEFENSIVE TERRAINS",
      content: "Occupying strategic positions grants massive bonuses. Units on Fortresses (+4 defense base) or Mountain Passes (+2 defense base) have their entire total defense rating doubled, turning these sectors into highly formidable strongholds."
    },
    {
      title: "5. VICTORY CONDITIONS",
      content: (
        <div>
          <p style={{ margin: '0 0 8px 0' }}>
            A campaign is won by achieving <strong>any of the following conditions</strong>:
          </p>
          <ul style={{ margin: '6px 0 0 16px', padding: 0, listStyleType: 'disc' }}>
            <li style={{ marginBottom: '4px' }}>Annihilate all enemy forces.</li>
            <li style={{ marginBottom: '4px' }}>Occupy both enemy arsenals simultaneously.</li>
            <li>Isolate all remaining enemy units from their LoC network.</li>
          </ul>
        </div>
      )
    }
  ];

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
      {sections.map((sec, idx) => {
        const isOpen = openSection === idx;
        return (
          <div key={idx} style={{ borderBottom: '1px solid #cbd5e1', paddingBottom: '6px', marginBottom: '4px' }}>
            <div
              onClick={() => toggleSection(idx)}
              style={{
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                cursor: 'pointer',
                fontSize: '11px',
                fontWeight: 'bold',
                color: '#002fa7',
                padding: '6px 0',
                userSelect: 'none'
              }}
            >
              <span>{sec.title}</span>
              <span style={{ fontSize: '9px', color: '#475569' }}>{isOpen ? '▼' : '▶'}</span>
            </div>
            {isOpen && (
              <div style={{
                padding: '8px 4px 10px 4px',
                fontSize: '10.5px',
                color: '#475569',
                lineHeight: '1.5'
              }}>
                {sec.content}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
