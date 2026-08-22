"""Alpaca Model Context Protocol (MCP) Server Tool Definitions & Connector."""

from typing import Any
from pydantic import BaseModel, Field


class AlpacaMCPTools:
    """Tool schema definitions compatible with official Alpaca FastMCP server."""

    @staticmethod
    def get_account_tool() -> dict[str, Any]:
        return {
            "name": "alpaca_get_account",
            "description": "Fetch Alpaca paper trading account equity, buying power, and portfolio status.",
            "parameters": {"type": "object", "properties": {}},
        }

    @staticmethod
    def get_option_chain_tool() -> dict[str, Any]:
        return {
            "name": "alpaca_get_option_chain",
            "description": "Fetch real-time option chain quotes, Greeks, and open interest for an underlying symbol.",
            "parameters": {
                "type": "object",
                "properties": {
                    "symbol": {"type": "string", "description": "Underlying equity symbol (e.g. NVDA)"},
                    "expiration": {"type": "string", "description": "Target expiration date in YYYY-MM-DD format"},
                },
                "required": ["symbol"],
            },
        }

    @staticmethod
    def submit_multileg_order_tool() -> dict[str, Any]:
        return {
            "name": "alpaca_submit_multileg_order",
            "description": "Submit an atomic multi-leg limit options order to Alpaca Paper Trading.",
            "parameters": {
                "type": "object",
                "properties": {
                    "symbol": {"type": "string"},
                    "quantity": {"type": "integer"},
                    "limit_price": {"type": "number"},
                    "legs": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "contract_symbol": {"type": "string"},
                                "side": {"type": "string", "enum": ["buy", "sell"]},
                                "ratio_qty": {"type": "integer"},
                                "position_intent": {"type": "string"},
                            },
                            "required": ["contract_symbol", "side", "ratio_qty", "position_intent"],
                        },
                    },
                },
                "required": ["symbol", "quantity", "limit_price", "legs"],
            },
        }
