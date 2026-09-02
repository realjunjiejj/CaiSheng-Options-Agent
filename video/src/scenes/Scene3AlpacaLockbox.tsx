import React from "react";
import { AbsoluteFill, useCurrentFrame, useVideoConfig, interpolate } from "remotion";
import { theme } from "../theme";
import { Entrance, WordReveal, Badge } from "../components/Motion";

export const Scene3AlpacaLockbox: React.FC = () => {
  const frame = useCurrentFrame();
  const { durationInFrames } = useVideoConfig();

  const exitOpacity = interpolate(
    frame,
    [durationInFrames - 15, durationInFrames],
    [1, 0],
    { extrapolateLeft: "clamp", extrapolateRight: "clamp" }
  );

  return (
    <AbsoluteFill
      style={{
        opacity: exitOpacity,
        display: "flex",
        flexDirection: "column",
        justifyContent: "center",
        alignItems: "center",
        padding: "0 80px",
        fontFamily: theme.fonts.display,
        color: theme.colors.text,
      }}
    >
      {/* Criterion Badge */}
      <div style={{ marginBottom: 16 }}>
        <Badge
          text="CRITERIA 2: TECHNOLOGY IMPLEMENTATION"
          color={theme.colors.accentCyan}
          bg="rgba(6, 182, 212, 0.12)"
          icon="⚙️"
          delay={5}
        />
      </div>

      <Entrance delay={10} distance={25}>
        <h2
          style={{
            fontSize: 54,
            fontWeight: 800,
            margin: "0 0 10px 0",
            letterSpacing: "-0.02em",
            textAlign: "center",
            background: `linear-gradient(135deg, #FFFFFF 40%, ${theme.colors.accentCyan} 100%)`,
            WebkitBackgroundClip: "text",
            WebkitTextFillColor: "transparent",
          }}
        >
          The Alpaca Technology Lockbox
        </h2>
      </Entrance>

      <Entrance delay={18} distance={15}>
        <div
          style={{
            fontSize: 20,
            color: theme.colors.textMuted,
            fontFamily: theme.fonts.mono,
            marginBottom: 44,
          }}
        >
          Full Official Alpaca Tooling Stack Backed by a Non-Bypassable Order Gateway
        </div>
      </Entrance>

      {/* 2x2 Technology Pillar Cards */}
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "1fr 1fr",
          gap: 24,
          width: "100%",
          maxWidth: 1280,
          marginBottom: 36,
        }}
      >
        {/* Pillar 1: Official CLI */}
        <Entrance delay={26} distance={25}>
          <div
            style={{
              backgroundColor: theme.colors.bgCard,
              border: `1px solid ${theme.colors.bgCardBorder}`,
              borderRadius: 16,
              padding: "24px 28px",
              boxShadow: "0 15px 35px rgba(0,0,0,0.4)",
            }}
          >
            <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 8 }}>
              <span style={{ fontSize: 22 }}>📟</span>
              <span style={{ fontSize: 18, fontWeight: 700, color: theme.colors.primary }}>
                Official Alpaca CLI
              </span>
            </div>
            <div style={{ fontSize: 13, fontFamily: theme.fonts.mono, color: theme.colors.textMuted }}>
              Runs <code>version</code>, <code>doctor</code>, <code>account get</code>, and <code>clock markets</code> to produce tamper-evident, sanitized preflight receipts with zero credential leaks.
            </div>
          </div>
        </Entrance>

        {/* Pillar 2: FastMCP Server V2 */}
        <Entrance delay={34} distance={25}>
          <div
            style={{
              backgroundColor: theme.colors.bgCard,
              border: `1px solid ${theme.colors.bgCardBorder}`,
              borderRadius: 16,
              padding: "24px 28px",
              boxShadow: "0 15px 35px rgba(0,0,0,0.4)",
            }}
          >
            <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 8 }}>
              <span style={{ fontSize: 22 }}>🔌</span>
              <span style={{ fontSize: 18, fontWeight: 700, color: theme.colors.accentCyan }}>
                Official FastMCP Server V2
              </span>
            </div>
            <div style={{ fontSize: 13, fontFamily: theme.fonts.mono, color: theme.colors.textMuted }}>
              Runs over stdio scoped to <code>assets,options-data</code>. The official MCP proof is read-only; CaiSheng's separate write gateway requires a canonical approved token.
            </div>
          </div>
        </Entrance>

        {/* Pillar 3: Official Alpaca Skills */}
        <Entrance delay={42} distance={25}>
          <div
            style={{
              backgroundColor: theme.colors.bgCard,
              border: `1px solid ${theme.colors.bgCardBorder}`,
              borderRadius: 16,
              padding: "24px 28px",
              boxShadow: "0 15px 35px rgba(0,0,0,0.4)",
            }}
          >
            <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 8 }}>
              <span style={{ fontSize: 22 }}>📦</span>
              <span style={{ fontSize: 18, fontWeight: 700, color: theme.colors.accentPurple }}>
                Official Agent Skills
              </span>
            </div>
            <div style={{ fontSize: 13, fontFamily: theme.fonts.mono, color: theme.colors.textMuted }}>
              Direct integration of <code>alpacahq/alpaca-skills</code>: backtest, paper-trading, CLI, and MCP skills locked with SHA-256 fingerprints in <code>skills-lock.json</code>.
            </div>
          </div>
        </Entrance>

        {/* Pillar 4: Level 3 MLeg API */}
        <Entrance delay={50} distance={25}>
          <div
            style={{
              backgroundColor: theme.colors.bgCard,
              border: `1px solid ${theme.colors.bgCardBorder}`,
              borderRadius: 16,
              padding: "24px 28px",
              boxShadow: "0 15px 35px rgba(0,0,0,0.4)",
            }}
          >
            <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 8 }}>
              <span style={{ fontSize: 22 }}>🔒</span>
              <span style={{ fontSize: 18, fontWeight: 700, color: theme.colors.accentGreen }}>
                Level-3 Multi-Leg Gateway
              </span>
            </div>
            <div style={{ fontSize: 13, fontFamily: theme.fonts.mono, color: theme.colors.textMuted }}>
              Exactly ONE file is permitted to call Alpaca submit-order. Constructs atomic multi-leg limit orders with position intents. Enforced by repository invariant tests.
            </div>
          </div>
        </Entrance>
      </div>

      {/* Footer Statement */}
      <WordReveal
        text="Official sponsor ecosystem for data and diagnostics. One auditable, policy-enforced gateway for execution."
        delay={60}
        perWordFrames={3}
        style={{
          fontSize: 18,
          color: theme.colors.textMuted,
          fontFamily: theme.fonts.mono,
          justifyContent: "center",
          textAlign: "center",
        }}
        highlightWords={["One", "auditable,", "gateway"]}
        highlightColor={theme.colors.primary}
      />
    </AbsoluteFill>
  );
};
