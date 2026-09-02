# Extractable UI Components

## 1. `AlpacaHeroBanner`
- **Source**: `app.py` / `src/volagent/ui/theme.py`
- **Category**: `layout`
- **Description**: Signature Alpaca Yellow header with Alpaca logo mark, status pills, headline, and mandate badges.
- **Extractable Props**:
  - `accountNav` (string, default: "$100,000.00")
  - `systemStatus` (string, default: "CLEAN")
  - `activeMandate` (string, default: "$100,000 Portfolio Mandate")

## 2. `DialecticDebateSplit`
- **Source**: `app.py`
- **Category**: `basic`
- **Description**: Two side-by-side cards comparing Long-Vol Specialist vs Short-Vol Specialist theses with citation links.
- **Extractable Props**:
  - `longThesis` (string)
  - `shortThesis` (string)
  - `longConfidence` (float)
  - `shortConfidence` (float)

## 3. `RiskGateGrid`
- **Source**: `app.py` / `src/volagent/ui/theme.py`
- **Category**: `basic`
- **Description**: Grid of green/red check badges representing the 20-point deterministic risk gate and portfolio mandate gate.
- **Extractable Props**:
  - `gatePassed` (boolean)
  - `checkedRules` (list)

## 4. `PayoffChartCard`
- **Source**: `src/volagent/ui/charts.py`
- **Category**: `basic`
- **Description**: Interactive options expiration and IV crush payoff diagram with break-even markers.
- **Extractable Props**:
  - `spotPrice` (float)
  - `strategyDecision` (string)
  - `maxLoss` (float)

## 5. `AlpacaCodeBox`
- **Source**: `src/volagent/ui/theme.py`
- **Category**: `basic`
- **Description**: Dark macOS terminal code preview box with Python syntax highlighting.
- **Extractable Props**:
  - `snippet` (string)
