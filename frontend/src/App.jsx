

// src/App.jsx
import React, { useState, useEffect, useRef } from 'react';
import { COLS, ROWS, TERRAIN_MAP } from './constants';
import { INITIAL_UNITS } from './initialUnits';
import Lobby from './components/Lobby';
import RulesBook from './components/RulesBook';

// Combat Profiles for Tactical Telemetry
const UNIT_PROFILES = {
  artillery: { attack: 5, defense: 8, label: "Artillery", tip: "Range 3 support unit." },
  cavalry: { attack: 5, defense: 5, label: "Cavalry", tip: "Speed 2 unit. Charge rating: 7." },
  infantry: { attack: 4, defense: 6, label: "Infantry", tip: "Robust line unit." },
  relay: { attack: 0, defense: 1, label: "Relay", tip: "Maintains connection lines." },
  arsenal: { attack: 0, defense: 500, label: "Arsenal", tip: "Primary command objective." }
};

export default function App() {
  // Game Mode Configuration State
  const [gameMode, setGameMode] = useState('single');
  const [playerSide, setPlayerSide] = useState('North');
  const [layoutType, setLayoutType] = useState('skirmish_10x10');
  const [activeArsenals, setActiveArsenals] = useState(['4,0', '5,9']);
  const [activeForts, setActiveForts] = useState(['4,0', '5,9']);
  const [boardCols, setBoardCols] = useState(10);
  const [boardRows, setBoardRows] = useState(10);

  const getTerrain = (x, y) => {
    const key = `${x},${y}`;
    if (TERRAIN_MAP.mountains.includes(key)) return { type: 'mountain', label: '▲', color: '#b9b7a4', border: '1px solid #002fa7' };
    if (TERRAIN_MAP.passes.includes(key)) return { type: 'pass', label: '⚬', color: '#e5e3c9', border: '2px dashed #002fa7' };
    if (activeForts.includes(key)) return { type: 'fort', label: '⛊', color: '#d4af37', border: '1px solid #002fa7' };
    if (activeArsenals.includes(key)) return { type: 'arsenal', label: '★', color: '#fffec2', border: '2px solid #002fa7' };
    return { type: 'plain', label: '', color: '#ffffff', border: '1px solid #cbd5e1' };
  };

  // Lobby / Authentication States
  const [inLobby, setInLobby] = useState(true);
  const [playerName, setPlayerName] = useState('');
  const [roomName, setRoomName] = useState('');
  const [roomPassword, setRoomPassword] = useState('');
  const [isConnecting, setIsConnecting] = useState(false);

  // Game Core States
  const [units, setUnits] = useState(INITIAL_UNITS);
  const [turn, setTurn] = useState('North');
  const [movesLeft, setMovesLeft] = useState(5);
  const [attackExecuted, setAttackExecuted] = useState(false);
  const [locCells, setLocCells] = useState({ North: [], South: [] });
  const [connectedUnitIds, setConnectedUnitIds] = useState([]);
  const [movedUnitsThisTurn, setMovedUnitsThisTurn] = useState([]);
  const [selectedUnitId, setSelectedUnitId] = useState(null);
  const [socket, setSocket] = useState(null);
  const [errorMessage, setErrorMessage] = useState('');
  const [canUndo, setCanUndo] = useState(false);
  const [roomUrl, setRoomUrl] = useState('');

  // Telemetry, Animations & Graveyard State Tracking
  const [hoveredCell, setHoveredCell] = useState(null);
  const [xKeyHeld, setXKeyHeld] = useState(false);
  const [zKeyHeld, setZKeyHeld] = useState(false);
  const [sKeyHeld, setSKeyHeld] = useState(false);
  const [isAttackStack, setIsAttackStack] = useState(false);
  const [shiftKeyHeld, setShiftKeyHeld] = useState(false);
  const [multiSelectedIds, setMultiSelectedIds] = useState([]);
  const [tracers, setTracers] = useState([]);          // moving projectile dots
  const [killFlash, setKillFlash] = useState(null);
  const [repelFlash, setRepelFlash] = useState(null); // {x,y,result}// {x,y} of tile to flash red on kill
  const [graveyardTiles, setGraveyardTiles] = useState({}); // Tracks layout keys: {"x,y": count}
  const [showRules, setShowRules] = useState(false);   // info panel toggle
  const gridRef = useRef(null);
  const prevUnitsRef = useRef(INITIAL_UNITS);
  const currentUnitsRef = useRef(INITIAL_UNITS);

  // Position change tracking to lift units during moves
  const [movingUnitId, setMovingUnitId] = useState(null);
  const [lungingUnitIds, setLungingUnitIds] = useState({});
  const [repelShieldUnitId, setRepelShieldUnitId] = useState(null);
  const [dyingUnits, setDyingUnits] = useState([]);
  const [rollingUnitId, setRollingUnitId] = useState(null);
  const [rollDirection, setRollDirection] = useState(null); // 'north' | 'south' | 'east' | 'west' | 'ne' | 'nw' | 'se' | 'sw'
  const [delayedFaces, setDelayedFaces] = useState({});
  const [mines, setMines] = useState([]);
  const [lazarusPits, setLazarusPits] = useState([]);
  const [awaitingLazarusChoice, setAwaitingLazarusChoice] = useState(null);
  useEffect(() => {
    const prevUnits = prevUnitsRef.current;
    if (prevUnits && prevUnits.length > 0) {
      for (const u of units) {
        const prev = prevUnits.find(p => p.id === u.id);
        if (prev && (prev.x !== u.x || prev.y !== u.y)) {
          const isCavalry = u.type.toLowerCase() === 'cavalry';
          if (!isCavalry) {
            const dx = u.x - prev.x;
            const dy = u.y - prev.y;
            let dir = null;
            if (dx > 0 && dy === 0) dir = 'east';
            else if (dx < 0 && dy === 0) dir = 'west';
            else if (dx === 0 && dy > 0) dir = 'south';
            else if (dx === 0 && dy < 0) dir = 'north';
            else if (dx > 0 && dy < 0) dir = 'ne';
            else if (dx < 0 && dy < 0) dir = 'nw';
            else if (dx > 0 && dy > 0) dir = 'se';
            else if (dx < 0 && dy > 0) dir = 'sw';

            if (dir) {
              setRollingUnitId(u.id);
              setRollDirection(dir);
              // Freeze face symbols at their pre-rotated state during the 600ms tumble
              const oldFaces = prev.faces || {
                top: prev.symbol,
                bottom: prev.symbol === 'A' ? 'I' : 'A',
                front: prev.symbol === 'C' ? 'I' : 'C',
                back: prev.symbol === 'R' ? 'I' : 'R',
                left: 'I',
                right: 'A'
              };
              setDelayedFaces(prevMap => ({ ...prevMap, [u.id]: oldFaces }));

              setTimeout(() => {
                setRollingUnitId(null);
                setRollDirection(null);
                setDelayedFaces(prevMap => {
                  const next = { ...prevMap };
                  delete next[u.id];
                  return next;
                });
              }, 600);
            }
          } else {
            // Cavalry slides and lifts
            setMovingUnitId(u.id);
            setTimeout(() => {
              setMovingUnitId(null);
            }, 600);
          }
          break;
        }
      }
    }
    prevUnitsRef.current = units;
  }, [units]);

  // Player Identity States
  const [mySide, setMySide] = useState(null);
  const [players, setPlayers] = useState({ North: null, South: null });
  const [winner, setWinner] = useState(null); // 'North', 'South', or null

  // Dynamically inject structural layout rules and transient projectile animations
  useEffect(() => {
    const styleSheet = document.createElement("style");
    styleSheet.innerText = `
      /* 3D Grid Perspective and Alignment */
      .grid-3d-perspective {
        perspective: 1200px;
        transform-style: preserve-3d;
        padding: 40px 10px;
        display: flex;
        align-items: center;
        justify-content: center;
      }
      .grid-3d-board {
        transform: rotateX(55deg) rotateZ(-45deg);
        transform-style: preserve-3d;
        box-shadow: 15px 15px 35px rgba(0, 0, 0, 0.35), -5px -5px 15px rgba(255, 255, 255, 0.4);
        transition: transform 0.5s cubic-bezier(0.25, 0.8, 0.25, 1);
      }
      .cell-3d {
        transform-style: preserve-3d;
      }

      /* 3D Cube Styles */
      .cube-container {
        position: relative;
        width: 30px;
        height: 30px;
        transform-style: preserve-3d;
        transform: translateZ(15px);
        transition: filter 0.25s ease;
      }
      .cube-container.lifted {
        transform: translateZ(25px);
        transition: transform 0.25s cubic-bezier(0.175, 0.885, 0.32, 1.275);
      }
      .cube-container.moving {
        transform: translateZ(45px) rotateX(8deg) rotateY(8deg);
      }
      .cube-face {
        position: absolute;
        width: 30px;
        height: 30px;
        display: flex;
        align-items: center;
        justify-content: center;
        font-family: monospace;
        font-weight: bold;
        font-size: 13px;
        color: #ffffff;
        backface-visibility: hidden;
      }
      .cube-face-top {
        transform: rotateX(0deg) translateZ(15px);
        border: 1.5px solid rgba(255, 255, 255, 0.6);
        box-shadow: inset 0 0 4px rgba(255, 255, 255, 0.3);
      }
      .cube-face-front {
        transform: rotateX(-90deg) translateZ(15px);
        filter: brightness(82%);
        border: 1px solid rgba(255, 255, 255, 0.2);
      }
      .cube-face-right {
        transform: rotateY(90deg) translateZ(15px);
        filter: brightness(68%);
        border: 1px solid rgba(255, 255, 255, 0.2);
      }
      .cube-face-left {
        transform: rotateY(-90deg) translateZ(15px);
        filter: brightness(75%);
        border: 1px solid rgba(255, 255, 255, 0.2);
      }
      .cube-face-back {
        transform: rotateX(90deg) translateZ(15px);
        filter: brightness(90%);
        border: 1px solid rgba(255, 255, 255, 0.2);
      }
      .cube-face-bottom {
        transform: rotateX(180deg) translateZ(15px);
        filter: brightness(60%);
        border: 1px solid rgba(255, 255, 255, 0.2);
      }
      .cube-shadow {
        position: absolute;
        width: 24px;
        height: 24px;
        background-color: rgba(0, 0, 0, 0.3);
        filter: blur(4px);
        transform: translateZ(1px);
        transition: transform 0.25s ease, opacity 0.25s ease, background-color 0.25s ease;
        border-radius: 4px;
        pointer-events: none;
      }
      .cube-container.lifted ~ .cube-shadow {
        transform: translateZ(1px) scale(0.8);
        background-color: rgba(0, 0, 0, 0.4);
        filter: blur(6px);
      }
      .cube-container.moving ~ .cube-shadow {
        transform: translateZ(1px) scale(0.6);
        background-color: rgba(0, 0, 0, 0.15);
        filter: blur(8px);
        opacity: 0.6;
      }

      /* Absolute overlay positioning for smooth motion transitions */
      .absolute-unit-wrapper {
        position: absolute;
        width: 10%;
        height: 10%;
        display: flex;
        align-items: center;
        justify-content: center;
        transition: left 0.6s cubic-bezier(0.25, 0.8, 0.25, 1), top 0.6s cubic-bezier(0.25, 0.8, 0.25, 1);
        transform-style: preserve-3d;
        pointer-events: none;
        z-index: 10;
      }
      .absolute-unit-wrapper .cube-container {
        pointer-events: auto;
      }

      /* Projectile dot travelling across the grid in 3D */
      @keyframes projectileTravel {
        0%   { transform: translate3d(var(--px0), var(--py0), 16px); opacity: 1; }
        85%  { opacity: 1; }
        100% { transform: translate3d(var(--px1), var(--py1), 16px); opacity: 0; }
      }
      .projectile-dot {
        position: absolute;
        border-radius: 50%;
        pointer-events: none;
        z-index: 200;
        animation: projectileTravel var(--dur) ease-in forwards;
        left: 0; top: 0;
      }

      /* Magical Protection Shield Glow */
      .magical-shield {
        box-shadow: 0 0 25px #3b82f6, 0 0 10px #3b82f6, inset 0 0 15px #ffffff !important;
        animation: shieldPulse 0.4s ease-in-out alternate infinite;
      }
      @keyframes shieldPulse {
        0% { transform: scale(1) translateZ(15px); }
        100% { transform: scale(1.08) translateZ(18px); filter: brightness(1.25); }
      }

      /* Magical Protection Shield Glow on individual faces */
      .magical-shield-face {
        box-shadow: 0 0 25px #3b82f6, inset 0 0 10px #3b82f6 !important;
        border-color: #60a5fa !important;
        filter: brightness(1.3) saturate(1.2);
      }

      /* 3D disintegration dissolution animation */
      .cube-container.disintegrating {
        animation: disintegrate 0.75s cubic-bezier(0.25, 0.8, 0.25, 1) forwards;
      }
      @keyframes disintegrate {
        0% { transform: translateZ(15px) scale(1) rotateZ(0deg); opacity: 1; filter: brightness(2) saturate(2); }
        100% { transform: translateZ(60px) scale(0) rotateZ(360deg); opacity: 0; filter: brightness(4) blur(3px); }
      }

      /* 3D Rolling animations */
      .cube-container.roll-east {
        animation: rollEastAnim 0.6s cubic-bezier(0.25, 0.8, 0.25, 1) forwards;
      }
      .cube-container.roll-west {
        animation: rollWestAnim 0.6s cubic-bezier(0.25, 0.8, 0.25, 1) forwards;
      }
      .cube-container.roll-north {
        animation: rollNorthAnim 0.6s cubic-bezier(0.25, 0.8, 0.25, 1) forwards;
      }
      .cube-container.roll-south {
        animation: rollSouthAnim 0.6s cubic-bezier(0.25, 0.8, 0.25, 1) forwards;
      }
      .cube-container.roll-ne {
        animation: rollNEAnim 0.6s cubic-bezier(0.25, 0.8, 0.25, 1) forwards;
      }
      .cube-container.roll-nw {
        animation: rollNWAnim 0.6s cubic-bezier(0.25, 0.8, 0.25, 1) forwards;
      }
      .cube-container.roll-se {
        animation: rollSEAnim 0.6s cubic-bezier(0.25, 0.8, 0.25, 1) forwards;
      }
      .cube-container.roll-sw {
        animation: rollSWAnim 0.6s cubic-bezier(0.25, 0.8, 0.25, 1) forwards;
      }

      @keyframes rollEastAnim {
        0% { transform: translateZ(15px) rotateY(0deg); }
        100% { transform: translateZ(15px) rotateY(90deg); }
      }
      @keyframes rollWestAnim {
        0% { transform: translateZ(15px) rotateY(0deg); }
        100% { transform: translateZ(15px) rotateY(-90deg); }
      }
      @keyframes rollNorthAnim {
        0% { transform: translateZ(15px) rotateX(0deg); }
        100% { transform: translateZ(15px) rotateX(90deg); }
      }
      @keyframes rollSouthAnim {
        0% { transform: translateZ(15px) rotateX(0deg); }
        100% { transform: translateZ(15px) rotateX(-90deg); }
      }
      @keyframes rollNEAnim {
        0% { transform: translateZ(15px) rotateY(0deg) rotateX(0deg); }
        50% { transform: translateZ(15px) rotateY(90deg) rotateX(0deg); }
        100% { transform: translateZ(15px) rotateY(90deg) rotateX(90deg); }
      }
      @keyframes rollNWAnim {
        0% { transform: translateZ(15px) rotateY(0deg) rotateX(0deg); }
        50% { transform: translateZ(15px) rotateY(-90deg) rotateX(0deg); }
        100% { transform: translateZ(15px) rotateY(-90deg) rotateX(90deg); }
      }
      @keyframes rollSEAnim {
        0% { transform: translateZ(15px) rotateY(0deg) rotateX(0deg); }
        50% { transform: translateZ(15px) rotateY(90deg) rotateX(0deg); }
        100% { transform: translateZ(15px) rotateY(90deg) rotateX(-90deg); }
      }
      @keyframes rollSWAnim {
        0% { transform: translateZ(15px) rotateY(0deg) rotateX(0deg); }
        50% { transform: translateZ(15px) rotateY(-90deg) rotateX(0deg); }
        100% { transform: translateZ(15px) rotateY(-90deg) rotateX(-90deg); }
      }
      /* Red kill-flash bloom on target tile */
      @keyframes killBloom {
        0%   { opacity: 0.9; transform: scale(0.5); }
        60%  { opacity: 0.7; transform: scale(1.4); }
        100% { opacity: 0;   transform: scale(2); }
      }
      .kill-flash {
        position: absolute; inset: 0;
        background: radial-gradient(circle, #ef444480 0%, transparent 70%);
        border-radius: 3px;
        pointer-events: none;
        z-index: 150;
        animation: killBloom 0.55s ease-out forwards;
      }

      /* Skull pulsing on graveyard tile */
      @keyframes skullPulse {
        0%, 100% { opacity: 0.55; transform: translate(-50%,-50%) scale(1); }
        50%       { opacity: 0.85; transform: translate(-50%,-50%) scale(1.15); }
      }
      .skull-marker {
        position: absolute;
        top: 50%; left: 50%;
        transform: translate(-50%,-50%);
        font-size: 14px;
        z-index: 3;
        pointer-events: none;
        animation: skullPulse 2.2s ease-in-out infinite;
        filter: grayscale(30%);
      }
      
      @keyframes repelBloom {
  0%   { opacity: 0.9; transform: scale(0.5); }
  60%  { opacity: 0.6; transform: scale(1.3); }
  100% { opacity: 0;   transform: scale(1.8); }
}
.repel-flash-blue {
  position: absolute; inset: 0;
  background: radial-gradient(circle, #3b82f680 0%, transparent 70%);
  border-radius: 3px; pointer-events: none; z-index: 150;
  animation: repelBloom 0.55s ease-out forwards;
}
.repel-flash-amber {
  position: absolute; inset: 0;
  background: radial-gradient(circle, #f59e0b80 0%, transparent 70%);
  border-radius: 3px; pointer-events: none; z-index: 150;
  animation: repelBloom 0.55s ease-out forwards;
}

/* Oscillating Selection Glow */
@keyframes selectionGlow {
  0%, 100% {
    box-shadow: 0 0 6px var(--glow-color), inset 0 0 4px var(--glow-color);
    opacity: 0.9;
  }
  50% {
    box-shadow: 0 0 16px var(--glow-color), inset 0 0 8px var(--glow-color);
    opacity: 1;
  }
}
.cell-selected-active {
  --glow-color: #d4af37;
  animation: selectionGlow 1.6s ease-in-out infinite;
  border: 2px solid #d4af37 !important;
  z-index: 10 !important;
}
.cell-selected-multi-stack {
  --glow-color: #10b981;
  animation: selectionGlow 1.6s ease-in-out infinite;
  border: 2px solid #10b981 !important;
  z-index: 10 !important;
}
.cell-selected-multi-shape {
  --glow-color: #10b981;
  animation: selectionGlow 1.6s ease-in-out infinite;
  border: 2px dashed #10b981 !important;
  z-index: 10 !important;
}
.cell-selected-enemy {
  --glow-color: #ef4444;
  animation: selectionGlow 1.6s ease-in-out infinite;
  border: 2px dashed #ef4444 !important;
  z-index: 10 !important;
}
.cell-selected-enemy-stack {
  --glow-color: #ef4444;
  animation: selectionGlow 1.6s ease-in-out infinite;
  border: 2px solid #ef4444 !important;
  z-index: 10 !important;
}
.cell-reachable {
  --glow-color: #10b981;
  animation: selectionGlow 1.6s ease-in-out infinite;
  border: 2px solid #10b981 !important;
  z-index: 5 !important;
  background-color: rgba(16, 185, 129, 0.15) !important;
}
.cell-attack-range {
  --glow-color: #ef4444;
  animation: selectionGlow 1.6s ease-in-out infinite;
  border: 2px solid #ef4444 !important;
  z-index: 5 !important;
  background-color: rgba(239, 68, 68, 0.15) !important;
}

/* Skirmish Lazarus Pits, Mines, and Shields */
.cell-lazarus-pit {
  background: radial-gradient(circle, rgba(6, 182, 212, 0.45) 0%, rgba(8, 145, 178, 0.15) 70%) !important;
  border: 2px dashed #06b6d4 !important;
  box-shadow: inset 0 0 15px rgba(6, 182, 212, 0.3) !important;
  animation: lazarusPulse 2s infinite ease-in-out;
}
@keyframes lazarusPulse {
  0%, 100% { filter: brightness(1); }
  50% { filter: brightness(1.35) saturate(1.2); }
}
.mine-marker {
  position: absolute;
  width: 14px;
  height: 14px;
  background: radial-gradient(circle, #f43f5e 20%, #9f1239 80%);
  border: 1.5px solid #ffffff;
  border-radius: 50%;
  box-shadow: 0 0 8px #f43f5e, inset 0 0 3px rgba(0,0,0,0.5);
  animation: minePulse 1s infinite alternate ease-in-out;
  z-index: 50;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%) translateZ(2px);
}
@keyframes minePulse {
  0% { transform: translate(-50%, -50%) translateZ(2px) scale(0.85); box-shadow: 0 0 4px #f43f5e; }
  100% { transform: translate(-50%, -50%) translateZ(2px) scale(1.1); box-shadow: 0 0 10px #f43f5e; }
}
.magical-shield-bubble {
  position: absolute;
  width: 36px;
  height: 36px;
  background: radial-gradient(circle, rgba(96, 165, 250, 0.15) 30%, rgba(59, 130, 246, 0.45) 85%);
  border: 1.5px solid rgba(147, 197, 253, 0.85);
  border-radius: 50%;
  box-shadow: 0 0 12px rgba(59, 130, 246, 0.6), inset 0 0 8px rgba(96, 165, 250, 0.5);
  pointer-events: none;
  z-index: 100;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%) translateZ(15px);
  animation: shieldPulse 1.8s infinite ease-in-out;
}
@keyframes shieldPulse {
  0%, 100% { transform: translate(-50%, -50%) translateZ(15px) scale(0.95); opacity: 0.85; }
  50% { transform: translate(-50%, -50%) translateZ(15px) scale(1.05); opacity: 1; }
}
    `;
    document.head.appendChild(styleSheet);
    return () => styleSheet.remove();
  }, []);

  // Track 'X' and 'Shift' key down-states for diagnostics and stack operations
  useEffect(() => {
    const handleKeyDown = (e) => {
      if (e.key.toLowerCase() === 'x') setXKeyHeld(true);
      if (e.key.toLowerCase() === 'z') setZKeyHeld(true);
      if (e.key.toLowerCase() === 's') setSKeyHeld(true);
      if (e.key === 'Shift') setShiftKeyHeld(true);
    };
    const handleKeyUp = (e) => {
      if (e.key.toLowerCase() === 'x') setXKeyHeld(false);
      if (e.key.toLowerCase() === 'z') setZKeyHeld(false);
      if (e.key.toLowerCase() === 's') setSKeyHeld(false);
      if (e.key === 'Shift') setShiftKeyHeld(false);
    };
    window.addEventListener('keydown', handleKeyDown);
    window.addEventListener('keyup', handleKeyUp);
    return () => {
      window.removeEventListener('keydown', handleKeyDown);
      window.removeEventListener('keyup', handleKeyUp);
    };
  }, []);

  // Intercept unit diffs → animated projectile + kill flash + skull graveyard
  useEffect(() => {
    if (inLobby || !gridRef.current) {
      prevUnitsRef.current = units;
      return;
    }

    const prevMap = prevUnitsRef.current.reduce((acc, u) => ({ ...acc, [u.id]: u }), {});
    const currentMap = units.reduce((acc, u) => ({ ...acc, [u.id]: u }), {});

    let deadUnit = null;
    for (const id in prevMap) {
      if (!currentMap[id]) { deadUnit = prevMap[id]; break; }
    }

    if (deadUnit) {
      const tileKey = `${deadUnit.x},${deadUnit.y}`;
      setGraveyardTiles(prev => ({
        ...prev,
        [tileKey]: {
          count: (prev[tileKey]?.count || 0) + 1,
          side: deadUnit.side
        }
      }));

      // 2. Kill-flash on target tile
      setKillFlash({ x: deadUnit.x, y: deadUnit.y });
      setTimeout(() => setKillFlash(null), 600);

      // 3. Animated projectile dot from nearest attacker to target
      const attackerSide = deadUnit.side === 'North' ? 'South' : 'North';
      const potentialAttackers = prevUnitsRef.current.filter(u => u.side === attackerSide);

      let closestAttacker = null;
      let closestDist = Infinity;
      potentialAttackers.forEach(attacker => {
        const unitType = attacker.type.toLowerCase();
        const maxRange = unitType === 'artillery' ? 3 : 1;
        const dx = Math.abs(deadUnit.x - attacker.x);
        const dy = Math.abs(deadUnit.y - attacker.y);
        const dist = Math.hypot(dx, dy);
        if (dx <= maxRange && dy <= maxRange && dist < closestDist) {
          closestDist = dist;
          closestAttacker = attacker;
        }
      });

      if (closestAttacker) {
        const startCell = gridRef.current.querySelector(`[data-coord="${closestAttacker.x},${closestAttacker.y}"]`);
        const endCell = gridRef.current.querySelector(`[data-coord="${deadUnit.x},${deadUnit.y}"]`);

        if (startCell && endCell) {
          const gridRect = gridRef.current.getBoundingClientRect();
          const startRect = startCell.getBoundingClientRect();
          const endRect = endCell.getBoundingClientRect();

          const x1 = startRect.left + startRect.width / 2 - gridRect.left;
          const y1 = startRect.top + startRect.height / 2 - gridRect.top;
          const x2 = endRect.left + endRect.width / 2 - gridRect.left;
          const y2 = endRect.top + endRect.height / 2 - gridRect.top;

          const unitType = closestAttacker.type.toLowerCase();
          // Faster for cavalry, medium for infantry, slow arc for artillery
          const dur = unitType === 'cavalry' ? '0.25s' : unitType === 'artillery' ? '0.6s' : '0.35s';
          const color = unitType === 'artillery' ? '#f59e0b'   // amber shell
            : unitType === 'cavalry' ? '#06b6d4'   // cyan streak
              : '#ef4444';                              // red infantry round
          const size = unitType === 'artillery' ? 10 : 7;

          const traceId = Math.random().toString(36).substring(2, 9);
          setTracers(prev => [...prev, { id: traceId, x1, y1, x2, y2, dur, color, size }]);
          const clearMs = unitType === 'artillery' ? 650 : unitType === 'cavalry' ? 300 : 400;
          setTimeout(() => setTracers(prev => prev.filter(t => t.id !== traceId)), clearMs);
        }
      }
    }
    prevUnitsRef.current = units;
  }, [units, inLobby]);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const sharedRoom = params.get('room');
    if (sharedRoom) {
      setRoomName(sharedRoom);
      setGameMode('multi');
    }
  }, []);

  const handleConnectToRoom = (e) => {
    e.preventDefault();
    if (!playerName.trim()) {
      setErrorMessage("System Failure: Identification callsign cannot be blank.");
      return;
    }

    const isSandbox = gameMode === 'single' || gameMode === 'ai_vs_ai';
    const finalRoom = isSandbox ? `sandbox-${Date.now()}` : roomName.trim();
    const finalPassword = isSandbox ? 'local-ai' : roomPassword.trim();

    if (gameMode === 'multi' && (!roomName.trim() || !roomPassword.trim())) {
      setErrorMessage("System Failure: Network matches require an active Room ID and Password.");
      return;
    }

    if (gameMode === 'multi') {
      const params = new URLSearchParams(window.location.search);
      params.set('room', finalRoom);
      window.history.replaceState({}, '', `${window.location.pathname}?${params.toString()}`);
      setRoomUrl(window.location.href);
    }

    const isProd = !window.location.hostname.includes("localhost") && !window.location.hostname.includes("127.0.0.1");
    const backendHost = isProd ? "le-jeu-de-la-guerre.onrender.com" : "127.0.0.1:8000";
    const protocol = window.location.protocol === "https:" ? "wss" : "ws";

    setIsConnecting(true);
    setErrorMessage("Establishing connection... Note: Render servers may take 30-40 seconds to spin up from cold sleep.");

    const secureWsUrl = `${protocol}://${backendHost}/ws/${encodeURIComponent(finalRoom)}?name=${encodeURIComponent(playerName.trim())}&password=${encodeURIComponent(finalPassword)}&vs_ai=${gameMode === 'single'}&ai_vs_ai=${gameMode === 'ai_vs_ai'}&player_side=${playerSide}&layout_type=${layoutType}`;
    const ws = new WebSocket(secureWsUrl);

    ws.onopen = () => {
      setInLobby(false);
      setErrorMessage('');
      setIsConnecting(false);
    };

    ws.onmessage = (event) => {
      const data = JSON.parse(event.data);


      // --- DEBUG INTERCEPTOR ---
      console.log("📥 [WS INCOMING] Units count in update:", data.units?.length);
      if (data.units) {
        // Find which units were present before but missing now
        const prevIds = units.map(u => u.id);
        const nextIds = data.units.map(u => u.id);
        const vanished = units.filter(u => !nextIds.includes(u.id));

        if (vanished.length > 0) {
          console.error("💀 [DEBUG] Units vanished during sync:", vanished);
        }
      }

      if (data.type === 'error') {
        setErrorMessage(data.message);
        if (data.message.toLowerCase().includes('password') || data.message.toLowerCase().includes('authentication') || data.message.toLowerCase().includes('full')) {
          setInLobby(true);
          ws.close();
        } else {
          setTimeout(() => setErrorMessage(''), 4000);
        }
      } else {
        // Intercept unit death to trigger disintegration animations
        const incomingIds = (data.units || []).map(u => u.id);
        const deadUnits = currentUnitsRef.current.filter(u => !incomingIds.includes(u.id));

        if (deadUnits.length > 0) {
          setDyingUnits(prev => [...prev, ...deadUnits.map(du => ({ ...du, phase: 'ramming' }))]);
          
          // Phase 2: transition to disintegration at impact (350ms)
          setTimeout(() => {
            setDyingUnits(prev => prev.map(u => deadUnits.some(du => du.id === u.id) ? { ...u, phase: 'disintegrating' } : u));
          }, 350);

          // Phase 3: clean up from dying state (1100ms)
          setTimeout(() => {
            setDyingUnits(prev => prev.filter(u => !deadUnits.some(du => du.id === u.id)));
          }, 1100);
        }

        // Combat Animation Triggers snapshot (before overwriting currentUnitsRef)
        const currentUnits = currentUnitsRef.current;

        if (data.lastCombat) {
          const tx = data.lastCombat.targetX;
          const ty = data.lastCombat.targetY;
          const res = data.lastCombat.result;

          // Look up the defending unit in the snapshot state before they were potentially deleted
          const defender = currentUnits.find(u => u.x === tx && u.y === ty);
          if (defender) {
            const defenderSide = defender.side;
            const attackerSide = defenderSide === 'North' ? 'South' : 'North';

            // Find all Infantry/Cavalry attackers in range of the target in the snapshot
            const attackers = currentUnits.filter(u => {
              if (u.side !== attackerSide) return false;
              const dx = Math.abs(u.x - tx);
              const dy = Math.abs(u.y - ty);
              const maxRange = u.type.toLowerCase() === 'artillery' ? 3 : 1;
              return dx <= maxRange && dy <= maxRange;
            });

            // Trigger lunge animation for non-artillery attackers
            attackers.forEach(attacker => {
              const uType = attacker.type.toLowerCase();
              if (uType !== 'artillery') {
                const diffX = tx - attacker.x;
                const diffY = ty - attacker.y;
                const len = Math.hypot(diffX, diffY) || 1;
                const dx = (diffX / len) * 0.45;
                const dy = (diffY / len) * 0.45;

                setLungingUnitIds(prev => ({ ...prev, [attacker.id]: { dx, dy } }));
                setTimeout(() => {
                  setLungingUnitIds(prev => {
                    const next = { ...prev };
                    delete next[attacker.id];
                    return next;
                  });
                }, 350);
              }
            });

            // Trigger protection shield & repel flashes if combat was repelled
            if (res !== "DESTROY") {
              setRepelFlash({ x: tx, y: ty, result: res });
              setTimeout(() => setRepelFlash(null), 600);

              setRepelShieldUnitId(defender.id);
              setTimeout(() => setRepelShieldUnitId(null), 900);
            }
          }
        }

        // Now safe to update units state
        setUnits(data.units || []);
        currentUnitsRef.current = data.units || [];
        if (data.cols !== undefined) setBoardCols(data.cols);
        if (data.rows !== undefined) setBoardRows(data.rows);

        if (data.arsenals) {
          const n_ars = data.arsenals.North.map(([x,y]) => `${x},${y}`);
          const s_ars = data.arsenals.South.map(([x,y]) => `${x},${y}`);
          setActiveArsenals([...n_ars, ...s_ars]);
        }
        if (data.fortresses) {
          const server_forts = data.fortresses.map(([x,y]) => `${x},${y}`);
          const server_arsenals = [...(data.arsenals?.North || []), ...(data.arsenals?.South || [])].map(([x,y]) => `${x},${y}`);
          const pure_forts = server_forts.filter(f => !server_arsenals.includes(f));
          setActiveForts(pure_forts);
        }

        setTurn(data.turn);
        setMovesLeft(data.movesLeft ?? 5);
        setAttackExecuted(data.attackExecuted ?? false);
        setLocCells(data.linesOfCommunication || { North: [], South: [] });
        setConnectedUnitIds(data.connectedUnitIds || []);
        setMovedUnitsThisTurn(data.movedUnitsThisTurn || []);
        setCanUndo(data.canUndo ?? false);
        setMines(data.mines || []);
        setLazarusPits(data.lazarusPits || []);
        setAwaitingLazarusChoice(data.awaitingLazarusChoice || null);

        if (data.yourSide) setMySide(data.yourSide);
        if (data.players) setPlayers(data.players);

        // DELAY WINNER DECLARATION TO ALLOW ANIMATIONS TO RESOLVE
        if (data.winner !== undefined) {
          if (data.winner) {
            setTimeout(() => {
              setWinner(data.winner);
            }, 1200);
          } else {
            setWinner(null);
          }
        }
      }
    };

    ws.onerror = () => {
      setErrorMessage("Network Failure: Server did not respond to handshake. (Note: Render's free tier spins down after 15 mins of inactivity. Please refresh and try again in 30-40 seconds.)");
      setIsConnecting(false);
    };
    ws.onclose = () => {
      setInLobby(true);
      setMySide(null);
      setPlayers({ North: null, South: null });
      setWinner(null);
      setIsConnecting(false);
      setBoardCols(10);
      setBoardRows(10);
    };

    setSocket(ws);
  };

  const getConnectedComponent = (startUnit, allUnits) => {
    if (!startUnit) return [];
    const component = [];
    const queue = [startUnit];
    const visitedIds = new Set([startUnit.id]);

    while (queue.length > 0) {
      const current = queue.shift();
      component.push(current);

      const neighbors = allUnits.filter(u => {
        if (u.side !== startUnit.side || visitedIds.has(u.id)) return false;
        const dx = Math.abs(u.x - current.x);
        const dy = Math.abs(u.y - current.y);
        return dx <= 1 && dy <= 1; // Contiguous adjacent chain (including diagonals)
      });

      for (const neighbor of neighbors) {
        visitedIds.add(neighbor.id);
        queue.push(neighbor);
      }
    }
    return component;
  };

  const isSelectionConnected = (selectedIds) => {
    if (selectedIds.length <= 1) return true;
    const selectedUnits = units.filter(u => selectedIds.includes(u.id));
    const start = selectedUnits[0];
    const visited = new Set([start.id]);
    const queue = [start];
    while (queue.length > 0) {
      const current = queue.shift();
      const neighbors = selectedUnits.filter(u => {
        if (visited.has(u.id)) return false;
        const dx = Math.abs(u.x - current.x);
        const dy = Math.abs(u.y - current.y);
        return dx <= 1 && dy <= 1;
      });
      for (const n of neighbors) {
        visited.add(n.id);
        queue.push(n);
      }
    }
    return visited.size === selectedIds.length;
  };

  const unitPositionsMap = units.reduce((acc, unit) => {
    acc[`${unit.x},${unit.y}`] = unit;
    return acc;
  }, {});

  const isMyTurn = mySide === turn;

  const handleCellClick = (x, y) => {
    const clickedUnit = unitPositionsMap[`${x},${y}`];

    if (clickedUnit) {
      const isFriendlyClick = clickedUnit.side === activeMySide;
      const currentSelectionSide = multiSelectedIds.length > 0 ? units.find(u => u.id === multiSelectedIds[0])?.side : null;
      const oppositeFactionSelected = currentSelectionSide && currentSelectionSide !== clickedUnit.side;

      let effectiveIds = oppositeFactionSelected ? [] : multiSelectedIds;

      if (isFriendlyClick) {
        // Friendly unit selection
        if (sKeyHeld) {
          if (isAdjacentToSelection(clickedUnit, effectiveIds, units)) {
            setIsAttackStack(true);
            if (shiftKeyHeld) {
              const comp = getConnectedComponent(clickedUnit, units);
              setMultiSelectedIds(comp.map(u => u.id));
            } else {
              setMultiSelectedIds(prev => {
                const base = oppositeFactionSelected ? [] : prev;
                return base.includes(clickedUnit.id) ? base.filter(id => id !== clickedUnit.id) : [...base, clickedUnit.id];
              });
            }
          } else {
            setSelectedUnitId(null);
            setMultiSelectedIds([]);
          }
        } else if (xKeyHeld) {
          if (isAdjacentToSelection(clickedUnit, effectiveIds, units)) {
            setIsAttackStack(false);
            if (shiftKeyHeld) {
              const comp = getConnectedComponent(clickedUnit, units);
              setMultiSelectedIds(comp.map(u => u.id));
            } else {
              setMultiSelectedIds(prev => {
                const base = oppositeFactionSelected ? [] : prev;
                return base.includes(clickedUnit.id) ? base.filter(id => id !== clickedUnit.id) : [...base, clickedUnit.id];
              });
            }
          } else {
            setSelectedUnitId(null);
            setMultiSelectedIds([]);
          }
        } else {
          // Single select friendly
          setIsAttackStack(true);
          const nextSelectedId = clickedUnit.id === selectedUnitId ? null : clickedUnit.id;
          setSelectedUnitId(nextSelectedId);
          setMultiSelectedIds(nextSelectedId ? [clickedUnit.id] : []);
        }
      } else {
        // Enemy unit click
        if (zKeyHeld) {
          // Inspect enemy group
          if (isAdjacentToSelection(clickedUnit, effectiveIds, units)) {
            setIsAttackStack(false);
            setSelectedUnitId(null); // Clear friendly selectedUnitId
            if (shiftKeyHeld) {
              const comp = getConnectedComponent(clickedUnit, units);
              setMultiSelectedIds(comp.map(u => u.id));
            } else {
              setMultiSelectedIds(prev => {
                const base = oppositeFactionSelected ? [] : prev;
                return base.includes(clickedUnit.id) ? base.filter(id => id !== clickedUnit.id) : [...base, clickedUnit.id];
              });
            }
          } else {
            setSelectedUnitId(null);
            setMultiSelectedIds([]);
          }
        } else {
          // Clicked enemy unit WITHOUT holding Z
          const hasFriendlySelection = selectedUnitId || (multiSelectedIds.length > 0 && isAttackStack);
          if (isMyTurn && hasFriendlySelection && isEnemyInAttackRange(x, y) && socket?.readyState === WebSocket.OPEN) {
            socket.send(JSON.stringify({ action: 'attack', x, y }));
            setSelectedUnitId(null);
            setMultiSelectedIds([]);
          } else {
            // Otherwise, treat it as a single unit inspection for this enemy!
            setIsAttackStack(false);
            setSelectedUnitId(null);
            const alreadySelected = multiSelectedIds.length === 1 && multiSelectedIds[0] === clickedUnit.id;
            setMultiSelectedIds(alreadySelected ? [] : [clickedUnit.id]);
          }
        }
      }
      return;
    }

    // Clicking an empty cell
    if (isMyTurn && selectedUnitId && socket?.readyState === WebSocket.OPEN) {
      if (reachableCells.includes(`${x},${y}`)) {
        socket.send(JSON.stringify({ action: 'move', unitId: selectedUnitId, x, y }));
      }
    }
    // Always clear selection on empty cell click!
    setSelectedUnitId(null);
    setMultiSelectedIds([]);
  };

  const handleAction = (actionType) => {
    if (actionType !== 'restart' && !isMyTurn) return;
    if (socket?.readyState === WebSocket.OPEN) {
      socket.send(JSON.stringify({ action: actionType }));
      setSelectedUnitId(null);
      setMultiSelectedIds([]);
      if (actionType === 'restart') {
        setGraveyardTiles({});
        setWinner(null);
      }
    }
  };

  const handleExitToLobby = () => {
    if (socket) {
      socket.close();
    } else {
      setInLobby(true);
      setMySide(null);
      setPlayers({ North: null, South: null });
      setWinner(null);
      setBoardCols(10);
      setBoardRows(10);
    }
  };

  const isCellInLoc = (x, y, side) => {
    const coords = locCells[side] || [];
    return coords.some(coord => coord[0] === x && coord[1] === y);
  };

  const isAdjacentToSelection = (unit, selectedIds, units) => {
    if (selectedIds.length === 0) return true;
    const selectedUnits = units.filter(u => selectedIds.includes(u.id));
    return selectedUnits.some(su => {
      const dx = Math.abs(su.x - unit.x);
      const dy = Math.abs(su.y - unit.y);
      return dx <= 1 && dy <= 1;
    });
  };

  const checkLineOfSight = (fromX, fromY, toX, toY, maxRange) => {
    const dxDiff = Math.abs(toX - fromX);
    const dyDiff = Math.abs(toY - fromY);
    if (dxDiff !== 0 && dyDiff !== 0 && dxDiff !== dyDiff) return false;

    const distance = Math.max(dxDiff, dyDiff);
    if (distance > maxRange || distance === 0) return false;

    let x0 = fromX;
    let y0 = fromY;
    const x1 = toX;
    const y1 = toY;

    const dx = Math.abs(x1 - x0);
    const dy = Math.abs(y1 - y0);
    const sx = x0 < x1 ? 1 : -1;
    const sy = y0 < y1 ? 1 : -1;
    let err = dx - dy;

    let cx = x0;
    let cy = y0;
    while (true) {
      if ((cx !== x0 || cy !== y0) && (cx !== x1 || cy !== y1)) {
        if (getTerrain(cx, cy).type === 'mountain') {
          return false;
        }
      }
      if (cx === x1 && cy === y1) break;

      const e2 = 2 * err;
      if (e2 > -dy) {
        err -= dy;
        cx += sx;
      }
      if (e2 < dx) {
        err += dx;
        cy += sy;
      }
    }
    return true;
  };

  const getReachableTiles = (unit) => {
    if (!unit) return [];
    if (!connectedUnitIds.includes(unit.id)) return [];
    if (movedUnitsThisTurn.includes(unit.id)) return [];

    const unitType = unit.type.toLowerCase();
    const speed = unitType === 'cavalry' ? 2 : 1;
    const startX = unit.x;
    const startY = unit.y;

    const queue = [{ x: startX, y: startY, dist: 0 }];
    const visited = new Set([`${startX},${startY}`]);
    const reachable = [];

    const isMountain = (cx, cy) => getTerrain(cx, cy).type === 'mountain';
    const isOccupied = (cx, cy) => units.some(u => u.x === cx && u.y === cy);

    while (queue.length > 0) {
      const { x: cx, y: cy, dist } = queue.shift();

      if (dist > 0) {
        if (!isMountain(cx, cy) && !isOccupied(cx, cy)) {
          reachable.push(`${cx},${cy}`);
        }
      }

      if (dist >= speed) continue;

      for (let dx = -1; dx <= 1; dx++) {
        for (let dy = -1; dy <= 1; dy++) {
          if (dx === 0 && dy === 0) continue;
          const nx = cx + dx;
          const ny = cy + dy;
          if (nx >= 0 && nx < boardCols && ny >= 0 && ny < boardRows) {
            const key = `${nx},${ny}`;
            if (!isMountain(nx, ny) && !visited.has(key)) {
              visited.add(key);
              queue.push({ x: nx, y: ny, dist: dist + 1 });
            }
          }
        }
      }
    }

    return reachable;
  };

  const selectedUnit = selectedUnitId ? units.find(u => u.id === selectedUnitId) : null;
  const reachableCells = (selectedUnit && isMyTurn && multiSelectedIds.length <= 1 && !sKeyHeld) ? getReachableTiles(selectedUnit) : [];

  const cells = [];
  for (let y = 0; y < boardRows; y++) {
    for (let x = 0; x < boardCols; x++) {
      cells.push({
        x, y,
        terrain: getTerrain(x, y),
        occupyingUnit: unitPositionsMap[`${x},${y}`],
        isNorthLoc: isCellInLoc(x, y, 'North'),
        isSouthLoc: isCellInLoc(x, y, 'South'),
        isReachable: reachableCells.includes(`${x},${y}`)
      });
    }
  }

  const getStackOrientation = () => {
    const activeAttackers = units.filter(u => multiSelectedIds.includes(u.id));
    if (activeAttackers.length < 2) return null;

    const sorted = [...activeAttackers].sort((a, b) => a.x !== b.x ? a.x - b.x : a.y - b.y);
    const dx = sorted[1].x - sorted[0].x;
    const dy = sorted[1].y - sorted[0].y;

    if (Math.abs(dx) > 1 || Math.abs(dy) > 1 || (dx === 0 && dy === 0)) return null;

    for (let i = 1; i < sorted.length; i++) {
      if ((sorted[i].x - sorted[i - 1].x) !== dx || (sorted[i].y - sorted[i - 1].y) !== dy) {
        return null;
      }
    }
    return { stepX: dx, stepY: dy, sorted };
  };

  const stackOrientation = getStackOrientation();

  const isEnemyInAttackRange = (cellX, cellY) => {
    const targetUnit = unitPositionsMap[`${cellX},${cellY}`];
    if (!targetUnit || targetUnit.side === turn) return false;
    if (attackExecuted) return false;

    if (stackOrientation) {
      const { stepX, stepY, sorted } = stackOrientation;
      const first = sorted[0];
      const crossProduct = (cellY - first.y) * stepX - (cellX - first.x) * stepY;
      if (crossProduct !== 0) return false;

      let head = null;
      let minDistance = Infinity;
      for (const u of sorted) {
        if (!connectedUnitIds.includes(u.id)) continue; // Disconnected units cannot attack
        const dist = Math.max(Math.abs(u.x - cellX), Math.abs(u.y - cellY));
        if (dist < minDistance) {
          minDistance = dist;
          head = u;
        }
      }

      if (!head) return false;
      const headRange = head.type?.toLowerCase() === 'artillery' ? 3 : (head.type?.toLowerCase() === 'relay' ? 0 : 2);
      return checkLineOfSight(head.x, head.y, cellX, cellY, headRange);
    } else if (selectedUnitId) {
      if (!connectedUnitIds.includes(selectedUnitId)) return false; // Disconnected unit cannot attack
      const origin = units.find(u => u.id === selectedUnitId);
      if (!origin) return false;

      const maxRange = origin.type?.toLowerCase() === 'artillery' ? 3 : (origin.type?.toLowerCase() === 'relay' ? 0 : 2);
      return checkLineOfSight(origin.x, origin.y, cellX, cellY, maxRange);
    }
    return false;
  };

  const getUnitLiveStats = (unit) => {
    if (!unit) return null;
    const base = UNIT_PROFILES[unit.type.toLowerCase()] || { attack: 10, defense: 10, label: "Asset" };
    const isConnected = connectedUnitIds.includes(unit.id);

    return {
      ...base,
      attack: isConnected ? base.attack : 0,
      currentDefense: isConnected ? base.defense : 0,
      isConnected
    };
  };

  // Sidebar Scoreboard calculations tracking baseline configuration arrays
  const northActive = units.filter(u => u.side === 'North').length;
  const southActive = units.filter(u => u.side === 'South').length;
  const northDead = INITIAL_UNITS.filter(u => u.side === 'North').length - northActive;
  const southDead = INITIAL_UNITS.filter(u => u.side === 'South').length - southActive;

  const activeAttackers = units.filter(u => multiSelectedIds.includes(u.id));
  const totalAttackPower = activeAttackers.reduce((sum, u) => {
    const stats = getUnitLiveStats(u);
    return sum + (stats?.attack || 0);
  }, 0);
  const totalDefensePower = activeAttackers.reduce((sum, u) => {
    const stats = getUnitLiveStats(u);
    return sum + (stats?.currentDefense || 0);
  }, 0);

  const hoveredUnit = hoveredCell ? unitPositionsMap[`${hoveredCell.x},${hoveredCell.y}`] : null;
  const hoveredStats = getUnitLiveStats(hoveredUnit);

  const debordPortrait = new URL('./assets/guy_debord.jpg', import.meta.url).href;
  const heroImage = new URL('./assets/hero.png', import.meta.url).href;

  if (inLobby) {
    return (
      <Lobby
        gameMode={gameMode}
        setGameMode={setGameMode}
        playerName={playerName}
        setPlayerName={setPlayerName}
        roomName={roomName}
        setRoomName={setRoomName}
        roomPassword={roomPassword}
        setRoomPassword={setRoomPassword}
        errorMessage={errorMessage}
        handleConnectToRoom={handleConnectToRoom}
        debordPortrait={debordPortrait}
        isConnecting={isConnecting}
        playerSide={playerSide}
        setPlayerSide={setPlayerSide}
        layoutType={layoutType}
        setLayoutType={setLayoutType}
      />
    );
  }

  const isSinglePlayer = gameMode === 'single';
  const isAiVsAi = gameMode === 'ai_vs_ai';

  const activeMySide = mySide || (players.South === playerName ? 'South' : 'North');
  const opponentSide = activeMySide === 'North' ? 'South' : 'North';

  const myName = isAiVsAi ? "🤖 AI_NORTH" : (players[activeMySide] ?? playerName);
  const opponentName = isAiVsAi ? (activeMySide === 'North' ? '🤖 AI_SOUTH' : '🤖 AI_NORTH') : (players[opponentSide] ?? (isSinglePlayer ? '🤖 CPU_TACTICIAN' : 'Awaiting Commander...'));

  // WIN SCREEN OVERLAY
  if (winner) {
    const winnerName = players[winner] ?? (winner === opponentSide && isSinglePlayer ? '🤖 CPU_TACTICIAN' : winner);
    const isMyWin = winner === activeMySide;
    const winColor = winner === 'North' ? '#002fa7' : '#991b1b';

    return (
      <div style={{ ...styles.container, justifyContent: 'center', minHeight: '100vh' }}>
        <div style={{
          display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '24px',
          padding: '60px 40px', backgroundColor: '#ffffff',
          border: '1px solid #002fa7', borderRadius: '12px',
          boxShadow: '0 4px 20px rgba(0, 47, 167, 0.08)',
          maxWidth: '520px', width: '100%', textAlign: 'center',
          color: '#002fa7', boxSizing: 'border-box'
        }}>
          <div style={{ fontSize: '11px', color: '#475569', letterSpacing: '3px', fontWeight: 'bold' }}>
            CAMPAIGN CONCLUDED
          </div>
          <div style={{ fontSize: '32px', fontWeight: 'bold', letterSpacing: '4px', color: winColor }}>
            {winner.toUpperCase()} VICTORIOUS
          </div>
          <div style={{ fontSize: '14px', color: '#475569' }}>
            Commander <span style={{ color: winColor, fontWeight: 'bold' }}>{winnerName}</span> has won the battle
          </div>

          <div style={{ display: 'flex', gap: '24px', marginTop: '8px', fontSize: '12px', color: '#475569', justifyContent: 'center', width: '100%' }}>
            <div>
              <div style={{ color: '#002fa7', fontWeight: 'bold', marginBottom: '2px' }}>NORTH</div>
              <div>Active: {units.filter(u => u.side === 'North').length}</div>
              <div style={{ color: '#991b1b', fontWeight: 'bold' }}>Lost: {INITIAL_UNITS.filter(u => u.side === 'North').length - units.filter(u => u.side === 'North').length}</div>
            </div>
            <div style={{ width: '1px', backgroundColor: '#002fa7' }} />
            <div>
              <div style={{ color: '#991b1b', fontWeight: 'bold', marginBottom: '2px' }}>SOUTH</div>
              <div>Active: {units.filter(u => u.side === 'South').length}</div>
              <div style={{ color: '#991b1b', fontWeight: 'bold' }}>Lost: {INITIAL_UNITS.filter(u => u.side === 'South').length - units.filter(u => u.side === 'South').length}</div>
            </div>
          </div>

          <button
            onClick={() => handleAction('restart')}
            style={{ marginTop: '8px', backgroundColor: '#002fa7', border: 'none', color: '#ffffff', padding: '12px 32px', borderRadius: '6px', fontSize: '13px', fontWeight: 'bold', cursor: 'pointer', letterSpacing: '2px', fontFamily: 'monospace' }}
          >
            ⚔ DEPLOY AGAIN
          </button>
        </div>
      </div>
    );
  }

  // LAZARUS CHOICE POPUP OVERLAY
  let lazarusChoiceOverlay = null;
  if (awaitingLazarusChoice) {
    const isMyChoice = awaitingLazarusChoice.side === activeMySide;
    if (isMyChoice) {
      const choices = [
        { sym: 'I', name: 'Infantry', desc: 'Standard combat unit' },
        { sym: 'A', name: 'Artillery', desc: 'Ranged support' },
        { sym: 'C', name: 'Cavalry', desc: 'Fast slides' },
        { sym: 'R', name: 'Relay', desc: 'Supply network' },
        { sym: 'M', name: 'Mine Creator', desc: 'Leaves landmines' },
        { sym: 'S', name: 'Shield / Mirror', desc: 'Attack immune' }
      ];
      lazarusChoiceOverlay = (
        <div style={{
          position: 'fixed', inset: 0, backgroundColor: 'rgba(0,0,0,0.65)',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          zIndex: 9999, backdropFilter: 'blur(4px)'
        }}>
          <div style={{
            backgroundColor: '#ffffff', border: '2px solid #06b6d4', borderRadius: '12px',
            boxShadow: '0 8px 32px rgba(6, 182, 212, 0.25)', padding: '32px 24px',
            maxWidth: '480px', width: '90%', boxSizing: 'border-box', textAlign: 'center', color: '#0f172a'
          }}>
            <div style={{ fontSize: '11px', color: '#06b6d4', letterSpacing: '4px', fontWeight: 'bold', marginBottom: '8px' }}>
              LAZARUS PIT ACTIVE
            </div>
            <div style={{ fontSize: '20px', fontWeight: 'bold', letterSpacing: '1px', marginBottom: '16px' }}>
              RESHAPE CUBE IDENTITY
            </div>
            <p style={{ fontSize: '13px', color: '#475569', marginBottom: '24px' }}>
              Select a tactical symbol to rotate to the top face:
            </p>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: '12px' }}>
              {choices.map(c => (
                <button
                  key={c.sym}
                  onClick={() => {
                    if (socket && socket.readyState === WebSocket.OPEN) {
                      socket.send(JSON.stringify({
                        action: 'choose_lazarus_face',
                        symbol: c.sym
                      }));
                    }
                  }}
                  style={{
                    display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '4px',
                    padding: '12px 6px', border: '1px solid #e2e8f0', borderRadius: '8px',
                    backgroundColor: '#f8fafc', cursor: 'pointer', boxSizing: 'border-box'
                  }}
                >
                  <span style={{ fontSize: '20px', fontWeight: 'bold', fontFamily: 'monospace', color: '#0891b2' }}>{c.sym}</span>
                  <span style={{ fontSize: '11px', fontWeight: 'bold', color: '#0f172a' }}>{c.name}</span>
                  <span style={{ fontSize: '9px', color: '#64748b' }}>{c.desc}</span>
                </button>
              ))}
            </div>
          </div>
        </div>
      );
    } else {
      lazarusChoiceOverlay = (
        <div style={{
          position: 'fixed', inset: 0, backgroundColor: 'rgba(0,0,0,0.5)',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          zIndex: 9999, backdropFilter: 'blur(3px)'
        }}>
          <div style={{
            backgroundColor: '#ffffff', border: '1px solid #475569', borderRadius: '8px',
            padding: '24px', maxWidth: '360px', width: '90%', boxSizing: 'border-box', textAlign: 'center', color: '#0f172a'
          }}>
            <div style={{ fontSize: '11px', color: '#64748b', letterSpacing: '2px', fontWeight: 'bold', marginBottom: '8px' }}>
              COMMUNICATIONS INTERCEPT
            </div>
            <div style={{ fontSize: '15px', fontWeight: 'bold', marginBottom: '12px' }}>
              OPPONENT RESHAPING CUBE
            </div>
            <p style={{ fontSize: '12px', color: '#64748b', margin: 0 }}>
              Waiting for commander to choose a face in the Lazarus Pit...
            </p>
          </div>
        </div>
      );
    }
  }

  return (
    <div style={styles.container}>
      {lazarusChoiceOverlay}
      {/* HEADER PANELS - Structurally height locked to stop layout shifting */}
      <div style={styles.header}>
        <div style={styles.headerTitleSection}>
          <h1 style={styles.title}>LE JEU DE LA GUERRE</h1>
          {gameMode === 'multi' && (
            <div style={styles.sharePanel}>
              <span style={{ color: '#64748b' }}>DISPATCH LINK:</span>
              <input readOnly value={roomUrl} onClick={(e) => { e.target.select(); document.execCommand('copy'); }} style={styles.linkInput} />
            </div>
          )}
        </div>

        <div style={styles.identityPanel}>
          <div style={{ ...styles.playerTag, borderColor: activeMySide === 'North' ? '#002fa7' : '#991b1b' }}>
            <span style={{ fontSize: '9px', color: '#475569' }}>YOU</span>
            <span style={{ color: activeMySide === 'North' ? '#002fa7' : '#991b1b', fontWeight: 'bold', fontSize: '13px' }}>{myName}</span>
          </div>
          <span style={{ color: '#002fa7', fontSize: '12px', alignSelf: 'center' }}>VS</span>
          <div style={{ ...styles.playerTag, borderColor: opponentSide === 'North' ? '#002fa7' : '#991b1b' }}>
            <span style={{ fontSize: '9px', color: '#475569' }}>OPPONENT</span>
            <span style={{ color: opponentSide === 'North' ? '#002fa7' : '#991b1b', fontWeight: 'bold', fontSize: '13px' }}>{opponentName}</span>
          </div>
        </div>
        <div style={styles.controlPanel}>
          <button onClick={handleExitToLobby} style={{ ...styles.fixedBtn, borderColor: '#991b1b', color: '#991b1b' }}>EXIT</button>
          <button onClick={() => handleAction('undo')} disabled={!canUndo || !isMyTurn} style={{ ...styles.fixedBtn, opacity: (canUndo && isMyTurn) ? 1 : 0.3 }}>UNDO</button>
          <button onClick={() => handleAction('restart')} style={styles.fixedBtn}>RESTART</button>
          <div style={{ ...styles.statusBadge, borderColor: turn === 'North' ? '#002fa7' : '#991b1b' }}>
            TURN: <span style={{ color: turn === 'North' ? '#002fa7' : '#991b1b' }}>{players[turn] ? players[turn].toUpperCase() : turn.toUpperCase()}</span>
          </div>
          <div style={styles.metricsBadge}>MOVES: <span style={styles.HighlightText}>{movesLeft}/5</span></div>
          <div style={styles.metricsBadge}>
            ATTACK: <span style={{ color: attackExecuted ? '#991b1b' : '#10b981', fontWeight: 'bold' }}>{attackExecuted ? "USED" : "READY"}</span>
          </div>
          <button onClick={() => handleAction('end_turn')} disabled={!isMyTurn} style={{ ...styles.endTurnButton, opacity: isMyTurn ? 1 : 0.4 }}>END TURN</button>
        </div>
      </div>
      {isAiVsAi ? (
        <div style={styles.waitingBanner}>🛰️ SIMULATION ACTIVE: OBSERVING {turn.toUpperCase()} TACTICAL MATRIX...</div>
      ) : (
        !isMyTurn && <div style={styles.waitingBanner}>{isSinglePlayer ? "🤖 AI CALCULATING ASSAULT VECTORS..." : `⏳ AWAITING OPPONENT...`}</div>
      )}
      {errorMessage && <div style={{ ...styles.errorAlert, backgroundColor: errorMessage.includes('Success') || errorMessage.includes('eliminated') || errorMessage.includes('repelled') ? '#d1fae5' : '#fee2e2', borderColor: errorMessage.includes('Success') || errorMessage.includes('eliminated') || errorMessage.includes('repelled') ? '#10b981' : '#fca5a5', color: errorMessage.includes('Success') || errorMessage.includes('eliminated') || errorMessage.includes('repelled') ? '#065f46' : '#991b1b' }}>📡 SYSTEM LOG: {errorMessage}</div>}

      {/* TWO-COLUMN SIDEBAR INTERFACE WRAPPER */}
      <div style={styles.workspaceLayout}>

        {/* SIDEBAR STATUS REPORT PANEL */}
        <div style={styles.sidebarPanel}>
          <div style={{ fontWeight: 'bold', color: '#002fa7', fontSize: '12px', marginBottom: '10px', letterSpacing: '1px' }}>📊 BATTLEFIELD REPORT</div>
          <div style={styles.sidebarDivider} />

          <div style={styles.factionStatsBlock}>
            <div style={{ color: '#002fa7', fontWeight: 'bold', fontSize: '11px', marginBottom: '4px' }}>🔴 NORTH FORCES</div>
            <div style={styles.statRow}><span style={styles.statLabel}>ACTIVE:</span><span style={{ color: '#002fa7', fontWeight: 'bold' }}>{northActive}</span></div>
            <div style={styles.statRow}><span style={styles.statLabel}>CASUALTIES:</span><span style={{ color: '#991b1b', fontWeight: 'bold' }}>💀 {northDead}</span></div>
          </div>

          <div style={{ ...styles.sidebarDivider, margin: '14px 0' }} />

          <div style={styles.factionStatsBlock}>
            <div style={{ color: '#991b1b', fontWeight: 'bold', fontSize: '11px', marginBottom: '4px' }}>🔵 SOUTH FORCES</div>
            <div style={styles.statRow}><span style={styles.statLabel}>ACTIVE:</span><span style={{ color: '#991b1b', fontWeight: 'bold' }}>{southActive}</span></div>
            <div style={styles.statRow}><span style={styles.statLabel}>CASUALTIES:</span><span style={{ color: '#991b1b', fontWeight: 'bold' }}>💀 {southDead}</span></div>
          </div>

          <div style={{ ...styles.sidebarDivider, margin: '14px 0' }} />

          {/* ── RULES / INTEL TOGGLE ── */}
          <button
            onClick={() => setShowRules(true)}
            style={{ width: '100%', background: '#ffffff', border: '1px solid #002fa7', color: '#002fa7', padding: '6px 8px', borderRadius: '4px', fontSize: '10px', cursor: 'pointer', fontFamily: 'monospace', letterSpacing: '1px', marginBottom: '12px', fontWeight: 'bold' }}
          >
            📋 FIELD MANUAL
          </button>

          {/* Radar Intel panel inside sidebar */}
          <div style={{
            backgroundColor: '#ffffff',
            border: '1px solid #002fa7',
            borderRadius: '4px',
            padding: '10px',
            fontSize: '10px',
            color: '#002fa7',
            marginTop: '4px'
          }}>
            <div style={{ fontWeight: 'bold', color: '#002fa7', marginBottom: '6px', fontSize: '10px', borderBottom: '1px solid #002fa7', paddingBottom: '4px' }}>📡 RADAR INTEL</div>

            {multiSelectedIds.length > 0 ? (
              (() => {
                const selectedUnits = units.filter(u => multiSelectedIds.includes(u.id));
                const firstUnit = selectedUnits[0];
                const isFriendlyGroup = firstUnit && firstUnit.side === activeMySide;
                const groupColor = isFriendlyGroup ? '#002fa7' : '#991b1b';

                return (
                  <div>
                    <div style={{ color: groupColor, fontWeight: 'bold', fontSize: '11px', marginBottom: '4px' }}>
                      {isFriendlyGroup
                        ? (multiSelectedIds.length === 1 ? "FRIENDLY UNIT SELECTION" : "FRIENDLY GROUP TELEMETRY")
                        : (multiSelectedIds.length === 1 ? "ENEMY UNIT TELEMETRY" : "ENEMY GROUP TELEMETRY")
                      }
                    </div>
                    <div style={{ fontSize: '10px', color: '#475569', display: 'flex', flexDirection: 'column', gap: '3px' }}>
                      <div>DIVISIONS: <span style={{ color: groupColor, fontWeight: 'bold' }}>{multiSelectedIds.length}</span></div>
                      <div>GROUP ATK: <span style={{ color: groupColor, fontWeight: 'bold' }}>{totalAttackPower}</span></div>
                      <div>GROUP DEF: <span style={{ color: groupColor, fontWeight: 'bold' }}>{totalDefensePower}</span></div>

                      {multiSelectedIds.length > 1 && (
                        <div style={{
                          fontWeight: 'bold',
                          marginTop: '2px',
                          color: stackOrientation ? '#10b981' : groupColor
                        }}>
                          {stackOrientation ? "✓ ALIGNED STACK (COMBINED FIRE)" : "✓ CONNECTED SHAPE GROUP"}
                        </div>
                      )}
                    </div>

                    {isFriendlyGroup && hoveredUnit && hoveredUnit.side !== turn && (
                      <div style={{ marginTop: '6px', paddingTop: '4px', borderTop: '1px solid #cbd5e1', fontSize: '9px' }}>
                        <div style={{ fontWeight: 'bold', color: hoveredUnit.side === 'North' ? '#002fa7' : '#991b1b', marginBottom: '2px' }}>
                          TARGET: {hoveredStats.label} [{hoveredUnit.symbol}] (DEF: {hoveredStats.currentDefense})
                        </div>
                        <div style={{ fontWeight: 'bold' }}>
                          {totalAttackPower - hoveredStats.currentDefense >= 2 ? (
                            <span style={{ color: '#10b981' }}>✓ DESTROY CONFIRMED</span>
                          ) : totalAttackPower - hoveredStats.currentDefense === 1 ? (
                            <span style={{ color: '#f59e0b' }}>↩ PUSH TO RETREAT</span>
                          ) : (
                            <span style={{ color: '#ef4444' }}>✗ ATTACK REPELLED</span>
                          )}
                        </div>
                      </div>
                    )}
                  </div>
                );
              })()
            ) : hoveredUnit ? (
              <div>
                <div style={{ color: hoveredUnit.side === 'North' ? '#002fa7' : '#991b1b', fontWeight: 'bold', fontSize: '11px', marginBottom: '4px' }}>
                  {hoveredStats.label} [{hoveredUnit.symbol}]
                </div>
                <div style={{ fontSize: '10px', color: '#475569', display: 'flex', flexDirection: 'column', gap: '3px' }}>
                  <div>ATK: <span style={{ color: '#002fa7', fontWeight: 'bold' }}>{hoveredStats.attack}</span></div>
                  <div>DEF: <span style={{ color: '#002fa7', fontWeight: 'bold' }}>{hoveredStats.currentDefense}</span></div>
                  <div style={{ color: hoveredStats.isConnected ? '#002fa7' : '#991b1b', fontWeight: 'bold', marginTop: '2px' }}>
                    {hoveredStats.isConnected ? "✓ SUPPLY CONNECTED" : "✗ OUT OF SUPPLY"}
                  </div>
                </div>
                <div style={{ marginTop: '10px', paddingTop: '6px', borderTop: '1px dashed #cbd5e1', fontSize: '9px', color: '#64748b', fontStyle: 'italic', lineHeight: '1.4' }}>
                  {hoveredUnit.side === turn ? (
                    "💡 Hold X + Click to view group stats, or Hold S + Click to form an attacking stack (add Shift to select connected groups)."
                  ) : (
                    "💡 Hold Z + Click to view enemy group stats (add Shift to select connected groups)."
                  )}
                </div>
              </div>
            ) : (
              <div style={{ color: '#64748b', fontStyle: 'italic', fontSize: '10px' }}>Radar scanning... Hover over a division to analyze telemetry.</div>
            )}
          </div>
        </div>

        {/* INTERACTIVE WAR MAP GRID */}
        <div style={{ display: 'flex', flexDirection: 'column', flexGrow: 1 }}>
          {/* Top column numbers (0 to 24) */}
          <div style={{ display: 'flex', alignItems: 'center', marginBottom: '4px' }}>
            <div style={{ width: '24px', minWidth: '24px' }} /> {/* Spacer matching left column width */}
            <div style={{
              flexGrow: 1,
              display: 'grid',
              gridTemplateColumns: `repeat(${boardCols}, minmax(0, 1fr))`,
              gap: '1px',
              padding: '0 8px',
              boxSizing: 'border-box'
            }}>
              {Array.from({ length: boardCols }).map((_, i) => (
                <div key={i} style={{ display: 'flex', justifyContent: 'center', fontSize: '9px', color: '#002fa7', opacity: 0.4, fontWeight: 'bold' }}>
                  {i}
                </div>
              ))}
            </div>
          </div>

          {/* Row numbers and Grid */}
          <div style={{ display: 'flex', flexGrow: 1, alignItems: 'stretch' }}>
            {/* Left row numbers (0 to 19) */}
            <div style={{
              width: '24px',
              minWidth: '24px',
              display: 'grid',
              gridTemplateRows: `repeat(${boardRows}, minmax(0, 1fr))`,
              gap: '1px',
              padding: '8px 0',
              boxSizing: 'border-box',
              alignItems: 'center'
            }}>
              {Array.from({ length: boardRows }).map((_, i) => (
                <div key={i} style={{ display: 'flex', justifyContent: 'center', fontSize: '9px', color: '#002fa7', opacity: 0.4, fontWeight: 'bold' }}>
                  {i}
                </div>
              ))}
            </div>

            {/* 3D Perspective Wrap */}
            <div className="grid-3d-perspective" style={{ width: '100%' }}>
              <div
                ref={gridRef}
                className="grid-3d-board"
                style={{
                  ...styles.gridContainer,
                  gridTemplateColumns: `repeat(${boardCols}, minmax(0, 1fr))`,
                  maxWidth: boardCols === 10 ? '550px' : '100%',
                  margin: boardCols === 10 ? '0 auto' : '0'
                }}
              >
                {/* Animated projectile dots */}
                {tracers.map(t => (
                  <div
                    key={t.id}
                    className="projectile-dot"
                    style={{
                      width: `${t.size}px`,
                      height: `${t.size}px`,
                      backgroundColor: t.color,
                      boxShadow: `0 0 8px ${t.color}, 0 0 3px #fff`,
                      '--px0': `${t.x1}px`,
                      '--py0': `${t.y1}px`,
                      '--px1': `${t.x2}px`,
                      '--py1': `${t.y2}px`,
                      '--dur': t.dur
                    }}
                  />
                ))}

                {cells.map(({ x, y, terrain, occupyingUnit, isNorthLoc, isSouthLoc, isReachable }) => {
                  const isSelected = occupyingUnit && occupyingUnit.id === selectedUnitId;
                  const isMultiSelected = occupyingUnit && multiSelectedIds.includes(occupyingUnit.id);
                  const isUnitConnected = occupyingUnit && connectedUnitIds.includes(occupyingUnit.id);
                  const inRange = isEnemyInAttackRange(x, y);
                  const tileKey = `${x},${y}`;
                  const residue = graveyardTiles[tileKey];
                  const hasResidue = residue && residue.count > 0;
                  const isFlashing = killFlash && killFlash.x === x && killFlash.y === y;
                  const isRepelling = repelFlash && repelFlash.x === x && repelFlash.y === y;

                  const isLazarusPit = lazarusPits.some(([px, py]) => px === x && py === y);
                  const hasMine = mines.some(m => m.x === x && m.y === y);

                  let cellClass = "";
                  if (isSelected) {
                    cellClass = "cell-selected-active";
                  } else if (isMultiSelected) {
                    const isFriendly = occupyingUnit.side === activeMySide;
                    if (isFriendly) {
                      cellClass = stackOrientation ? "cell-selected-multi-stack" : "cell-selected-multi-shape";
                    } else {
                      cellClass = stackOrientation ? "cell-selected-enemy-stack" : "cell-selected-enemy";
                    }
                  } else if (isReachable) {
                    cellClass = "cell-reachable";
                  } else if (inRange) {
                    cellClass = "cell-attack-range";
                  } else if (isLazarusPit) {
                    cellClass = "cell-lazarus-pit";
                  }

                  return (
                    <div
                      key={`${x}-${y}`}
                      data-coord={tileKey}
                      className={`cell-3d ${cellClass}`}
                      onClick={() => handleCellClick(x, y)}
                      onMouseEnter={() => setHoveredCell({ x, y })}
                      onMouseLeave={() => setHoveredCell(null)}
                      style={{
                        ...styles.cell,
                        backgroundColor: inRange ? 'rgba(239, 68, 68, 0.15)' : (isReachable ? 'rgba(16, 185, 129, 0.15)' : terrain.color),
                        border: inRange ? '2px solid #ef4444' : (isReachable ? '2px solid #10b981' : (terrain.border || '1px solid #cbd5e1')),
                        boxShadow: inRange ? 'inset 0 0 10px rgba(239, 68, 68, 0.15)' : (isReachable ? 'inset 0 0 10px rgba(16, 185, 129, 0.15)' : 'none'),
                        cursor: isMyTurn ? 'pointer' : 'default',
                        transformStyle: 'preserve-3d'
                      }}
                    >
                      {/* Kill flash bloom */}
                      {isFlashing && <div className="kill-flash" />}
                      {isRepelling && <div className={repelFlash.result === "RETREAT" ? "repel-flash-amber" : "repel-flash-blue"} />}

                      {/* Skull on graveyard tile (behind live unit if reoccupied) */}
                      {hasResidue && (
                        <span
                          className="skull-marker"
                          style={{
                            filter: residue.side === 'North'
                              ? 'drop-shadow(0 0 3px #002fa7) sepia(100%) hue-rotate(190deg) saturate(300%)'
                              : 'drop-shadow(0 0 3px #991b1b) sepia(100%) hue-rotate(330deg) saturate(300%)'
                          }}
                        >
                          💀
                        </span>
                      )}

                      {hasMine && <div className="mine-marker" />}

                      {!occupyingUnit && (isNorthLoc || isSouthLoc) && (
                        <div style={{ ...styles.locDot, backgroundColor: isNorthLoc && isSouthLoc ? '#6b21a8' : isNorthLoc ? '#002fa7' : '#991b1b' }} />
                      )}

                      {isLazarusPit && !occupyingUnit && (
                        <span style={{ position: 'absolute', top: '50%', left: '50%', transform: 'translate(-50%, -50%) translateZ(4px)', fontSize: '11px', opacity: 0.8 }}>🌀</span>
                      )}

                      <span style={{ ...styles.terrainLabel, color: '#002fa7', opacity: 0.3 }}>{terrain.label}</span>
                    </div>
                  );
                })}

                {/* 3D absolute-positioned units overlay with transitions */}
                {units.filter(u => u.x < 10 && u.y < 10).map(unit => {
                  const x = unit.x;
                  const y = unit.y;
                  const isSelected = unit.id === selectedUnitId;
                  const isMultiSelected = multiSelectedIds.includes(unit.id);
                  const isUnitConnected = connectedUnitIds.includes(unit.id);
                  const isMoving = movingUnitId === unit.id;
                  const isHovered = hoveredCell && hoveredCell.x === x && hoveredCell.y === y;
                  const hasShield = repelShieldUnitId === unit.id;

                  // Lunge offsets during attack/ramming animations (in board percentages)
                  const lunge = lungingUnitIds[unit.id];
                  const dx = lunge ? lunge.dx : 0;
                  const dy = lunge ? lunge.dy : 0;

                  const isRolling = rollingUnitId === unit.id;
                  const faces = delayedFaces[unit.id] || unit.faces;
                  const isShieldUnit = faces?.top === 'S';

                  return (
                    <div
                      key={unit.id}
                      className="absolute-unit-wrapper"
                      style={{
                        left: `calc(${x * 10}% + ${dx * 10}%)`,
                        top: `calc(${y * 10}% + ${dy * 10}%)`
                      }}
                    >
                      <div
                        className={`cube-container ${isSelected || isMultiSelected || isHovered ? 'lifted' : ''} ${isMoving ? 'moving' : ''} ${isRolling ? `roll-${rollDirection}` : ''}`}
                        onClick={() => handleCellClick(x, y)}
                        onMouseEnter={() => setHoveredCell({ x, y })}
                        onMouseLeave={() => setHoveredCell(null)}
                      >
                        {/* Top Face */}
                        <div
                          className={`cube-face cube-face-top ${hasShield || isShieldUnit ? 'magical-shield-face' : ''}`}
                          style={{
                            backgroundColor: unit.side === 'North'
                              ? (isUnitConnected ? '#002fa7' : 'rgba(0, 47, 167, 0.22)')
                              : (isUnitConnected ? '#991b1b' : 'rgba(153, 27, 27, 0.22)'),
                            color: isUnitConnected ? '#ffffff' : 'rgba(255, 255, 255, 0.5)',
                            border: isUnitConnected ? '1.5px solid rgba(255, 255, 255, 0.6)' : '1px dashed rgba(255, 255, 255, 0.35)'
                          }}
                        >
                          {faces?.top || unit.symbol}
                        </div>
                        {/* Front Face */}
                        <div
                          className={`cube-face cube-face-front ${hasShield || isShieldUnit ? 'magical-shield-face' : ''}`}
                          style={{
                            backgroundColor: unit.side === 'North'
                              ? (isUnitConnected ? '#002687' : 'rgba(0, 38, 135, 0.18)')
                              : (isUnitConnected ? '#7f1d1d' : 'rgba(127, 29, 29, 0.18)'),
                            color: isUnitConnected ? '#ffffff' : 'rgba(255, 255, 255, 0.5)',
                            border: isUnitConnected ? '1px solid rgba(255, 255, 255, 0.2)' : '1px dashed rgba(255, 255, 255, 0.15)'
                          }}
                        >
                          {faces?.front || 'C'}
                        </div>
                        {/* Right Face */}
                        <div
                          className={`cube-face cube-face-right ${hasShield || isShieldUnit ? 'magical-shield-face' : ''}`}
                          style={{
                            backgroundColor: unit.side === 'North'
                              ? (isUnitConnected ? '#001a5e' : 'rgba(0, 26, 94, 0.18)')
                              : (isUnitConnected ? '#5c1414' : 'rgba(92, 20, 20, 0.18)'),
                            color: isUnitConnected ? '#ffffff' : 'rgba(255, 255, 255, 0.5)',
                            border: isUnitConnected ? '1px solid rgba(255, 255, 255, 0.2)' : '1px dashed rgba(255, 255, 255, 0.15)'
                          }}
                        >
                          {faces?.right || 'A'}
                        </div>
                        {/* Left Face */}
                        <div
                          className={`cube-face cube-face-left ${hasShield || isShieldUnit ? 'magical-shield-face' : ''}`}
                          style={{
                            backgroundColor: unit.side === 'North'
                              ? (isUnitConnected ? '#00227a' : 'rgba(0, 34, 122, 0.18)')
                              : (isUnitConnected ? '#8c1f1f' : 'rgba(140, 31, 31, 0.18)'),
                            color: isUnitConnected ? '#ffffff' : 'rgba(255, 255, 255, 0.5)',
                            border: isUnitConnected ? '1px solid rgba(255, 255, 255, 0.2)' : '1px dashed rgba(255, 255, 255, 0.15)'
                          }}
                        >
                          {faces?.left || 'I'}
                        </div>
                        {/* Back Face */}
                        <div
                          className={`cube-face cube-face-back ${hasShield || isShieldUnit ? 'magical-shield-face' : ''}`}
                          style={{
                            backgroundColor: unit.side === 'North'
                              ? (isUnitConnected ? '#002cb0' : 'rgba(0, 44, 176, 0.18)')
                              : (isUnitConnected ? '#b22424' : 'rgba(178, 36, 36, 0.18)'),
                            color: isUnitConnected ? '#ffffff' : 'rgba(255, 255, 255, 0.5)',
                            border: isUnitConnected ? '1px solid rgba(255, 255, 255, 0.2)' : '1px dashed rgba(255, 255, 255, 0.15)'
                          }}
                        >
                          {faces?.back || 'R'}
                        </div>
                        {/* Bottom Face */}
                        <div
                          className={`cube-face cube-face-bottom ${hasShield || isShieldUnit ? 'magical-shield-face' : ''}`}
                          style={{
                            backgroundColor: unit.side === 'North'
                              ? (isUnitConnected ? '#00124a' : 'rgba(0, 18, 74, 0.18)')
                              : (isUnitConnected ? '#4a0b0b' : 'rgba(74, 11, 11, 0.18)'),
                            color: isUnitConnected ? '#ffffff' : 'rgba(255, 255, 255, 0.5)',
                            border: isUnitConnected ? '1px solid rgba(255, 255, 255, 0.2)' : '1px dashed rgba(255, 255, 255, 0.15)'
                          }}
                        >
                          {faces?.bottom || 'A'}
                        </div>
                      </div>
                      {/* Dynamic Drop Shadow */}
                      <div
                        className="cube-shadow"
                        style={{
                          opacity: isUnitConnected ? 1 : 0.3
                        }}
                      />
                    </div>
                  );
                })}

                {/* 3D absolute-positioned dying units disintegration overlay */}
                {dyingUnits.map(unit => {
                  const x = unit.x;
                  const y = unit.y;
                  const isDisintegrating = unit.phase === 'disintegrating';

                  return (
                    <div
                      key={`dying-${unit.id}`}
                      className="absolute-unit-wrapper"
                      style={{
                        left: `${x * 10}%`,
                        top: `${y * 10}%`
                      }}
                    >
                      <div
                        className={`cube-container ${isDisintegrating ? 'disintegrating' : ''}`}
                        style={{
                          filter: 'opacity(0.85)'
                        }}
                      >
                        {/* Top Face */}
                        <div
                          className="cube-face cube-face-top"
                          style={{
                            backgroundColor: unit.side === 'North' ? '#002fa7' : '#991b1b',
                            border: '1.5px solid rgba(255, 255, 255, 0.6)'
                          }}
                        >
                          {unit.symbol}
                        </div>
                        {/* Front Face */}
                        <div
                          className="cube-face cube-face-front"
                          style={{
                            backgroundColor: unit.side === 'North' ? '#002687' : '#7f1d1d',
                            border: '1px solid rgba(255, 255, 255, 0.2)'
                          }}
                        />
                        {/* Right Face */}
                        <div
                          className="cube-face cube-face-right"
                          style={{
                            backgroundColor: unit.side === 'North' ? '#001a5e' : '#5c1414',
                            border: '1px solid rgba(255, 255, 255, 0.2)'
                          }}
                        />
                        {/* Left Face */}
                        <div
                          className="cube-face cube-face-left"
                          style={{
                            backgroundColor: unit.side === 'North' ? '#00227a' : '#8c1f1f',
                            border: '1px solid rgba(255, 255, 255, 0.2)'
                          }}
                        />
                        {/* Back Face */}
                        <div
                          className="cube-face cube-face-back"
                          style={{
                            backgroundColor: unit.side === 'North' ? '#002cb0' : '#b22424',
                            border: '1px solid rgba(255, 255, 255, 0.2)'
                          }}
                        />
                      </div>
                      <div className="cube-shadow" style={{ opacity: isDisintegrating ? 0 : 0.4, transition: 'opacity 0.6s ease' }} />
                    </div>
                  );
                })}
              </div>
            </div>
          </div>
        </div>
      </div>
      {/* RULES BOOK MODAL OVERLAY */}
      {showRules && (
        <div
          onClick={() => setShowRules(false)}
          style={{
            position: 'fixed',
            inset: 0,
            backgroundColor: 'rgba(0, 47, 167, 0.4)',
            backdropFilter: 'blur(3px)',
            zIndex: 1000,
            display: 'flex',
            justifyContent: 'center',
            alignItems: 'center',
            padding: '20px'
          }}
        >
          <div
            onClick={(e) => e.stopPropagation()}
            style={{
              backgroundColor: '#ffffff',
              border: '2px solid #002fa7',
              borderRadius: '8px',
              padding: '30px',
              maxWidth: '640px',
              width: '100%',
              maxHeight: '85vh',
              overflowY: 'auto',
              display: 'flex',
              flexDirection: 'column',
              gap: '16px',
              position: 'relative',
              boxShadow: '0 8px 30px rgba(0, 47, 167, 0.2)',
              textAlign: 'left'
            }}
          >
            <button
              onClick={() => setShowRules(false)}
              style={{
                position: 'absolute',
                top: '16px',
                right: '16px',
                border: '1px solid #002fa7',
                background: 'transparent',
                color: '#002fa7',
                cursor: 'pointer',
                padding: '4px 10px',
                fontSize: '10px',
                fontWeight: 'bold',
                fontFamily: 'monospace',
                borderRadius: '4px'
              }}
            >
              CLOSE
            </button>
            <h2 style={{ fontSize: '14px', letterSpacing: '2px', color: '#002fa7', margin: '0 0 8px 0', borderBottom: '2px solid #002fa7', paddingBottom: '6px', fontWeight: 'bold' }}>
              TACTICAL FIELD MANUAL (RULES)
            </h2>
            <RulesBook />
          </div>
        </div>
      )}
    </div>
  );
}

