import React from "react";
import { useCurrentFrame, useVideoConfig, spring, interpolate } from "remotion";
import { theme } from "../theme";

export const Entrance: React.FC<{
  delay?: number;
  direction?: "up" | "down" | "none";
  distance?: number;
  children: React.ReactNode;
  style?: React.CSSProperties;
}> = ({ delay = 0, direction = "up", distance = 40, children, style }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const p = spring({
    frame: frame - delay,
    fps,
    config: theme.spring.smooth,
  });

  const translateY =
    direction === "none"
      ? 0
      : direction === "up"
      ? interpolate(p, [0, 1], [distance, 0])
      : interpolate(p, [0, 1], [-distance, 0]);

  return (
    <div
      style={{
        opacity: p,
        transform: `translateY(${translateY}px) scale(${interpolate(p, [0, 1], [0.96, 1])})`,
        ...style,
      }}
    >
      {children}
    </div>
  );
};

export const WordReveal: React.FC<{
  text: string;
  delay?: number;
  perWordFrames?: number;
  style?: React.CSSProperties;
  wordStyle?: React.CSSProperties;
  highlightWords?: string[];
  highlightColor?: string;
}> = ({
  text,
  delay = 0,
  perWordFrames = 3,
  style,
  wordStyle,
  highlightWords = [],
  highlightColor = theme.colors.primary,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const words = text.split(" ");

  return (
    <div
      style={{
        display: "flex",
        flexWrap: "wrap",
        gap: "0.28em",
        ...style,
      }}
    >
      {words.map((word, i) => {
        const p = spring({
          frame: frame - delay - i * perWordFrames,
          fps,
          config: theme.spring.snappy,
        });

        const isHighlighted = highlightWords.some(
          (hw) => word.toLowerCase().includes(hw.toLowerCase())
        );

        return (
          <span
            key={i}
            style={{
              display: "inline-block",
              opacity: p,
              transform: `translateY(${interpolate(p, [0, 1], [24, 0])}px)`,
              color: isHighlighted ? highlightColor : "inherit",
              fontWeight: isHighlighted ? 700 : "inherit",
              ...wordStyle,
            }}
          >
            {word}
          </span>
        );
      })}
    </div>
  );
};

export const AnimatedCounter: React.FC<{
  target: number;
  delay?: number;
  prefix?: string;
  suffix?: string;
  decimals?: number;
  style?: React.CSSProperties;
}> = ({ target, delay = 0, prefix = "", suffix = "", decimals = 0, style }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const p = spring({
    frame: frame - delay,
    fps,
    config: { damping: 24, stiffness: 80, mass: 1 },
  });

  const value = interpolate(p, [0, 1], [0, target], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  return (
    <span
      style={{
        fontVariantNumeric: "tabular-nums",
        fontFeatureSettings: '"tnum"',
        fontFamily: theme.fonts.mono,
        ...style,
      }}
    >
      {prefix}
      {value.toLocaleString("en-US", {
        minimumFractionDigits: decimals,
        maximumFractionDigits: decimals,
      })}
      {suffix}
    </span>
  );
};

export const Badge: React.FC<{
  text: string;
  color?: string;
  bg?: string;
  icon?: string;
  delay?: number;
}> = ({
  text,
  color = theme.colors.primary,
  bg = "rgba(245, 158, 11, 0.12)",
  icon = "●",
  delay = 0,
}) => {
  return (
    <Entrance delay={delay} direction="down" distance={15}>
      <div
        style={{
          display: "inline-flex",
          alignItems: "center",
          gap: 8,
          padding: "6px 14px",
          borderRadius: 999,
          backgroundColor: bg,
          border: `1px solid ${color}40`,
          color: color,
          fontSize: 14,
          fontFamily: theme.fonts.mono,
          fontWeight: 600,
          letterSpacing: "0.08em",
          textTransform: "uppercase",
        }}
      >
        <span style={{ fontSize: 10 }}>{icon}</span>
        {text}
      </div>
    </Entrance>
  );
};
