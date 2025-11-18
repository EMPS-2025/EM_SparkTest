# app/app.py - Complete with OpenAI Insights & Custom UI Format
"""
EM Spark - Energy Market AI Assistant
With OpenAI-powered insights and custom UI formatting
"""

# >>> MUST BE FIRST LINES <<<
import os
import sys

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(THIS_DIR, ".."))

if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import traceback
from datetime import date, datetime
import dataclasses
from typing import Dict, List, Any, Optional, Tuple
import json

# Disable Chainlit persistence before importing Chainlit to avoid DB init errors
os.environ["CHAINLIT_DISABLE_PERSISTENCE"] = "true"

import chainlit as cl
from openai import OpenAI

# Import modules
from core.config import Config
from core.database import DatabaseManager
from parsers.bulletproof_parser import BulletproofParser
from parsers.smart_parser import SmartParser
from presenters.enhanced_response_builder import EnhancedResponseBuilder
from utils.formatters import (
    label_hour_ranges,
    label_slot_ranges,
)

PURCHASE_BID_KEYS = [
    'purchase_bid_avg',
    'purchase_bid',
    'purchase_bid_sum',
    'purchase_bid_total_mw',
    'purchase_bid_mw_sum',
    'purchase_bid_mw_total',
    'purchase_bid_txt',
    'purchase_bid_mw',
    'buy_bid_avg',
    'buy_bid_sum',
    'buy_bid_total_mw',
    'buy_bid_mw_sum',
]

SELL_BID_KEYS = [
    'sell_bid_avg',
    'sell_bid',
    'sell_bid_sum',
    'sell_bid_total_mw',
    'sell_bid_mw_sum',
    'sell_bid_mw_total',
    'sell_bid_txt',
    'sell_bid_mw',
    'sell_offer_avg',
    'sell_offer_sum',
    'sell_offer_total_mw',
    'sell_offer_mw_sum',
]


# ═══════════════════════════════════════════════════════════════
# DISABLE CHAINLIT PERSISTENCE
# ═══════════════════════════════════════════════════════════════

def disable_chainlit_data_layer():
    try:
        import chainlit.data as cl_data
        if hasattr(cl_data, '_data_layer'):
            cl_data._data_layer = None
            print("✓ Chainlit persistence disabled")
    except Exception as e:
        pass

disable_chainlit_data_layer()


# ═══════════════════════════════════════════════════════════════
# INITIALIZATION
# ═══════════════════════════════════════════════════════════════

config = Config()
db = DatabaseManager(config)

parser = BulletproofParser(config)

#parser = SmartParser(config)

response_builder = EnhancedResponseBuilder()

# Initialize OpenAI client
openai_client = None
if config.OPENAI_API_KEY:
    openai_client = OpenAI(api_key=config.OPENAI_API_KEY)
    print("✓ OpenAI client initialized")
else:
    print("⚠️  OpenAI API key not found - insights will be generic")


# ═══════════════════════════════════════════════════════════════
# CHAINLIT EVENT HANDLERS
# ═══════════════════════════════════════════════════════════════

@cl.on_chat_start
async def start_session():
    """Initialize user session."""
    
    await cl.Message(
        content="""# 👋 Welcome to EM-SPARK!

I'm your AI-powered energy market analyst. I can help you with:

- 📊 **DAM** - Day-Ahead Market analysis
- 🟢 **GDAM** - Green Day-Ahead Market
- 🔵 **RTM** - Real-Time Market

- 💹 **Derivatives** - MCX/NSE futures data
- 📈 **Market Comparisons** - Side-by-side analysis
- 📊 **Bid/Ask Insights** - Purchase & sell bid analytics

**Try asking:**
- "RTM rate for 15 Nov 2025"
- "DAM rate for 14 Nov 2025"
- "Compare DAM and GDAM for yesterday"

*Powered by OpenAI for intelligent insights* 🤖
"""
    ).send()


