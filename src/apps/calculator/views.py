from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse, HTMLResponse
import asyncio, json

from apps.networks.ethereum.calculator import WalletAnalyzer
from conf import cfg
from models.users import User
from utils.utils import require_user

router = APIRouter()

@router.get("/calculator")
async def calculator_page(request: Request, user: User = Depends(require_user)):
    if isinstance(user, HTMLResponse):
        return user
    return cfg.templates.TemplateResponse("calculator.html", {"request": request})

@router.get("/check")
async def check(wallet: str, start_date: str, end_date: str, user: User = Depends(require_user)):
    if isinstance(user, HTMLResponse):
        return user

    async def event_generator():
        analyzer = WalletAnalyzer()
        try:
            result = await analyzer.run(wallet, start_date, end_date)
            payload = {
                "starting_balance": {
                    "eth": result["starting_balance"]["ETH"],
                    "eur": result["starting_balance"]["ETH_eur"],
                },
                "ending_balance": {
                    "eth": result["ending_balance"]["ETH"],
                    "eur": result["ending_balance"]["ETH_eur"],
                },
                "total_gas_eth": result["total_gas_eth"],
                "total_gas_eur": result["total_gas_eur"],
                "transactions": result["transactions"]["outgoing"] + result["transactions"]["incoming"],
            }
            yield f"data: {json.dumps({'type': 'result', 'data': payload})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'type': 'log', 'msg': str(e)})}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")
