# Theme & Design Tokens

## Compact Token Summary

### Color Palette (Alpaca Official Identity)
- `ALPACA_YELLOW`: `#FFD000` (Signature vibrant Alpaca gold/yellow - primary brand, active states, CTA buttons)
- `ALPACA_YELLOW_HOVER`: `#FFE033` (Hover transition state)
- `ALPACA_YELLOW_SOFT`: `rgba(255, 208, 0, 0.12)` (Pills, subtle highlights)
- `ALPACA_DARK`: `#0C0F14` (Deep obsidian background canvas)
- `ALPACA_CARD`: `#141820` (Surface card background)
- `ALPACA_CARD_HOVER`: `#1C222E` (Card hover state)
- `ALPACA_BORDER`: `#252C38` (Razor-sharp subtle card and grid border)
- `ALPACA_BLACK`: `#000000` (Hero text and dark elements)
- `ALPACA_WHITE`: `#FFFFFF` (Primary headlines and text)
- `TEXT_PRIMARY`: `#FFFFFF` (Main headings and critical values)
- `TEXT_SECONDARY`: `#9DA7B3` (Body descriptions and secondary indicators)
- `TEXT_MUTED`: `#6B7785` (Table captions and subtle labels)
- `GREEN_PROFIT`: `#00C805` (Alpaca Emerald Green / Long Volatility / Profit / Gate Pass)
- `RED_LOSS`: `#FF3B30` (Alpaca Coral Red / Short Risk / Loss / Gate Veto)
- `CYAN_ACCENT`: `#0070F3` (Electric Blue / Model Forecasts / Tech Badges)
- `PURPLE_VOL`: `#9333EA` / `#C084FC` (Volatility Lilac / IV Crush / Short Butterfly)

### Typography & Fonts
- **Headings & Body**: `Inter`, `-apple-system`, `BlinkMacSystemFont`, `"Segoe UI"`, `sans-serif` (weights: 400, 500, 600, 700, 800, 900)
- **Code, Tickers, Greeks & Metrics**: `JetBrains Mono`, monospace (weights: 400, 500, 600, 700, 800)

### Layout & Spacing Tokens
- Container Max Width: `1240px`
- Card Border Radius: `16px`
- Button Border Radius: `10px`
- Code Box Border Radius: `12px`
- Badge / Pill Radius: `8px` - `20px`
- Card Box Shadow: `0 8px 24px rgba(0, 0, 0, 0.35)`
- Hero Box Shadow: `0 12px 36px rgba(255, 208, 0, 0.25)`

---

## Raw Source Theme Dumps

### `src/volagent/ui/theme.py`
```python
"""Alpaca-branded high-contrast Pro Terminal theme for CaiSheng."""

# Alpaca Official Brand Palette
ALPACA_YELLOW = "#FFD000"        # Signature Alpaca Yellow
ALPACA_YELLOW_HOVER = "#FFE033"  # Vibrant Hover Yellow
ALPACA_YELLOW_SOFT = "rgba(255, 208, 0, 0.12)"
ALPACA_DARK = "#0C0F14"          # Deep Obsidian Background
ALPACA_CARD = "#141820"          # Modern Terminal Card
ALPACA_CARD_HOVER = "#1C222E"
ALPACA_BORDER = "#252C38"        # Crisp boundary border
ALPACA_BLACK = "#000000"
ALPACA_WHITE = "#FFFFFF"

TEXT_PRIMARY = "#FFFFFF"
TEXT_SECONDARY = "#9DA7B3"
TEXT_MUTED = "#6B7785"

# Trading Indicators
GREEN_PROFIT = "#00C805"   # Alpaca Emerald Green
RED_LOSS = "#FF3B30"       # Alpaca Coral Red
CYAN_ACCENT = "#0070F3"    # Electric Blue
PURPLE_VOL = "#9333EA"     # Volatility Purple

CUSTOM_CSS = """
<style>
    @import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500;600;700;800&family=Inter:wght@400;500;600;700;800;900&display=swap');

    html, body, [class*="css"] {
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
        background-color: #0C0F14 !important;
        color: #FFFFFF !important;
    }
</style>
"""
```
