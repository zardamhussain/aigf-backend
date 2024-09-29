from contextlib import asynccontextmanager
import os
import argparse
import subprocess
import atexit
import time

import aiohttp
from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import BaseModel

from pipecat.transports.services.helpers.daily_rest import DailyRESTHelper, DailyRoomParams, DailyRoomProperties

from dotenv import load_dotenv
load_dotenv(override=True)
MAX_BOTS_PER_ROOM = 2

bot_procs = {}

daily_helpers= {
}


def cleanup():
    for proc in bot_procs.values():
        proc.terminate()
        proc.wait()


@asynccontextmanager
async def lifespan(app: FastAPI):

    aiohttp_session = aiohttp.ClientSession()
    daily_helpers["rest"] = DailyRESTHelper(
        daily_api_key=os.getenv("DAILY_API_KEY", ""),
        daily_api_url=os.getenv("DAILY_API_URL", 'https://api.daily.co/v1'),
        aiohttp_session=aiohttp_session
    )
    yield
    await aiohttp_session.close()
    cleanup()

app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/new-meeting")
async def start_agent(request: Request):
    
    room = await daily_helpers["rest"].create_room(DailyRoomParams(
        properties=DailyRoomProperties(
            exp= time.time() + 60*60,
        )
    ))
    
    if not room.url:
        raise HTTPException(
            status_code=500,
            detail="Missing 'room' property in request data. Cannot start agent without a target room!"
        )

    return JSONResponse({"status": "OK", "roomUrl": room.url, "roomName": room.name})


class JoinBotConfig(BaseModel):
    room_url: str
    participant_id: str

@app.post("/bot/join")
async def join_bot(config: JoinBotConfig):
    
    room_url = config.room_url

    if not room_url:
        raise HTTPException(
            status_code=500,
            detail="Missing 'room' property in request data. Cannot start agent without a target room!")


    num_bots_in_room = sum(
        1 for proc in bot_procs.values() if proc[1] == room_url and proc[0].poll() is None)
    if num_bots_in_room >= MAX_BOTS_PER_ROOM:
        raise HTTPException(
            status_code=500, detail=f"Max bot limited reach for room: {room_url}")

    
    token = await daily_helpers["rest"].get_token(room_url)

    if not token:
        raise HTTPException(
            status_code=500, detail=f"Failed to get token for room: {room_url}")

    try:
        proc = subprocess.Popen(
            [
                f"python3 -m bots -u {room_url} -t {token} -p {config.participant_id}"
            ],
            shell=True,
            bufsize=1,
            cwd=os.path.dirname(os.path.abspath(__file__))
        )
        bot_procs[proc.pid] = (proc, room_url)
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to start subprocess: {e}")

    return JSONResponse({"status": "OK"})
