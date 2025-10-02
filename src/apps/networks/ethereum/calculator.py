import asyncio
import json
import httpx
from datetime import datetime
from typing import Dict, Any

from conf import cfg
from utils.utils import load_json_file


class WalletAnalyzer:
    def __init__(self):
        self.ALCHEMY_API_KEY = 'h0thIy2074uqSGR-dPOtC'
        self.CG_API_KEY = 'CG-kbf7rFt27G6XBe2jekbqr3zY'
        self.URL_API = f'https://eth-mainnet.g.alchemy.com/v2/{self.ALCHEMY_API_KEY}'
        self.URL_BLOCKS = f'https://api.g.alchemy.com/data/v1/{self.ALCHEMY_API_KEY}/utility/blocks/by-timestamp'
        self.CG_PRICE_RANGE_URL = 'https://api.coingecko.com/api/v3/coins/{token_id}/market_chart/range'
        self.contract_to_id_map = load_json_file('apps/networks/ethereum/cg_eth_contract_id_map.json')
        # self.semaphore = asyncio.Semaphore(5)


    async def get_block_by_timestamp(self, client: httpx.AsyncClient, timestamp: int) -> str:
        headers = {'Authorization': f'Bearer {self.ALCHEMY_API_KEY}'}
        params = {'networks': 'eth-mainnet', 'timestamp': timestamp, 'direction': 'AFTER'}
        resp = await client.get(self.URL_BLOCKS, params=params, headers=headers)
        resp.raise_for_status()

        return hex(resp.json()['data'][0]['block']['number'])


    async def get_wallet_eth_balance(self, client: httpx.AsyncClient, wallet: str, block_number: str) -> float:
        payload = {'jsonrpc': '2.0', 'method': 'eth_getBalance', 'params': [wallet, block_number], 'id': 1}
        resp = await client.post(self.URL_API, json=payload)
        resp.raise_for_status()

        return int(resp.json()['result'], 16) / 1e18


    async def get_token_metadata(self, client: httpx.AsyncClient, contract_address: str) -> Dict[str, Any]:
        payload = {'jsonrpc': '2.0', 'method': 'alchemy_getTokenMetadata', 'params': [contract_address], 'id': 1}
        resp = await client.post(self.URL_API, json=payload)
        resp.raise_for_status()

        return resp.json().get('result', {})


    async def get_wallet_token_balances(self, client, wallet, block_number):
        payload = {
            'jsonrpc': '2.0',
            'method': 'alchemy_getTokenBalances',
            'params': [wallet, 'erc20', {'block': block_number}],
            'id': 1,
        }
        resp = await client.post(self.URL_API, json=payload)
        resp.raise_for_status()
        balances = {}
        for token in resp.json().get('result', {}).get('tokenBalances', []):
            raw_balance = int(token['tokenBalance'], 16)
            if raw_balance == 0:
                continue
            metadata = cfg.ERC20_TOKEN_METADATA.get(token['contractAddress'])
            if metadata is None:
                metadata = await self.get_token_metadata(client, token['contractAddress'])
                cfg.ERC20_TOKEN_METADATA[token['contractAddress']] = metadata
            decimals = metadata.get('decimals', 18)
            symbol = metadata.get('symbol', token['contractAddress'][:6])
            name = metadata.get('name', '')
            balances[token['contractAddress']] = {
                'symbol': symbol,
                'name': name,
                'balance': raw_balance / (10 ** decimals)
            }

        return balances


    async def get_transfers(self, client: httpx.AsyncClient, wallet: str, start_block: str, end_block: str, direction='outgoing') -> list:
        if direction == 'outgoing':
            params = {'fromBlock': start_block, 'toBlock': end_block, 'fromAddress': wallet,
                      'category': ['external', 'erc20', 'internal'], 'withMetadata': True}
        else:
            params = {'fromBlock': start_block, 'toBlock': end_block, 'toAddress': wallet,
                      'category': ['external', 'erc20', 'internal'], 'withMetadata': True}
        payload = {'jsonrpc': '2.0', 'method': 'alchemy_getAssetTransfers', 'params': [params], 'id': 1}
        resp = await client.post(self.URL_API, json=payload)
        resp.raise_for_status()

        return resp.json().get('result', {}).get('transfers', [])

    async def fetch_gas_fee(self, client: httpx.AsyncClient, tx_hash: str) -> float:
        payload = {'jsonrpc': '2.0', 'method': 'eth_getTransactionReceipt', 'params': [tx_hash], 'id': 1}
        resp = await client.post(self.URL_API, json=payload)
        resp.raise_for_status()
        receipt = resp.json()['result']
        gas_used = int(receipt['gasUsed'], 16)
        effective_gas_price = int(receipt.get('effectiveGasPrice') or receipt.get('gasPrice'), 16)

        return gas_used * effective_gas_price / 1e18


    async def get_token_prices(self, client: httpx.AsyncClient, token_id: str, start_ts: int, end_ts: int) -> dict:
        url = self.CG_PRICE_RANGE_URL.format(token_id=token_id)
        resp = await client.get(url, params={'vs_currency': 'eur', 'from': start_ts, 'to': end_ts})
        resp.raise_for_status()

        return {int(ts / 1000): price for ts, price in resp.json().get('prices', [])}


    async def fetch_token_prices_in_batches(self, client, contracts, start_ts, end_ts, batch_size=10, pause=1):
        token_price_maps = {}

        async def fetch_one(contract, cg_id):
            try:
                token_price_maps[contract] = await self.get_token_prices(client, cg_id, start_ts, end_ts)
            except Exception as e:
                print(f'Failed to fetch prices for {contract}: {e}')
                token_price_maps[contract] = None

        contracts_with_id = [(c, self.contract_to_id_map.get(c)) for c in contracts]
        contracts_with_id = [(c, cg_id) for c, cg_id in contracts_with_id if cg_id]

        for i in range(0, len(contracts_with_id), batch_size):
            batch = contracts_with_id[i:i+batch_size]
            await asyncio.gather(*(fetch_one(c, cg_id) for c, cg_id in batch))
            await asyncio.sleep(pause)

        return token_price_maps


    async def run(self, wallet: str, start_date: str, end_date: str) -> Dict[str, Any]:
        async with httpx.AsyncClient() as client:
            start_ts = int(datetime.strptime(start_date, '%Y-%m-%d').timestamp())
            end_ts = int(datetime.strptime(end_date, '%Y-%m-%d').timestamp())

            start_block = await self.get_block_by_timestamp(client, start_ts)
            end_block = await self.get_block_by_timestamp(client, end_ts)

            starting_eth = await self.get_wallet_eth_balance(client, wallet, start_block)
            ending_eth = await self.get_wallet_eth_balance(client, wallet, end_block)

            starting_tokens = await self.get_wallet_token_balances(client, wallet, start_block)
            ending_tokens = await self.get_wallet_token_balances(client, wallet, end_block)

            transfers_outgoing = await self.get_transfers(client, wallet, start_block, end_block, 'outgoing')
            transfers_incoming = await self.get_transfers(client, wallet, start_block, end_block, 'incoming')

            headers = {'x-cg-demo-api-key': self.CG_API_KEY}
            eth_resp = await client.get(self.CG_PRICE_RANGE_URL.format(token_id='ethereum'), headers=headers, params={'vs_currency': 'eur', 'from': start_ts, 'to': end_ts})
            eth_price_map = {int(ts / 1000): price for ts, price in eth_resp.json().get('prices', [])}

            tx_contracts = {tx.get('rawContract').get('address') for tx in transfers_outgoing + transfers_incoming}
            token_price_maps = await self.fetch_token_prices_in_batches(client, tx_contracts, start_ts, end_ts, batch_size=10, pause=1)

            def map_price(price_map, ts_float):
                if not price_map:
                    return 'unknown'
                ts_int = int(ts_float)
                if ts_int in price_map:
                    return price_map[ts_int]
                return price_map[min(price_map.keys(), key=lambda k: abs(k - ts_int))]

            tasks = [self.fetch_gas_fee(client, tx['hash']) for tx in transfers_outgoing]
            gas_fees_eth = await asyncio.gather(*tasks)
            total_gas_eur = 0
            for tx, fee in zip(transfers_outgoing, gas_fees_eth):
                ts = datetime.strptime(tx['metadata']['blockTimestamp'], '%Y-%m-%dT%H:%M:%S.%fZ').timestamp()
                eth_price = map_price(eth_price_map, ts)
                tx['gas_fee_eth'] = fee
                tx['gas_fee_eur'] = fee * eth_price if eth_price != 'unknown' else 'unknown'

                contract = tx.get('rawContract').get('address')
                token_price_map = token_price_maps.get(contract)
                if 'value' in tx:
                    if token_price_map:
                        token_price = map_price(token_price_map, ts)
                        amount = float(tx['value'])
                        tx['token_price_eur'] = token_price
                        tx['value_eur'] = amount * token_price if token_price != 'unknown' else 'unknown'
                    else:
                        tx['token_price_eur'] = 'unknown'
                        tx['value_eur'] = 'unknown'

                total_gas_eur += tx['gas_fee_eur'] if tx['gas_fee_eur'] != 'unknown' else 0

            total_gas_eth = sum(gas_fees_eth)

            for token_map, ts in [(starting_tokens, start_ts), (ending_tokens, end_ts)]:
                for contract, token in token_map.items():
                    token_price_map = token_price_maps.get(contract)
                    price = map_price(token_price_map, ts) if token_price_map else 'unknown'
                    token['value_eur'] = token['balance'] * price if price != 'unknown' else 'unknown'

            return {
                'starting_balance': {
                    'ETH': starting_eth,
                    'ETH_eur': starting_eth * map_price(eth_price_map, start_ts),
                    'tokens': starting_tokens
                },
                'ending_balance': {
                    'ETH': ending_eth,
                    'ETH_eur': ending_eth * map_price(eth_price_map, end_ts),
                    'tokens': ending_tokens
                },
                'transactions': {
                    'outgoing': transfers_outgoing,
                    'incoming': transfers_incoming
                },
                'total_gas_eth': total_gas_eth,
                'total_gas_eur': total_gas_eur
            }


# WALLET = '0xe742B245cd5A8874aB71c5C004b5B9F877EDf0c0'
# analyzer = WalletAnalyzer()
# result = asyncio.run(analyzer.run(WALLET, '2025-08-29', '2025-09-29'))
# print(json.dumps(result, indent=2))