@cl.on_message
async def handle_message(msg: cl.Message):
    """Main message handler."""
    user_query = msg.content.strip()
    
    # Show progress
    progress_msg = cl.Message(content="🤖 Analyzing your query...")
    await progress_msg.send()
    
    try:
        # Parse query
        print(f"\n📝 Query: {user_query}")
        specs = parser.parse(user_query)
        
        if not specs:
            await progress_msg.remove()
            await send_error_message(user_query)
            return
        
        primary_spec = specs[0]
        print(f"✓ Parsed: {primary_spec}")
        
        # Update progress
        progress_msg.content = "📥 Fetching market data..."
        await progress_msg.update()
        
        # Fetch data for all three markets (for comparison)
        selection_details = describe_time_selection(primary_spec)
        all_market_data: Dict[str, Dict[str, Any]] = {}
        all_market_prev_year: Dict[str, Optional[Dict[str, Any]]] = {}

        for market in ["DAM", "GDAM", "RTM"]:
            market_spec = clone_spec_for_market(primary_spec, market)
            all_market_data[market] = fetch_market_data(market_spec)

            prev_year_spec = shift_spec_by_year(market_spec, -1)
            all_market_prev_year[market] = (
                fetch_market_data(prev_year_spec) if prev_year_spec else None
            )

        primary_data = all_market_data.get(primary_spec.market, {})

        # Update progress
        progress_msg.content = "🤖 Generating AI insights..."
        await progress_msg.update()

        # Build response with OpenAI insights
        response = await build_complete_response(
            primary_spec,
            primary_data,
            all_market_data,
            all_market_prev_year,
            selection_details,
            user_query
        )
        
        # Remove progress and send response
        await progress_msg.remove()
        
        await cl.Message(
            content=response
        ).send()
        
    except Exception as e:
        print(f"❌ Error: {e}")
        traceback.print_exc()
        
        try:
            await progress_msg.remove()
        except:
            pass
        
        await cl.Message(
            content=f"⚠️ An error occurred: {str(e)}\n\nPlease try rephrasing your query."
        ).send()


# ═══════════════════════════════════════════════════════════════
# DATA FETCHING & PROCESSING
# ═══════════════════════════════════════════════════════════════

def fetch_market_data(spec) -> Dict[str, Any]:
    """Fetch market data for the requested period and compute KPIs."""

    if not spec:
        return empty_market_payload()

    try:
        if spec.granularity == "quarter" or (spec.slots and len(spec.slots) > 0):
            rows = db.fetch_quarter(
                spec.market,
                spec.start_date,
                spec.end_date,
                None,
                None,
            )
        else:
            rows = db.fetch_hourly(
                spec.market,
                spec.start_date,
                spec.end_date,
                None,
                None,
            )

        if not rows:
            print(f"⚠️  No data found for {spec.market} between {spec.start_date} and {spec.end_date}")
            return empty_market_payload()

        filtered_rows = filter_rows_by_time(rows, spec)
        if not filtered_rows:
            print(f"⚠️  No rows left after filtering time selection for {spec.market}")
            return empty_market_payload()

        metrics = compute_market_metrics(filtered_rows, spec)
        metrics['rows'] = filtered_rows

        print(
            "✓ Processed {market}: TWAP=₹{twap:.4f}, Vol={vol:.2f} GWh, Purchase={purchase:,.0f} MW, "
            "Sell={sell:,.0f} MW".format(
                market=spec.market,
                twap=metrics['twap'],
                vol=metrics['total_volume_gwh'],
                purchase=metrics['purchase_bid_total_mw'],
                sell=metrics['sell_bid_total_mw'],
            )
        )

        return metrics

    except Exception as e:
        print(f"❌ Error fetching data for {getattr(spec, 'market', 'N/A')}: {e}")
        traceback.print_exc()
        return empty_market_payload()


def empty_market_payload() -> Dict[str, Any]:
    """Return a default payload when data is missing."""
    return {
        'twap': 0.0,
        'min_price': 0.0,
        'max_price': 0.0,
        'total_volume_gwh': 0.0,
        'purchase_bid_total_mw': 0.0,
        'sell_bid_total_mw': 0.0,
        'scheduled_total_mw': 0.0,
        'mcv_total_mw': 0.0,
        'duration_hours': 0.0,
        'rows': [],
    }


