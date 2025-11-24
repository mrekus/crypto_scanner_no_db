import asyncio
import json
from collections import defaultdict

from async_lru import alru_cache

import httpx
from zoneinfo import ZoneInfo
from datetime import datetime, timedelta
from typing import Dict, Any, List

from utils.utils import load_json_file

from conf import cfg


class WalletAnalyzer:
    def __init__(self):
        self.ALCHEMY_API_KEY = cfg.ALCHEMY_API_KEY
        self.CG_API_KEY = cfg.CG_API_KEY
        self.URL_API = f'https://eth-mainnet.g.alchemy.com/v2/{self.ALCHEMY_API_KEY}'
        self.URL_BLOCKS = f'https://api.g.alchemy.com/data/v1/{self.ALCHEMY_API_KEY}/utility/blocks/by-timestamp'
        self.CG_PRICE_RANGE_URL = 'https://api.coingecko.com/api/v3/coins/{token_id}/market_chart/range'
        self.contract_to_id_map = load_json_file('apps/networks/ethereum/cg_eth_contract_id_map.json')
        self.token_metadata_path = 'apps/networks/ethereum/token_metadata.json'
        self.token_metadata = load_json_file(self.token_metadata_path)

        self.semaphore = asyncio.Semaphore(8)


    async def get_block_by_timestamp(self, client: httpx.AsyncClient, timestamp: int) -> str:
        headers = {'Authorization': f'Bearer {self.ALCHEMY_API_KEY}'}
        params = {
            'networks': 'eth-mainnet',
            'timestamp': timestamp,
            'direction': 'AFTER'
        }
        resp = await client.get(self.URL_BLOCKS, params=params, headers=headers)
        resp.raise_for_status()

        return hex(resp.json()['data'][0]['block']['number'])


    async def get_wallet_eth_balance(self, client: httpx.AsyncClient, wallet: str, block_number: str) -> float:
        payload = {
            'jsonrpc': '2.0',
            'method': 'eth_getBalance',
            'params': [wallet, block_number],
            'id': 1
        }
        resp = await client.post(self.URL_API, json=payload)
        resp.raise_for_status()

        return int(resp.json()['result'], 16) / 1e18


    async def get_token_metadata(self, client: httpx.AsyncClient, contract_address: str) -> Dict[str, Any]:
        payload = {
            'jsonrpc': '2.0',
            'method': 'alchemy_getTokenMetadata',
            'params': [contract_address],
            'id': 1,
        }
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
        updated = False

        for token in resp.json().get('result', {}).get('tokenBalances', []):
            raw_balance = int(token['tokenBalance'], 16)

            if raw_balance == 0:
                continue

            contract_address = token['contractAddress'].lower()
            metadata = self.token_metadata.get(contract_address)

            if metadata is None:
                metadata = await self.get_token_metadata(client, contract_address)
                self.token_metadata[contract_address] = metadata
                updated = True

            decimals = metadata.get('decimals', 18)
            symbol = metadata.get('symbol', contract_address[:6])
            name = metadata.get('name', '')
            balances[contract_address] = {
                'symbol': symbol,
                'name': name,
                'balance': raw_balance / (10 ** decimals),
            }

        if updated:
            with open(self.token_metadata_path, 'w', encoding='utf-8') as f:
                json.dump(self.token_metadata, f, ensure_ascii=False, indent=2)

        return balances


    async def get_transfers(self, client: httpx.AsyncClient, wallet: str, start_block: str, end_block: str, direction='outgoing') -> list:
        if direction == 'outgoing':
            params = {
                'fromBlock': start_block,
                'toBlock': end_block,
                'fromAddress': wallet,
                'category': ['external', 'erc20', 'internal'],
                'withMetadata': True,
            }
        else:
            params = {
                'fromBlock': start_block,
                'toBlock': end_block,
                'toAddress': wallet,
                'category': ['external', 'erc20', 'internal'],
                'withMetadata': True,
            }
        payload = {
            'jsonrpc': '2.0',
            'method': 'alchemy_getAssetTransfers',
            'params': [params],
            'id': 1,
        }
        resp = await client.post(self.URL_API, json=payload)
        resp.raise_for_status()

        return resp.json().get('result', {}).get('transfers', [])


    async def fetch_gas_fee(self, client: httpx.AsyncClient, tx_hash: str) -> float:
        payload = {
            'jsonrpc': '2.0',
            'method': 'eth_getTransactionReceipt',
            'params': [tx_hash],
            'id': 1,
        }
        resp = await client.post(self.URL_API, json=payload)
        resp.raise_for_status()
        receipt = resp.json()['result']
        gas_used = int(receipt['gasUsed'], 16)
        effective_gas_price = int(receipt.get('effectiveGasPrice') or receipt.get('gasPrice'), 16)

        return gas_used * effective_gas_price / 1e18


    @alru_cache(maxsize=512)
    async def _fetch_prices_cached(self, token_id: str, start_ts: int, end_ts: int):
        return token_id, start_ts, end_ts


    async def get_token_prices(self, client: httpx.AsyncClient, token_id: str, start_ts: int, end_ts: int, headers=None):
        if not token_id:
            return None

        await self._fetch_prices_cached(token_id, start_ts, end_ts)

        url = self.CG_PRICE_RANGE_URL.format(token_id=token_id)
        params = {
            'vs_currency': 'eur',
            'from': start_ts,
            'to': end_ts,
        }

        try:
            resp = await client.get(url, params=params, headers=headers, timeout=30)
            if resp.status_code == 404:
                return None
            resp.raise_for_status()
            return {int(ts / 1000): price for ts, price in resp.json().get('prices', [])}

        except Exception:
            return None


    async def fetch_token_prices_in_batches(
        self,
        client: httpx.AsyncClient,
        contracts,
        start_ts,
        end_ts,
        batch_size=3,
        pause=1.0,
        headers: dict = None
    ):
        token_price_maps = {}

        valid_contracts = [
            (c.lower(), self.contract_to_id_map.get(c.lower()))
            for c in contracts if c and self.contract_to_id_map.get(c.lower())
        ]

        async def fetch_one(contract, cg_id):
            async with self.semaphore:
                try:
                    return contract, await self.get_token_prices(client, cg_id, start_ts, end_ts, headers=headers)
                except Exception as e:
                    print(f'Failed to fetch {contract}: {e}')
                    return contract, None

        for i in range(0, len(valid_contracts), batch_size):
            batch = valid_contracts[i:i + batch_size]
            results = await asyncio.gather(*(fetch_one(c, cg_id) for c, cg_id in batch))
            token_price_maps.update(dict(results))
            await asyncio.sleep(pause)

        return token_price_maps


    # async def calculate_fifo(self, client: httpx.AsyncClient, wallet: str, end_block: str):
    #     all_incoming_transfers = await self.get_transfers(client, wallet, '0x0', end_block, 'incoming')
    #     all_outgoing_transfers = await self.get_transfers(client, wallet, '0x0', end_block, 'outgoing')
    #     print('genesis ', json.dumps(all_incoming_transfers), len(all_outgoing_transfers))

    @staticmethod
    def map_price(price_map, ts_float):
        if not price_map:
            return 'unknown'
        ts_int = round(ts_float)
        if ts_int in price_map:
            return price_map[ts_int]
        closest_key = min(price_map.keys(), key=lambda k: abs(k - ts_int))
        return price_map[closest_key]


    @staticmethod
    def iterate_transactions(transactions):
        token_dict = defaultdict(list)

        for tx in transactions:
            asset = tx.get('asset', 'UNKNOWN')
            ts_str = tx['metadata']['blockTimestamp']
            ts = datetime.strptime(ts_str, '%Y-%m-%dT%H:%M:%S.%fZ').timestamp()
            amount = tx.get('value', 0)
            price = tx.get('token_price_eur', 'unknown')
            value_eur = tx.get('value_eur', 'unknown')
            token_dict[asset].append({'timestamp': ts, 'amount': amount, 'price': price, 'value_eur': value_eur})

        return token_dict


    @staticmethod
    def calculate_holdings_at_timestamp(incoming, outgoing, cutoff_ts, start_ts=None):
        from collections import defaultdict
        holdings = defaultdict(lambda: {'amount': 0.0, 'value_eur': 0.0})
        sales = defaultdict(list)

        for token, txs in incoming.items():
            txs.sort(key=lambda x: x['timestamp'])
        for token, txs in outgoing.items():
            txs.sort(key=lambda x: x['timestamp'])

        queues = {token: [dict(tx) for tx in txs] for token, txs in incoming.items()}

        for token, outs in outgoing.items():
            if token not in queues:
                continue
            for out in outs:
                if out['timestamp'] > cutoff_ts:
                    continue
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
                        if last_in['price'] != 'unknown':
                            last_in['value_eur'] = last_in['amount'] * last_in['price']

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

        for token, txs in queues.items():
            for tx in txs:
                if tx['timestamp'] <= cutoff_ts:
                    amt = tx['amount']
                    val = tx['value_eur']
                    holdings[token]['amount'] += amt
                    if val != 'unknown':
                        holdings[token]['value_eur'] += val

        for token in sales:
            sales[token].sort(key=lambda x: x['timestamp_sell'])

        if start_ts is not None:
            for token in sales:
                sales[token] = [s for s in sales[token] if s['timestamp_sell'] >= start_ts]

        return holdings, sales


    async def run(self, wallets: List[str], start_date: str, end_date: str, timezone: str = 'UTC', fifo: bool = False) -> Dict[str, Any]:
        async with httpx.AsyncClient() as client:
            tz = ZoneInfo(timezone)
            start_dt = datetime.strptime(start_date, '%Y-%m-%d').replace(
                hour=0, minute=0, second=0, tzinfo=tz)
            end_dt = datetime.strptime(end_date, '%Y-%m-%d').replace(
                hour=0, minute=0, second=0, tzinfo=tz) + timedelta(days=1)
            start_ts = int(start_dt.timestamp())
            end_ts = int(end_dt.timestamp())
            # TODO: change to genesis ts with non demo coingecko api
            # genesis_ts = 0
            one_year_from_now = datetime.now(tz=tz) - timedelta(days=729)
            genesis_ts = int(one_year_from_now.timestamp())

            start_block = await self.get_block_by_timestamp(client, start_ts)
            end_block = await self.get_block_by_timestamp(client, end_ts)

            start_block_transfers = '0x0' if fifo else start_block

            total_starting_eth = 0
            total_ending_eth = 0

            combined_starting_tokens: Dict[str, Any] = {}
            combined_ending_tokens: Dict[str, Any] = {}

            combined_transfers_outgoing = []
            combined_transfers_incoming = []

            for wallet in wallets:
                starting_eth = await self.get_wallet_eth_balance(client, wallet, start_block)
                ending_eth = await self.get_wallet_eth_balance(client, wallet, end_block)

                total_starting_eth += starting_eth
                total_ending_eth += ending_eth

                starting_tokens = await self.get_wallet_token_balances(client, wallet, start_block)
                ending_tokens = await self.get_wallet_token_balances(client, wallet, end_block)

                for contract, token in starting_tokens.items():
                    if contract not in combined_starting_tokens:
                        combined_starting_tokens[contract] = token.copy()
                    else:
                        combined_starting_tokens[contract]['balance'] += token['balance']

                for contract, token in ending_tokens.items():
                    if contract not in combined_ending_tokens:
                        combined_ending_tokens[contract] = token.copy()
                    else:
                        combined_ending_tokens[contract]['balance'] += token['balance']

                transfers_outgoing = await self.get_transfers(client, wallet, start_block_transfers, end_block, 'outgoing')
                transfers_incoming = await self.get_transfers(client, wallet, start_block_transfers, end_block, 'incoming')

                combined_transfers_outgoing.extend(transfers_outgoing)
                combined_transfers_incoming.extend(transfers_incoming)

            headers = {'x-cg-demo-api-key': self.CG_API_KEY}
            eth_resp = await client.get(self.CG_PRICE_RANGE_URL.format(token_id='ethereum'), headers=headers, params={'vs_currency': 'eur', 'from': genesis_ts, 'to': end_ts})
            eth_price_map = {int(ts / 1000): price for ts, price in eth_resp.json().get('prices', [])}

            tx_contracts = {
                (tx.get('rawContract') or {}).get('address')
                for tx in (combined_transfers_outgoing + combined_transfers_incoming)
                if (tx.get('rawContract') or {}).get('address')
            }
            token_price_maps = await self.fetch_token_prices_in_batches(client, tx_contracts, genesis_ts, end_ts,
                                                                        batch_size=3, pause=1.0, headers=headers)
            tasks = [self.fetch_gas_fee(client, tx['hash']) for tx in combined_transfers_outgoing if
                     int(datetime.strptime(tx['metadata']['blockTimestamp'], '%Y-%m-%dT%H:%M:%S.%fZ').timestamp()) >= start_ts]
            gas_fees_eth = await asyncio.gather(*tasks)
            total_gas_eur = 0
            for tx, fee in zip(combined_transfers_outgoing, gas_fees_eth):
                ts = datetime.strptime(tx['metadata']['blockTimestamp'], '%Y-%m-%dT%H:%M:%S.%fZ').timestamp()
                eth_price = self.map_price(eth_price_map, ts)
                tx['gas_fee_eth'] = fee
                tx['gas_fee_eur'] = fee * eth_price if eth_price != 'unknown' else 'unknown'

                contract = tx.get('rawContract').get('address')
                token_price_map = token_price_maps.get(contract)
                if 'value' in tx:
                    amount = float(tx['value'])
                    if tx.get('asset') == 'ETH':
                        eth_price = self.map_price(eth_price_map, ts)
                        tx['token_price_eur'] = eth_price
                        tx['value_eur'] = amount * eth_price if eth_price != 'unknown' else 'unknown'
                    else:
                        token_price = self.map_price(token_price_map, ts)
                        tx['token_price_eur'] = token_price
                        tx['value_eur'] = amount * token_price if token_price != 'unknown' else 'unknown'

                total_gas_eur += tx['gas_fee_eur'] if tx['gas_fee_eur'] != 'unknown' else 0

            total_gas_eth = sum(gas_fees_eth)

            for tx in combined_transfers_incoming:
                ts = datetime.strptime(tx['metadata']['blockTimestamp'], '%Y-%m-%dT%H:%M:%S.%fZ').timestamp()

                contract = tx.get('rawContract', {}).get('address')
                token_price_map = token_price_maps.get(contract)

                if 'value' in tx:
                    amount = float(tx['value'])
                    if tx.get('asset') == 'ETH':
                        eth_price = self.map_price(eth_price_map, ts)
                        tx['token_price_eur'] = eth_price
                        tx['value_eur'] = amount * eth_price if eth_price != 'unknown' else 'unknown'
                    else:
                        token_price = self.map_price(token_price_map, ts)
                        tx['token_price_eur'] = token_price
                        tx['value_eur'] = amount * token_price if token_price != 'unknown' else 'unknown'

            for token_map, ts in [(combined_starting_tokens, start_ts), (combined_ending_tokens, end_ts)]:
                for contract, token in token_map.items():
                    token_price_map = token_price_maps.get(contract)
                    price = self.map_price(token_price_map, ts) if token_price_map else 'unknown'
                    token['value_eur'] = token['balance'] * price if price != 'unknown' else 'unknown'

            sales = None
            total_holdings = None
            if fifo:
                wallet_set = set(w.lower() for w in wallets)

                filtered_incoming = [tx for tx in combined_transfers_incoming if
                                     tx.get('from', '').lower() not in wallet_set]
                filtered_outgoing = [tx for tx in combined_transfers_outgoing if
                                     tx.get('to', '').lower() not in wallet_set]

                incoming_iter = self.iterate_transactions(filtered_incoming)
                outgoing_iter = self.iterate_transactions(filtered_outgoing)

                total_holdings, sales = self.calculate_holdings_at_timestamp(incoming_iter, outgoing_iter, end_ts, start_ts)

            return {
                'starting_balance': {
                    'ETH': total_starting_eth,
                    'ETH_eur': total_starting_eth * self.map_price(eth_price_map, start_ts),
                    'tokens': combined_starting_tokens
                },
                'ending_balance': {
                    'ETH': total_ending_eth,
                    'ETH_eur': total_ending_eth * self.map_price(eth_price_map, end_ts),
                    'tokens': combined_ending_tokens
                },
                'transactions': {
                    'outgoing': combined_transfers_outgoing,
                    'incoming': combined_transfers_incoming
                },
                'total_gas_eth': total_gas_eth,
                'total_gas_eur': total_gas_eur,
                'sales': sales,
                'total_holdings': total_holdings,
            }


# WALLET = '0xa9B21B41fC68A14eaA984581dDD0b31641bF287a'
# analyzer = WalletAnalyzer()
# result = asyncio.run(analyzer.run(WALLET, '2025-10-01', '2025-10-06', fifo=True))
# # print(json.dumps(result, indent=2))
