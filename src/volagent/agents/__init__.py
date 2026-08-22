"""Multi-Agent specialist agents package."""

from volagent.agents.event_magnitude import run_event_magnitude_agent
from volagent.agents.explainer import generate_decision_explanation
from volagent.agents.long_vol import run_long_vol_advocate, run_short_vol_advocate
from volagent.agents.model_risk import run_model_risk_critic, validate_track_compliance
from volagent.agents.prompts import (
    EVENT_MAGNITUDE_PROMPT,
    LONG_VOL_ADVOCATE_PROMPT,
    MODEL_RISK_CRITIC_PROMPT,
    SHORT_VOL_ADVOCATE_PROMPT,
)

__all__ = [
    "run_event_magnitude_agent",
    "run_long_vol_advocate",
    "run_short_vol_advocate",
    "run_model_risk_critic",
    "validate_track_compliance",
    "generate_decision_explanation",
    "EVENT_MAGNITUDE_PROMPT",
    "LONG_VOL_ADVOCATE_PROMPT",
    "SHORT_VOL_ADVOCATE_PROMPT",
    "MODEL_RISK_CRITIC_PROMPT",
]
