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

# Institutional Alpaca & Options Alpha Accents
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
    :root {{
        --cs-ease-out: cubic-bezier(0.23, 1, 0.32, 1);
        --cs-duration-fast: 120ms;
        --cs-duration-ui: 180ms;
        --cs-font-ui: -apple-system, BlinkMacSystemFont, "SF Pro Text", "Segoe UI", sans-serif;
        --cs-font-mono: "SFMono-Regular", "Cascadia Code", Consolas, monospace;
    }}

    /* 1. Global Reset & Continuous Canvas */
    html, body, [class*="css"] {{
        font-family: var(--cs-font-ui);
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

    .cs-eyebrow {{
        display: flex;
        align-items: center;
        gap: 8px;
        font-family: var(--cs-font-mono);
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

    .cs-version {{
        padding: 2px 7px;
        border: 1px solid {CARD_BORDER};
        border-radius: 999px;
        background: {CANVAS_SUBTLE};
        color: {TEXT_SECONDARY};
        font-size: 0.66rem;
        letter-spacing: 0;
        text-transform: none;
    }}

    .cs-status-pills {{
        display: flex;
        align-items: center;
        gap: 10px;
        flex-wrap: wrap;
    }}

    .cs-proof-pill {{
        background: {CANVAS_SUBTLE};
        border: 1px solid {CARD_BORDER};
        color: {TEXT_SECONDARY};
        border-radius: 9999px;
        font-family: var(--cs-font-mono);
        font-size: 0.68rem;
        font-weight: 700;
        padding: 5px 10px;
        display: inline-flex;
        align-items: center;
        white-space: nowrap;
    }}

    .cs-proof-pill-accent {{
        background: {ALPACA_YELLOW_BG};
        border-color: {ALPACA_YELLOW_BORDER};
        color: #854D0E;
    }}

    /* Judge overview: one narrative, no decorative dashboard chrome. */
    .cs-overview {{
        animation: cs-content-enter 220ms var(--cs-ease-out) both;
    }}

    .cs-overview-hero {{
        max-width: 1120px;
        padding: 34px 0 30px;
    }}

    .cs-overview-kicker,
    .cs-overview-heading span,
    .cs-overview-footer span {{
        color: {BRAND_AMBER};
        font-family: var(--cs-font-mono);
        font-size: 0.68rem;
        font-weight: 800;
        letter-spacing: 0.065em;
    }}

    .cs-overview-hero h1 {{
        max-width: 850px;
        margin: 8px 0 12px;
        font-size: clamp(2.25rem, 5vw, 4.35rem) !important;
        line-height: 0.98 !important;
        letter-spacing: -0.055em !important;
    }}

    .cs-overview-hero > p {{
        max-width: 820px;
        margin: 0;
        color: {TEXT_SECONDARY} !important;
        font-size: 1rem;
        line-height: 1.6;
    }}

    .cs-overview-stats {{
        display: grid;
        grid-template-columns: repeat(4, minmax(0, 1fr));
        margin-top: 30px;
        border-top: 1px solid {CARD_BORDER};
        border-bottom: 1px solid {CARD_BORDER};
    }}

    .cs-overview-stats > div {{
        padding: 15px 18px;
        border-right: 1px solid {CARD_BORDER_SUBTLE};
    }}

    .cs-overview-stats > div:first-child {{ padding-left: 0; }}
    .cs-overview-stats > div:last-child {{ border-right: 0; }}
    .cs-overview-stats strong {{
        display: block;
        color: {TEXT_PRIMARY};
        font-family: var(--cs-font-mono);
        font-size: 1.35rem;
        font-variant-numeric: tabular-nums;
    }}
    .cs-overview-stats span {{
        color: {TEXT_MUTED};
        font-size: 0.72rem;
    }}

    .cs-overview-section {{
        padding: 26px 0;
        border-bottom: 1px solid {CARD_BORDER};
    }}

    .cs-overview-heading {{
        display: flex;
        align-items: baseline;
        justify-content: space-between;
        gap: 18px;
        margin-bottom: 16px;
    }}

    .cs-overview-heading small {{
        color: {TEXT_MUTED};
        font-size: 0.72rem;
    }}

    .cs-flow {{
        display: grid;
        grid-template-columns: repeat(6, minmax(0, 1fr));
    }}

    .cs-flow > div {{
        position: relative;
        min-width: 0;
        padding: 2px 18px 2px 0;
    }}

    .cs-flow > div:not(:last-child)::after {{
        content: "→";
        position: absolute;
        top: 1px;
        right: 7px;
        color: {TEXT_MUTED};
        font-family: var(--cs-font-mono);
    }}

    .cs-flow b,
    .cs-flow strong,
    .cs-flow span {{ display: block; }}
    .cs-flow b {{
        color: {BRAND_AMBER};
        font-family: var(--cs-font-mono);
        font-size: 0.62rem;
    }}
    .cs-flow strong {{
        margin-top: 5px;
        color: {TEXT_PRIMARY};
        font-size: 0.84rem;
    }}
    .cs-flow span {{
        margin-top: 3px;
        color: {TEXT_MUTED};
        font-size: 0.68rem;
        line-height: 1.4;
    }}

    .cs-stack-list > div {{
        display: grid;
        grid-template-columns: 120px minmax(0, 1fr) auto;
        align-items: center;
        gap: 18px;
        padding: 12px 0;
        border-top: 1px solid {CARD_BORDER_SUBTLE};
    }}
    .cs-stack-list strong {{ color: {TEXT_PRIMARY}; font-size: 0.85rem; }}
    .cs-stack-list span {{ color: {TEXT_SECONDARY}; font-size: 0.78rem; }}
    .cs-stack-list code {{
        padding: 3px 7px;
        border-radius: 5px;
        background: {CANVAS_SUBTLE};
        color: {TEXT_SECONDARY};
        font-family: var(--cs-font-mono);
        font-size: 0.64rem;
    }}

    .cs-overview-footer {{
        display: grid;
        grid-template-columns: 0.8fr 1.2fr 1.7fr;
        gap: 28px;
        padding: 20px 0 4px;
    }}
    .cs-overview-footer span,
    .cs-overview-footer strong {{ display: block; }}
    .cs-overview-footer span {{ color: {TEXT_MUTED}; font-size: 0.62rem; }}
    .cs-overview-footer strong {{
        margin-top: 5px;
        color: {TEXT_PRIMARY};
        font-size: 0.74rem;
        line-height: 1.45;
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
        transition: color var(--cs-duration-ui) var(--cs-ease-out), border-color var(--cs-duration-ui) var(--cs-ease-out), transform var(--cs-duration-fast) var(--cs-ease-out) !important;
    }}

    [data-testid="stRadio"] [role="radiogroup"] > label > div:first-child,
    [data-testid="stRadioGroup"] > label > div:first-child {{
        display: none !important;
    }}

    [data-testid="stRadioOption"] > div > div > div:first-child:not([data-testid="stMarkdownContainer"]) {{
        display: none !important;
    }}

    [data-testid="stRadio"] [role="radiogroup"] > label p,
    [data-testid="stRadioGroup"] > label p,
    [data-testid="stRadio"] [role="radiogroup"] > label span,
    [data-testid="stRadioGroup"] > label span {{
        color: #64748B !important;
        font-family: var(--cs-font-ui) !important;
        font-weight: 500 !important;
        font-size: 0.9rem !important;
        margin: 0 !important;
        transition: color var(--cs-duration-ui) var(--cs-ease-out) !important;
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
        font-family: var(--cs-font-ui) !important;
        font-weight: 600 !important;
        font-size: 0.85rem !important;
        border: 1px solid #0F172A !important;
        border-radius: 6px !important;
        padding: 6px 14px !important;
        box-shadow: 0 1px 2px 0 rgba(0, 0, 0, 0.05) !important;
        transition: transform var(--cs-duration-fast) var(--cs-ease-out), background-color var(--cs-duration-ui) var(--cs-ease-out), border-color var(--cs-duration-ui) var(--cs-ease-out), box-shadow var(--cs-duration-ui) var(--cs-ease-out) !important;
    }}

    .stButton > button:active, button[kind="primary"]:active, button[kind="secondary"]:active {{
        transform: scale(0.97) !important;
    }}

    button[kind="secondary"] {{
        background: #FFFFFF !important;
        color: {TEXT_PRIMARY} !important;
        border: 1px solid {CARD_BORDER} !important;
    }}
    .stButton > button:focus-visible,
    button[kind="primary"]:focus-visible,
    button[kind="secondary"]:focus-visible,
    [data-testid="stRadio"] [role="radiogroup"] > label:focus-within {{
        outline: 3px solid rgba(2, 132, 199, 0.25) !important;
        outline-offset: 2px !important;
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

    .cs-context-row {{
        display: flex;
        align-items: center;
        gap: 8px;
        margin: -8px 0 14px;
        font-family: var(--cs-font-mono);
        font-size: 0.66rem;
        font-weight: 700;
        letter-spacing: 0.045em;
    }}

    .cs-context-badge {{
        padding: 4px 8px;
        border-radius: 999px;
        border: 1px solid {ALPACA_YELLOW_BORDER};
        background: {ALPACA_YELLOW_BG};
        color: #854D0E;
    }}

    .cs-context-boundary {{
        color: {TEXT_MUTED};
    }}

    .cs-evidence-pending {{
        display: flex;
        align-items: center;
        gap: 8px;
        margin: 2px 0 22px;
        color: {TEXT_MUTED};
        font-family: var(--cs-font-mono);
        font-size: 0.72rem;
        letter-spacing: 0.015em;
    }}

    .cs-evidence-pending-dot {{
        width: 6px;
        height: 6px;
        flex: 0 0 6px;
        border-radius: 50%;
        background: #F59E0B;
    }}

    @keyframes cs-content-enter {{
        from {{ opacity: 0; transform: translateY(5px); }}
        to {{ opacity: 1; transform: translateY(0); }}
    }}

    .cs-decision-hero {{
        margin: 18px 0 10px;
        padding: 0 0 18px;
        border-bottom: 1px solid {CARD_BORDER};
        animation: cs-content-enter 220ms var(--cs-ease-out) both;
    }}

    .cs-decision-topline,
    .cs-instrument,
    .cs-section-heading,
    .cs-critic-strip {{
        display: flex;
        align-items: center;
    }}

    .cs-decision-topline {{
        justify-content: space-between;
        gap: 16px;
    }}

    .cs-instrument {{
        gap: 12px;
    }}

    .cs-symbol {{
        min-width: 52px;
        height: 42px;
        padding: 0 10px;
        display: inline-flex;
        align-items: center;
        justify-content: center;
        border-radius: 9px;
        border: 1px solid {BRAND_AMBER_BORDER};
        background: {BRAND_AMBER_BG};
        color: {BRAND_AMBER};
        font-family: var(--cs-font-mono);
        font-size: 0.9rem;
        font-weight: 800;
    }}

    .cs-spot {{
        color: {TEXT_PRIMARY};
        font-family: var(--cs-font-mono);
        font-size: 1.75rem;
        font-weight: 800;
        font-variant-numeric: tabular-nums;
        letter-spacing: -0.035em;
        line-height: 1.05;
    }}

    .cs-scenario-id {{
        margin-top: 3px;
        color: {TEXT_MUTED};
        font-family: var(--cs-font-mono);
        font-size: 0.66rem;
    }}

    .cs-thesis {{
        max-width: 960px;
        margin: 16px 0;
        color: #334155;
        font-size: 0.92rem;
        line-height: 1.55;
    }}

    .cs-thesis span {{
        display: block;
        margin-bottom: 4px;
        color: {TEXT_PRIMARY};
        font-family: var(--cs-font-mono);
        font-size: 0.68rem;
        font-weight: 800;
        letter-spacing: 0.055em;
    }}

    .cs-metric-strip {{
        display: grid;
        grid-template-columns: repeat(3, minmax(0, 1fr));
        border-top: 1px solid {CARD_BORDER_SUBTLE};
        border-bottom: 1px solid {CARD_BORDER_SUBTLE};
    }}

    .cs-metric {{
        padding: 13px 16px;
        border-right: 1px solid {CARD_BORDER_SUBTLE};
    }}

    .cs-metric:first-child {{ padding-left: 0; }}
    .cs-metric:last-child {{ border-right: 0; }}

    .cs-metric-label {{
        margin-bottom: 4px;
        color: {TEXT_MUTED};
        font-family: var(--cs-font-mono);
        font-size: 0.64rem;
        font-weight: 700;
        letter-spacing: 0.045em;
    }}

    .cs-metric-value {{
        font-family: var(--cs-font-mono);
        font-size: 1.35rem;
        font-weight: 800;
        font-variant-numeric: tabular-nums;
    }}

    .cs-metric-value small {{
        margin-left: 6px;
        color: {TEXT_MUTED};
        font-size: 0.62rem;
        font-weight: 600;
    }}

    .cs-metric-amber {{ color: {BRAND_AMBER}; }}
    .cs-metric-blue {{ color: {CYAN_ACCENT}; }}
    .cs-metric-red {{ color: {RED_LOSS}; }}

    .cs-runtime-proof {{
        display: flex;
        flex-wrap: wrap;
        gap: 7px;
        margin: 0 0 16px;
    }}

    .cs-runtime-proof span {{
        padding: 3px 7px;
        border-radius: 5px;
        background: {CANVAS_SUBTLE};
        color: {TEXT_SECONDARY};
        font-family: var(--cs-font-mono);
        font-size: 0.62rem;
        font-weight: 700;
    }}

    .cs-agent-section {{
        animation: cs-content-enter 240ms 40ms var(--cs-ease-out) both;
    }}

    .cs-section-heading {{
        justify-content: space-between;
        gap: 12px;
        margin-bottom: 10px;
        color: {TEXT_PRIMARY};
        font-family: var(--cs-font-mono);
        font-size: 0.72rem;
        font-weight: 800;
        letter-spacing: 0.045em;
    }}

    .cs-section-heading small {{
        color: {TEXT_MUTED};
        font-size: 0.64rem;
        font-weight: 600;
        letter-spacing: 0;
    }}

    .cs-agent-grid {{
        display: grid;
        grid-template-columns: repeat(2, minmax(0, 1fr));
        gap: 10px;
    }}

    .cs-agent-card {{
        min-height: 160px;
        padding: 15px;
        border: 1px solid {CARD_BORDER};
        border-radius: 10px;
        background: {CANVAS_BG};
    }}

    .cs-agent-label {{
        display: flex;
        align-items: center;
        gap: 7px;
        color: {TEXT_PRIMARY};
        font-family: var(--cs-font-mono);
        font-size: 0.66rem;
        font-weight: 800;
        letter-spacing: 0.035em;
    }}

    .cs-agent-label b {{
        margin-left: auto;
        font-size: 0.66rem;
    }}

    .cs-agent-dot {{
        width: 7px;
        height: 7px;
        border-radius: 999px;
    }}

    .cs-agent-long .cs-agent-dot {{ background: {CYAN_ACCENT}; }}
    .cs-agent-short .cs-agent-dot {{ background: {PURPLE_VOL}; }}

    .cs-agent-card p {{
        min-height: 62px;
        margin: 12px 0;
        color: {TEXT_SECONDARY} !important;
        font-size: 0.8rem;
        line-height: 1.45;
    }}

    .cs-agent-metrics {{
        display: flex;
        flex-wrap: wrap;
        gap: 6px;
    }}

    .cs-agent-metrics span {{
        padding: 3px 7px;
        border: 1px solid {CARD_BORDER};
        border-radius: 999px;
        color: {TEXT_SECONDARY};
        font-family: var(--cs-font-mono);
        font-size: 0.61rem;
        font-weight: 700;
    }}

    .cs-critic-strip {{
        display: grid;
        grid-template-columns: auto auto minmax(0, 1fr);
        gap: 10px;
        margin: 10px 0 14px;
        padding: 9px 11px;
        border: 1px solid {CARD_BORDER};
        border-radius: 8px;
        background: {CANVAS_SUBTLE};
        font-family: var(--cs-font-mono);
        font-size: 0.63rem;
    }}

    .cs-critic-strip span {{ color: {TEXT_SECONDARY}; font-weight: 800; }}
    .cs-critic-strip strong {{ font-weight: 800; }}
    .cs-critic-strip small {{ color: {TEXT_MUTED}; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }}
    .cs-critic-pass strong {{ color: {GREEN_PROFIT}; }}
    .cs-critic-fail strong {{ color: {RED_LOSS}; }}

    .cs-empty-payoff {{
        min-height: 190px;
        display: flex;
        flex-direction: column;
        align-items: center;
        justify-content: center;
        gap: 5px;
        margin-bottom: 16px;
        border: 1px dashed {RED_BORDER};
        border-radius: 10px;
        background: {RED_BG};
        font-family: var(--cs-font-mono);
        text-align: center;
    }}

    .cs-empty-payoff strong {{ color: {RED_LOSS}; font-size: 0.74rem; }}
    .cs-empty-payoff span {{ color: {TEXT_SECONDARY}; font-size: 0.66rem; }}

    /* Status Pills */
    .pill-badge {{
        display: inline-flex;
        align-items: center;
        font-family: var(--cs-font-mono);
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

    .cs-contract-table-wrap {{
        width: 100%;
        overflow-x: auto;
        -webkit-overflow-scrolling: touch;
    }}

    @media (hover: hover) and (pointer: fine) {{
        [data-testid="stRadio"] [role="radiogroup"] > label:hover p,
        [data-testid="stRadioGroup"] > label:hover p {{
            color: {TEXT_PRIMARY} !important;
        }}

        .stButton > button:hover,
        button[kind="primary"]:hover {{
            background: #1E293B !important;
            border-color: #1E293B !important;
            transform: translateY(-1px) !important;
        }}

        button[kind="secondary"]:hover {{
            background: {CANVAS_SUBTLE} !important;
            border-color: #CBD5E1 !important;
        }}
    }}

    @media (max-width: 900px) {{
        .block-container {{ padding: 0.8rem 1.25rem 3rem !important; }}
        .cs-judge-header {{ align-items: flex-start; flex-direction: column; }}
        .cs-status-pills {{ justify-content: flex-start; }}
        .cs-overview-stats {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
        .cs-overview-stats > div:nth-child(2) {{ border-right: 0; }}
        .cs-overview-stats > div:nth-child(-n+2) {{ border-bottom: 1px solid {CARD_BORDER_SUBTLE}; }}
        .cs-flow {{ grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 18px 0; }}
        .cs-stack-list > div {{ grid-template-columns: 100px minmax(0, 1fr); }}
        .cs-stack-list code {{ grid-column: 2; justify-self: start; }}
        .cs-overview-footer {{ grid-template-columns: 1fr; gap: 14px; }}
        [data-testid="stHorizontalBlock"] {{ flex-wrap: wrap !important; }}
        [data-testid="stHorizontalBlock"] > [data-testid="stColumn"] {{
            flex: 1 1 100% !important;
            width: 100% !important;
            min-width: 100% !important;
        }}
        .cs-agent-grid {{ grid-template-columns: 1fr; }}
        .cs-agent-card {{ min-height: 0; }}
        .cs-agent-card p {{ min-height: 0; }}
        .cs-critic-strip {{ grid-template-columns: auto auto; }}
        .cs-critic-strip small {{ grid-column: 1 / -1; white-space: normal; }}
    }}

    @media (min-width: 641px) and (max-width: 900px) {{
        .st-key-scenario_selector [data-testid="stHorizontalBlock"] {{
            flex-wrap: nowrap !important;
        }}
        .st-key-scenario_selector [data-testid="stHorizontalBlock"] > [data-testid="stColumn"] {{
            flex: 1 1 0 !important;
            width: auto !important;
            min-width: 0 !important;
        }}
        .st-key-scenario_selector .stButton > button {{
            padding-inline: 8px !important;
            font-size: 0.76rem !important;
        }}
    }}

    @media (max-width: 640px) {{
        .block-container {{ padding-inline: 0.95rem !important; }}
        .cs-subtitle {{ max-width: 29ch; }}
        .cs-status-pills {{ gap: 6px; }}
        .cs-proof-pill {{ font-size: 0.61rem; padding: 4px 7px; }}
        body [data-testid="stRadio"] [data-testid="stRadioGroup"] {{
            display: grid !important;
            grid-template-columns: repeat(2, minmax(0, 1fr)) !important;
            gap: 0 16px !important;
        }}
        [data-testid="stRadioOption"] {{ width: 100% !important; }}
        .cs-overview-hero {{ padding: 22px 0 20px; }}
        .cs-overview-hero h1 {{ font-size: 2.35rem !important; }}
        .cs-overview-hero > p {{ font-size: 0.88rem; }}
        .cs-overview-stats > div {{ padding: 12px 10px; }}
        .cs-overview-stats > div:nth-child(odd) {{ padding-left: 0; }}
        .cs-overview-stats strong {{ font-size: 1.1rem; }}
        .cs-overview-heading {{ display: block; }}
        .cs-overview-heading small {{ display: block; margin-top: 4px; }}
        .cs-flow {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
        .cs-flow > div:nth-child(2n)::after {{ display: none; }}
        .cs-stack-list > div {{ grid-template-columns: 1fr; gap: 4px; }}
        .cs-stack-list code {{ grid-column: 1; }}
        .cs-decision-topline {{ align-items: flex-start; flex-wrap: wrap; }}
        .cs-metric-strip {{ grid-template-columns: 1fr; }}
        .cs-metric {{ padding: 10px 0; border-right: 0; border-bottom: 1px solid {CARD_BORDER_SUBTLE}; }}
        .cs-metric:last-child {{ border-bottom: 0; }}
    }}

    .cs-validation {{
        max-width: 920px;
        padding: 22px 0;
    }}

    .cs-validation-strip {{
        display: grid;
        grid-template-columns: repeat(3, minmax(0, 1fr));
        border-top: 1px solid {CARD_BORDER};
        border-bottom: 1px solid {CARD_BORDER};
    }}

    .cs-validation-strip > div {{
        padding: 14px 18px;
        border-right: 1px solid {CARD_BORDER_SUBTLE};
    }}

    .cs-validation-strip > div:first-child {{ padding-left: 0; }}
    .cs-validation-strip > div:last-child {{ border-right: 0; }}
    .cs-validation-strip strong,
    .cs-validation-strip span {{ display: block; }}
    .cs-validation-strip strong {{
        color: {TEXT_PRIMARY};
        font-family: var(--cs-font-mono);
        font-size: 1.45rem;
        font-variant-numeric: tabular-nums;
    }}
    .cs-validation-strip span {{
        margin-top: 3px;
        color: {TEXT_MUTED};
        font-size: 0.7rem;
    }}

    @media (max-width: 640px) {{
        .block-container {{ padding: 0.65rem 0.9rem 2.5rem !important; }}
        .cs-judge-header {{ flex-direction: column; padding-bottom: 14px; }}
        .cs-status-pills {{ justify-content: flex-start; }}
        .cs-subtitle {{ max-width: 34rem; }}
        .cs-metric-strip {{ grid-template-columns: 1fr; }}
        .cs-metric {{ padding: 10px 0; border-right: 0; border-bottom: 1px solid {CARD_BORDER_SUBTLE}; }}
        .cs-metric:last-child {{ border-bottom: 0; }}
        .cs-section-heading {{ align-items: flex-start; flex-direction: column; gap: 2px; }}
        .cs-decision-topline {{ align-items: flex-start; }}
        .cs-scenario-id {{ max-width: 15rem; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }}
    }}

    @media (prefers-reduced-motion: reduce) {{
        *, *::before, *::after {{
            scroll-behavior: auto !important;
            animation-duration: 0.01ms !important;
            animation-iteration-count: 1 !important;
            transition-duration: 0.01ms !important;
        }}
    }}
</style>
"""
