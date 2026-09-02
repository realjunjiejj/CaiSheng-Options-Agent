import React from "react";
import { AbsoluteFill, useCurrentFrame, useVideoConfig, interpolate } from "remotion";
import { theme } from "../theme";
import { Entrance, WordReveal, Badge } from "../components/Motion";

export const Scene5CommandCockpit: React.FC = () => {
  const frame = useCurrentFrame();
  const { durationInFrames } = useVideoConfig();

  const exitOpacity = interpolate(
    frame,
    [durationInFrames - 20, durationInFrames],
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
          text="CRITERIA 4: PRESENTATION & EXECUTION"
          color={theme.colors.primary}
          bg="rgba(245, 158, 11, 0.12)"
          icon="🏆"
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
            background: `linear-gradient(135deg, #FFFFFF 40%, ${theme.colors.primary} 100%)`,
            WebkitBackgroundClip: "text",
            WebkitTextFillColor: "transparent",
          }}
        >
          Capital Command Cockpit
        </h2>
      </Entrance>

      <Entrance delay={18} distance={15}>
        <div
          style={{
            fontSize: 20,
            color: theme.colors.textMuted,
            fontFamily: theme.fonts.mono,
            marginBottom: 40,
          }}
        >
          1-Minute Order Auditability · 345 Tests Passing · HMAC Autonomy Lease
        </div>
      </Entrance>

      {/* 4 Judging Criteria Scorecard Grid */}
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "1fr 1fr 1fr 1fr",
          gap: 18,
          width: "100%",
          maxWidth: 1360,
          marginBottom: 36,
        }}
      >
        {/* Box 1: P&L */}
        <Entrance delay={26} distance={20}>
          <div
            style={{
              backgroundColor: theme.colors.bgCard,
              border: `1px solid rgba(16, 185, 129, 0.3)`,
              borderRadius: 14,
              padding: "20px 18px",
              boxShadow: "0 10px 25px rgba(0,0,0,0.4)",
            }}
          >
            <div style={{ fontSize: 13, fontFamily: theme.fonts.mono, color: theme.colors.accentGreen, fontWeight: 700, marginBottom: 6 }}>
              1. P&L PERFORMANCE
            </div>
            <div style={{ fontSize: 13, color: theme.colors.textMuted, lineHeight: 1.5 }}>
              • $100k Fixed Mandate<br />
              • -$500 Kill-Switch<br />
              • 1% Drawdown Breaker<br />
              • Replay ≠ Live P&amp;L
            </div>
          </div>
        </Entrance>

        {/* Box 2: Tech */}
        <Entrance delay={34} distance={20}>
          <div
            style={{
              backgroundColor: theme.colors.bgCard,
              border: `1px solid rgba(6, 182, 212, 0.3)`,
              borderRadius: 14,
              padding: "20px 18px",
              boxShadow: "0 10px 25px rgba(0,0,0,0.4)",
            }}
          >
            <div style={{ fontSize: 13, fontFamily: theme.fonts.mono, color: theme.colors.accentCyan, fontWeight: 700, marginBottom: 6 }}>
              2. TECH STACK
            </div>
            <div style={{ fontSize: 13, color: theme.colors.textMuted, lineHeight: 1.5 }}>
              • Official Alpaca CLI<br />
              • FastMCP Server V2<br />
              • Official Agent Skills<br />
              • Level-3 MLeg Gateway
            </div>
          </div>
        </Entrance>

        {/* Box 3: Creativity */}
        <Entrance delay={42} distance={20}>
          <div
            style={{
              backgroundColor: theme.colors.bgCard,
              border: `1px solid rgba(139, 92, 246, 0.3)`,
              borderRadius: 14,
              padding: "20px 18px",
              boxShadow: "0 10px 25px rgba(0,0,0,0.4)",
            }}
          >
            <div style={{ fontSize: 13, fontFamily: theme.fonts.mono, color: theme.colors.accentPurple, fontWeight: 700, marginBottom: 6 }}>
              3. CREATIVITY
            </div>
            <div style={{ fontSize: 13, color: theme.colors.textMuted, lineHeight: 1.5 }}>
              • Non-Directional Vol<br />
              • LangGraph Dialectic<br />
              • Model-Risk Critic<br />
              • Implied Move Anchor
            </div>
          </div>
        </Entrance>

        {/* Box 4: Execution */}
        <Entrance delay={50} distance={20}>
          <div
            style={{
              backgroundColor: theme.colors.bgCard,
              border: `1px solid rgba(245, 158, 11, 0.3)`,
              borderRadius: 14,
              padding: "20px 18px",
              boxShadow: "0 10px 25px rgba(0,0,0,0.4)",
            }}
          >
            <div style={{ fontSize: 13, fontFamily: theme.fonts.mono, color: theme.colors.primary, fontWeight: 700, marginBottom: 6 }}>
              4. PRESENTATION
            </div>
            <div style={{ fontSize: 13, color: theme.colors.textMuted, lineHeight: 1.5 }}>
              • Streamlit Cockpit<br />
              • SHA-256 Decision Logs<br />
              • 345 Passing Tests<br />
              • 1-Click Receipts
            </div>
          </div>
        </Entrance>
      </div>

      {/* Hero Finale */}
      <WordReveal
        text="CaiSheng 财神 — The Autonomous Options Alpha Desk Built for Alpaca."
        delay={60}
        perWordFrames={3}
        style={{
          fontSize: 24,
          fontWeight: 700,
          color: theme.colors.primary,
          justifyContent: "center",
          textAlign: "center",
        }}
        highlightWords={["CaiSheng", "财神", "Options", "Alpha"]}
        highlightColor="#FBBF24"
      />
    </AbsoluteFill>
  );
};
