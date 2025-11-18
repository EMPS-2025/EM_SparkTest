# core/database.py - FIXED with correct field names
"""Database connection management with proper bid/ask field handling."""
import os
import psycopg2
import psycopg2.extras
from typing import List, Dict, Optional
from datetime import date


class DatabaseManager:
    """Manages database connections and queries."""
    
    def __init__(self, config=None):
        dsn = os.getenv("DATABASE_URL", "").strip()
        if not dsn:
            raise RuntimeError("DATABASE_URL is not set in .env")
        self.dsn = dsn
    
    def _connect(self):
        return psycopg2.connect(self.dsn, sslmode="require")
    
    # ═══════════════════════════════════════════════════════════
    # DAM/GDAM/RTM Queries - FIXED
    # ═══════════════════════════════════════════════════════════
    
    def fetch_hourly(
        self,
        market: str,
        start_date: date,
        end_date: date,
        block_start: Optional[int] = None,
        block_end: Optional[int] = None
    ) -> List[Dict]:
        """Fetch hourly price data with correct aggregations."""
        with self._connect() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
                if block_start and block_end:
                    cur.execute(
                        """
                        SELECT * FROM public.rpc_get_hourly_prices_range(%s,%s,%s,%s,%s);
                        """,
                        (market, start_date, end_date, block_start, block_end)
                    )
                else:
                    cur.execute(
                        """
                        SELECT * FROM public.rpc_get_hourly_prices_range(%s,%s,%s,NULL,NULL);
                        """,
                        (market, start_date, end_date)
                    )
                
                rows = [dict(r) for r in cur.fetchall()]
                
                # DEBUG: Print first row to verify fields
                if rows:
                    print(f"✓ Fetched {len(rows)} hourly rows for {market}")
                    print(f"  Sample: Price={rows[0].get('price_avg_rs_per_mwh')}, "
                          f"Scheduled={rows[0].get('scheduled_mw_sum')}, "
                          f"PurchaseBid={rows[0].get('purchase_bid_avg')}, "
                          f"SellBid={rows[0].get('sell_bid_avg')}")
                else:
                    print(f"⚠️  No hourly data found for {market} on {start_date}")
                
                # Ensure numeric fields with correct names
                for row in rows:
                    row['price_avg_rs_per_mwh'] = float(row.get('price_avg_rs_per_mwh', 0) or 0)
                    row['scheduled_mw_sum'] = float(row.get('scheduled_mw_sum', 0) or 0)
                    row['duration_min'] = int(row.get('duration_min', 60) or 60)
                    row['purchase_bid_avg'] = float(row.get('purchase_bid_avg', 0) or 0)
                    row['sell_bid_avg'] = float(row.get('sell_bid_avg', 0) or 0)
                    row['mcv_sum'] = float(row.get('mcv_sum', 0) or 0)
                
                return rows
    
    def fetch_quarter(
        self,
        market: str,
        start_date: date,
        end_date: date,
        slot_start: Optional[int] = None,
        slot_end: Optional[int] = None
    ) -> List[Dict]:
        """Fetch 15-minute slot price data."""
        with self._connect() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
                if slot_start and slot_end:
                    cur.execute(
                        """
                        SELECT * FROM public.rpc_get_quarter_prices_range(%s,%s,%s,%s,%s);
                        """,
                        (market, start_date, end_date, slot_start, slot_end)
                    )
                else:
                    cur.execute(
                        """
                        SELECT * FROM public.rpc_get_quarter_prices_range(%s,%s,%s,NULL,NULL);
                        """,
                        (market, start_date, end_date)
                    )
                
                rows = [dict(r) for r in cur.fetchall()]
                
                # DEBUG
                if rows:
                    print(f"✓ Fetched {len(rows)} quarter rows for {market}")
                else:
                    print(f"⚠️  No quarter data found for {market} on {start_date}")
                
                # Ensure numeric fields
                for row in rows:
                    row['price_rs_per_mwh'] = float(row.get('price_rs_per_mwh', 0) or 0)
                    row['scheduled_mw'] = float(row.get('scheduled_mw', 0) or 0)
                    row['duration_min'] = int(row.get('duration_min', 15) or 15)
                    row['purchase_bid'] = float(row.get('purchase_bid', 0) or 0)
                    row['sell_bid'] = float(row.get('sell_bid', 0) or 0)
                    row['mcv'] = float(row.get('mcv', 0) or 0)
                
                return rows
    
    # ═══════════════════════════════════════════════════════════
    # Derivative Queries
    # ═══════════════════════════════════════════════════════════
    
    def fetch_deriv_daily_fallback(
        self,
        target_day: date,
        exchange: Optional[str] = None
    ) -> List[Dict]:
        """Fetch derivative daily close with fallback."""
        with self._connect() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
                cur.execute(
                    "SELECT * FROM public.rpc_deriv_daily_with_fallback(%s,%s);",
                    (exchange, target_day)
                )
                return [dict(r) for r in cur.fetchall()]
    
    def fetch_deriv_month_expiry(
        self,
        contract_month_first: date,
        exchange: Optional[str] = None
    ) -> List[Dict]:
        """Fetch derivative expiry data."""
        with self._connect() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
                cur.execute(
                    "SELECT * FROM public.rpc_deriv_expiry_for_month(%s,%s);",
                    (exchange, contract_month_first)
                )
                return [dict(r) for r in cur.fetchall()]