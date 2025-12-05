import asyncio
import json
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from typing import List, Dict, Any

import httpx
from conf import cfg


class SolanaAnalyzer:
    def __init__(self):
        self.rpc_url = f"https://mainnet.helius-rpc.com/?api-key={cfg.HELIUS_API_KEY}"  # Solana RPC
        self.tx_url = f"https://api.helius.xyz/v0/transactions?api-key={cfg.HELIUS_API_KEY}"  # Helius v0
        self.sem = asyncio.Semaphore(1)  # rate-limit control

    async def fetch_signatures(self, wallet: str, before: str | None = None) -> List[Dict[str, Any]]:
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "getSignaturesForAddress",
            "params": [wallet, {"limit": 1000, **({"before": before} if before else {})}]
        }
        async with self.sem:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(self.rpc_url, json=payload)
                resp.raise_for_status()
                return resp.json().get("result", [])

    async def fetch_transactions(self, sigs: List[str], batch_size: int = 10) -> List[Dict[str, Any]]:
        results: List[Dict[str, Any]] = []

        async def fetch_batch(batch: List[str], retries=3):
            for attempt in range(retries):
                async with self.sem:
                    async with httpx.AsyncClient(timeout=60) as client:
                        resp = await client.post(self.tx_url, json={"signatures": batch})
                        if resp.status_code == 429:
                            await asyncio.sleep(2 ** attempt)
                            continue
                        resp.raise_for_status()
                        data = resp.json()  # already a list
                        # Retry missing signatures individually
                        received_sigs = {tx["signature"] for tx in data if tx}
                        missing = [s for s in batch if s not in received_sigs]
                        for sig in missing:
                            await asyncio.sleep(0.5)
                            resp2 = await client.post(self.tx_url, json={"signatures": [sig]})
                            if resp2.status_code == 429:
                                await asyncio.sleep(2)
                                resp2 = await client.post(self.tx_url, json={"signatures": [sig]})
                            resp2.raise_for_status()
                            tx = resp2.json()
                            if tx:
                                data.extend(tx)
                        return data
            raise RuntimeError("Failed to fetch batch after retries")

        for i in range(0, len(sigs), batch_size):
            batch = sigs[i:i + batch_size]
            batch_data = await fetch_batch(batch)
            results.extend(batch_data)
            await asyncio.sleep(0.2)  # avoid hitting rate limits

        return results

    async def run(self, wallets: List[str], start_date: str, end_date: str, timezone: str = "UTC") -> Dict[str, Any]:
        tz = ZoneInfo(timezone)
        start_ts = int(datetime.fromisoformat(start_date).replace(tzinfo=tz).timestamp())
        end_ts = int((datetime.fromisoformat(end_date) + timedelta(days=1)).replace(tzinfo=tz).timestamp())
        result = {}

        for w in wallets:
            sigs: List[Dict[str, Any]] = []
            before = None

            while True:
                batch = await self.fetch_signatures(w, before)
                if not batch:
                    break
                if before is not None:
                    batch = batch[1:]
                    if not batch:
                        break
                sigs.extend(batch)
                before = batch[-1]["signature"]
                if len(batch) < 1000:
                    break

            all_sigs = [s["signature"] for s in sigs]
            txs = await self.fetch_transactions(all_sigs)
            transfers = []
            balance = 0

            for tx in sorted(txs, key=lambda x: x.get("blockTime") or 0):
                ts = tx.get("blockTime")
                if ts is None or ts > end_ts:
                    continue
                keys = [str(a) for a in tx["transaction"]["message"]["accountKeys"]]
                if w not in keys:
                    continue
                idx = keys.index(w)
                pre = tx["meta"]["preBalances"]
                post = tx["meta"]["postBalances"]
                delta = post[idx] - pre[idx]
                transfers.append({"timestamp": ts, "delta_lamports": delta, "delta_sol": delta / 1e9})
                if ts <= start_ts:
                    balance += delta

            result[w] = {"balance_at_start": balance / 1e9, "transfers": transfers}

        return result


if __name__ == "__main__":
    analyzer = SolanaAnalyzer()
    result = asyncio.run(
        analyzer.run(
            ["Bcgr66vRcQDctHNEMGS2eFheG41fXsJcRCEK79Rz8PEY"],
            "2025-11-22",
            "2025-12-01",
        )
    )
    print(json.dumps(result, indent=2))
