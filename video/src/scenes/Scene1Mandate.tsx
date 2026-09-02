import React from "react";
import { AbsoluteFill, useCurrentFrame, useVideoConfig, interpolate } from "remotion";
import { theme } from "../theme";
import { Entrance, WordReveal, Badge } from "../components/Motion";

export const Scene1Mandate: React.FC = () => {
  const frame = useCurrentFrame();
  const { durationInFrames } = useVideoConfig();

  // Scene exit transition
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
        padding: "0 100px",
        fontFamily: theme.fonts.display,
        color: theme.colors.text,
      }}
    >
      {/* Top Header Badge */}
      <div style={{ marginBottom: 24 }}>
        <Badge
          text="ALPACA HACKATHON 2026 · AUTONOMOUS AGENT"
          color={theme.colors.primary}
          bg="rgba(245, 158, 11, 0.12)"
          icon="⚡"
          delay={5}
        />
      </div>

      {/* Main Hero Title */}
      <Entrance delay={12} distance={30}>
        <h1
          style={{
            fontSize: 76,
            fontWeight: 900,
            margin: "0 0 12px 0",
            letterSpacing: "-0.03em",
            textAlign: "center",
            background: `linear-gradient(135deg, #FFFFFF 30%, ${theme.colors.primary} 100%)`,
            WebkitBackgroundClip: "text",
            WebkitTextFillColor: "transparent",
            textShadow: `0 0 40px ${theme.colors.primaryGlow}`,
          }}
        >
          CaiSheng 财神
        </h1>
      </Entrance>

      {/* Subtitle */}
      <Entrance delay={22} distance={20}>
        <div
          style={{
            fontSize: 28,
            color: theme.colors.accentCyan,
            fontFamily: theme.fonts.mono,
            letterSpacing: "0.04em",
            marginBottom: 48,
            textAlign: "center",
          }}
        >
          Autonomous Options-Volatility Capital Allocator
        </div>
      </Entrance>

      {/* Mandate Hero Metrics Cards */}
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "1fr 1fr 1fr",
          gap: 32,
          width: "100%",
          maxWidth: 1280,
          marginBottom: 40,
        }}
      >
        {/* Card 1: Starting NAV */}
        <Entrance delay={32} distance={35}>
          <div
            style={{
              backgroundColor: theme.colors.bgCard,
              border: `1px solid ${theme.colors.bgCardBorder}`,
              borderRadius: 20,
              padding: "28px 32px",
              boxShadow: "0 20px 40px rgba(0,0,0,0.5)",
              position: "relative",
              overflow: "hidden",
            }}
          >
            <div
              style={{
                fontSize: 14,
                fontFamily: theme.fonts.mono,
                color: theme.colors.textMuted,
                letterSpacing: "0.06em",
                textTransform: "uppercase",
                marginBottom: 10,
              }}
            >
              Competition Baseline
            </div>
            <div style={{ fontSize: 44, fontWeight: 800, color: theme.colors.accentGreen }}>
              $100,000.00
            </div>
            <div
              style={{
                fontSize: 13,
                color: theme.colors.textDim,
                fontFamily: theme.fonts.mono,
                marginTop: 8,
              }}
            >
              Immutable SQLite Mandate NAV
            </div>
          </div>
        </Entrance>

        {/* Card 2: Strategic Edge */}
        <Entrance delay={42} distance={35}>
          <div
            style={{
              backgroundColor: theme.colors.bgCard,
              border: `1px solid ${theme.colors.bgCardBorder}`,
              borderRadius: 20,
              padding: "28px 32px",
              boxShadow: "0 20px 40px rgba(0,0,0,0.5)",
            }}
          >
            <div
              style={{
                fontSize: 14,
                fontFamily: theme.fonts.mono,
                color: theme.colors.textMuted,
                letterSpacing: "0.06em",
                textTransform: "uppercase",
                marginBottom: 10,
              }}
            >
              Alpha Thesis
            </div>
            <div style={{ fontSize: 40, fontWeight: 800, color: theme.colors.primary }}>
              Non-Directional
            </div>
            <div
              style={{
                fontSize: 13,
                color: theme.colors.textDim,
                fontFamily: theme.fonts.mono,
                marginTop: 8,
              }}
            >
              Long Straddle vs Short Iron Fly
            </div>
          </div>
        </Entrance>

        {/* Card 3: Execution Safety */}
        <Entrance delay={52} distance={35}>
          <div
            style={{
              backgroundColor: theme.colors.bgCard,
              border: `1px solid ${theme.colors.bgCardBorder}`,
              borderRadius: 20,
              padding: "28px 32px",
              boxShadow: "0 20px 40px rgba(0,0,0,0.5)",
            }}
          >
            <div
              style={{
                fontSize: 14,
                fontFamily: theme.fonts.mono,
                color: theme.colors.textMuted,
                letterSpacing: "0.06em",
                textTransform: "uppercase",
                marginBottom: 10,
              }}
            >
              Risk Posture
            </div>
            <div style={{ fontSize: 40, fontWeight: 800, color: theme.colors.accentCyan }}>
              FAIL CLOSED
            </div>
            <div
              style={{
                fontSize: 13,
                color: theme.colors.textDim,
                fontFamily: theme.fonts.mono,
                marginTop: 8,
              }}
            >
              20-Point Deterministic Gate
            </div>
          </div>
        </Entrance>
      </div>

      {/* Kinetic Statement */}
      <WordReveal
        text="CaiSheng does not predict direction. It measures volatility mispricing and can abstain."
        delay={65}
        perWordFrames={3}
        style={{
          fontSize: 22,
          color: theme.colors.textMuted,
          justifyContent: "center",
          maxWidth: 900,
          textAlign: "center",
        }}
        highlightWords={["volatility", "mispricing", "abstain."]}
        highlightColor={theme.colors.primary}
      />
    </AbsoluteFill>
  );
};
