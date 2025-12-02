import asyncio
import random
from collections import defaultdict
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import json
import httpx
from conf import cfg


class BitcoinAnalyzer:
    def __init__(self):
        self.MAESTRO_API_KEY = cfg.MAESTRO_API_KEY
        self.CG_API_KEY = cfg.CG_API_KEY
        self.URL_MAESTRO = cfg.MAESTRO_API_URL
        self.CG_PRICE_RANGE_URL = 'https://pro-api.coingecko.com/api/v3/coins/{token_id}/market_chart/range'

        self.semaphore = asyncio.Semaphore(5)


    async def get_block_by_timestamp(self, client: httpx.AsyncClient, ts: int) -> int:
        headers = {'api-key': self.MAESTRO_API_KEY}
        url = f'{self.URL_MAESTRO}/blocks/{ts}'
        params = {'from_timestamp': 'true'}
        r = await client.get(url, headers=headers, params=params)
        r.raise_for_status()
        return r.json()['data']['height']


    async def get_all_txs(self, client: httpx.AsyncClient, address: str, batch_size=1000):
        headers = {'api-key': self.MAESTRO_API_KEY}
        url = f'{self.URL_MAESTRO}/wallets/{address}/txs'
        offset = 0
        all_txs = []

        while True:
            params = {'limit': batch_size, 'offset': offset}
            r = await client.get(url, headers=headers, params=params)
            r.raise_for_status()
            data = r.json().get('data', [])
            if not data:
                break
            all_txs.extend(data)
            if len(data) < batch_size:
                break
            offset += batch_size

        return all_txs


    async def get_full_tx(self, client: httpx.AsyncClient, tx_hash: str):
        headers = {'api-key': self.MAESTRO_API_KEY}
        url = f'{self.URL_MAESTRO}/transactions/{tx_hash}'
        retries = 3
        backoff = 1

        async with self.semaphore:
            for _ in range(retries):
                r = await client.get(url, headers=headers)
                if r.status_code == 200:
                    return r.json()['data']
                if r.status_code == 429:
                    await asyncio.sleep(backoff + random.random())
                    backoff *= 2
                    continue
                r.raise_for_status()
        raise Exception(f'Failed to fetch tx {tx_hash} after {retries} retries')


    async def get_all_txs_multi(self, client, wallets, batch_size=1000):
        all_txs = []
        for addr in wallets:
            headers = {'api-key': self.MAESTRO_API_KEY}
            url = f'{self.URL_MAESTRO}/addresses/{addr}/txs'
            offset = 0
            while True:
                params = {'limit': batch_size, 'offset': offset}
                r = await client.get(url, headers=headers, params=params)
                r.raise_for_status()
                data = r.json().get('data', [])
                if not data:
                    break
                for tx in data:
                    tx['_origin_address'] = addr
                all_txs.extend(data)
                if len(data) < batch_size:
                    break
                offset += batch_size
        return all_txs

    async def reconstruct_utxo_set(self, client, wallets, txs, up_to_height, price_map, fifo=False):
        utxos = {}
        total_fees_btc = 0
        total_fees_eur = 0

        incoming = defaultdict(list)
        outgoing = defaultdict(list)
        incoming_txs = []
        outgoing_txs = []

        for tx_summary in txs:

            full_tx = await self.get_full_tx(client, tx_summary['tx_hash'])
            height = full_tx.get('height')
            if height is None or height > up_to_height:
                continue

            txid = tx_summary['tx_hash']
            ts_str = full_tx.get('timestamp')
            if ts_str:
                dt = datetime.strptime(ts_str, '%Y-%m-%d %H:%M:%S')
                ts = int(dt.timestamp())
            else:
                ts = None

            for idx, out in enumerate(full_tx.get('outputs', [])):
                if out.get('address') in wallets:
                    utxos[f'{txid}:{idx}'] = int(out['satoshis'])
                    tx_data = {
                        'hash': txid,
                        'to': out.get('address'),
                        'from': full_tx.get('inputs', [{}])[0].get('address', 'unknown'),
                        'amount': int(out['satoshis']) / 1e8,
                        'timestamp': ts,
                        'value_eur': (int(out['satoshis']) / 1e8 * price_map[
                            min(price_map.keys(), key=lambda k: abs(k - ts))]) if ts else 'unknown',
                    }
                    incoming_txs.append(tx_data)
                    if fifo:
                        incoming['BTC'].append({
                            'amount': int(out['satoshis']) / 1e8,
                            'timestamp': ts,
                            'price': price_map[min(price_map.keys(), key=lambda k: abs(k - ts))] if ts else 'unknown'
                        })

            for inp in full_tx.get('inputs', []):
                if inp.get('address') in wallets:
                    key = f'{inp["txid"]}:{inp["vout"]}'
                    utxos.pop(key, None)
                    tx_data = {
                        'hash': txid,
                        'from': inp.get('address'),
                        'to': full_tx.get('outputs', [{}])[0].get('address', 'unknown'),
                        'amount': int(inp['satoshis']) / 1e8,
                        'timestamp': ts,
                        'value_eur': (int(inp['satoshis']) / 1e8 * price_map[
                            min(price_map.keys(), key=lambda k: abs(k - ts))]) if ts else 'unknown',
                    }
                    outgoing_txs.append(tx_data)
                    if fifo:
                        outgoing['BTC'].append({
                            'amount': int(inp['satoshis']) / 1e8,
                            'timestamp': ts,
                            'price': price_map[min(price_map.keys(), key=lambda k: abs(k - ts))] if ts else 'unknown'
                        })

            input_sum = sum(
                int(inp.get('satoshis', 0)) for inp in full_tx.get('inputs', []) if inp.get('address') in wallets)
            output_sum = sum(int(out.get('satoshis', 0)) for out in full_tx.get('outputs', []))
            if input_sum > 0:
                fee_btc = max(input_sum - output_sum, 0) / 1e8
                total_fees_btc += fee_btc
                if ts:
                    closest_price = price_map[min(price_map.keys(), key=lambda k: abs(k - ts))]
                    total_fees_eur += fee_btc * closest_price

        sales = {}
        if fifo:
            sales = self.calculate_fifo_sales(incoming, outgoing, start_ts=min(price_map.keys()),
                                              cutoff_ts=max(price_map.keys()))

        return utxos, total_fees_btc, total_fees_eur, sales, incoming_txs, outgoing_txs


    @staticmethod
    def calculate_fifo_sales(incoming, outgoing, cutoff_ts, start_ts=None):
        queues = {token: [dict(tx) for tx in txs] for token, txs in incoming.items()}
        sales = defaultdict(list)

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

        if start_ts is not None:
            for token in sales:
                sales[token] = [s for s in sales[token] if s['timestamp_sell'] >= start_ts]

        return sales

    async def get_balance_at_height(self, client: httpx.AsyncClient, wallets, height: int, price_map: dict, fifo=False):
        txs = await self.get_all_txs_multi(client, wallets)
        utxos, fees_btc, fees_eur, sales, incoming_tx, outgoing_tx = await self.reconstruct_utxo_set(
            client, wallets, txs, height, price_map, fifo=fifo
        )
        balance = sum(utxos.values()) / 1e8
        return balance, fees_btc, fees_eur, sales, incoming_tx, outgoing_tx


    async def get_price_map(self, client: httpx.AsyncClient, start_ts: int, end_ts: int):
        url = self.CG_PRICE_RANGE_URL.format(token_id='bitcoin')
        params = {'vs_currency': 'eur', 'from': start_ts, 'to': end_ts}
        headers = {'x-cg-pro-api-key': self.CG_API_KEY}
        r = await client.get(url, params=params, headers=headers)
        r.raise_for_status()
        return {int(t / 1000): p for t, p in r.json().get('prices', [])}


    @staticmethod
    def map_price(price_map, ts):
        ts = round(ts)
        if ts in price_map:
            return price_map[ts]
        return price_map[min(price_map.keys(), key=lambda k: abs(k - ts))]


    async def run(self, wallets, start_date, end_date, timezone='UTC', fifo=False):
        async with httpx.AsyncClient(timeout=60) as client:
            tz = ZoneInfo(timezone)
            start_dt = datetime.strptime(start_date, '%Y-%m-%d').replace(
                hour=0, minute=0, second=0, tzinfo=tz)
            end_dt = datetime.strptime(end_date, '%Y-%m-%d').replace(
                hour=0, minute=0, second=0, tzinfo=tz) + timedelta(days=1)
            start_ts = int(start_dt.timestamp())
            end_ts = int(end_dt.timestamp())

            start_height = await self.get_block_by_timestamp(client, start_ts)
            end_height = await self.get_block_by_timestamp(client, end_ts)
            price_map = await self.get_price_map(client, start_ts, end_ts)

            (bal_start, fees_start_btc, fees_start_eur, _, incoming_tx, _), (bal_end, fees_end_btc, fees_end_eur,
                                                             sales, _, outgoing_tx) = await asyncio.gather(
                self.get_balance_at_height(client, wallets, start_height, price_map, fifo=fifo),
                self.get_balance_at_height(client, wallets, end_height, price_map, fifo=fifo),
            )

            total_fees_btc = fees_end_btc - fees_start_btc
            total_fees_eur = fees_end_eur - fees_start_eur

            price_start = self.map_price(price_map, start_ts)
            price_end = self.map_price(price_map, end_ts)

            def aggregate_transactions(transactions):
                agg = defaultdict(
                    lambda: {'hash': None, 'from': None, 'to': None, 'timestamp': None, 'amount': 0, 'value_eur': 0})
                for tx in transactions:
                    h = tx['hash']
                    agg[h]['hash'] = h
                    agg[h]['from'] = tx['from']
                    agg[h]['to'] = tx['to']
                    agg[h]['timestamp'] = tx['timestamp']
                    agg[h]['amount'] += tx['amount']
                    agg[h]['value_eur'] += tx['value_eur']
                return list(agg.values())

            result = {
                'starting_balance': {
                    'BTC': bal_start,
                    'BTC_eur': bal_start * price_start,
                    'tokens': {}
                },
                'ending_balance': {
                    'BTC': bal_end,
                    'BTC_eur': bal_end * price_end,
                    'tokens': {}
                },
                'transactions': {
                    'incoming': aggregate_transactions(incoming_tx),
                    'outgoing': aggregate_transactions(outgoing_tx)
                },
                'total_gas_btc': total_fees_btc,
                'total_gas_eur': total_fees_eur,
                'sales': sales if fifo else None,
                'total_holdings': None
            }

            return result


# analyzer = BitcoinAnalyzer()
# result = asyncio.run(analyzer.run(
#     ['bc1q4mhdqjk43v0tcx4jhvn273kxqlhn8a2w4r2n2n'],
#     '2025-11-22',
#     '2025-11-25',
#     fifo=True
# ))
# print(json.dumps(result, indent=2))
