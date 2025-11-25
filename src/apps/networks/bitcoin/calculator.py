import asyncio
import httpx
import json
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from conf import cfg


class BitcoinAnalyzer:
    def __init__(self):
        self.MAESTRO_API_KEY = cfg.MAESTRO_API_KEY
        self.CG_API_KEY = cfg.CG_API_KEY

        self.URL_MAESTRO = cfg.MAESTRO_API_URL
        self.CG_PRICE_RANGE_URL = "https://pro-api.coingecko.com/api/v3/coins/{token_id}/market_chart/range"

    async def get_block_by_timestamp(self, client: httpx.AsyncClient, ts: int) -> int:
        headers = {"api-key": self.MAESTRO_API_KEY}
        url = f"{self.URL_MAESTRO}/blocks/{ts}"
        params = {"from_timestamp": "true"}
        r = await client.get(url, headers=headers, params=params)
        r.raise_for_status()
        return r.json()["data"]["height"]

    async def get_utxos_at_height(self, client: httpx.AsyncClient, address: str, height: int):
        headers = {"api-key": self.MAESTRO_API_KEY}
        params = {"height": height}
        r = await client.get(f"{self.URL_MAESTRO}/addresses/{address}/utxos", headers=headers, params=params)
        r.raise_for_status()
        return r.json()["data"]

    async def get_balance_at_height(self, client: httpx.AsyncClient, address: str, height: int) -> float:
        utxos = await self.get_utxos_at_height(client, address, height)
        total_sats = sum(int(u["satoshis"]) for u in utxos)
        return total_sats / 1e8

    async def get_price_map(self, client: httpx.AsyncClient, start_ts: int, end_ts: int):
        url = self.CG_PRICE_RANGE_URL.format(token_id="bitcoin")
        params = {"vs_currency": "eur", "from": start_ts, "to": end_ts}
        headers = {"x-cg-pro-api-key": self.CG_API_KEY}

        r = await client.get(url, params=params, headers=headers)
        r.raise_for_status()
        return {int(t / 1000): p for t, p in r.json().get("prices", [])}

    @staticmethod
    def map_price(price_map, ts):
        ts = round(ts)
        if ts in price_map:
            return price_map[ts]
        return price_map[min(price_map.keys(), key=lambda k: abs(k - ts))]

    async def run(self, address: str, start_date: str, end_date: str, timezone="UTC"):
        async with httpx.AsyncClient(timeout=30) as client:
            tz = ZoneInfo(timezone)

            start_dt = datetime.strptime(start_date, "%Y-%m-%d").replace(
                hour=0, minute=0, second=0, tzinfo=tz
            )
            end_dt = datetime.strptime(end_date, "%Y-%m-%d").replace(
                hour=0, minute=0, second=0, tzinfo=tz
            ) + timedelta(days=1)

            start_ts = int(start_dt.timestamp())
            end_ts = int(end_dt.timestamp())

            start_height = await self.get_block_by_timestamp(client, start_ts)
            end_height = await self.get_block_by_timestamp(client, end_ts)

            bal_start = await self.get_balance_at_height(client, address, start_height)
            bal_end = await self.get_balance_at_height(client, address, end_height)

            price_map = await self.get_price_map(client, start_ts, end_ts)

            price_start = self.map_price(price_map, start_ts)
            price_end = self.map_price(price_map, end_ts)

            return {
                "starting_balance_btc": bal_start,
                "ending_balance_btc": bal_end,
                "starting_balance_eur": bal_start * price_start,
                "ending_balance_eur": bal_end * price_end,
                "start_height": start_height,
                "end_height": end_height,
                "price_start_eur": price_start,
                "price_end_eur": price_end,
            }


# analyzer = BitcoinAnalyzer()
# result = asyncio.run(analyzer.run("bc1q4mhdqjk43v0tcx4jhvn273kxqlhn8a2w4r2n2n", "2025-11-21", "2025-11-23"))
# print(json.dumps(result, indent=2))
