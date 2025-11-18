"""Tailwind-friendly response builder for EM-SPARK."""

from datetime import date
from typing import List, Dict, Optional, Any


MARKET_META = {
    "DAM": {"emoji": "📊", "label": "Spot Market (DAM)"},
    "GDAM": {"emoji": "🟢", "label": "Spot Market (GDAM)"},
    "RTM": {"emoji": "🔵", "label": "Spot Market (RTM)"},
}


def _render_snapshot_kpi(label: str, value: str) -> str:
    """Standalone helper to avoid attribute loss during hot reloads."""
    return f"""
<div class="rounded-2xl border border-slate-100 p-4">
  <p class="text-xs text-slate-500">{label}</p>
  <p class="text-lg font-semibold">{value}</p>
</div>
"""


def _format_currency_value(value: float) -> str:
    """Module-level helper retained across hot reloads."""
    return f"₹{value:.2f}"


class EnhancedResponseBuilder:
    """Render rich HTML sections that match the desired UI."""

    # NOTE: legacy attribute kept for compatibility with existing imports
    _snapshot_kpi = staticmethod(_render_snapshot_kpi)

    def build_overview_header(
        self,
        market_badge: str,
        date_label: str,
        selection_details: Dict[str, Any],
        user_query: str,
    ) -> str:
        return f"""
<section class="rounded-3xl bg-gradient-to-r from-sky-600 via-indigo-600 to-fuchsia-500 text-white p-6 shadow-xl border border-white/10">
  <div class="flex flex-col gap-3">
    <div class="flex items-center justify-between">
      <div class="text-sm uppercase tracking-[0.3em] opacity-90">EM-SPARK RESPONSE</div>
      <div class="text-xs bg-white/20 px-3 py-1 rounded-full">{user_query[:60] or 'Energy Market Query'}</div>
    </div>
    <div>
      <p class="text-base font-semibold opacity-90">{market_badge}</p>
      <h1 class="text-2xl font-semibold">{date_label}</h1>
    </div>
    <div class="flex flex-wrap gap-3 text-sm">
      <span class="px-3 py-1 bg-white/20 rounded-full">🕒 {selection_details['time_label']}</span>
      <span class="px-3 py-1 bg-white/20 rounded-full">⏱ {selection_details['duration_hours']} hrs analyzed</span>
    </div>
  </div>
</section>
"""

    def build_snapshot_card(
        self,
        market: str,
        delivery_label: str,
        time_window: str,
        twap: float,
        min_price: float,
        max_price: float,
        total_volume_gwh: float,
    ) -> str:
        meta = MARKET_META.get(market, {"emoji": "📈", "label": market})
        return f"""
<section class="bg-white rounded-3xl p-6 shadow-lg border border-slate-100">
  <div class="flex items-center gap-3 mb-4">
    <div class="text-3xl">{meta['emoji']}</div>
    <div>
      <p class="text-sm text-slate-500">{delivery_label}</p>
      <h2 class="text-xl font-semibold">{meta['label']}</h2>
      <p class="text-xs text-slate-400">{time_window}</p>
    </div>
  </div>
    <div class="grid grid-cols-1 sm:grid-cols-3 gap-4">
    {self._snapshot_kpi("TWAP Price", self._format_currency(twap) + " /kWh")}
    {self._snapshot_kpi("Min / Max Block", f"{self._format_currency(min_price)} / {self._format_currency(max_price)} /kWh")}
    {self._snapshot_kpi("Total Cleared Volume", f"{total_volume_gwh:.1f} GWh")}
  </div>
</section>
"""

    def build_market_comparison_section(
        self,
        spec_year: int,
        current_year_data: Dict[str, Dict[str, Any]],
        previous_year_data: Dict[str, Optional[Dict[str, Any]]],
    ) -> str:
        rows = []
        prev_year = spec_year - 1
        for market in ["DAM", "GDAM", "RTM"]:
            current = current_year_data.get(market, {})
            prev = (previous_year_data.get(market) or {}) if previous_year_data else {}
            rows.append(self._comparison_row(market, current, prev))
        table_rows = "".join(rows)
        return f"""
<section class="bg-white rounded-3xl p-6 shadow-lg border border-slate-100">
  <div class="flex items-center gap-3 mb-4">
    <div class="text-2xl">📈</div>
    <div>
      <h3 class="text-xl font-semibold">Market Comparison · {spec_year} vs {prev_year}</h3>
      <p class="text-sm text-slate-500">Volumes (GWh) and average prices (₹/kWh)</p>
    </div>
  </div>
  <div class="overflow-hidden rounded-2xl border border-slate-100">
    <table class="min-w-full text-sm">
      <thead class="bg-slate-50 text-slate-500">
        <tr>
          <th class="text-left px-4 py-2">Market</th>
          <th class="text-right px-4 py-2">Volume {spec_year}</th>
          <th class="text-right px-4 py-2">Volume {prev_year}</th>
          <th class="text-right px-4 py-2">Price {spec_year}</th>
          <th class="text-right px-4 py-2">Price {prev_year}</th>
          <th class="text-right px-4 py-2">YoY Δ</th>
        </tr>
      </thead>
      <tbody class="divide-y divide-slate-100">
        {table_rows}
      </tbody>
    </table>
  </div>
</section>
"""

    def build_bid_analysis_section(self, all_market_data: Dict[str, Dict[str, Any]]) -> str:
        cards = []
        ratios = []
        for market in ["DAM", "GDAM", "RTM"]:
            data = all_market_data.get(market, {})
            purchase = data.get('purchase_bid_total_mw', 0.0)
            sell = data.get('sell_bid_total_mw', 0.0)
            scheduled = data.get('scheduled_total_mw', 0.0)
            ratio = purchase / sell if sell else 0.0
            ratios.append(ratio)
            cards.append(
                f"""
<div class="bg-slate-50 rounded-2xl p-4 flex flex-col gap-1">
  <div class="text-xs uppercase text-slate-500">{market}</div>
  <div class="text-lg font-semibold">{purchase:,.0f} MW <span class=\"text-xs text-slate-500\">buy</span></div>
  <div class="text-slate-500 text-sm">{sell:,.0f} MW sell · {scheduled:,.0f} MW scheduled</div>
  <div class="text-xs text-slate-500">Bid ratio {ratio:.2f}</div>
</div>
"""
            )
        valid_ratios = [r for r in ratios if r]
        avg_ratio = sum(valid_ratios) / len(valid_ratios) if valid_ratios else 0.0
        tightness = self._tightness_badge(avg_ratio)
        return f"""
<section class="bg-white rounded-3xl p-6 shadow-lg border border-slate-100">
  <div class="flex items-center justify-between mb-4">
    <div>
      <h3 class="text-xl font-semibold">Market Bids & Scheduling</h3>
      <p class="text-sm text-slate-500">Aggregated MW across selected delivery window</p>
    </div>
    <div class="text-xs px-3 py-1 rounded-full bg-slate-100">{tightness}</div>
  </div>
  <div class="grid grid-cols-1 md:grid-cols-3 gap-4">
    {''.join(cards)}
  </div>
</section>
"""

    def build_ai_insights_section(self, insights: List[str]) -> str:
        items = "".join(f"<li class=\"leading-relaxed\">{text}</li>" for text in insights)
        return f"""
<section class="bg-white rounded-3xl p-6 shadow-lg border border-slate-100">
  <div class="flex items-center gap-3 mb-4">
    <div class="text-2xl">🤖</div>
    <div>
      <h3 class="text-xl font-semibold">EM-SPARK AI Insights</h3>
      <p class="text-sm text-slate-500">Powered by OpenAI</p>
    </div>
  </div>
  <ul class="list-disc list-inside text-slate-700 space-y-2">
    {items}
  </ul>
</section>
"""

    def compose_dashboard(self, sections: List[str]) -> str:
        body = "".join(sections)
        return f"""
<div class="font-['Inter'] text-slate-900 bg-slate-50/60 rounded-[32px] p-6 space-y-6">
  {body}
</div>
"""

    def _comparison_row(self, market: str, current: Dict[str, Any], prev: Dict[str, Any]) -> str:
        meta = MARKET_META.get(market, {"emoji": "📈", "label": market})
        price_cur = current.get('twap', 0.0)
        price_prev = prev.get('twap', 0.0)
        vol_cur = current.get('total_volume_gwh', 0.0)
        vol_prev = prev.get('total_volume_gwh', 0.0)
        yoy = self._format_delta(price_cur, price_prev)
        return (
            f"<tr>"
            f"<td class='px-4 py-3 font-medium'>{meta['emoji']} {market}</td>"
            f"<td class='px-4 py-3 text-right'>{vol_cur:,.2f} GWh</td>"
            f"<td class='px-4 py-3 text-right text-slate-500'>{vol_prev:,.2f} GWh</td>"
            f"<td class='px-4 py-3 text-right'>{self._format_currency(price_cur)} /kWh</td>"
            f"<td class='px-4 py-3 text-right text-slate-500'>{self._format_currency(price_prev)} /kWh</td>"
            f"<td class='px-4 py-3 text-right'>{yoy}</td>"
            f"</tr>"
        )

    def __getattr__(self, name: str):
        if name == "_format_currency":
            return _format_currency_value
        raise AttributeError(name)

    def _tightness_badge(self, ratio: float) -> str:
        if ratio > 1.05:
            return "Tight"
        if ratio > 0.95:
            return "Balanced"
        return "Loose"

    def _format_currency(self, value: float) -> str:
        return _format_currency_value(value)

    def _format_delta(self, current: float, previous: float) -> str:
        if previous <= 0:
            return "—"
        change = ((current - previous) / previous) * 100
        icon = "🔺" if change > 0 else "🔻" if change < 0 else "➖"
        return f"{icon} {abs(change):.1f}%"


def format_time_range(hours: Optional[List[int]]) -> str:
    """Legacy helper retained for compatibility."""
    if not hours or len(hours) == 24:
        return "00:00 - 24:00 hrs (All India)"
    sorted_hours = sorted(hours)
    parts = []
    start = sorted_hours[0]
    prev = start
    for h in sorted_hours[1:]:
        if h != prev + 1:
            parts.append((start, prev))
            start = h
        prev = h
    parts.append((start, prev))
    ranges = [f"{(s-1):02d}:00 - {e:02d}:00" for s, e in parts]
    return " + ".join(ranges) + " hrs (All India)"
