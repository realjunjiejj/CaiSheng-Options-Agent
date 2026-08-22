# Notice and Acknowledgements

## Project Overview
VolAgent Alpha is a neuro-symbolic multi-agent options volatility and event trading desk built as an educational and research submission for the **Alpaca AI Trading Agents Hackathon** (Track 02: Volatility & Event Trading Agents).

## Architectural Foundations & Academic Citations
1. **Multi-Agent Dialectical Debate:**
   Inspired by the multi-agent trading debate concepts in *TradingAgents: Multi-Agents LLM Financial Trading Framework* by Xiao et al. (Tauric Research, 2024; arXiv:2412.20138), adapted here specifically for unsigned options jump distributions and event volatility dynamics rather than directional equities.
2. **Variance Risk Premium & Jump Dynamics:**
   - Bollerslev, T., Tauchen, G., & Zhou, H. (2009). Expected Stock Returns and Variance Risk Premia. *The Review of Financial Studies*.
   - Carr, P., & Wu, L. (2009). Variance Risk Premia. *The Review of Financial Studies*.
   - Patel, N., et al. (2020). Implied Volatility Dynamics Surrounding Earnings Announcements.

## Safety & Operational Disclaimers
- VolAgent Alpha is configured to operate strictly with simulated and paper-trading endpoints (`ALPACA_PAPER_TRADE=True`).
- Real-world capital execution is disabled by default via strict kill switch (`VOLAGENT_ALLOW_ORDER_SUBMISSION=False`).
- All financial metrics and receipts generated in replay mode reflect frozen point-in-time file-backed artifacts.
