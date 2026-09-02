import React from "react";
import { AbsoluteFill, useCurrentFrame, useVideoConfig, interpolate } from "remotion";
import { theme } from "../theme";
import { Entrance, WordReveal, Badge } from "../components/Motion";

export const Scene4RiskGovernor: React.FC = () => {
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
          text="CRITERIA 1: P&L PERFORMANCE & GOVERNANCE"
          color={theme.colors.accentGreen}
          bg="rgba(16, 185, 129, 0.12)"
          icon="🛡️"
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
            background: `linear-gradient(135deg, #FFFFFF 40%, ${theme.colors.accentGreen} 100%)`,
            WebkitBackgroundClip: "text",
            WebkitTextFillColor: "transparent",
          }}
        >
          20-Point Deterministic Risk Governor
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
          Institutional Portfolio Protection & Uncompromised Economic Truth
        </div>
      </Entrance>

      {/* Grid of Risk Dimensions */}
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "1.1fr 1fr 1fr",
          gap: 24,
          width: "100%",
          maxWidth: 1320,
          marginBottom: 36,
        }}
      >
        {/* Box 1: Broker-Authoritative Risk Envelope */}
        <Entrance delay={26} distance={25}>
          <div
            style={{
              backgroundColor: theme.colors.bgCard,
              border: `1px solid rgba(245, 158, 11, 0.35)`,
              borderRadius: 16,
              padding: "24px 26px",
              boxShadow: "0 15px 35px rgba(0,0,0,0.4)",
            }}
          >
            <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 12 }}>
              <span style={{ fontSize: 20 }}>🚨</span>
              <span style={{ fontSize: 17, fontWeight: 700, color: theme.colors.primary }}>
                Risk Envelope
              </span>
            </div>
            <div style={{ fontSize: 13, fontFamily: theme.fonts.mono, color: theme.colors.textMuted, lineHeight: 1.6 }}>
              • <b>NORMAL</b>: Clean lineage & limits<br />
              • <b>LIQUIDATE_ONLY</b>: Untracked broker exposure detected; all new entries instantly blocked<br />
              • Two-Way SQLite Reconciliation matches broker positions to durable order intents.
            </div>
          </div>
        </Entrance>

        {/* Box 2: Mandate Hard Boundaries */}
        <Entrance delay={36} distance={25}>
          <div
            style={{
              backgroundColor: theme.colors.bgCard,
              border: `1px solid rgba(16, 185, 129, 0.3)`,
              borderRadius: 16,
              padding: "24px 26px",
              boxShadow: "0 15px 35px rgba(0,0,0,0.4)",
            }}
          >
            <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 12 }}>
              <span style={{ fontSize: 20 }}>📊</span>
              <span style={{ fontSize: 17, fontWeight: 700, color: theme.colors.accentGreen }}>
                Hard Boundaries
              </span>
            </div>
            <div style={{ fontSize: 13, fontFamily: theme.fonts.mono, color: theme.colors.textMuted, lineHeight: 1.6 }}>
              • <b>Trade Risk Cap</b>: ≤ 0.5% NAV ($500 max)<br />
              • <b>Daily Loss Halt</b>: -$500 threshold<br />
              • <b>Drawdown Breaker</b>: 1.0% from HWM<br />
              • <b>Concurrency</b>: Max 2 active strategies<br />
              • <b>Throttle</b>: Max 1 new entry per day
            </div>
          </div>
        </Entrance>

        {/* Box 3: Three-Tier Accounting Truth */}
        <Entrance delay={46} distance={25}>
          <div
            style={{
              backgroundColor: theme.colors.bgCard,
              border: `1px solid rgba(6, 182, 212, 0.3)`,
              borderRadius: 16,
              padding: "24px 26px",
              boxShadow: "0 15px 35px rgba(0,0,0,0.4)",
            }}
          >
            <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 12 }}>
              <span style={{ fontSize: 20 }}>⚖️</span>
              <span style={{ fontSize: 17, fontWeight: 700, color: theme.colors.accentCyan }}>
                Accounting Truth
              </span>
            </div>
            <div style={{ fontSize: 13, fontFamily: theme.fonts.mono, color: theme.colors.textMuted, lineHeight: 1.6 }}>
              • <b>Full Account P&L</b>: Live Alpaca equity minus $100k starting NAV<br />
              • <b>Governed P&L</b>: Completed lifecycles with verified entry & exit IDs<br />
              • <b>Replay P&L</b>: Sealed synthetic validation — never conflated with live.
            </div>
          </div>
        </Entrance>
      </div>

      {/* Footer Statement */}
      <WordReveal
        text="Integrity first: CaiSheng refuses to invent trades, hide losses, or bypass safety gates."
        delay={58}
        perWordFrames={3}
        style={{
          fontSize: 18,
          color: theme.colors.textMuted,
          fontFamily: theme.fonts.mono,
          justifyContent: "center",
          textAlign: "center",
        }}
        highlightWords={["refuses", "to", "invent", "trades,"]}
        highlightColor={theme.colors.accentRed}
      />
    </AbsoluteFill>
  );
};
