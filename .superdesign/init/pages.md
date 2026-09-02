# Page Component Dependency Trees

## 1. App Root & Pro Trading Desk
- `app.py`
  - `src/volagent/ui/theme.py`
  - `src/volagent/ui/charts.py`
  - `src/volagent/ui/pages/cockpit.py`
  - `src/volagent/ui/pages/live_canary.py`
  - `src/volagent/ui/pages/historical_replay.py`
  - `src/volagent/ui/pages/scoreboard.py`
  - `src/volagent/ui/pages/research.py`
  - `src/volagent/ui/pages/rough_vol_simulator.py`
  - `src/volagent/graph/builder.py`
  - `src/volagent/config.py`
  - `src/volagent/domain/enums.py`
  - `src/volagent/execution/alpaca.py`
  - `src/volagent/execution/ledger.py`

## 2. Capital Command Page
- `src/volagent/ui/pages/cockpit.py`
  - `src/volagent/config.py`
  - `src/volagent/data/alpaca_sdk.py`
  - `src/volagent/execution/ledger.py`
  - `src/volagent/cli/preflight.py`
  - `src/volagent/cli/reconcile.py`

## 3. Scoreboard & Controlled Ablations
- `src/volagent/ui/pages/scoreboard.py`
  - `src/volagent/evaluation/evaluator.py`
  - `src/volagent/data/replay.py`
  - `src/volagent/ui/theme.py`

## 4. Rough Volatility Simulator
- `src/volagent/ui/pages/rough_vol_simulator.py`
  - `src/volagent/ui/theme.py`
  - `src/volagent/quant/rough_vol.py`
  - `src/volagent/quant/path_signatures.py`
