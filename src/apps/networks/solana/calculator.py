import asyncio
import json
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from typing import List, Dict, Any
from collections import defaultdict

import httpx
from conf import cfg


class SolanaAnalyzer:
    def __init__(self):
        self.rpc_url = f"https://mainnet.helius-rpc.com/?api-key={cfg.HELIUS_API_KEY}"
        self.sem = asyncio.Semaphore(1)
        self.CG_PRICE_RANGE_URL = "https://pro-api.coingecko.com/api/v3/coins/{token_id}/market_chart/range"
        self.SOL_TOKEN_ID = "solana"
        self.contract_to_id_map = {}  # SPL token mint → coingecko id map

    async def fetch_all(self, wallet: str) -> List[Dict[str, Any]]:
        # mock
        return [
            {
                "signature": "5h6xBEauJ3PK6SWCZ1PGjBvj8vDdWG3KpwATGy1ARAXFSDwt8GFXM7W5Ncn16wmqokgpiKRLuS83KUxyZyv2sUYv",
                "slot": 1054,
                "err": None,
                "memo": None,
                "blockTime": 1641038400,
                "confirmationStatus": "finalized"
            },
            {
                "signature": "kwjd820slPK6SWCZ1PGjBvj8vDdWG3KpwATGy1ARAXFSDwt8GFXM7W5Ncn16wmqokgpiKRLuS83KUxyZyv2sUYv",
                "slot": 1055,
                "err": None,
                "memo": None,
                "blockTime": 1641038460,
                "confirmationStatus": "finalized"
            }
        ]

    async def fetch_full(self, client, sig: str) -> Dict[str, Any]:
        payload = {"jsonrpc": "2.0", "id": 1, "method": "getTransaction", "params": [sig, {"encoding": "jsonParsed"}]}
        async with self.sem:
            r = await client.post(self.rpc_url, json=payload)
        r.raise_for_status()
        return r.json()["result"]

    async def fetch_balance_at(self, client, wallet: str, block: int) -> int:
        payload = {"jsonrpc": "2.0", "id": 1, "method": "getBalance", "params": [wallet, {"commitment": "confirmed", "minContextSlot": block}]}
        async with self.sem:
            r = await client.post(self.rpc_url, json=payload)
        r.raise_for_status()
        return r.json()["result"]["value"]

    async def get_token_prices(self, client, token_id: str, start_ts: int, end_ts: int, headers: dict):
        url = self.CG_PRICE_RANGE_URL.format(token_id=token_id)
        params = {"vs_currency": "eur", "from": start_ts, "to": end_ts}
        try:
            r = await client.get(url, params=params, headers=headers, timeout=30)
            if r.status_code == 404:
                return None
            r.raise_for_status()
            return {int(ts / 1000): price for ts, price in r.json().get("prices", [])}
        except:
            return None

    async def fetch_token_prices_in_batches(self, client, contracts, start_ts, end_ts, headers=None, batch_size=3, pause=1.0):
        token_price_maps = {}
        valid_contracts = [(c.lower(), self.contract_to_id_map.get(c.lower())) for c in contracts if c and self.contract_to_id_map.get(c.lower())]

        async def fetch_one(contract, cg_id):
            try:
                return contract, await self.get_token_prices(client, cg_id, start_ts, end_ts, headers)
            except:
                return contract, None

        for i in range(0, len(valid_contracts), batch_size):
            batch = valid_contracts[i:i + batch_size]
            results = await asyncio.gather(*(fetch_one(c, cg_id) for c, cg_id in batch))
            token_price_maps.update(dict(results))
            await asyncio.sleep(pause)
        return token_price_maps

    def map_price(self, price_map, ts):
        if not price_map:
            return "unknown"
        key = round(ts)
        if key in price_map:
            return price_map[key]
        return price_map[min(price_map.keys(), key=lambda k: abs(k - key))]

    async def run(self, wallets: List[str], start_date: str, end_date: str, timezone: str = "UTC") -> Dict[str, Any]:
        tz = ZoneInfo(timezone)
        start_dt = datetime.fromisoformat(start_date).replace(tzinfo=tz)
        end_dt = datetime.fromisoformat(end_date).replace(tzinfo=tz) + timedelta(days=1)
        start_ts, end_ts = int(start_dt.timestamp()), int(end_dt.timestamp())

        async with httpx.AsyncClient(timeout=60) as client:
            result = {}
            all_contracts = set()
            headers = {'x-cg-pro-api-key': cfg.CG_API_KEY}

            for w in wallets:
                raw = await self.fetch_all(w)
                incoming, outgoing = [], []
                total_fees_lamports = 0
                txs = [t for t in raw if t.get("blockTime") and start_ts <= t["blockTime"] <= end_ts]

                for entry in txs:
                    full = await self.fetch_full(client, entry["signature"])
                    if full is None or "meta" not in full:
                        continue
                    meta = full["meta"]
                    pre, post = meta["preBalances"], meta["postBalances"]
                    fee = meta.get("fee", 0)
                    total_fees_lamports += fee

                    keys = [str(k) for k in full["transaction"]["message"]["accountKeys"]]
                    if w not in keys:
                        continue
                    idx = keys.index(w)
                    delta = post[idx] - pre[idx]

                    if delta > 0:
                        incoming.append({"signature": entry["signature"], "timestamp": entry["blockTime"], "lamports": delta, "sol": delta / 1e9})
                    elif delta < 0:
                        outgoing.append({"signature": entry["signature"], "timestamp": entry["blockTime"], "lamports": delta, "sol": delta / 1e9})

                    all_contracts.add("SOL")  # base SOL

            # fetch SOL prices in range
            sol_price_map = await self.get_token_prices(client, self.SOL_TOKEN_ID, start_ts, end_ts, headers=headers)

            # map prices
            for tx in incoming + outgoing:
                ts = tx["timestamp"]
                price = self.map_price(sol_price_map, ts)
                tx["eur"] = (tx["sol"] * price) if price != "unknown" else "unknown"

            bal_start_lamports = await self.fetch_balance_at(client, wallets[0], min([t["slot"] for t in raw]))
            bal_end_lamports = await self.fetch_balance_at(client, wallets[0], max([t["slot"] for t in raw]))

            result = {
                "starting_balance": {"SOL": bal_start_lamports / 1e9, "SOL_eur": (bal_start_lamports / 1e9) * self.map_price(sol_price_map, start_ts), "tokens": {}},
                "ending_balance": {"SOL": bal_end_lamports / 1e9, "SOL_eur": (bal_end_lamports / 1e9) * self.map_price(sol_price_map, end_ts), "tokens": {}},
                "transactions": {"incoming": incoming, "outgoing": outgoing},
                "total_gas_sol": total_fees_lamports / 1e9,
                "total_gas_eur": total_fees_lamports / 1e9 * self.map_price(sol_price_map, end_ts),
                "sales": None,
                "total_holdings": None
            }

            return result


if __name__ == "__main__":
    analyzer = SolanaAnalyzer()
    r = asyncio.run(
        analyzer.run(
            ["Bcgr66vRcQDctHNEMGS2eFheG41fXsJcRCEK79Rz8PEY"],
            "2025-11-22",
            "2025-12-01",
        )
    )
    print(json.dumps(r, indent=2))
