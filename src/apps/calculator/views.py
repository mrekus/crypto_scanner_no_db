from typing import List

from fastapi import APIRouter, Request, Query
from fastapi.responses import StreamingResponse
import json

from starlette.responses import Response

from apps.networks.bitcoin.calculator import BitcoinAnalyzer
from apps.networks.ethereum.calculator import WalletAnalyzer
from apps.networks.solana.calculator import SolanaAnalyzer
from conf import cfg

router = APIRouter()

@router.get('/calculator')
async def calculator_page(request: Request):
    return cfg.templates.TemplateResponse('calculator.html', {'request': request})


@router.get('/check')
async def check(
    wallets: List[str] = Query(...),
    start_date: str = None,
    end_date: str = None,
    timezone: str = 'UTC',
    fifo: bool = False,
):
    wallets = [w.strip() for w in wallets[0].split(',')]

    async def event_generator():
        try:
            wallet = wallets[0]
            is_btc = wallet.startswith('bc1') or wallet.startswith('1') or wallet.startswith('3')
            is_eth = wallet.startswith('0x')
            is_solana = len(wallet) in (43, 44)  # typical Solana address length

            if is_btc:
                analyzer = BitcoinAnalyzer()
            elif is_eth:
                analyzer = WalletAnalyzer()
            elif is_solana:
                analyzer = SolanaAnalyzer()
            else:
                raise ValueError("Unknown wallet type")

            result = await analyzer.run(wallets, start_date, end_date, timezone, fifo)

            if is_btc:
                payload = {
                    'starting_balance': {
                        'btc': result['starting_balance']['BTC'],
                        'eur': result['starting_balance']['BTC_eur'],
                        'tokens': result['starting_balance']['tokens'],
                    },
                    'ending_balance': {
                        'btc': result['ending_balance']['BTC'],
                        'eur': result['ending_balance']['BTC_eur'],
                        'tokens': result['ending_balance']['tokens'],
                    },
                    'fees': result['total_gas_btc'],
                    'fees_eur': result['total_gas_eur'],
                    'outgoing': result['transactions']['outgoing'],
                    'incoming': result['transactions']['incoming'],
                    'sales': result['sales'],
                }
            elif is_eth:
                payload = {
                    'starting_balance': {
                        'eth': result['starting_balance']['ETH'],
                        'eur': result['starting_balance']['ETH_eur'],
                        'tokens': result['starting_balance']['tokens'],
                    },
                    'ending_balance': {
                        'eth': result['ending_balance']['ETH'],
                        'eur': result['ending_balance']['ETH_eur'],
                        'tokens': result['ending_balance']['tokens'],
                    },
                    'fees': result['total_gas_eth'],
                    'fees_eur': result['total_gas_eur'],
                    'outgoing': result['transactions']['outgoing'],
                    'incoming': result['transactions']['incoming'],
                    'sales': result['sales'],
                }
            elif is_solana:
                payload = {
                    'starting_balance': {
                        'sol': result['starting_balance']['SOL'],
                        'eur': result['starting_balance']['SOL_eur'],
                        'tokens': result['starting_balance']['tokens'],
                    },
                    'ending_balance': {
                        'sol': result['ending_balance']['SOL'],
                        'eur': result['ending_balance']['SOL_eur'],
                        'tokens': result['ending_balance']['tokens'],
                    },
                    'fees': result['total_gas_sol'],
                    'fees_eur': result['total_gas_eur'],
                    'outgoing': result['transactions']['outgoing'],
                    'incoming': result['transactions']['incoming'],
                    'sales': result['sales'],
                }

            yield f'data: {json.dumps({"type": "result", "data": payload})}\n\n'

        except Exception as e:
            yield f'data: {json.dumps({"type": "log", "msg": str(e)})}\n\n'


    return StreamingResponse(
        event_generator(),
        media_type='text/event-stream',
        headers={
            'Access-Control-Allow-Origin': cfg.CORS_ENDPOINT,
            'Access-Control-Allow-Methods': 'GET, OPTIONS',
            'Access-Control-Allow-Headers': 'Content-Type',
        }
    )


@router.options('/check')
async def check_options():
    return Response(
        headers={
            'Access-Control-Allow-Origin': cfg.CORS_ORIGIN,
            'Access-Control-Allow-Methods': 'GET, OPTIONS',
            'Access-Control-Allow-Headers': 'Content-Type',
        }
    )
    
