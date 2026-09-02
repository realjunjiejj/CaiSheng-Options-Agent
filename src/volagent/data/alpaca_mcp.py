"""Alpaca Model Context Protocol (MCP) Server Tool Definitions & Executable Service."""

from datetime import datetime, timedelta, timezone
import json
from typing import Any
import uuid

from mcp.server.mcpserver import MCPServer
from volagent.config import VolAgentSettings, load_config
from volagent.data.alpaca_sdk import AlpacaLiveMarketAdapter, AlpacaPortfolioAdapter
from volagent.domain.enums import ExecutionStatus
from volagent.domain.execution import OrderPlan
from volagent.errors import BrokerExecutionError
from volagent.execution.alpaca import AlpacaPaperBroker
from volagent.execution.ledger import ExecutionLedger



def sanitize_secrets(val: Any) -> Any:
    """Recursively sanitize any sensitive credentials in dicts, lists, tuples, and primitives."""
    sensitive_keys = {"api_key", "secret_key", "password", "token", "auth", "secret", "private_key"}
    if isinstance(val, dict):
        sanitized = {}
        for k, v in val.items():
            if any(s in str(k).lower() for s in sensitive_keys):
                sanitized[k] = "[REDACTED]"
            else:
                sanitized[k] = sanitize_secrets(v)
        return sanitized
    elif isinstance(val, list):
        return [sanitize_secrets(item) for item in val]
    elif isinstance(val, tuple):
        return tuple(sanitize_secrets(item) for item in val)
    elif isinstance(val, set):
        return {sanitize_secrets(item) for item in val}
    return val


class AlpacaMCPTools:
    """Tool schema definitions compatible with official Alpaca MCP server."""

    @staticmethod
    def get_account_tool() -> dict[str, Any]:
        return {
            "name": "alpaca_get_account",
            "description": "Fetch Alpaca paper trading account equity, buying power, and portfolio status.",
            "parameters": {"type": "object", "properties": {}},
        }

    @staticmethod
    def get_positions_tool() -> dict[str, Any]:
        return {
            "name": "alpaca_get_positions",
            "description": "Fetch all open equity and option positions currently held in Alpaca paper account.",
            "parameters": {"type": "object", "properties": {}},
        }

    @staticmethod
    def get_orders_tool() -> dict[str, Any]:
        return {
            "name": "alpaca_get_orders",
            "description": "Fetch recent broker orders filtered by status (open, closed, all).",
            "parameters": {
                "type": "object",
                "properties": {
                    "status": {"type": "string", "enum": ["open", "closed", "all"], "default": "open"},
                    "limit": {"type": "integer", "default": 50},
                },
            },
        }

    @staticmethod
    def get_quote_tool() -> dict[str, Any]:
        return {
            "name": "alpaca_get_quote",
            "description": "Fetch latest bid/ask quotes and trade price for an underlying symbol or option contract.",
            "parameters": {
                "type": "object",
                "properties": {
                    "symbol": {"type": "string", "description": "Ticker symbol"},
                },
                "required": ["symbol"],
            },
        }

    @staticmethod
    def get_market_clock_tool() -> dict[str, Any]:
        return {
            "name": "alpaca_get_market_clock",
            "description": "Fetch real-time market open/close clock and next open/close timestamps.",
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
                    "symbol": {"type": "string", "description": "Underlying equity symbol"},
                    "target_dte": {"type": "integer", "minimum": 1, "default": 7},
                },
                "required": ["symbol"],
            },
        }

    @staticmethod
    def submit_multileg_order_tool() -> dict[str, Any]:
        return {
            "name": "alpaca_submit_multileg_order",
            "description": "Submit an atomic multi-leg limit options order to Alpaca Paper Trading through the verified order gate.",
            "parameters": {
                "type": "object",
                "properties": {
                    "approval_token": {"type": "string"},
                    "decision_id": {"type": "string"},
                },
                "required": ["approval_token", "decision_id"],
            },
        }