const styles = {
  container: { backgroundColor: '#fdfbe6', minHeight: '100vh', color: '#002fa7', fontFamily: 'monospace', display: 'flex', flexDirection: 'column', alignItems: 'center', padding: '16px' },
  lobbyCard: { backgroundColor: '#ffffff', border: '1px solid #002fa7', borderRadius: '6px', padding: '30px', width: '100%', maxWidth: '400px', marginTop: '100px' },
  lobbyTitle: { fontSize: '20px', letterSpacing: '2px', textAlign: 'center', margin: '0 0 4px 0', color: '#002fa7' },
  lobbySubtitle: { fontSize: '10px', color: '#002fa7', textAlign: 'center', margin: '0 0 16px 0' },
  toggleContainer: { display: 'flex', backgroundColor: '#fdfbe6', border: '1px solid #002fa7', borderRadius: '4px', padding: '2px', marginBottom: '16px' },
  toggleBtn: { flex: 1, border: 'none', padding: '8px', fontSize: '10px', fontFamily: 'monospace', borderRadius: '3px', cursor: 'pointer' },
  lobbyError: { backgroundColor: '#fee2e2', color: '#b91c1c', padding: '8px', borderRadius: '4px', fontSize: '11px', marginBottom: '12px' },
  form: { display: 'flex', flexDirection: 'column', gap: '14px' },
  inputGroup: { display: 'flex', flexDirection: 'column', gap: '4px' },
  label: { fontSize: '9px', color: '#002fa7', fontWeight: 'bold' },
  input: { backgroundColor: '#fdfbe6', border: '1px solid #002fa7', borderRadius: '4px', color: '#002fa7', padding: '8px 12px', fontSize: '12px', fontFamily: 'monospace', outline: 'none' },
  lobbyButton: { backgroundColor: '#ffffff', border: '1px solid #002fa7', color: '#002fa7', padding: '10px', borderRadius: '4px', fontSize: '12px', fontWeight: 'bold', cursor: 'pointer' },

  header: { width: '100%', maxWidth: '1280px', minHeight: '62px', display: 'flex', flexWrap: 'wrap', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px', borderBottom: '1px solid #002fa7', paddingBottom: '12px', gap: '16px', boxSizing: 'border-box' },
  headerTitleSection: { display: 'flex', flexDirection: 'column' },
  title: { fontSize: '18px', letterSpacing: '2px', color: '#002fa7', margin: 0, lineHeight: '1.2', fontWeight: 'bold', whiteSpace: 'nowrap' },
  sharePanel: { display: 'flex', alignItems: 'center', gap: '6px', marginTop: '2px', fontSize: '10px', color: '#002fa7' },
  linkInput: { backgroundColor: '#ffffff', border: '1px solid #002fa7', color: '#002fa7', padding: '2px 6px', borderRadius: '4px', width: '150px', fontSize: '10px', outline: 'none' },
  identityPanel: { display: 'flex', gap: '8px', alignItems: 'center', flexWrap: 'wrap', justifyContent: 'center' },
  playerTag: { display: 'flex', flexDirection: 'column', backgroundColor: '#ffffff', border: '1px solid', borderRadius: '4px', padding: '6px 12px', minWidth: '110px', boxSizing: 'border-box', justifyContent: 'center', alignItems: 'center', textAlign: 'center' },
  controlPanel: { display: 'flex', gap: '8px', alignItems: 'center', flexWrap: 'wrap', justifyContent: 'flex-end' },

  // Fixed button formatting dimensions
  fixedBtn: { backgroundColor: '#ffffff', border: '1px solid #002fa7', color: '#002fa7', width: '80px', height: '34px', borderRadius: '4px', cursor: 'pointer', fontSize: '11px', fontWeight: 'bold', display: 'inline-flex', alignItems: 'center', justifyContent: 'center' },
  statusBadge: { backgroundColor: '#ffffff', border: '1px solid', width: '150px', height: '34px', borderRadius: '4px', fontSize: '11px', fontWeight: 'bold', display: 'inline-flex', alignItems: 'center', justifyContent: 'center', boxSizing: 'border-box', whiteSpace: 'nowrap' },
  metricsBadge: { backgroundColor: '#ffffff', border: '1px solid #002fa7', width: '110px', height: '34px', borderRadius: '4px', fontSize: '11px', color: '#002fa7', display: 'inline-flex', alignItems: 'center', justifyContent: 'center', boxSizing: 'border-box', whiteSpace: 'nowrap' },
  HighlightText: { color: '#002fa7', fontWeight: 'bold' },
  endTurnButton: { backgroundColor: '#002fa7', border: '1px solid #002fa7', color: '#ffffff', width: '95px', height: '34px', borderRadius: '4px', fontSize: '11px', fontWeight: 'bold', cursor: 'pointer', display: 'inline-flex', alignItems: 'center', justifyContent: 'center' },

  errorAlert: { width: '100%', maxWidth: '1280px', border: '1px solid', color: '#b91c1c', padding: '8px 12px', borderRadius: '4px', marginBottom: '10px', fontSize: '12px', boxSizing: 'border-box' },
  waitingBanner: { width: '100%', maxWidth: '1280px', backgroundColor: '#ffffff', border: '1px solid #002fa7', color: '#002fa7', padding: '6px', borderRadius: '4px', marginBottom: '10px', fontSize: '11px', textAlign: 'center', boxSizing: 'border-box' },

  // Split view design linking grid layout and sidebar status tracking
  workspaceLayout: { display: 'flex', width: '100%', maxWidth: '1280px', gap: '16px', alignItems: 'flex-start' },
  sidebarPanel: { width: '240px', minWidth: '240px', backgroundColor: '#ffffff', border: '1px solid #002fa7', borderRadius: '6px', padding: '14px', boxSizing: 'border-box', color: '#002fa7' },
  sidebarDivider: { height: '1px', backgroundColor: '#002fa7', width: '100%', margin: '8px 0' },
  factionStatsBlock: { display: 'flex', flexDirection: 'column' },
  statRow: { display: 'flex', justifyContent: 'space-between', fontSize: '11px', marginTop: '4px' },
  statLabel: { color: '#475569' },

  gridContainer: { position: 'relative', flexGrow: 1, display: 'grid', gridTemplateColumns: 'repeat(25, minmax(0, 1fr))', gap: '1px', backgroundColor: '#cbd5e1', padding: '8px', borderRadius: '6px', border: '1px solid #cbd5e1' },
  cell: { position: 'relative', aspectRatio: '1', display: 'flex', alignItems: 'center', justifyContent: 'center', userSelect: 'none', transition: 'background-color 0.15s ease' },
  unitBadge: { width: '80%', height: '80%', display: 'flex', alignItems: 'center', justifyContent: 'center', borderRadius: '3px', border: '2px solid', fontWeight: 'bold', fontSize: '12px', zIndex: 2 },
  locDot: { position: 'absolute', top: '50%', left: '50%', transform: 'translate(-50%, -50%)', width: '8px', height: '8px', borderRadius: '50%', zIndex: 1, opacity: 1, boxShadow: '0 0 3px rgba(0,0,0,0.3)' },
  terrainLabel: { fontSize: '9px', opacity: 0.2 },
  coords: { position: 'absolute', bottom: '1px', right: '1px', fontSize: '4.5px', color: '#002fa7', opacity: 0.3 },

  floatingHud: { position: 'fixed', bottom: '16px', right: '16px', backgroundColor: 'rgba(255, 255, 255, 0.95)', border: '1px solid #002fa7', color: '#002fa7', borderRadius: '6px', padding: '10px', width: '180px', fontSize: '10px', zIndex: 100, boxShadow: '0 4px 12px rgba(0,2,200,0.1)' }
};