def filter_rows_by_time(rows: List[Dict[str, Any]], spec) -> List[Dict[str, Any]]:
    """Filter DB rows so they respect the requested hour/slot selection."""

    if spec.granularity == "quarter" or (spec.slots and len(spec.slots) > 0):
        allowed_slots = set(spec.slots or range(1, 97))
        filtered = []
        for row in rows:
            slot = _extract_int(row, ['slot_index', 'slot_no', 'slot'])
            if slot is None:
                block = _extract_int(row, ['block_index', 'block_no', 'delivery_block'])
                if block is not None:
                    slot = (max(1, block) - 1) * 4 + 1

            if slot in allowed_slots:
                filtered.append(row)
        return filtered

    allowed_hours = set(spec.hours or range(1, 25))
    filtered = []
    for row in rows:
        block = _extract_int(
            row,
            [
                'block_index',
                'block_no',
                'delivery_block',
                'hour_block',
                'hour_txt',
                'time_block_txt',
            ],
        )
        if block in allowed_hours:
            filtered.append(row)
    return filtered


def compute_market_metrics(rows: List[Dict[str, Any]], spec) -> Dict[str, Any]:
    """Calculate TWAP, extremes, bid totals, and volumes."""

    prices_kwh: List[float] = []
    minute_total = 0.0
    price_weight = 0.0
    volume_mwh = 0.0
    purchase_total = 0.0
    sell_total = 0.0
    scheduled_total = 0.0
    mcv_total = 0.0
    default_duration = 15 if spec.granularity == "quarter" else 60

    for row in rows:
        duration_min = float(row.get('duration_min') or default_duration)
        price_mwh = _extract_float(
            row,
            [
                'price_avg_rs_per_mwh',
                'price_rs_per_mwh',
                'price_rs_per_mw',
                'mcp_rs_per_mwh',
            ],
        )
        price_kwh = price_mwh / 1000.0 if price_mwh else 0.0
        duration_hours = duration_min / 60.0

        prices_kwh.append(price_kwh)
        price_weight += price_kwh * duration_min
        minute_total += duration_min

        scheduled_mw = _extract_float(
            row,
            ['scheduled_mw_sum', 'scheduled_mw', 'cleared_volume_mw', 'scheduled_mw_txt'],
        )
        purchase_bid = _extract_float(row, PURCHASE_BID_KEYS)
        sell_bid = _extract_float(row, SELL_BID_KEYS)
        mcv = _extract_float(row, ['mcv_sum', 'mcv', 'mcv_txt'])

        volume_mwh += scheduled_mw * duration_hours
        purchase_total += purchase_bid * duration_hours
        sell_total += sell_bid * duration_hours
        scheduled_total += scheduled_mw * duration_hours
        mcv_total += mcv * duration_hours

    twap = (price_weight / minute_total) if minute_total else 0.0
    min_price = min(prices_kwh) if prices_kwh else 0.0
    max_price = max(prices_kwh) if prices_kwh else 0.0

    return {
        'twap': twap,
        'min_price': min_price,
        'max_price': max_price,
        'total_volume_gwh': volume_mwh / 1000.0,
        'purchase_bid_total_mw': purchase_total,
        'sell_bid_total_mw': sell_total,
        'scheduled_total_mw': scheduled_total,
        'mcv_total_mw': mcv_total,
        'duration_hours': minute_total / 60.0,
    }


def _extract_int(row: Dict[str, Any], keys: List[str]) -> Optional[int]:
    for key in keys:
        value = row.get(key)
        if value is None:
            continue
        try:
            return int(value)
        except (TypeError, ValueError):
            continue
    return None


def _extract_float(row: Dict[str, Any], keys: List[str], default: float = 0.0) -> float:
    for key in keys:
        value = row.get(key)
        if value is None:
            continue
        try:
            return float(value)
        except (TypeError, ValueError):
            continue
    lowered_items = list(row.items())
    for key in keys:
        target = key.lower()
        for actual_key, value in lowered_items:
            if value is None:
                continue
            actual_key_str = str(actual_key)
            if actual_key_str.lower() == target:
                continue
            if target in actual_key_str.lower():
                try:
                    return float(value)
                except (TypeError, ValueError):
                    continue
    return default


