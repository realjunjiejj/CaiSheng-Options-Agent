"""Emil Kowalski Studio-Grade Design System for CaiSheng Options Alpha Desk.

Continuous Canvas, Box-Free Architecture:
- Zero bento-box card clutter: eliminates unnecessary card containers, borders, and shadows.
- Typographic hierarchy: primary data (like $100K equity) breathes directly on the white canvas.
- Subtle hairline dividers (1px solid #F1F5F9 / #E2E8F0) and whitespace instead of box-in-box nesting.
- Borderless text navigation tabs with active underline indicator (Linear / Apple style).
- Emil Kowalski micro-interactions: :active scale(0.97), cubic-bezier easing, tabular numbers.
"""

# Core Design Tokens
CANVAS_BG = "#FFFFFF"           # Crisp white continuous canvas
CANVAS_SUBTLE = "#F8FAFC"       # Slate 50 subtle background
CARD_BG = "#FFFFFF"             # Transparent / canvas matching
CARD_BORDER = "#E2E8F0"         # Hairline Slate 200 divider
CARD_BORDER_SUBTLE = "#F1F5F9"  # Slate 100 hairline
CARD_SHADOW = "none"            # No drop shadows
CARD_SHADOW_ELEVATED = "none"

# Text Hierarchy
TEXT_PRIMARY = "#0F172A"        # Slate 900
TEXT_SECONDARY = "#475569"      # Slate 600
TEXT_MUTED = "#94A3B8"          # Slate 400

# Institutional Alpaca & Track 02 Accents
ALPACA_YELLOW = "#FACC15"       # Warm Alpaca Gold
ALPACA_YELLOW_HOVER = "#EAB308"
ALPACA_YELLOW_BG = "#FEFCE8"    # Yellow 50
ALPACA_YELLOW_BORDER = "#FEF08A"# Yellow 200

BRAND_AMBER = "#D97706"         # Amber 600
BRAND_AMBER_BG = "#FEF3C7"      # Amber 100
BRAND_AMBER_BORDER = "#FDE68A"

GREEN_PROFIT = "#059669"        # Emerald 600
GREEN_BG = "#ECFDF5"            # Mint 50 tint
GREEN_BORDER = "#A7F3D0"        # Mint 200

RED_LOSS = "#DC2626"            # Rose / Crimson 600
RED_BG = "#FEF2F2"              # Rose 50 tint
RED_BORDER = "#FECACA"          # Rose 200

CYAN_ACCENT = "#0284C7"         # Sky 600
CYAN_BG = "#F0F9FF"             # Sky 50 tint
CYAN_BORDER = "#BAE6FD"

PURPLE_VOL = "#7C3AED"          # Violet 600
PURPLE_BG = "#F5F3FF"           # Violet 50 tint
PURPLE_BORDER = "#DDD6FE"

# Compatibility aliases
CYBER_YELLOW = ALPACA_YELLOW
CYBER_YELLOW_HOVER = ALPACA_YELLOW_HOVER
DEEP_ONYX = CANVAS_BG
SURFACE_CHARCOAL = CANVAS_BG
SURFACE_GLASS = CANVAS_BG
BORDER_GLASS = CARD_BORDER
BORDER_DARK = CARD_BORDER
PURE_WHITE = "#FFFFFF"
ALPACA_DARK = CANVAS_BG
ALPACA_CARD = CANVAS_BG
ALPACA_CARD_HOVER = "#F8FAFC"
ALPACA_BORDER = CARD_BORDER
ALPACA_BLACK = TEXT_PRIMARY
ALPACA_WHITE = "#FFFFFF"

BG_COLOR = CANVAS_BG
SURFACE_COLOR = CANVAS_BG
ACCENT_IV = ALPACA_YELLOW
ACCENT_GREEN = GREEN_PROFIT
ACCENT_RED = RED_LOSS
LONG_VOL_COLOR = CYAN_ACCENT
SHORT_VOL_COLOR = PURPLE_VOL
PASS_COLOR = GREEN_PROFIT
FAIL_COLOR = RED_LOSS

