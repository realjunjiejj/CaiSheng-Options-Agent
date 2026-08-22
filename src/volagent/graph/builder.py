"""LangGraph workflow builder with parallel fan-out and fail-closed routing."""

from functools import partial
from typing import Any
from langgraph.graph import END, START, StateGraph

from volagent.config import VolAgentSettings, load_config
from volagent.domain.state import VolAgentState
from volagent.graph.nodes import (
    critic_and_compliance_node,
    event_magnitude_node,
    fetch_market_snapshot,
    forecast_node,
    initialize_run,
    long_vol_node,
    short_vol_node,
    strategy_and_risk_node,
    volatility_quant_node,
)


class VolAgentWorkflow:
    """Multi-Agent LangGraph StateGraph pipeline for options volatility trading."""

    def __init__(self, config: VolAgentSettings | None = None, llm_client: Any = None):
        self.config = config or load_config()
        self.llm_client = llm_client
        self.graph = self._build_graph()

    def _build_graph(self) -> Any:
        builder = StateGraph(VolAgentState)

        # 1. Register Nodes using agent_settings parameter to avoid LangChain RunnableConfig warning
        builder.add_node("initialize_run", partial(initialize_run, agent_settings=self.config))
        builder.add_node("fetch_market_snapshot", partial(fetch_market_snapshot, agent_settings=self.config))
        builder.add_node("event_magnitude_node", partial(event_magnitude_node, agent_settings=self.config, llm_client=self.llm_client))
        builder.add_node("volatility_quant_node", partial(volatility_quant_node, agent_settings=self.config))
        builder.add_node("forecast_node", partial(forecast_node, agent_settings=self.config))
        builder.add_node("long_vol_node", partial(long_vol_node, agent_settings=self.config, llm_client=self.llm_client))
        builder.add_node("short_vol_node", partial(short_vol_node, agent_settings=self.config, llm_client=self.llm_client))
        builder.add_node("critic_and_compliance_node", partial(critic_and_compliance_node, agent_settings=self.config, llm_client=self.llm_client))
        builder.add_node("strategy_and_risk_node", partial(strategy_and_risk_node, agent_settings=self.config))

        # 2. Wire Parallel Graph Edges
        builder.add_edge(START, "initialize_run")
        builder.add_edge("initialize_run", "fetch_market_snapshot")

        # Parallel Fan-Out 1: Event Magnitude || Vol Quant
        builder.add_edge("fetch_market_snapshot", "event_magnitude_node")
        builder.add_edge("fetch_market_snapshot", "volatility_quant_node")

        # Fan-In to Forecast Node
        builder.add_edge("event_magnitude_node", "forecast_node")
        builder.add_edge("volatility_quant_node", "forecast_node")

        # Parallel Fan-Out 2: Long-Vol Advocate || Short-Vol Advocate
        builder.add_edge("forecast_node", "long_vol_node")
        builder.add_edge("forecast_node", "short_vol_node")

        # Fan-In to Critic Node
        builder.add_edge("long_vol_node", "critic_and_compliance_node")
        builder.add_edge("short_vol_node", "critic_and_compliance_node")

        # Critic to Strategy & Risk Gate
        builder.add_edge("critic_and_compliance_node", "strategy_and_risk_node")
        builder.add_edge("strategy_and_risk_node", END)

        return builder.compile()

    def run(self, initial_inputs: dict[str, Any]) -> dict[str, Any]:
        """Execute the workflow synchronously."""
        return self.graph.invoke(initial_inputs)
