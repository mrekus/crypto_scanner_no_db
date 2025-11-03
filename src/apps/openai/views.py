import json
from fastapi import APIRouter
from fastapi.responses import JSONResponse
from openai import OpenAI
from pydantic import BaseModel

router = APIRouter()


class AIRequest(BaseModel):
    prompt: str
    context: dict = {}


@router.post('/ai')
async def ai_endpoint(req: AIRequest):
    client = OpenAI(
        api_key='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'
    )

    instructions = f'''
    You receive on-chain analysis results in JSON. Fulfill the user prompt strictly using the provided data. Provide a concise, structured, human-readable summary. 
    Use bullet points, tables, or short paragraphs. 
    Do NOT ask follow-up questions, speculate, or provide advice beyond the data. 
    Limit response length to the key metrics and insights.
    Round numbers to about 2 decimal places, or whatever makes sense.
    Tokens without value are shitcoins, APIs don't track their value.

    JSON:
    {json.dumps(req.context)}
    '''

    response = client.responses.create(
        model='gpt-5-nano',
        instructions=instructions,
        input=req.prompt,
        store=False,
    )

    return JSONResponse({'response': response.output_text})