async def build_complete_response(
    spec,
    primary_data: Dict[str, Any],
    all_market_data: Dict[str, Dict[str, Any]],
    all_market_prev_year: Dict[str, Optional[Dict[str, Any]]],
    selection_details: Dict[str, Any],
    user_query: str
) -> str:
    """Build complete response with OpenAI insights and Tailwind-friendly HTML."""

    date_label = format_date_range(spec.start_date, spec.end_date)
    market_badge = {"DAM": "📊 Spot Market (DAM)", "GDAM": "🟢 Spot Market (GDAM)", "RTM": "🔵 Spot Market (RTM)"}.get(spec.market, "📊 Spot Market")

    hero = response_builder.build_overview_header(
        market_badge=market_badge,
        date_label=date_label,
        selection_details=selection_details,
        user_query=user_query,
    )

    snapshot = response_builder.build_snapshot_card(
        market=spec.market,
        delivery_label=date_label,
        time_window=selection_details['time_label'],
        twap=primary_data.get('twap', 0.0),
        min_price=primary_data.get('min_price', 0.0),
        max_price=primary_data.get('max_price', 0.0),
        total_volume_gwh=primary_data.get('total_volume_gwh', 0.0),
    )

    comparison = response_builder.build_market_comparison_section(
        spec_year=spec.start_date.year,
        current_year_data=all_market_data,
        previous_year_data=all_market_prev_year,
    )

    bids = response_builder.build_bid_analysis_section(all_market_data)

    insights_list = await generate_ai_insights(
        user_query,
        spec,
        primary_data,
        all_market_data,
        selection_details,
        all_market_prev_year,
    )

    insights = response_builder.build_ai_insights_section(insights_list)

    return response_builder.compose_dashboard([
        hero,
        snapshot,
        comparison,
        bids,
        insights,
    ])


async def generate_ai_insights(
    user_query: str,
    spec,
    primary_data: Dict[str, Any],
    all_market_data: Dict[str, Dict[str, Any]],
    selection_details: Dict[str, Any],
    all_market_prev_year: Dict[str, Optional[Dict[str, Any]]],
) -> List[str]:
    """Generate OpenAI-powered market insights as bullet points."""

    fallback = build_default_insights(spec, all_market_data, selection_details)

    if not openai_client:
        return fallback

    try:
        def fmt_market_line(market: str) -> str:
            data = all_market_data.get(market, {})
            prev = (all_market_prev_year.get(market) or {}) if all_market_prev_year else {}
            price = data.get('twap', 0.0)
            volume = data.get('total_volume_gwh', 0.0)
            prev_price = prev.get('twap', 0.0)
            prev_volume = prev.get('total_volume_gwh', 0.0)
            yoy = ((price - prev_price) / prev_price * 100) if prev_price else 0.0
            return (
                f"- {market} price ₹{price:.2f}/kWh (YoY {yoy:+.1f}%), "
                f"volume {volume:.1f} GWh (prev {prev_volume:.1f} GWh)"
            )

        summary_lines = "\n".join(fmt_market_line(m) for m in ["DAM", "GDAM", "RTM"])

        bid_summary = "\n".join(
            f"- {m}: buy {all_market_data.get(m, {}).get('purchase_bid_total_mw', 0):,.0f} MW, sell {all_market_data.get(m, {}).get('sell_bid_total_mw', 0):,.0f} MW"
            for m in ["DAM", "GDAM", "RTM"]
        )

        prompt = f"""You are an expert energy market analyst for India's power exchanges.

User query: {user_query}
Delivery window: {selection_details['time_label']} ({selection_details['duration_hours']} hrs)

Market snapshots:\n{summary_lines}

Bid stack summary:\n{bid_summary}

Provide four crisp insights covering price trends, volume signals, GDAM vs DAM premium/discount, and procurement guidance. Each bullet must start with an emoji or bold tag, be data-driven, and stay under two sentences."""

        print("📤 Calling OpenAI for insights...")
        response = openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are an expert energy market analyst providing concise, data-driven insights."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.6,
            max_tokens=320,
        )

        raw_text = response.choices[0].message.content.strip()
        bullets = parse_bullets(raw_text)
        print(f"✓ OpenAI insights generated (tokens: {response.usage.total_tokens})")
        return bullets or fallback

    except Exception as e:
        print(f"⚠️  OpenAI API error: {e}")
        return fallback