class AlpacaMCPService:
    """Handles MCP tool invocations, enforces order gates, sanitizes data, and audits all calls."""

    def __init__(
        self,
        portfolio_adapter: AlpacaPortfolioAdapter | None = None,
        ledger: ExecutionLedger | None = None,
        settings: VolAgentSettings | None = None,
    ):
        self.settings = settings or load_config()
        self.portfolio_adapter = portfolio_adapter or AlpacaPortfolioAdapter(
            api_key=self.settings.alpaca_api_key,
            secret_key=self.settings.alpaca_secret_key,
            paper=self.settings.alpaca_paper_trade,
        )
        self.ledger = ledger or ExecutionLedger()
        self.server = self._init_mcp_server()

    def _init_mcp_server(self) -> MCPServer:
        server = MCPServer("caisheng-alpaca-options")

        @server.tool(name="alpaca_get_account", description="Fetch Alpaca account equity, cash, and buying power")
        def mcp_get_account() -> dict[str, Any]:
            res = self.handle_tool_call("alpaca_get_account", {})
            return res.get("result", {})

        @server.tool(name="alpaca_get_positions", description="Fetch active broker positions")
        def mcp_get_positions() -> dict[str, Any]:
            res = self.handle_tool_call("alpaca_get_positions", {})
            return res.get("result", {})

        @server.tool(name="alpaca_get_orders", description="Fetch broker orders")
        def mcp_get_orders(status: str = "open", limit: int = 50) -> dict[str, Any]:
            res = self.handle_tool_call("alpaca_get_orders", {"status": status, "limit": limit})
            return res.get("result", {})

        @server.tool(name="alpaca_get_market_clock", description="Fetch market clock state")
        def mcp_get_market_clock() -> dict[str, Any]:
            res = self.handle_tool_call("alpaca_get_market_clock", {})
            return res.get("result", {})

        @server.tool(name="alpaca_get_quote", description="Fetch real-time quote for symbol")
        def mcp_get_quote(symbol: str) -> dict[str, Any]:
            res = self.handle_tool_call("alpaca_get_quote", {"symbol": symbol})
            return res.get("result", {})

        @server.tool(name="alpaca_get_option_chain", description="Fetch option chain snapshot for symbol")
        def mcp_get_option_chain(symbol: str, target_dte: int = 7) -> dict[str, Any]:
            res = self.handle_tool_call("alpaca_get_option_chain", {"symbol": symbol, "target_dte": target_dte})
            return res.get("result", {})

        @server.tool(name="alpaca_submit_multileg_order", description="Submit multi-leg options order through verified gateway")
        def mcp_submit_multileg_order(approval_token: str, decision_id: str) -> dict[str, Any]:
            res = self.handle_tool_call("alpaca_submit_multileg_order", {
                "approval_token": approval_token,
                "decision_id": decision_id,
            }, decision_id=decision_id)
            return res.get("result", {})

        return server


    def sanitize_arguments(self, args: Any) -> Any:
        """Redact any sensitive credentials from tool arguments recursively."""
        return sanitize_secrets(args)

    def handle_tool_call(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        decision_id: str | None = None,
    ) -> dict[str, Any]:
        """Execute an MCP tool call and record a sanitized audit event in the ledger."""
        call_id = f"mcp-{uuid.uuid4().hex[:12]}"
        sanitized_args = self.sanitize_arguments(arguments)
        status = "SUCCESS"
        result: dict[str, Any] = {}

        try:
            if tool_name == "alpaca_get_account":
                snap = self.portfolio_adapter.fetch_portfolio_snapshot(ledger=self.ledger)
                if snap.is_stale:
                    status = "ERROR"
                    result = {
                        "error": self.portfolio_adapter.last_error or "Account snapshot stale or unavailable",
                        "is_stale": True,
                    }
                else:
                    result = {
                        "account_id": snap.account_id,
                        "equity": snap.equity,
                        "cash": snap.cash,
                        "buying_power": snap.buying_power,
                        "daily_pnl_dollars": snap.total_daily_pl,
                        "as_of_time": snap.timestamp.isoformat(),
                    }

            elif tool_name == "alpaca_get_positions":
                positions = self.portfolio_adapter.list_positions()
                raw_positions = []
                for p in positions:
                    if hasattr(p, "model_dump"):
                        raw_positions.append(p.model_dump(mode="json"))
                    elif hasattr(p, "__dict__"):
                        raw_positions.append({k: str(v) for k, v in p.__dict__.items() if not k.startswith("_")})
                    else:
                        raw_positions.append(str(p))
                result = {"positions": raw_positions}

            elif tool_name == "alpaca_get_orders":
                orders = self.portfolio_adapter.list_orders(status=arguments.get("status", "open"))
                raw_orders = []
                for o in orders:
                    if hasattr(o, "model_dump"):
                        raw_orders.append(o.model_dump(mode="json"))
                    elif hasattr(o, "__dict__"):
                        raw_orders.append({k: str(v) for k, v in o.__dict__.items() if not k.startswith("_")})
                    else:
                        raw_orders.append(str(o))
                result = {"orders": raw_orders}

            elif tool_name == "alpaca_get_market_clock":
                clock = self.portfolio_adapter.get_market_clock()
                result = clock

            elif tool_name == "alpaca_get_quote":
                sym = str(arguments.get("symbol") or "").strip().upper()
                if not sym:
                    raise BrokerExecutionError("A non-empty symbol is required.")
                market_adapter = AlpacaLiveMarketAdapter(
                    api_key=self.settings.alpaca_api_key,
                    secret_key=self.settings.alpaca_secret_key,
                    stock_feed=self.settings.market_data.stock_feed,
                    options_feed=self.settings.market_data.options_feed,
                )
                quote_data = market_adapter.get_underlying_snapshot(sym)
                if quote_data is None:
                    raise BrokerExecutionError(
                        market_adapter.last_error or f"Fresh Alpaca quote unavailable for {sym}."
                    )
                result = {
                    "symbol": sym,
                    "spot": quote_data.price,
                    "bid": quote_data.bid,
                    "ask": quote_data.ask,
                    "quote_time": quote_data.quote_time.isoformat(),
                }

            elif tool_name == "alpaca_get_option_chain":
                sym = str(arguments.get("symbol") or "").strip().upper()
                if not sym:
                    raise BrokerExecutionError("A non-empty symbol is required.")
                target_dte = max(1, int(arguments.get("target_dte", 7)))
                market_adapter = AlpacaLiveMarketAdapter(
                    api_key=self.settings.alpaca_api_key,
                    secret_key=self.settings.alpaca_secret_key,
                    stock_feed=self.settings.market_data.stock_feed,
                    options_feed=self.settings.market_data.options_feed,
                )
                underlying = market_adapter.get_underlying_snapshot(sym)
                if underlying is None:
                    raise BrokerExecutionError(
                        market_adapter.last_error or f"Fresh Alpaca quote unavailable for {sym}."
                    )
                start_expiry = datetime.now(timezone.utc).date() + timedelta(days=target_dte)
                chain = market_adapter.get_option_chain(
                    sym,
                    earliest_expiration=start_expiry,
                    latest_expiration=start_expiry + timedelta(days=7),
                    spot_price=underlying.price,
                )
                if not chain:
                    raise BrokerExecutionError(
                        market_adapter.last_error or f"Fresh Alpaca option chain unavailable for {sym}."
                    )
                result = {
                    "symbol": sym,
                    "contracts_count": len(chain),
                    "underlying_spot": underlying.price,
                    "as_of": max(contract.quote_time for contract in chain).isoformat(),
                }

            elif tool_name == "alpaca_submit_multileg_order":
                # Raw MCP arguments are intentionally not converted into an
                # executable OrderPlan.  They do not contain immutable quote
                # provenance, expiry/strike/type snapshots, a risk report, or
                # an existing approval token.  Fabricating those fields would
                # let MCP bypass the canonical preview -> approval -> gateway
                # path.  Reject in a controlled, auditable way.
                approval_token = str(arguments.get("approval_token", "")).strip()
                requested_decision_id = str(
                    arguments.get("decision_id") or decision_id or ""
                ).strip()
                decision_id = requested_decision_id or decision_id
                if not approval_token or not requested_decision_id:
                    status = "REJECTED"
                    result = {
                        "status": "REJECTED",
                        "error": (
                            "Canonical approval_token and decision_id are required; "
                            "raw order construction is forbidden."
                        ),
                    }
                else:
                    order_row = self.ledger.get_order_by_approval_token(approval_token)
                    decision_row = self.ledger.get_decision_record(requested_decision_id)
                    if not order_row or order_row.get("status") != ExecutionStatus.APPROVED.value:
                        status = "REJECTED"
                        result = {"status": "REJECTED", "error": "Approved canonical OrderPlan not found."}
                    elif order_row.get("decision_id") != requested_decision_id:
                        status = "REJECTED"
                        result = {"status": "REJECTED", "error": "OrderPlan decision_id does not match the requested DecisionRecord."}
                    elif not decision_row or decision_row.get("status") != "APPROVED":
                        status = "REJECTED"
                        result = {"status": "REJECTED", "error": "Authoritative APPROVED DecisionRecord not found."}
                    else:
                        plan = OrderPlan.model_validate(json.loads(order_row["full_order_plan"]))
                        if plan.approval_token != approval_token or plan.decision_id != requested_decision_id:
                            status = "REJECTED"
                            result = {"status": "REJECTED", "error": "Persisted order identity mismatch."}
                        elif decision_row.get("selected_strategy_id") != plan.strategy_id:
                            status = "REJECTED"
                            result = {"status": "REJECTED", "error": "DecisionRecord did not select this strategy."}
                        else:
                            broker = AlpacaPaperBroker(
                                api_key=self.settings.alpaca_api_key,
                                secret_key=self.settings.alpaca_secret_key,
                                ledger=self.ledger,
                            )
                            receipt = broker.submit_paper_order(plan)
                            if receipt.status in {
                                ExecutionStatus.REJECTED,
                                ExecutionStatus.CANCELED,
                                ExecutionStatus.FAILED,
                            }:
                                status = "REJECTED"
                            result = {
                                "status": receipt.status.value,
                                "receipt_id": receipt.receipt_id,
                                "broker_order_id": receipt.broker_order_id,
                                "filled_quantity": receipt.filled_quantity,
                                "client_order_id": receipt.client_order_id,
                            }


            else:
                status = "ERROR"
                result = {"error": f"Unknown MCP tool: {tool_name}"}

        except BrokerExecutionError as exc:
            status = "REJECTED"
            result = {"status": "REJECTED", "error": str(exc)}
        except Exception as exc:
            status = "ERROR"
            result = {"error": f"{type(exc).__name__}: {exc}"}

        # Persist audit record
        self.ledger.record_mcp_audit_event(
            event_id=call_id,
            tool_name=tool_name,
            sanitized_arguments=sanitized_args if isinstance(sanitized_args, dict) else {"args": sanitized_args},
            result_status=status,
            raw_response=result,
            decision_id=decision_id,
        )

        return {
            "call_id": call_id,
            "tool_name": tool_name,
            "status": status,
            "result": result,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    @staticmethod
    def _health_route(transport: str) -> Any:
        """Return the common health route used by both network transports."""
        from starlette.responses import JSONResponse
        from starlette.routing import Route

        async def handle_health(request: Any) -> JSONResponse:
            return JSONResponse({
                "status": "healthy",
                "service": "caisheng-mcp",
                "transport": transport,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })

        return Route("/healthz", endpoint=handle_health, methods=["GET"])

    def create_sse_app(self, host: str = "0.0.0.0") -> Any:
        """Create the SDK-supported legacy SSE ASGI application."""
        app = self.server.sse_app(
            host=host,
            sse_path="/sse",
            message_path="/messages",
        )
        app.routes.append(self._health_route("sse"))
        return app

    def create_streamable_http_app(self, host: str = "0.0.0.0") -> Any:
        """Create the SDK-supported Streamable HTTP ASGI application."""
        app = self.server.streamable_http_app(
            host=host,
            streamable_http_path="/mcp",
            stateless_http=False,
        )
        app.routes.append(self._health_route("streamable-http"))
        return app

    def run_sse_server(self, host: str = "0.0.0.0", port: int = 8000) -> None:
        """Run the legacy SSE transport with Uvicorn."""
        import uvicorn
        app = self.create_sse_app(host=host)
        uvicorn.run(app, host=host, port=port, log_level="info")

    def run_streamable_http_server(self, host: str = "0.0.0.0", port: int = 8000) -> None:
        """Run the preferred Streamable HTTP transport with Uvicorn."""
        import uvicorn
        app = self.create_streamable_http_app(host=host)
        uvicorn.run(app, host=host, port=port, log_level="info")
