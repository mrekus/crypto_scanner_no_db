from typing import List, Optional

from fastapi import APIRouter, Depends, Request, Query
from fastapi.responses import StreamingResponse, HTMLResponse
import json

from apps.networks.ethereum.calculator import WalletAnalyzer
from conf import cfg
from models.users import User
from utils.utils import require_user

router = APIRouter()

@router.get('/calculator')
async def calculator_page(request: Request, user: User = Depends(require_user)):
    if isinstance(user, HTMLResponse):
        return user
    return cfg.templates.TemplateResponse('calculator.html', {'request': request})


@router.get('/check')
async def check(
    wallets: List[str] = Query(...),
    start_date: str = None,
    end_date: str = None,
    timezone: str = 'UTC',
    fifo: bool = False,
    user: User = Depends(require_user)
):
    # if isinstance(user, HTMLResponse):
    #     return user
    wallets = [w.strip() for w in wallets[0].split(',')]

    async def event_generator():
        analyzer = WalletAnalyzer()
        try:
            result = await analyzer.run(wallets, start_date, end_date, timezone, fifo)
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
                'total_gas_eth': result['total_gas_eth'],
                'total_gas_eur': result['total_gas_eur'],
                'outgoing': result['transactions']['outgoing'],
                'incoming': result['transactions']['incoming'],
                'total_holdings': result['total_holdings'],
                'sales': result['sales'],
            }

            yield f"data: {json.dumps({'type': 'result', 'data': payload})}\n\n"

        except Exception as e:
            yield f"data: {json.dumps({'type': 'log', 'msg': str(e)})}\n\n"

    return StreamingResponse(event_generator(), media_type='text/event-stream')
