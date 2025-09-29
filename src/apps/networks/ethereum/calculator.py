import json
import asyncio
from datetime import datetime
from typing import Optional, Dict, Any

import httpx


class WalletAnalyzer:
    def __init__(self):
        self.ALCHEMY_API_KEY = "h0thIy2074uqSGR-dPOtC"
        self.CG_API_KEY = 'CG-kbf7rFt27G6XBe2jekbqr3zY'
        self.URL_API = f"https://eth-mainnet.g.alchemy.com/v2/{self.ALCHEMY_API_KEY}"
        self.URL_BLOCKS = f"https://api.g.alchemy.com/data/v1/{self.ALCHEMY_API_KEY}/utility/blocks/by-timestamp"
        self.ETH_PRICE_URL = "https://api.coingecko.com/api/v3/coins/ethereum/history"
        self.ETH_PRICE_RANGE_URL = 'https://api.coingecko.com/api/v3/coins/ethereum/market_chart/range'

    @staticmethod
    def _iso_date(year: int, month: int, day: int, hour: int = 0, minute: int = 0, second: int = 0) -> str:
        dt = datetime(year, month, day, hour, minute, second)
        return dt.isoformat() + "Z"

    async def get_block_by_timestamp(self, client: httpx.AsyncClient, timestamp: int) -> str:
        headers = {"Authorization": f"Bearer {self.ALCHEMY_API_KEY}"}
        params = {"networks": "eth-mainnet", "timestamp": timestamp, "direction": "AFTER"}
        resp = await client.get(self.URL_BLOCKS, params=params, headers=headers)
        resp.raise_for_status()
        block_number = resp.json()["data"][0]["block"]["number"]
        return hex(block_number)

    async def get_eth_price_for_date(self, client: httpx.AsyncClient, date: str) -> float:
        headers = {"x-cg-demo-api-key": self.CG_API_KEY}
        resp = await client.get(self.ETH_PRICE_URL, params={"date": date, "localization": False}, headers=headers)
        resp.raise_for_status()
        return resp.json()["market_data"]["current_price"]["usd"]

    async def get_wallet_eth_balance(self, client: httpx.AsyncClient, wallet: str, block_number: str) -> float:
        payload = {"jsonrpc": "2.0", "method": "eth_getBalance", "params": [wallet, block_number], "id": 1}
        resp = await client.post(self.URL_API, json=payload)
        resp.raise_for_status()
        return int(resp.json()["result"], 16) / 1e18

    async def get_token_metadata(self, client: httpx.AsyncClient, contract_address: str) -> Dict[str, Any]:
        payload = {"jsonrpc": "2.0", "method": "alchemy_getTokenMetadata", "params": [contract_address], "id": 1}
        resp = await client.post(self.URL_API, json=payload)
        resp.raise_for_status()
        return resp.json().get("result", {})

    async def get_wallet_token_balances(self, client: httpx.AsyncClient, wallet: str, block_number: str) -> Dict[str, Dict]:
        payload = {
            "jsonrpc": "2.0",
            "method": "alchemy_getTokenBalances",
            "params": [wallet, "erc20", {"block": block_number}],
            "id": 1,
        }
        resp = await client.post(self.URL_API, json=payload)
        resp.raise_for_status()
        result = resp.json().get("result", {})
        balances = {}

        for token in result.get("tokenBalances", []):
            raw_balance = int(token["tokenBalance"], 16)
            if raw_balance == 0:
                continue
            metadata = await self.get_token_metadata(client, token["contractAddress"])
            decimals = metadata.get("decimals", 18)
            symbol = metadata.get("symbol", token["contractAddress"][:6])
            name = metadata.get("name", "")
            human_balance = raw_balance / (10 ** decimals)
            balances[token["contractAddress"]] = {"symbol": symbol, "name": name, "balance": human_balance}

        return balances

    async def get_outgoing_transfers(self, client: httpx.AsyncClient, wallet: str, start_block: str, end_block: str) -> list:
        payload = {
            "jsonrpc": "2.0",
            "method": "alchemy_getAssetTransfers",
            "params": [
                {
                    "fromBlock": start_block,
                    "toBlock": end_block,
                    "fromAddress": wallet,
                    "category": ["external", "erc20", "internal"],
                    "withMetadata": True,
                }
            ],
            "id": 1,
        }
        resp = await client.post(self.URL_API, json=payload)
        resp.raise_for_status()
        return resp.json().get("result", {}).get("transfers", [])

    async def get_incoming_transfers(self, client: httpx.AsyncClient, wallet: str, start_block: str, end_block: str) -> list:
        payload = {
            "jsonrpc": "2.0",
            "method": "alchemy_getAssetTransfers",
            "params": [
                {
                    "fromBlock": start_block,
                    "toBlock": end_block,
                    "toAddress": wallet,
                    "category": ["external", "erc20", "erc721", "internal"],
                    "withMetadata": True,
                }
            ],
            "id": 1,
        }
        resp = await client.post(self.URL_API, json=payload)
        resp.raise_for_status()
        return resp.json().get("result", {}).get("transfers", [])

    async def fetch_gas_fee(self, client: httpx.AsyncClient, tx_hash: str) -> float:
        payload_receipt = {"jsonrpc": "2.0", "method": "eth_getTransactionReceipt", "params": [tx_hash], "id": 1}
        resp = await client.post(self.URL_API, json=payload_receipt)
        resp.raise_for_status()
        receipt = resp.json()["result"]
        gas_used = int(receipt["gasUsed"], 16)
        effective_gas_price = int(receipt.get("effectiveGasPrice") or receipt.get("gasPrice"), 16)
        return gas_used * effective_gas_price / 1e18

    async def analyze_wallet(self, wallet: str, start_date: str, end_date: str) -> Dict[str, Any]:
        async with httpx.AsyncClient() as client:
            start_ts = int(datetime.strptime(start_date, "%Y-%m-%d").timestamp())
            end_ts = int(datetime.strptime(end_date, "%Y-%m-%d").timestamp())

            start_block = await self.get_block_by_timestamp(client, start_ts)
            end_block = await self.get_block_by_timestamp(client, end_ts)

            starting_eth = await self.get_wallet_eth_balance(client, wallet, start_block)
            ending_eth = await self.get_wallet_eth_balance(client, wallet, end_block)

            starting_tokens = await self.get_wallet_token_balances(client, wallet, start_block)
            ending_tokens = await self.get_wallet_token_balances(client, wallet, end_block)

            transfers_outgoing = await self.get_outgoing_transfers(client, wallet, start_block, end_block)
            transfers_incoming = await self.get_incoming_transfers(client, wallet, start_block, end_block)

            headers = {"x-cg-demo-api-key": self.CG_API_KEY}
            price_resp = await client.get(
                self.ETH_PRICE_RANGE_URL,
                headers=headers,
                params={"vs_currency": "eur", "from": start_ts, "to": end_ts}
            )
            price_data = price_resp.json()
            price_map = {int(ts / 1000): price for ts, price in price_data.get("prices", [])}

            def map_price(ts_float):
                ts_int = int(ts_float)
                if ts_int in price_map:
                    return price_map[ts_int]
                closest_ts = min(price_map.keys(), key=lambda k: abs(k - ts_int))
                return price_map[closest_ts]

            tasks = [self.fetch_gas_fee(client, tx["hash"]) for tx in transfers_outgoing]
            gas_fees_eth = await asyncio.gather(*tasks)
            total_gas_eur = 0
            for tx, fee in zip(transfers_outgoing, gas_fees_eth):
                ts = datetime.strptime(tx['metadata']['blockTimestamp'], '%Y-%m-%dT%H:%M:%S.%fZ').timestamp()
                price_usd = map_price(ts)
                tx["gas_fee_eth"] = fee
                tx["gas_fee_eur"] = fee * price_usd
                total_gas_eur += tx["gas_fee_eur"]

            total_gas_eth = sum(gas_fees_eth)

            return {
                "starting_balance": {
                    "ETH": starting_eth,
                    "ETH_usd": starting_eth * map_price(start_ts),
                    "tokens": starting_tokens
                },
                "ending_balance": {
                    "ETH": ending_eth,
                    "ETH_usd": ending_eth * map_price(end_ts),
                    "tokens": ending_tokens
                },
                "transfers": {
                    "outgoing": transfers_outgoing,
                    "incoming": transfers_incoming
                },
                "total_gas_eth": total_gas_eth,
                "total_gas_usd": total_gas_eur
            }


WALLET = '0xe742B245cd5A8874aB71c5C004b5B9F877EDf0c0'
analyzer = WalletAnalyzer()
result = asyncio.run(analyzer.analyze_wallet(WALLET, "2025-08-29", "2025-09-29"))
print(json.dumps(result, indent=2))
