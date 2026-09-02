import React from "react";
import { AbsoluteFill, useCurrentFrame, useVideoConfig, interpolate } from "remotion";
import { theme } from "../theme";
import { Entrance, WordReveal, Badge } from "../components/Motion";

export const Scene2NeuroSymbolic: React.FC = () => {
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
          text="CRITERIA 3: CREATIVITY & ORIGINALITY"
          color={theme.colors.accentPurple}
          bg="rgba(139, 92, 246, 0.12)"
          icon="🧠"
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
            background: `linear-gradient(135deg, #FFFFFF 40%, ${theme.colors.accentPurple} 100%)`,
            WebkitBackgroundClip: "text",
            WebkitTextFillColor: "transparent",
          }}
        >
          Neuro-Symbolic Volatility Dialectic
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
          LangGraph Multi-Agent Debate ➔ Anchored to Alpaca Option-Implied Moves
        </div>
      </Entrance>

      {/* 3-Agent Dialectic Grid */}
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "1fr 1fr 1.15fr",
          gap: 24,
          width: "100%",
          maxWidth: 1360,
          marginBottom: 36,
        }}
      >
        {/* Agent 1: Long Vol */}
        <Entrance delay={28} distance={30}>
          <div
            style={{
              backgroundColor: theme.colors.bgCard,
              border: `1px solid rgba(16, 185, 129, 0.3)`,
              borderRadius: 18,
              padding: "26px 24px",
              boxShadow: "0 15px 35px rgba(0,0,0,0.4)",
            }}
          >
            <div
              style={{
                display: "flex",
                alignItems: "center",
                gap: 10,
                marginBottom: 14,
              }}
            >
              <span style={{ fontSize: 24 }}>📈</span>
              <span
                style={{
                  fontSize: 18,
                  fontWeight: 700,
                  color: theme.colors.accentGreen,
                }}
              >
                Long-Vol Advocate
              </span>
            </div>
            <div
              style={{
                fontSize: 14,
                fontFamily: theme.fonts.mono,
                color: theme.colors.textMuted,
                lineHeight: 1.6,
                marginBottom: 16,
              }}
            >
              • Catalysts: Earnings & FOMC events<br />
              • Models explosive tail distribution<br />
              • Targets: ATM Long Straddle<br />
              • Hard Cap: Debit ≤ $500 NAV
            </div>
            <div
              style={{
                padding: "8px 12px",
                borderRadius: 8,
                backgroundColor: "rgba(16, 185, 129, 0.1)",
                border: "1px solid rgba(16, 185, 129, 0.2)",
                fontSize: 12,
                fontFamily: theme.fonts.mono,
                color: theme.colors.accentGreen,
              }}
            >
              Candidate: LONG_STRADDLE
            </div>
          </div>
        </Entrance>

        {/* Agent 2: Short Vol */}
        <Entrance delay={38} distance={30}>
          <div
            style={{
              backgroundColor: theme.colors.bgCard,
              border: `1px solid rgba(245, 158, 11, 0.3)`,
              borderRadius: 18,
              padding: "26px 24px",
              boxShadow: "0 15px 35px rgba(0,0,0,0.4)",
            }}
          >
            <div
              style={{
                display: "flex",
                alignItems: "center",
                gap: 10,
                marginBottom: 14,
              }}
            >
              <span style={{ fontSize: 24 }}>📉</span>
              <span
                style={{
                  fontSize: 18,
                  fontWeight: 700,
                  color: theme.colors.primary,
                }}
              >
                Short-Vol Advocate
              </span>
            </div>
            <div
              style={{
                fontSize: 14,
                fontFamily: theme.fonts.mono,
                color: theme.colors.textMuted,
                lineHeight: 1.6,
                marginBottom: 16,
              }}
            >
              • Harvests post-earnings IV crush<br />
              • Models steep volatility surface<br />
              • Targets: Short Iron Butterfly<br />
              • Hard Cap: Defined wing width
            </div>
            <div
              style={{
                padding: "8px 12px",
                borderRadius: 8,
                backgroundColor: "rgba(245, 158, 11, 0.1)",
                border: "1px solid rgba(245, 158, 11, 0.2)",
                fontSize: 12,
                fontFamily: theme.fonts.mono,
                color: theme.colors.primary,
              }}
            >
              Candidate: SHORT_IRON_BUTTERFLY
            </div>
          </div>
        </Entrance>

        {/* Agent 3: Model-Risk Critic */}
        <Entrance delay={48} distance={30}>
          <div
            style={{
              backgroundColor: theme.colors.bgCard,
              border: `1px solid rgba(239, 68, 68, 0.35)`,
              borderRadius: 18,
              padding: "26px 24px",
              boxShadow: "0 15px 35px rgba(0,0,0,0.4)",
            }}
          >
            <div
              style={{
                display: "flex",
                alignItems: "center",
                gap: 10,
                marginBottom: 14,
              }}
            >
              <span style={{ fontSize: 24 }}>🛡️</span>
              <span
                style={{
                  fontSize: 18,
                  fontWeight: 700,
                  color: theme.colors.accentRed,
                }}
              >
                Model-Risk Critic
              </span>
            </div>
            <div
              style={{
                fontSize: 14,
                fontFamily: theme.fonts.mono,
                color: theme.colors.textMuted,
                lineHeight: 1.6,
                marginBottom: 16,
              }}
            >
              • Haircuts executable bid/ask spreads<br />
              • Evaluates out-of-distribution regimes<br />
              • Strict VETO authority over proposals<br />
              • Fail-Closed: Forces NO_TRADE if edge &lt; 2%
            </div>
            <div
              style={{
                padding: "8px 12px",
                borderRadius: 8,
                backgroundColor: "rgba(239, 68, 68, 0.12)",
                border: "1px solid rgba(239, 68, 68, 0.25)",
                fontSize: 12,
                fontFamily: theme.fonts.mono,
                color: "#FCA5A5",
                fontWeight: 600,
              }}
            >
              Independent Veto Gate: ACTIVE
            </div>
          </div>
        </Entrance>
      </div>

      {/* Synthesis Footnote */}
      <WordReveal
        text="Agent roles explain and challenge. Pricing, expected value, sizing, risk, and execution eligibility remain deterministic."
        delay={60}
        perWordFrames={3}
        style={{
          fontSize: 18,
          color: theme.colors.accentCyan,
          fontFamily: theme.fonts.mono,
          justifyContent: "center",
          textAlign: "center",
        }}
        highlightWords={["Pricing,", "risk,", "deterministic."]}
        highlightColor="#38BDF8"
      />
    </AbsoluteFill>
  );
};
