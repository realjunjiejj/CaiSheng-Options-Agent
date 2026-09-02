import React from "react";
import { Composition, AbsoluteFill, Sequence } from "remotion";
import { BgMesh, Grade, Grain, Vignette } from "./components/Layers";
import { Scene1Mandate } from "./scenes/Scene1Mandate";
import { Scene2NeuroSymbolic } from "./scenes/Scene2NeuroSymbolic";
import { Scene3AlpacaLockbox } from "./scenes/Scene3AlpacaLockbox";
import { Scene4RiskGovernor } from "./scenes/Scene4RiskGovernor";
import { Scene5CommandCockpit } from "./scenes/Scene5CommandCockpit";

const MainPresentation: React.FC = () => {
  return (
    <AbsoluteFill style={{ backgroundColor: "#07090E" }}>
      {/* Layer 1: Atmospheric Background Mesh */}
      <BgMesh />

      {/* Layer 2 & 3: Master Choreography Scenes */}
      <Sequence from={0} durationInFrames={450} name="Scene 1 - The Mandate">
        <Scene1Mandate />
      </Sequence>

      <Sequence from={450} durationInFrames={600} name="Scene 2 - Neuro-Symbolic Debate">
        <Scene2NeuroSymbolic />
      </Sequence>

      <Sequence from={1050} durationInFrames={600} name="Scene 3 - Alpaca Lockbox">
        <Scene3AlpacaLockbox />
      </Sequence>

      <Sequence from={1650} durationInFrames={600} name="Scene 4 - Risk Governor">
        <Scene4RiskGovernor />
      </Sequence>

      <Sequence from={2250} durationInFrames={450} name="Scene 5 - Command Cockpit">
        <Scene5CommandCockpit />
      </Sequence>

      {/* Layer 4: Filmic Color Grade */}
      <Grade />

      {/* Layer 5: Procedural Film Grain & Vignette */}
      <Grain />
      <Vignette />
    </AbsoluteFill>
  );
};

export const Root: React.FC = () => {
  return (
    <Composition
      id="CaiShengJudgePitch"
      component={MainPresentation}
      durationInFrames={2700} // 90 seconds @ 30fps
      fps={30}
      width={1920}
      height={1080}
    />
  );
};