def build_default_insights(spec, all_market_data, selection_details) -> List[str]:
    dam = all_market_data.get('DAM', {})
    gdam = all_market_data.get('GDAM', {})
    rtm = all_market_data.get('RTM', {})

    dam_price = dam.get('twap', 0.0)
    gdam_price = gdam.get('twap', 0.0)
    rtm_price = rtm.get('twap', 0.0)

    dam_vol = dam.get('total_volume_gwh', 0.0)
    gdam_vol = gdam.get('total_volume_gwh', 0.0)
    rtm_vol = rtm.get('total_volume_gwh', 0.0)

    gdam_premium = ((gdam_price - dam_price) / dam_price * 100) if dam_price else 0.0

    return [
        f"📊 DAM TWAP at ₹{dam_price:.2f}/kWh with {dam_vol:.1f} GWh cleared across {selection_details['time_label']}.",
        f"🟢 GDAM is {gdam_premium:+.1f}% vs DAM (₹{gdam_price:.2f}/kWh) with {gdam_vol:.1f} GWh of green energy.",
        f"🔵 RTM balances the grid at ₹{rtm_price:.2f}/kWh and {rtm_vol:.1f} GWh, signalling intraday volatility.",
        "🧭 Diversify procurement across DAM for value, GDAM for renewable tags, and RTM for fine-tuning schedules.",
    ]


def parse_bullets(text: str) -> List[str]:
    bullets: List[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped[0] in {'•', '-', '*'}:
            stripped = stripped[1:].strip()
        bullets.append(stripped)
    if not bullets and text.strip():
        bullets.append(text.strip())
    return bullets


def describe_time_selection(spec) -> Dict[str, Any]:
    if spec.granularity == "quarter" and spec.slots:
        slots = sorted(set(spec.slots))
        time_label, index_label, count = label_slot_ranges(slots)
        duration_hours = count * 0.25
        pretty_label = f"{time_label} hrs (All India)"
    else:
        hours = sorted(set(spec.hours or list(range(1, 25))))
        time_label, index_label, count = label_hour_ranges(hours)
        if count >= 24:
            pretty_label = "00:00–24:00 hrs (All India)"
        else:
            pretty_label = f"{time_label} hrs (All India)"
        duration_hours = float(count)

    return {
        'time_label': pretty_label,
        'index_label': index_label,
        'duration_hours': round(duration_hours, 2),
    }


def format_date_range(start: date, end: date) -> str:
    if start == end:
        return start.strftime("%d %b %Y")
    if start.year == end.year:
        if start.month == end.month:
            return f"{start.strftime('%d')}–{end.strftime('%d %b %Y')}"
        return f"{start.strftime('%d %b')} – {end.strftime('%d %b %Y')}"
    return f"{start.strftime('%d %b %Y')} – {end.strftime('%d %b %Y')}"


def clone_spec_for_market(spec, market: str):
    return dataclasses.replace(spec, market=market)


def shift_spec_by_year(spec, years: int):
    if not spec:
        return None
    start = _shift_date_safe(spec.start_date, years)
    end = _shift_date_safe(spec.end_date, years)
    if not start or not end:
        return None
    return dataclasses.replace(spec, start_date=start, end_date=end)


def _shift_date_safe(original: date, years: int) -> Optional[date]:
    try:
        return original.replace(year=original.year + years)
    except ValueError:
        if original.month == 2 and original.day == 29:
            return original.replace(year=original.year + years, day=28)
        return None


async def send_error_message(query: str):
    """Send helpful error message."""
    await cl.Message(
        content=f"""⚠️ I couldn't understand your query: "{query}"

**Try these examples:**

✅ **Simple queries:**
- `DAM rate for 14 Nov 2025`
- `GDAM today`
- `RTM yesterday`
- `RTM rate for 15 Nov 2025`

✅ **Time ranges:**
- `DAM for 8-9 hrs on 14 Nov 2025`
- `RTM for 5-9 hrs for 25 Sept 2025`

*I use AI to understand natural language queries!* 🤖
"""
    ).send()


# ═══════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("✓ EM-SPARK Application Ready with OpenAI Insights!")