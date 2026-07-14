import React, { useState } from 'react';
import RulesBook from './RulesBook';

export default function Lobby({
  gameMode,
  setGameMode,
  playerName,
  setPlayerName,
  roomName,
  setRoomName,
  roomPassword,
  setRoomPassword,
  errorMessage,
  handleConnectToRoom,
  debordPortrait,
  isConnecting,
  playerSide,
  setPlayerSide,
  layoutType,
  setLayoutType
}) {

  return (
    <div style={{
      backgroundColor: '#fdfbe6',
      minHeight: '100vh',
      color: '#002fa7',
      fontFamily: 'monospace',
      display: 'flex',
      flexDirection: 'column',
      alignItems: 'center',
      justifyContent: 'center',
      padding: '24px 16px',
      boxSizing: 'border-box'
    }}>
      <div style={{
        display: 'flex',
        flexDirection: 'row',
        flexWrap: 'wrap',
        gap: '32px',
        justifyContent: 'center',
        alignItems: 'stretch',
        width: '100%',
        maxWidth: '1200px',
        boxSizing: 'border-box'
      }}>
        {/* LEFT COLUMN: Launcher & About Section */}
        <div style={{
          flex: '1 1 450px',
          maxWidth: '520px',
          display: 'flex',
          flexDirection: 'column',
          gap: '24px',
          boxSizing: 'border-box'
        }}>
          {/* LAUNCHER CARD */}
          <div style={{
            backgroundColor: '#ffffff',
            border: '1px solid #002fa7',
            borderRadius: '6px',
            padding: '24px 28px',
            width: '100%',
            boxSizing: 'border-box',
            display: 'flex',
            flexDirection: 'column',
            justifyContent: 'space-between'
          }}>
            <div>
              <h1 style={{ fontSize: '26px', letterSpacing: '4px', color: '#002fa7', fontWeight: '800', margin: '0 0 4px 0', textAlign: 'center' }}>LE JEU DE LA GUERRE</h1>
              <p style={{ fontSize: '11px', color: '#475569', letterSpacing: '1px', marginBottom: '24px', textAlign: 'center', margin: '0 0 24px 0' }}>GUY DEBORD'S STRATEGIC KRIEGSPIEL</p>

              <div style={{
                display: 'flex',
                backgroundColor: '#fdfbe6',
                border: '1px solid #002fa7',
                borderRadius: '4px',
                padding: '2px',
                marginBottom: '20px'
              }}>
                <button type="button" onClick={() => setGameMode('single')} style={{ flex: 1, border: 'none', padding: '8px', fontSize: '9px', fontFamily: 'monospace', borderRadius: '3px', cursor: 'pointer', letterSpacing: '1px', backgroundColor: gameMode === 'single' ? '#002fa7' : 'transparent', color: gameMode === 'single' ? '#ffffff' : '#002fa7', fontWeight: 'bold' }}>SINGLE PLAYER</button>
                <button type="button" onClick={() => setGameMode('multi')} style={{ flex: 1, border: 'none', padding: '8px', fontSize: '9px', fontFamily: 'monospace', borderRadius: '3px', cursor: 'pointer', letterSpacing: '1px', backgroundColor: gameMode === 'multi' ? '#002fa7' : 'transparent', color: gameMode === 'multi' ? '#ffffff' : '#002fa7', fontWeight: 'bold' }}>MULTIPLAYER</button>
                <button type="button" onClick={() => setGameMode('ai_vs_ai')} style={{ flex: 1, border: 'none', padding: '8px', fontSize: '9px', fontFamily: 'monospace', borderRadius: '3px', cursor: 'pointer', letterSpacing: '1px', backgroundColor: gameMode === 'ai_vs_ai' ? '#002fa7' : 'transparent', color: gameMode === 'ai_vs_ai' ? '#ffffff' : '#002fa7', fontWeight: 'bold' }}>AI VS AI</button>
              </div>

              {errorMessage && (
                <div style={{
                  backgroundColor: '#fee2e2',
                  color: '#b91c1c',
                  border: '1px solid #fca5a5',
                  padding: '8px',
                  borderRadius: '4px',
                  fontSize: '11px',
                  marginBottom: '12px'
                }}>{errorMessage}</div>
              )}

              <form onSubmit={handleConnectToRoom} style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                  <label style={{ fontSize: '9px', color: '#002fa7', fontWeight: 'bold' }}>TACTICAL CALLSIGN</label>
                  <input type="text" value={playerName} onChange={(e) => setPlayerName(e.target.value)} placeholder="Commander" style={{ backgroundColor: '#fdfbe6', border: '1px solid #002fa7', color: '#002fa7', borderRadius: '4px', padding: '8px 12px', fontSize: '12px', fontFamily: 'monospace', outline: 'none' }} required />
                </div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                  <label style={{ fontSize: '9px', color: '#002fa7', fontWeight: 'bold' }}>BOARD LAYOUT TEMPLATE</label>
                  <div style={{
                    display: 'flex',
                    backgroundColor: '#fdfbe6',
                    border: '1px solid #002fa7',
                    borderRadius: '4px',
                    padding: '2px'
                  }}>
                  <div style={{
                    display: 'flex',
                    backgroundColor: '#002fa7',
                    border: '1px solid #002fa7',
                    borderRadius: '4px',
                    padding: '8px',
                    justifyContent: 'center',
                    alignItems: 'center',
                    color: '#ffffff',
                    fontFamily: 'monospace',
                    fontSize: '10px',
                    fontWeight: 'bold'
                  }}>
                    SKIRMISH (10x10)
                  </div>
                  </div>
                </div>
                {gameMode === 'single' && (
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                    <label style={{ fontSize: '9px', color: '#002fa7', fontWeight: 'bold' }}>SELECT YOUR FORCES</label>
                    <div style={{
                      display: 'flex',
                      backgroundColor: '#fdfbe6',
                      border: '1px solid #002fa7',
                      borderRadius: '4px',
                      padding: '2px'
                    }}>
                      <button
                        type="button"
                        onClick={() => setPlayerSide('North')}
                        style={{
                          flex: 1, border: 'none', padding: '8px', fontSize: '9px',
                          fontFamily: 'monospace', borderRadius: '3px', cursor: 'pointer',
                          backgroundColor: playerSide === 'North' ? '#002fa7' : 'transparent',
                          color: playerSide === 'North' ? '#ffffff' : '#002fa7',
                          fontWeight: 'bold'
                        }}
                      >
                        🔵 NORTH (BLUE)
                      </button>
                      <button
                        type="button"
                        onClick={() => setPlayerSide('South')}
                        style={{
                          flex: 1, border: 'none', padding: '8px', fontSize: '9px',
                          fontFamily: 'monospace', borderRadius: '3px', cursor: 'pointer',
                          backgroundColor: playerSide === 'South' ? '#002fa7' : 'transparent',
                          color: playerSide === 'South' ? '#ffffff' : '#002fa7',
                          fontWeight: 'bold'
                        }}
                      >
                        🔴 SOUTH (RED)
                      </button>
                    </div>
                  </div>
                )}
                {gameMode === 'multi' && (
                  <>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                      <label style={{ fontSize: '9px', color: '#002fa7', fontWeight: 'bold' }}>THEATER ROOM ID</label>
                      <input type="text" value={roomName} onChange={(e) => setRoomName(e.target.value)} placeholder="sector-7" style={{ backgroundColor: '#fdfbe6', border: '1px solid #002fa7', color: '#002fa7', borderRadius: '4px', padding: '8px 12px', fontSize: '12px', fontFamily: 'monospace', outline: 'none' }} required />
                    </div>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                      <label style={{ fontSize: '9px', color: '#002fa7', fontWeight: 'bold' }}>ACCESS KEY</label>
                      <input type="password" value={roomPassword} onChange={(e) => setRoomPassword(e.target.value)} placeholder="••••••••" style={{ backgroundColor: '#fdfbe6', border: '1px solid #002fa7', color: '#002fa7', borderRadius: '4px', padding: '8px 12px', fontSize: '12px', fontFamily: 'monospace', outline: 'none' }} required />
                    </div>
                  </>
                )}
                <button
                  type="submit"
                  disabled={isConnecting}
                  style={{
                    backgroundColor: isConnecting ? '#475569' : '#002fa7',
                    color: '#ffffff',
                    border: '1px solid ' + (isConnecting ? '#475569' : '#002fa7'),
                    marginTop: '8px',
                    fontSize: '13px',
                    letterSpacing: '1px',
                    padding: '12px',
                    borderRadius: '4px',
                    fontWeight: 'bold',
                    cursor: isConnecting ? 'not-allowed' : 'pointer',
                    transition: 'all 0.15s ease'
                  }}
                >
                  {isConnecting ? 'ESTABLISHING SECURE PROTOCOLS...' : 'LAUNCH OPERATIONS'}
                </button>
              </form>
            </div>

            <div style={{ marginTop: '24px', borderTop: '1px solid #002fa7', paddingTop: '16px', fontSize: '10px', color: '#002fa7', textAlign: 'center' }}>
              • v1.0.0
            </div>
          </div>

          {/* ABOUT THE GAME CARD */}
          <div style={{
            backgroundColor: '#ffffff',
            border: '1px solid #002fa7',
            borderRadius: '6px',
            padding: '24px',
            boxSizing: 'border-box',
            textAlign: 'left'
          }}>
            <div style={{ display: 'flex', gap: '16px', alignItems: 'flex-start', marginBottom: '14px' }}>
              <img
                src={debordPortrait}
                alt="Guy Debord Portrait"
                style={{
                  width: '90px',
                  height: '115px',
                  objectFit: 'cover',
                  borderRadius: '4px',
                  border: '1px solid #002fa7',
                  backgroundColor: '#fdfbe6'
                }}
              />
              <div>
                <h2 style={{ fontSize: '13px', letterSpacing: '2px', color: '#002fa7', margin: '0 0 6px 0', borderBottom: '1px solid #002fa7', paddingBottom: '4px', fontWeight: 'bold' }}>ABOUT THE GAME</h2>
                <p style={{ fontSize: '10.5px', color: '#1e293b', lineHeight: '1.5', margin: 0 }}>
                  <strong>A Game of War</strong> (originally <em>Le Jeu de la Guerre</em>) is a digital implementation of the strategic Clausewitz simulator: board game designed by <strong>Guy Debord</strong> and <strong>Alice Becker-Ho</strong> in 1965 (originally published in 1987).
                </p>
              </div>
            </div>
            <p style={{ fontSize: '10px', color: '#1e293b', lineHeight: '1.4', margin: 0 }}>
              Guy Debord is celebrated as the chief strategist of the Situationist International and as the author of the searing critique of the media-saturated society of consumer capitalism: The Society of the Spectacle.

              What is much less well known is that after the May ’68 Revolution, Debord and his partner – Alice Becker-Ho – quit Paris and went to live in a remote French village. Over the next two decades, Debord devoted much of the rest of his life to inventing, refining and promoting what he came to regard as his most important project: The Game of War.

              For Debord, The Game of War wasn’t just a game – it was a guide to how people should live their lives within Fordist society. The Game of War is a Napoleonic-era military strategy game where armies must maintain their communications(supply lines) structure to survive and progress.
            </p>
          </div>
        </div>

        {/* RIGHT COLUMN: Interactive Rules Panel & Forces Table */}
        <div style={{
          backgroundColor: '#ffffff',
          border: '1px solid #002fa7',
          borderRadius: '6px',
          padding: '24px',
          flex: '1 1 500px',
          maxWidth: '620px',
          display: 'flex',
          flexDirection: 'column',
          gap: '12px',
          boxSizing: 'border-box',
          textAlign: 'left'
        }}>
          <h2 style={{ fontSize: '13px', letterSpacing: '2px', color: '#002fa7', margin: '0 0 8px 0', borderBottom: '2px solid #002fa7', paddingBottom: '6px', fontWeight: 'bold' }}>RULES OF THE GAME</h2>
          <RulesBook />
        </div>
      </div>
    </div>
  );
}