CUSTOM_CSS = f"""
<style>
    @import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500;600;700;800;900&family=Inter:wght@400;500;600;700;800;900&display=swap');

    /* 1. Global Reset & Continuous Canvas */
    html, body, [class*="css"] {{
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
        background-color: {CANVAS_BG} !important;
        color: {TEXT_PRIMARY} !important;
        margin: 0 !important;
        padding: 0 !important;
        -webkit-font-smoothing: antialiased;
        -moz-osx-font-smoothing: grayscale;
    }}

    .stApp {{
        background-color: {CANVAS_BG} !important;
    }}

    header[data-testid="stHeader"] {{
        display: none !important;
    }}

    footer {{
        display: none !important;
    }}

    .block-container {{
        max-width: 1480px !important;
        padding: 1rem 2.5rem 4rem !important;
        margin: 0 auto !important;
    }}

    /* Global Headings & Typography */
    h1, h2, h3, h4, h5, h6, .stMarkdown h1, .stMarkdown h2, .stMarkdown h3, .stMarkdown h4 {{
        color: {TEXT_PRIMARY} !important;
        font-weight: 800 !important;
        letter-spacing: -0.025em !important;
    }}

    .stMarkdown p, p {{
        color: #334155 !important;
    }}

    .stCaption, [data-testid="stCaptionContainer"] {{
        color: {TEXT_SECONDARY} !important;
    }}

    /* 2. Seamless Institutional Header (Flush with subtle bottom rule) */
    .cs-judge-header {{
        display: flex;
        justify-content: space-between;
        align-items: center;
        gap: 20px;
        padding: 12px 0 20px 0;
        background: transparent;
        border: none;
        border-bottom: 1px solid #E2E8F0;
        border-radius: 0;
        box-shadow: none;
        margin-bottom: 18px;
    }}

    .cs-header-left {{
        display: flex;
        align-items: center;
        gap: 16px;
    }}

    .cs-llama-badge {{
        width: 42px;
        height: 42px;
        background: {ALPACA_YELLOW};
        color: #000000;
        border-radius: 10px;
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 20px;
        font-weight: 800;
        flex-shrink: 0;
    }}

    .cs-eyebrow {{
        display: flex;
        align-items: center;
        gap: 8px;
        font-family: 'JetBrains Mono', monospace;
        font-size: 0.72rem;
        font-weight: 700;
        color: {BRAND_AMBER};
        letter-spacing: 0.06em;
        text-transform: uppercase;
    }}

    .cs-title {{
        color: {TEXT_PRIMARY};
        font-size: 1.6rem;
        font-weight: 800;
        letter-spacing: -0.03em;
        line-height: 1.15;
        margin-top: 2px;
    }}

    .cs-subtitle {{
        color: {TEXT_SECONDARY};
        font-size: 0.82rem;
        margin-top: 3px;
        font-weight: 400;
    }}

    .cs-status-pills {{
        display: flex;
        align-items: center;
        gap: 10px;
        flex-wrap: wrap;
    }}

    .cs-pill-armed {{
        background: {GREEN_BG};
        border: 1px solid {GREEN_BORDER};
        color: {GREEN_PROFIT};
        border-radius: 9999px;
        font-family: 'JetBrains Mono', monospace;
        font-size: 0.72rem;
        font-weight: 700;
        padding: 4px 12px;
        display: inline-flex;
        align-items: center;
        gap: 6px;
        white-space: nowrap;
    }}

    .cs-pill-mcp {{
        background: {CYAN_BG};
        border: 1px solid {CYAN_BORDER};
        color: {CYAN_ACCENT};
        border-radius: 9999px;
        font-family: 'JetBrains Mono', monospace;
        font-size: 0.72rem;
        font-weight: 700;
        padding: 4px 12px;
        white-space: nowrap;
    }}

    /* 3. Linear / Vercel Open Text Tabs (NO CAPSULE BOX) */
    [data-testid="stRadio"] > div, [data-testid="stRadioGroup"] {{
        background: transparent !important;
        border: none !important;
        border-radius: 0 !important;
        padding: 0 !important;
        gap: 32px !important;
        display: flex !important;
        flex-wrap: wrap !important;
        margin-bottom: 24px !important;
        border-bottom: 1px solid #F1F5F9 !important;
        box-shadow: none !important;
    }}

    [data-testid="stRadio"] [role="radiogroup"] > label,
    [data-testid="stRadioGroup"] > label {{
        background: transparent !important;
        border-radius: 0 !important;
        padding: 6px 0 12px 0 !important;
        margin: 0 !important;
        border: none !important;
        border-bottom: 2px solid transparent !important;
        cursor: pointer !important;
        display: inline-flex !important;
        align-items: center !important;
        box-shadow: none !important;
        transition: all 140ms ease !important;
    }}

    [data-testid="stRadio"] [role="radiogroup"] > label > div:first-child,
    [data-testid="stRadioGroup"] > label > div:first-child {{
        display: none !important;
    }}

    [data-testid="stRadio"] [role="radiogroup"] > label p,
    [data-testid="stRadioGroup"] > label p,
    [data-testid="stRadio"] [role="radiogroup"] > label span,
    [data-testid="stRadioGroup"] > label span {{
        color: #64748B !important;
        font-family: 'Inter', sans-serif !important;
        font-weight: 500 !important;
        font-size: 0.9rem !important;
        margin: 0 !important;
        transition: color 140ms ease !important;
    }}

    [data-testid="stRadio"] [role="radiogroup"] > label:hover p,
    [data-testid="stRadioGroup"] > label:hover p {{
        color: #0F172A !important;
    }}

    [data-testid="stRadio"] [role="radiogroup"] > label:has(input:checked),
    [data-testid="stRadioGroup"] > label:has(input:checked) {{
        background: transparent !important;
        box-shadow: none !important;
        border-bottom: 2px solid #0F172A !important;
    }}

    [data-testid="stRadio"] [role="radiogroup"] > label:has(input:checked) p,
    [data-testid="stRadioGroup"] > label:has(input:checked) p {{
        color: #0F172A !important;
        font-weight: 700 !important;
    }}

    /* 4. Mandate Governance Strip (Subtle integrated rule, no box) */
    .cs-mandate-banner {{
        background: #F8FAFC;
        border: none;
        border-left: 3px solid #F59E0B;
        border-radius: 4px;
        padding: 10px 16px;
        margin-bottom: 24px;
        display: flex;
        justify-content: space-between;
        align-items: center;
        gap: 16px;
        flex-wrap: wrap;
        font-size: 0.8rem;
        color: #475569;
    }}

    .cs-mandate-banner strong {{
        color: #0F172A;
    }}

    /* 5. Emil Kowalski Button Physics & Hover Elevation */
    .stButton > button, button[kind="primary"], button[kind="secondary"] {{
        background: #0F172A !important;
        color: #FFFFFF !important;
        font-family: 'Inter', sans-serif !important;
        font-weight: 600 !important;
        font-size: 0.85rem !important;
        border: 1px solid #0F172A !important;
        border-radius: 6px !important;
        padding: 6px 14px !important;
        box-shadow: 0 1px 2px 0 rgba(0, 0, 0, 0.05) !important;
        transition: transform 100ms cubic-bezier(0.23, 1, 0.32, 1), background-color 140ms ease, box-shadow 140ms ease !important;
    }}

    .stButton > button:hover, button[kind="primary"]:hover {{
        background: #1E293B !important;
        border-color: #1E293B !important;
        transform: translateY(-1px) !important;
    }}

    .stButton > button:active, button[kind="primary"]:active, button[kind="secondary"]:active {{
        transform: scale(0.97) !important;
    }}

    button[kind="secondary"] {{
        background: #FFFFFF !important;
        color: {TEXT_PRIMARY} !important;
        border: 1px solid {CARD_BORDER} !important;
    }}
    button[kind="secondary"]:hover {{
        background: #F8FAFC !important;
        border-color: #CBD5E1 !important;
    }}

    /* 6. Open Continuous Canvas (NO CARD BOXES) */
    .alpaca-card, .sd-card-dark, .sd-dark-glass, .cs-story-shell {{
        background: transparent !important;
        border: none !important;
        border-radius: 0 !important;
        padding: 0 !important;
        box-shadow: none !important;
        color: {TEXT_PRIMARY} !important;
        margin-bottom: 20px !important;
    }}

    .alpaca-portfolio-val {{
        font-family: 'JetBrains Mono', monospace !important;
        font-variant-numeric: tabular-nums !important;
        font-size: 2.5rem !important;
        font-weight: 900 !important;
        color: {TEXT_PRIMARY} !important;
        letter-spacing: -0.03em !important;
        line-height: 1.1 !important;
    }}

    .alpaca-timestamp {{
        font-size: 0.72rem !important;
        color: {TEXT_MUTED} !important;
        margin-top: 4px !important;
    }}

    .cs-replay-notice {{
        color: {TEXT_SECONDARY};
        background: #F8FAFC;
        border: none;
        border-left: 3px solid {BRAND_AMBER};
        border-radius: 4px;
        padding: 10px 16px;
        margin: 0 0 20px 0;
        font-size: 0.84rem;
        line-height: 1.5;
    }}

    .cs-replay-notice strong {{
        color: {TEXT_PRIMARY};
        font-family: 'JetBrains Mono', monospace;
    }}

    /* Status Pills */
    .pill-badge {{
        display: inline-flex;
        align-items: center;
        font-family: 'JetBrains Mono', monospace;
        font-weight: 700;
        font-size: 0.74rem;
        padding: 2px 8px;
        border-radius: 9999px;
        letter-spacing: 0.04em;
        text-transform: uppercase;
    }}

    .badge-long {{
        background: {GREEN_BG} !important;
        color: {GREEN_PROFIT} !important;
        border: 1px solid {GREEN_BORDER} !important;
    }}
    .badge-short {{
        background: {PURPLE_BG} !important;
        color: {PURPLE_VOL} !important;
        border: 1px solid {PURPLE_BORDER} !important;
    }}
    .badge-abstain {{
        background: {RED_BG} !important;
        color: {RED_LOSS} !important;
        border: 1px solid {RED_BORDER} !important;
    }}

    /* Form Inputs & Expanders */
    label, [data-testid="stWidgetLabel"] p, [data-testid="stWidgetLabel"] span {{
        color: #334155 !important;
        font-weight: 600 !important;
        font-size: 0.82rem !important;
    }}

    div[data-baseweb="input"], div[data-baseweb="select"] > div {{
        background-color: #FFFFFF !important;
        border-color: {CARD_BORDER} !important;
        border-radius: 6px !important;
        color: {TEXT_PRIMARY} !important;
    }}

    div[data-baseweb="input"] input, input[type="text"], input[type="number"], .stTextInput input {{
        background: #FFFFFF !important;
        color: {TEXT_PRIMARY} !important;
        border-radius: 6px !important;
    }}

    div[data-baseweb="input"]:focus-within {{
        border-color: {BRAND_AMBER} !important;
        box-shadow: 0 0 0 2px rgba(217, 119, 6, 0.15) !important;
    }}

    [data-testid="stExpander"] {{
        background: #FFFFFF !important;
        border: 1px solid #F1F5F9 !important;
        border-radius: 8px !important;
        box-shadow: none !important;
    }}

    [data-testid="stExpander"] summary {{
        color: {TEXT_PRIMARY} !important;
        font-weight: 600 !important;
    }}
</style>
"""
