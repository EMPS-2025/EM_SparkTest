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
from typing import Dict, List, Any, Optional
import json

import chainlit as cl
from openai import OpenAI

# Import modules
from core.config import Config
from core.database import DatabaseManager
from parsers.bulletproof_parser import BulletproofParser
from presenters.enhanced_response_builder import EnhancedResponseBuilder, format_time_range


# ═══════════════════════════════════════════════════════════════
# DISABLE CHAINLIT PERSISTENCE
# ═══════════════════════════════════════════════════════════════

os.environ["CHAINLIT_DISABLE_PERSISTENCE"] = "true"

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
parser = BulletproofParser()
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
        all_market_data = {}
        for market in ["DAM", "GDAM", "RTM"]:
            from core.models import QuerySpec
            market_spec = QuerySpec(
                market=market,
                start_date=primary_spec.start_date,
                end_date=primary_spec.end_date,
                granularity=primary_spec.granularity,
                hours=primary_spec.hours,
                slots=primary_spec.slots,
                stat=primary_spec.stat
            )
            all_market_data[market] = fetch_market_data(market_spec)
        
        primary_data = all_market_data[primary_spec.market]
        
        # Update progress
        progress_msg.content = "🤖 Generating AI insights..."
        await progress_msg.update()
        
        # Build response with OpenAI insights
        response = await build_complete_response(
            primary_spec,
            primary_data,
            all_market_data,
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
    """Fetch and process market data - FIXED with correct aggregations."""
    
    try:
        # Fetch hourly data
        rows = db.fetch_hourly(
            spec.market,
            spec.start_date,
            spec.end_date,
            None,
            None
        )
        
        if not rows:
            print(f"⚠️  No data found for {spec.market} on {spec.start_date}")
            return {
                'twap': 0,
                'min_price': 0,
                'max_price': 0,
                'total_volume_gwh': 0,
                'purchase_bid_total_mw': 0,
                'sell_bid_total_mw': 0,
                'scheduled_total_mw': 0,
                'mcv_total_mw': 0,
                'rows': []
            }
        
        # Calculate metrics - FIXED
        prices = [float(r['price_avg_rs_per_mwh']) / 1000.0 for r in rows if r.get('price_avg_rs_per_mwh')]
        
        twap = sum(prices) / len(prices) if prices else 0
        min_price = min(prices) if prices else 0
        max_price = max(prices) if prices else 0
        
        # Volume calculation (MW * hours) -> MWh -> GWh
        total_volume_mwh = sum(
            float(r.get('scheduled_mw_sum', 0) or 0)
            for r in rows
        )
        total_volume_gwh = total_volume_mwh / 1000.0
        
        # FIXED: Bids and MCV should be SUMMED, not averaged!
        purchase_bid_total = sum(float(r.get('purchase_bid_avg', 0) or 0) for r in rows)
        sell_bid_total = sum(float(r.get('sell_bid_avg', 0) or 0) for r in rows)
        mcv_total = sum(float(r.get('mcv_sum', 0) or 0) for r in rows)
        scheduled_total = sum(float(r.get('scheduled_mw_sum', 0) or 0) for r in rows)
        
        print(f"✓ Processed {spec.market}: TWAP=₹{twap:.4f}, Vol={total_volume_gwh:.2f}GWh, "
              f"PurchaseBid={purchase_bid_total:.0f}MW, SellBid={sell_bid_total:.0f}MW")
        
        return {
            'twap': twap,
            'min_price': min_price,
            'max_price': max_price,
            'total_volume_gwh': total_volume_gwh,
            'purchase_bid_total_mw': purchase_bid_total,
            'sell_bid_total_mw': sell_bid_total,
            'scheduled_total_mw': scheduled_total,
            'mcv_total_mw': mcv_total,
            'rows': rows
        }
        
    except Exception as e:
        print(f"❌ Error fetching data for {spec.market}: {e}")
        traceback.print_exc()
        return {
            'twap': 0,
            'min_price': 0,
            'max_price': 0,
            'total_volume_gwh': 0,
            'purchase_bid_total_mw': 0,
            'sell_bid_total_mw': 0,
            'scheduled_total_mw': 0,
            'mcv_total_mw': 0,
            'rows': []
        }


async def build_complete_response(
    spec,
    primary_data: Dict[str, Any],
    all_market_data: Dict[str, Dict[str, Any]],
    user_query: str
) -> str:
    """Build complete response with OpenAI insights."""
    
    # Market emoji
    market_emoji = {"DAM": "📊", "GDAM": "🟢", "RTM": "🔵"}.get(spec.market, "📊")
    
    # Time range
    time_range = format_time_range(spec.hours if spec.hours else list(range(1, 25)))
    
    # 1. Snapshot Card
    date_str = spec.start_date.strftime("%d %b %Y")
    
    snapshot = f"""## {market_emoji} {spec.market} Snapshot - {date_str}
{time_range}

**TWAP Price**  
₹{primary_data['twap']:.2f} /kWh

**Min / Max Block Price**  
₹{primary_data['min_price']:.2f} / ₹{primary_data['max_price']:.2f} /kWh

**Total Cleared Volume**  
{primary_data['total_volume_gwh']:.1f} GWh

---
"""
    
    # 2. Market Comparison Table
    comparison = f"""## 📊 Market Comparison · {spec.start_date.year} vs {spec.start_date.year - 1}
Volumes (GWh) and average prices (₹/kWh)

| Market | Volume {spec.start_date.year} | Volume {spec.start_date.year - 1} | Price {spec.start_date.year} | Price {spec.start_date.year - 1} | YoY Δ |
|--------|------------------------------|------------------------------|------------------------------|------------------------------|--------|
| 📊 DAM | {all_market_data.get('DAM', {}).get('total_volume_gwh', 0):.2f} GWh | 0.00 GWh | ₹{all_market_data.get('DAM', {}).get('twap', 0):.4f} /kWh | ₹0.0000 /kWh | — |
| 🟢 GDAM | {all_market_data.get('GDAM', {}).get('total_volume_gwh', 0):.2f} GWh | 0.00 GWh | ₹{all_market_data.get('GDAM', {}).get('twap', 0):.4f} /kWh | ₹0.0000 /kWh | — |
| 🔵 RTM | {all_market_data.get('RTM', {}).get('total_volume_gwh', 0):.2f} GWh | 0.00 GWh | ₹{all_market_data.get('RTM', {}).get('twap', 0):.4f} /kWh | ₹0.0000 /kWh | — |

---
"""
    
    # 3. Bid Analysis Section - FIXED with correct values
    dam_data = all_market_data.get('DAM', {})
    gdam_data = all_market_data.get('GDAM', {})
    rtm_data = all_market_data.get('RTM', {})
    
    dam_purchase = dam_data.get('purchase_bid_total_mw', 0)
    dam_sell = dam_data.get('sell_bid_total_mw', 0)
    dam_scheduled = dam_data.get('scheduled_total_mw', 0)
    
    gdam_purchase = gdam_data.get('purchase_bid_total_mw', 0)
    gdam_sell = gdam_data.get('sell_bid_total_mw', 0)
    gdam_scheduled = gdam_data.get('scheduled_total_mw', 0)
    
    rtm_purchase = rtm_data.get('purchase_bid_total_mw', 0)
    rtm_sell = rtm_data.get('sell_bid_total_mw', 0)
    rtm_scheduled = rtm_data.get('scheduled_total_mw', 0)
    
    # Calculate bid ratios
    dam_ratio = dam_purchase / dam_sell if dam_sell > 0 else 0
    gdam_ratio = gdam_purchase / gdam_sell if gdam_sell > 0 else 0
    rtm_ratio = rtm_purchase / rtm_sell if rtm_sell > 0 else 0
    
    # Determine market tightness
    avg_ratio = (dam_ratio + gdam_ratio + rtm_ratio) / 3 if (dam_ratio or gdam_ratio or rtm_ratio) else 0
    if avg_ratio > 1.0:
        tightness = "**Market Tightness: Slightly Tight** (Sell pressure exceeds buy)"
    elif avg_ratio > 0.9:
        tightness = "**Market Tightness: Balanced**"
    else:
        tightness = "**Market Tightness: Slightly Loose** (Sell pressure exceeds buy)"
    
    bid_analysis = f"""## 📊 Market Bids & Scheduling Analysis

**PURCHASE BIDS (MW)**
• **DAM:** {dam_purchase:,.0f} MW
• **GDAM:** {gdam_purchase:,.0f} MW
• **RTM:** {rtm_purchase:,.0f} MW

**SELL BIDS (MW)**
• **DAM:** {dam_sell:,.0f} MW
• **GDAM:** {gdam_sell:,.0f} MW
• **RTM:** {rtm_sell:,.0f} MW

**SCHEDULED MW & BID RATIO**
• **Scheduled:** DAM {dam_scheduled:,.0f} · GDAM {gdam_scheduled:,.0f} · RTM {rtm_scheduled:,.0f}
• **Bid Ratio (Buy/Sell):** DAM {dam_ratio:.2f} · GDAM {gdam_ratio:.2f} · RTM {rtm_ratio:.2f}

{tightness}

---
"""
    
    # 4. OpenAI-Powered Insights
    ai_insights = await generate_ai_insights(
        user_query,
        spec,
        primary_data,
        all_market_data
    )
    
    # Combine all sections
    return f"{snapshot}{comparison}{bid_analysis}{ai_insights}"


async def generate_ai_insights(
    user_query: str,
    spec,
    primary_data: Dict[str, Any],
    all_market_data: Dict[str, Dict[str, Any]]
) -> str:
    """Generate OpenAI-powered market insights."""
    
    if not openai_client:
        # Fallback to generic insights
        return """## 🤖 EM-SPARK AI INSIGHTS

• **DAM prices remain moderate**, with intraday volatility driven by evening peak demand.

• **GDAM continues to gain share**, reflecting strong renewable sell-side participation.

• **RTM volumes and bid ratios indicate active balancing activity**, but with slightly loose overall market conditions.

---
"""
    
    try:
        # Prepare market data for OpenAI
        dam_price = all_market_data.get('DAM', {}).get('twap', 0)
        gdam_price = all_market_data.get('GDAM', {}).get('twap', 0)
        rtm_price = all_market_data.get('RTM', {}).get('twap', 0)
        
        dam_vol = all_market_data.get('DAM', {}).get('total_volume_gwh', 0)
        gdam_vol = all_market_data.get('GDAM', {}).get('total_volume_gwh', 0)
        rtm_vol = all_market_data.get('RTM', {}).get('total_volume_gwh', 0)
        
        # Calculate key metrics
        if dam_price > 0 and gdam_price > 0:
            gdam_premium = ((gdam_price - dam_price) / dam_price) * 100
        else:
            gdam_premium = 0
        
        prompt = f"""You are an expert energy market analyst. Analyze the following Indian energy market data and provide 3-4 concise, actionable insights in bullet points.

Market Data for {spec.start_date.strftime('%d %b %Y')}:
- DAM Price: ₹{dam_price:.4f}/kWh, Volume: {dam_vol:.1f} GWh
- GDAM Price: ₹{gdam_price:.4f}/kWh, Volume: {gdam_vol:.1f} GWh (GDAM Premium: {gdam_premium:+.1f}%)
- RTM Price: ₹{rtm_price:.4f}/kWh, Volume: {rtm_vol:.1f} GWh

Purchase Bids (MW):
- DAM: {all_market_data.get('DAM', {}).get('purchase_bid_total_mw', 0):,.0f}
- GDAM: {all_market_data.get('GDAM', {}).get('purchase_bid_total_mw', 0):,.0f}
- RTM: {all_market_data.get('RTM', {}).get('purchase_bid_total_mw', 0):,.0f}

Provide insights on:
1. Price trends and volatility
2. Volume patterns
3. GDAM vs DAM comparison (is GDAM cheaper or more expensive? By how much?)
4. Procurement recommendations

Format as bullet points starting with "•". Keep each point to 1-2 sentences. Be specific with numbers."""

        print("📤 Calling OpenAI for insights...")
        
        response = openai_client.chat.completions.create(
            model="gpt-4o-mini",  # Using cost-effective model
            messages=[
                {"role": "system", "content": "You are an expert energy market analyst providing concise, data-driven insights."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7,
            max_tokens=300
        )
        
        insights_text = response.choices[0].message.content.strip()
        
        print(f"✓ OpenAI insights generated (tokens: {response.usage.total_tokens})")
        
        return f"""## 🤖 EM-SPARK AI INSIGHTS

{insights_text}

---
"""
    
    except Exception as e:
        print(f"⚠️  OpenAI API error: {e}")
        # Fallback to generic insights
        return """## 🤖 EM-SPARK AI INSIGHTS

• **DAM prices remain moderate**, with intraday volatility driven by evening peak demand.

• **GDAM continues to gain share**, reflecting strong renewable sell-side participation.

• **RTM volumes and bid ratios indicate active balancing activity**.

---
"""


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