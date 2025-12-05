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
        self.contract_to_id_map = {}


    async def fetch_all(self, wallet: str) -> List[Dict[str, Any]]:
        txs = []
        before = None

        async with httpx.AsyncClient(timeout=60) as client:
            while True:
                payload = {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "getTransactionsForAddress",
                    "params": [
                        wallet,
                        {
                            "limit": 1000,
                            "before": before,
                            "encoding": "jsonParsed"
                        }
                    ]
                }

                async with self.sem:
                    resp = await client.post(self.rpc_url, json=payload)
                resp.raise_for_status()

                result = resp.json()["result"]
                batch = result["data"]

                txs.extend(batch)

                return txs


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
        r = await client.get(url, params=params, headers=headers, timeout=30)
        r.raise_for_status()
        return {int(ts / 1000): price for ts, price in r.json().get("prices", [])}


    def map_price(self, price_map, ts):
        if not price_map:
            return "unknown"
        key = round(ts)
        if key in price_map:
            return price_map[key]
        return price_map[min(price_map.keys(), key=lambda k: abs(k - key))]


    async def reconstruct_fifo(self, incoming: Dict[str, List[dict]], outgoing: Dict[str, List[dict]], price_map: dict):
        queues = {token: [dict(tx) for tx in txs] for token, txs in incoming.items()}
        sales = defaultdict(list)
        for token, outs in outgoing.items():
            if token not in queues:
                continue
            for out in outs:
                to_remove = out['amount']
                sell_price = out.get('price', 'unknown')
                sell_ts = out['timestamp']
                while to_remove > 0 and queues[token]:
                    last_in = queues[token][0]
                    avail = last_in['amount']
                    buy_price = last_in.get('price', 'unknown')
                    buy_ts = last_in['timestamp']

                    if avail <= to_remove:
                        used_amt = avail
                        queues[token].pop(0)
                    else:
                        used_amt = to_remove
                        last_in['amount'] -= used_amt

                    if buy_price != 'unknown' and sell_price != 'unknown':
                        sales[token].append({
                            'timestamp_buy': buy_ts,
                            'timestamp_sell': sell_ts,
                            'amount': used_amt,
                            'price_buy': buy_price,
                            'price_sell': sell_price,
                            'value_buy_eur': used_amt * buy_price,
                            'value_sell_eur': used_amt * sell_price,
                            'profit_eur': used_amt * (sell_price - buy_price)
                        })
                    to_remove -= used_amt
        return sales


    async def run(self, wallets: List[str], start_date: str, end_date: str, timezone: str = "UTC", fifo=False) -> Dict[str, Any]:
        tz = ZoneInfo(timezone)
        start_dt = datetime.fromisoformat(start_date).replace(tzinfo=tz)
        end_dt = datetime.fromisoformat(end_date).replace(tzinfo=tz) + timedelta(days=1)
        start_ts, end_ts = int(start_dt.timestamp()), int(end_dt.timestamp())
        headers = {'x-cg-pro-api-key': cfg.CG_API_KEY}

        async with httpx.AsyncClient(timeout=60) as client:
            sol_price_map = await self.get_token_prices(client, self.SOL_TOKEN_ID, start_ts, end_ts, headers=headers)

            incoming, outgoing = defaultdict(list), defaultdict(list)
            total_fees_lamports = 0
            total_fees_eur = 0

            for w in wallets:
                raw = await self.fetch_all(w)
                txs = [t for t in raw if t.get("blockTime") and start_ts <= t["blockTime"] <= end_ts]

                for entry in txs:
                    full = await self.fetch_full(client, entry["signature"])
                    if full is None or "meta" not in full:
                        continue
                    meta = full["meta"]
                    pre, post = meta["preBalances"], meta["postBalances"]
                    fee = meta.get("fee", 0)
                    fee_eur = fee / 1e9 * self.map_price(sol_price_map, entry["blockTime"])
                    total_fees_lamports += fee
                    total_fees_eur += fee_eur

                    keys = [str(k) for k in full["transaction"]["message"]["accountKeys"]]
                    if w not in keys:
                        continue
                    idx = keys.index(w)
                    delta = post[idx] - pre[idx]

                    tx_record = {
                        "signature": entry["signature"],
                        "timestamp": entry["blockTime"],
                        "lamports": abs(delta),
                        "sol": abs(delta) / 1e9,
                        "price": self.map_price(sol_price_map, entry["blockTime"]),
                        "eur": (abs(delta) / 1e9) * self.map_price(sol_price_map, entry["blockTime"]),
                        "fee": fee,
                        "fee_eur": fee_eur
                    }

                    if delta > 0:
                        incoming["SOL"].append(tx_record)
                    elif delta < 0:
                        outgoing["SOL"].append(tx_record)

            bal_start_lamports = await self.fetch_balance_at(client, wallets[0], min(t["slot"] for t in raw))
            bal_end_lamports = await self.fetch_balance_at(client, wallets[0], max(t["slot"] for t in raw))

            sales = await self.reconstruct_fifo(incoming, outgoing, sol_price_map) if fifo else None

            return {
                "starting_balance": {"SOL": bal_start_lamports / 1e9, "SOL_eur": (bal_start_lamports / 1e9) * self.map_price(sol_price_map, start_ts), "tokens": {}},
                "ending_balance": {"SOL": bal_end_lamports / 1e9, "SOL_eur": (bal_end_lamports / 1e9) * self.map_price(sol_price_map, end_ts), "tokens": {}},
                "transactions": {"incoming": incoming["SOL"], "outgoing": outgoing["SOL"]},
                "total_gas_sol": total_fees_lamports / 1e9,
                "total_gas_eur": total_fees_eur,
                "sales": sales,
                "total_holdings": None
            }


if __name__ == "__main__":
    analyzer = SolanaAnalyzer()
    result = asyncio.run(analyzer.run(
        ["Bcgr66vRcQDctHNEMGS2eFheG41fXsJcRCEK79Rz8PEY"],
        "2025-11-22",
        "2025-12-01",
        fifo=True
    ))
    print(json.dumps(result, indent=2))
