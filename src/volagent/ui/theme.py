"""Alpaca-branded high-contrast Pro Terminal theme for VolAgent Alpha."""

# Alpaca Official Brand Palette
ALPACA_YELLOW = "#FCD700"  # Signature Alpaca Gold
ALPACA_YELLOW_HOVER = "#FFE135"
ALPACA_DARK = "#0D1117"    # Deep Obsidian Background
ALPACA_CARD = "#161B22"    # Terminal Card Background
ALPACA_CARD_HOVER = "#1C2128"
ALPACA_BORDER = "#30363D"  # Crisp boundary border

TEXT_PRIMARY = "#FFFFFF"
TEXT_SECONDARY = "#C9D1D9"
TEXT_MUTED = "#8B949E"

# Trading Indicators
GREEN_PROFIT = "#00E676"   # Neon Emerald
RED_LOSS = "#FF5252"       # Neon Coral
CYAN_ACCENT = "#58A6FF"    # Electric Blue
PURPLE_VOL = "#D2A8FF"     # Volatility Lilac

# Compatibility aliases
BG_COLOR = ALPACA_DARK
SURFACE_COLOR = ALPACA_CARD
ACCENT_IV = ALPACA_YELLOW
ACCENT_GREEN = GREEN_PROFIT
ACCENT_RED = RED_LOSS
LONG_VOL_COLOR = CYAN_ACCENT
SHORT_VOL_COLOR = PURPLE_VOL
PASS_COLOR = GREEN_PROFIT
FAIL_COLOR = RED_LOSS

CUSTOM_CSS = f"""
<style>
    @import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500;600;700&family=Inter:wght@400;500;600;700;800&display=swap');
    
    html, body, [class*="css"] {{
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
        background-color: {ALPACA_DARK} !important;
        color: {TEXT_PRIMARY} !important;
    }}
    
    .stApp {{
        background-color: {ALPACA_DARK};
    }}
    
    /* Top Terminal Navigation Header */
    .alpaca-header {{
        display: flex;
        justify-content: space-between;
        align-items: center;
        padding: 14px 20px;
        background: {ALPACA_CARD};
        border-bottom: 1px solid {ALPACA_BORDER};
        border-radius: 12px;
        margin-bottom: 24px;
    }}
    
    .alpaca-logo {{
        display: flex;
        align-items: center;
        gap: 10px;
        font-weight: 800;
        font-size: 1.25em;
        letter-spacing: -0.5px;
        color: #FFFFFF;
    }}
    
    .alpaca-badge {{
        background: {ALPACA_YELLOW};
        color: #000000;
        font-family: 'JetBrains Mono', monospace;
        font-weight: 700;
        font-size: 0.75em;
        padding: 2px 8px;
        border-radius: 6px;
        letter-spacing: 0.5px;
    }}
    
    /* Terminal Hero Card */
    .terminal-hero {{
        background: {ALPACA_CARD};
        border: 1px solid {ALPACA_BORDER};
        border-top: 4px solid {ALPACA_YELLOW};
        border-radius: 14px;
        padding: 24px;
        margin-bottom: 20px;
        box-shadow: 0 8px 24px rgba(0, 0, 0, 0.4);
    }}
    
    .ticker-symbol {{
        font-family: 'JetBrains Mono', monospace;
        font-size: 1.8em;
        font-weight: 800;
        color: #FFFFFF;
        letter-spacing: -0.5px;
    }}
    
    .decision-tag {{
        display: inline-block;
        font-family: 'JetBrains Mono', monospace;
        font-weight: 700;
        font-size: 0.85em;
        padding: 6px 14px;
        border-radius: 8px;
        text-transform: uppercase;
        letter-spacing: 0.5px;
    }}
    
    .tag-long {{
        background: rgba(0, 230, 118, 0.15);
        color: {GREEN_PROFIT};
        border: 1px solid rgba(0, 230, 118, 0.4);
    }}
    
    .tag-short {{
        background: rgba(210, 168, 255, 0.15);
        color: {PURPLE_VOL};
        border: 1px solid rgba(210, 168, 255, 0.4);
    }}
    
    .tag-reject {{
        background: rgba(255, 82, 82, 0.15);
        color: {RED_LOSS};
        border: 1px solid rgba(255, 82, 82, 0.4);
    }}
    
    /* Metric Boxes with Razor-Sharp High Contrast */
    .metric-grid {{
        display: grid;
        grid-template-columns: repeat(3, 1fr);
        gap: 16px;
        margin-top: 18px;
        border-top: 1px solid {ALPACA_BORDER};
        padding-top: 18px;
    }}
    
    .metric-box {{
        background: #0D1117;
        border: 1px solid {ALPACA_BORDER};
        border-radius: 10px;
        padding: 14px 18px;
    }}
    
    .metric-label {{
        font-size: 0.8em;
        font-weight: 600;
        text-transform: uppercase;
        color: {TEXT_MUTED};
        letter-spacing: 0.5px;
        margin-bottom: 4px;
    }}
    
    .metric-value {{
        font-family: 'JetBrains Mono', monospace;
        font-size: 1.45em;
        font-weight: 700;
        color: #FFFFFF;
    }}
    
    /* Sleek Mini Cards */
    .info-card {{
        background: {ALPACA_CARD};
        border: 1px solid {ALPACA_BORDER};
        border-radius: 12px;
        padding: 18px 20px;
        margin-bottom: 16px;
    }}
    
    .info-title {{
        font-size: 0.9em;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 0.5px;
        color: {ALPACA_YELLOW};
        margin-bottom: 10px;
        display: flex;
        align-items: center;
        gap: 8px;
    }}
    
    .greek-chip {{
        display: inline-block;
        font-family: 'JetBrains Mono', monospace;
        background: #0D1117;
        border: 1px solid {ALPACA_BORDER};
        color: {TEXT_PRIMARY};
        font-size: 0.85em;
        font-weight: 600;
        padding: 6px 12px;
        border-radius: 8px;
        margin-right: 6px;
        margin-bottom: 6px;
    }}
    
    /* High Contrast Alpaca Action Button */
    .stButton > button {{
        background: {ALPACA_YELLOW} !important;
        color: #000000 !important;
        font-family: 'Inter', sans-serif !important;
        font-weight: 700 !important;
        font-size: 1.05em !important;
        border: none !important;
        border-radius: 10px !important;
        padding: 14px 28px !important;
        box-shadow: 0 4px 14px rgba(252, 215, 0, 0.3) !important;
        transition: transform 0.1s ease, box-shadow 0.1s ease !important;
    }}
    
    .stButton > button:hover {{
        background: {ALPACA_YELLOW_HOVER} !important;
        transform: translateY(-1px) !important;
        box-shadow: 0 6px 20px rgba(252, 215, 0, 0.45) !important;
    }}
    
    /* Input field styling */
    .stTextInput > div > div > input {{
        background: {ALPACA_CARD} !important;
        border: 1px solid {ALPACA_BORDER} !important;
        color: #FFFFFF !important;
        border-radius: 8px !important;
        font-family: 'JetBrains Mono', monospace !important;
    }}
    
    /* Expandable details */
    .streamlit-expanderHeader {{
        background: {ALPACA_CARD} !important;
        border: 1px solid {ALPACA_BORDER} !important;
        border-radius: 8px !important;
        color: {TEXT_PRIMARY} !important;
    }}
    
    .block-container {{
        max-width: 960px;
        padding-top: 1.5rem;
        padding-bottom: 3rem;
    }}
</style>
"""
