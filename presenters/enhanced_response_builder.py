# presenters/enhanced_response_builder.py
"""
Response builder that matches the desired UI format with:
- Snapshot cards
- Market comparison tables
- Bid/Ask analysis
- AI insights
"""

from datetime import date
from typing import List, Dict, Optional, Any
from core.models import QuerySpec


class EnhancedResponseBuilder:
    """Build responses matching the exact UI format shown in mockups."""
    
    def build_snapshot_card(
        self,
        market: str,
        delivery_date: date,
        twap: float,
        min_price: float,
        max_price: float,
        total_volume_gwh: float,
        time_range: str = "00:00 - 24:00 hrs (All India)"
    ) -> str:
        """
        Build DAM/GDAM/RTM Snapshot card.
        
        Format:
        DAM Snapshot - 14 Nov 2025
        00:00 - 24:00 hrs (All India)
        
        TWAP Price: ₹4.32 /kWh
        Min / Max Block Price: ₹2.60 / ₹8.10 /kWh
        Total Cleared Volume: 780.4 GWh
        """
        
        market_emoji = {"DAM": "📊", "GDAM": "🟢", "RTM": "🔵"}.get(market, "📊")
        market_label = "Spot Market (DAM)" if market == "DAM" else f"Spot Market ({market})"
        
        date_str = delivery_date.strftime("%d %b %Y")
        
        card = f"""## {market_emoji} {market} Snapshot - {date_str}
{time_range}

**TWAP Price**  
₹{twap:.2f} /kWh

**Min / Max Block Price**  
₹{min_price:.2f} / ₹{max_price:.2f} /kWh

**Total Cleared Volume**  
{total_volume_gwh:.1f} GWh

---
"""
        return card
    
    def build_derivative_section(
        self,
        delivery_date: date,
        mcx_price: Optional[float],
        nse_price: Optional[float],
        contract_month: Optional[date] = None
    ) -> str:
        """
        Build Derivative Market section.
        
        Format:
        ### Derivative Market - 14 Nov 2025
        MCX / NSE - showing last close per exchange
        
        MCX · ELECMBL · Nov 2025: ₹2.95 /kWh
        NSE · ELECMBL · Nov 2025: ₹3.14 /kWh
        """
        
        date_str = delivery_date.strftime("%d %b %Y")
        
        if not mcx_price and not nse_price:
            return f"""### **Derivative Market - {date_str}**
MCX / NSE - showing last close per exchange

_Derivative market data not available for this period._

---
"""
        
        lines = [f"### **Derivative Market - {date_str}**"]
        lines.append("MCX / NSE - showing last close per exchange\n")
        
        if contract_month:
            month_str = contract_month.strftime("%b %Y")
        else:
            month_str = delivery_date.strftime("%b %Y")
        
        if mcx_price:
            lines.append(f"**MCX · ELECMBL · {month_str}:** ₹{mcx_price:.2f} /kWh")
        
        if nse_price:
            lines.append(f"**NSE · ELECMBL · {month_str}:** ₹{nse_price:.2f} /kWh")
        
        lines.append("\n_Futures are trading below DAM TWAP, indicating weaker forward sentiment vs current spot prices._\n")
        lines.append("---")
        
        return "\n".join(lines)
    
    def build_market_comparison_table(
        self,
        dam_data: Dict[str, Any],
        gdam_data: Dict[str, Any],
        rtm_data: Dict[str, Any],
        year_current: int = 2024,
        year_previous: int = 2023
    ) -> str:
        """
        Build Market Comparison table.
        
        Format:
        ## Market Comparison · 2024 vs 2023
        Volumes (GWh) and average prices (₹/kWh)
        
        | Market | Volume 2024 | Volume 2023 | Price 2024 | Price 2023 | YoY Δ |
        """
        
        card = f"""## 📊 Market Comparison · {year_current} vs {year_previous}
Volumes (GWh) and average prices (₹/kWh)

| Market | Volume {year_current} | Volume {year_previous} | Price {year_current} | Price {year_previous} | YoY Δ |
|--------|----------------------|----------------------|---------------------|---------------------|--------|
"""
        
        # DAM row
        if dam_data:
            card += self._build_comparison_row("📊 DAM", dam_data)
        
        # GDAM row
        if gdam_data:
            card += self._build_comparison_row("🟢 GDAM", gdam_data)
        
        # RTM row
        if rtm_data:
            card += self._build_comparison_row("🔵 RTM", rtm_data)
        
        card += "\n---\n"
        return card
    
    def _build_comparison_row(self, market_label: str, data: Dict[str, Any]) -> str:
        """Build a single row for comparison table."""
        
        vol_current = data.get('volume_current_gwh', 0)
        vol_previous = data.get('volume_previous_gwh', 0)
        price_current = data.get('price_current', 0)
        price_previous = data.get('price_previous', 0)
        
        # Calculate YoY change
        if price_previous > 0:
            yoy_change = ((price_current - price_previous) / price_previous) * 100
            arrow = "🔺" if yoy_change > 0 else "🔻"
            yoy_str = f"{arrow} {abs(yoy_change):.1f}%"
        else:
            yoy_str = "—"
        
        return (
            f"| {market_label} | {vol_current:,.2f} GWh | {vol_previous:,.2f} GWh | "
            f"₹{price_current:.4f} /kWh | ₹{price_previous:.4f} /kWh | {yoy_str} |\n"
        )
    
    def build_bid_analysis_section(
        self,
        dam_purchase: float,
        dam_sell: float,
        dam_scheduled: float,
        gdam_purchase: float,
        gdam_sell: float,
        gdam_scheduled: float,
        rtm_purchase: float,
        rtm_sell: float,
        rtm_scheduled: float,
    ) -> str:
        """
        Build Purchase/Sell Bids and Scheduled MW section.
        
        Format:
        ### PURCHASE BIDS (MW) | SELL BIDS (MW) | SCHEDULED MW & BID RATIO
        """
        
        # Calculate bid ratios
        dam_ratio = dam_purchase / dam_sell if dam_sell > 0 else 0
        gdam_ratio = gdam_purchase / gdam_sell if gdam_sell > 0 else 0
        rtm_ratio = rtm_purchase / rtm_sell if rtm_sell > 0 else 0
        
        # Determine market tightness
        avg_ratio = (dam_ratio + gdam_ratio + rtm_ratio) / 3
        if avg_ratio > 1.0:
            tightness = "**Market Tightness: Slightly Tight** (Buy pressure exceeds sell)"
        elif avg_ratio > 0.9:
            tightness = "**Market Tightness: Balanced**"
        else:
            tightness = "**Market Tightness: Slightly Loose** (Sell pressure exceeds buy)"
        
        card = f"""### 📊 Market Bids & Scheduling Analysis

**PURCHASE BIDS (MW)**
- **DAM:** {dam_purchase:,.0f} MW
- **GDAM:** {gdam_purchase:,.0f} MW
- **RTM:** {rtm_purchase:,.0f} MW

**SELL BIDS (MW)**
- **DAM:** {dam_sell:,.0f} MW
- **GDAM:** {gdam_sell:,.0f} MW
- **RTM:** {rtm_sell:,.0f} MW

**SCHEDULED MW & BID RATIO**
- **Scheduled:** DAM {dam_scheduled:,.0f} · GDAM {gdam_scheduled:,.0f} · RTM {rtm_scheduled:,.0f}
- **Bid Ratio (Buy/Sell):** DAM {dam_ratio:.2f} · GDAM {gdam_ratio:.2f} · RTM {rtm_ratio:.2f}

{tightness}

---
"""
        return card
    
    def build_ai_insights(
        self,
        dam_price: float,
        gdam_price: float,
        rtm_price: float,
        dam_volume: float,
        gdam_volume: float,
        rtm_volume: float,
    ) -> str:
        """
        Build AI-powered insights section.
        
        This would call your OpenAI API to generate insights.
        For now, returns template insights.
        """
        
        # Calculate key metrics
        dam_gdam_diff = ((gdam_price - dam_price) / dam_price * 100) if dam_price > 0 else 0
        
        insights = f"""### 🤖 EM-SPARK AI INSIGHTS

• **DAM prices remain moderate**, with intraday volatility driven by evening peak demand.

• **GDAM continues to gain share**, reflecting strong renewable sell-side participation.

• **RTM volumes and bid ratios indicate active balancing activity**, but with slightly loose overall market conditions.
"""
        
        if abs(dam_gdam_diff) > 5:
            if dam_gdam_diff > 0:
                insights += f"\n• **⚠️  GDAM is {abs(dam_gdam_diff):.1f}% more expensive than DAM** - consider DAM for procurement.\n"
            else:
                insights += f"\n• **✅ GDAM is {abs(dam_gdam_diff):.1f}% cheaper than DAM** - good opportunity for green procurement.\n"
        
        insights += "\n---\n"
        return insights
    
    def build_complete_response(
        self,
        snapshot: str,
        derivative: str,
        comparison: str,
        bid_analysis: str,
        insights: str
    ) -> str:
        """Combine all sections into complete response."""
        
        sections = [
            snapshot,
            derivative,
            comparison,
            bid_analysis,
            insights
        ]
        
        return "\n".join(sections)


# ═══════════════════════════════════════════════════════════════
# Helper functions
# ═══════════════════════════════════════════════════════════════

def format_time_range(hours: Optional[List[int]]) -> str:
    """Format hour list into readable time range."""
    if not hours or len(hours) == 24:
        return "00:00 - 24:00 hrs (All India)"
    
    # Get continuous ranges
    ranges = []
    start = hours[0]
    prev = start
    
    for h in hours[1:]:
        if h != prev + 1:
            ranges.append((start, prev))
            start = h
        prev = h
    ranges.append((start, prev))
    
    # Format ranges
    time_strs = []
    for s, e in ranges:
        start_str = f"{(s-1):02d}:00"
        end_str = f"{e:02d}:00"
        time_strs.append(f"{start_str} - {end_str}")
    
    return " + ".join(time_strs) + " hrs (All India)"