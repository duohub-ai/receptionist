"""RTVI Bot Server Implementation.

This FastAPI server manages RTVI bot instances and provides endpoints for both
direct browser access and RTVI client connections. It handles:
- Creating Daily rooms
- Managing bot processes
- Providing connection credentials
- Monitoring bot status

Requirements:
- Daily API key (set in .env file)
- Python 3.10+
- FastAPI
- Running bot implementation
"""

import argparse
import os
import subprocess
import time
from contextlib import asynccontextmanager
from typing import Any, Dict, Tuple

import aiohttp
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse
import sys
from loguru import logger

from pipecat.transports.services.helpers.daily_rest import DailyRESTHelper, DailyRoomParams

# Load environment variables from .env file
load_dotenv(override=True)

# Configure logger
logger.remove()  # Remove default handler
logger.add(sys.stdout, level="INFO")  # Add stdout handler with INFO level
logger.add("server.log", rotation="500 MB", level="DEBUG")  # Also log to file with rotation

# Maximum number of bot instances allowed per room
MAX_BOTS_PER_ROOM = 1

# Dictionary to track bot processes: {pid: (process, room_url)}
bot_procs = {}

# Store Daily API helpers
daily_helpers = {}


def cleanup():
    """Cleanup function to terminate all bot processes.

    Called during server shutdown.
    """
    for entry in bot_procs.values():
        proc = entry[0]
        proc.terminate()
        proc.wait()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """FastAPI lifespan manager that handles startup and shutdown tasks.

    - Creates aiohttp session
    - Initializes Daily API helper
    - Cleans up resources on shutdown
    """
    aiohttp_session = aiohttp.ClientSession()
    daily_helpers["rest"] = DailyRESTHelper(
        daily_api_key=os.getenv("DAILY_API_KEY", ""),
        daily_api_url=os.getenv("DAILY_API_URL", "https://api.daily.co/v1"),
        aiohttp_session=aiohttp_session,
    )
    yield
    await aiohttp_session.close()
    cleanup()


# Initialize FastAPI app with lifespan manager
app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)



# Add health check routes
@app.get("/health")
async def health_check():
    """Root health check endpoint."""
    return {"status": "healthy"}

@app.get("/health")
async def router_health_check():
    """Router-specific health check endpoint."""
    return {"status": "healthy"}


async def create_room_and_token() -> Tuple[str, str]:
    """Helper function to create a Daily room and generate an access token.

    Returns:
        tuple[str, str]: A tuple containing (room_url, token)

    Raises:
        HTTPException: If room creation or token generation fails
    """
    start_time = time.time()
    
    room = await daily_helpers["rest"].create_room(DailyRoomParams())
    if not room.url:
        raise HTTPException(status_code=500, detail="Failed to create room")

    token = await daily_helpers["rest"].get_token(room.url)
    if not token:
        raise HTTPException(status_code=500, detail=f"Failed to get token for room: {room.url}")

    elapsed_time = time.time() - start_time
    print(f"create_room_and_token latency: {elapsed_time:.2f}s")
    return room.url, token


@app.get("/")
async def start_agent(request: Request):
    """Endpoint for direct browser access to the bot.

    Creates a room, starts a bot instance, and redirects to the Daily room URL.

    Returns:
        RedirectResponse: Redirects to the Daily room URL

    Raises:
        HTTPException: If room creation, token generation, or bot startup fails
    """
    start_time = time.time()
    logger.info("Creating room")
    
    room_url, token = await create_room_and_token()
    logger.info(f"Room URL: {room_url}")

    # Check if there is already an existing process running in this room
    num_bots_in_room = sum(
        1 for proc in bot_procs.values() if proc[1] == room_url and proc[0].poll() is None
    )
    if num_bots_in_room >= MAX_BOTS_PER_ROOM:
        logger.error(f"Max bot limit reached for room: {room_url}")
        raise HTTPException(status_code=500, detail=f"Max bot limit reached for room: {room_url}")

    # Spawn a new bot process
    try:
        proc = subprocess.Popen(
            [f"python3 -m bot -u {room_url} -t {token}"],
            shell=True,
            bufsize=1,
            cwd=os.path.dirname(os.path.abspath(__file__)),
        )
        bot_procs[proc.pid] = (proc, room_url)
        logger.info(f"Started bot process with PID: {proc.pid}")
    except Exception as e:
        logger.error(f"Failed to start subprocess: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to start subprocess: {e}")

    elapsed_time = time.time() - start_time
    logger.info(f"start_agent latency: {elapsed_time:.2f}s")
    return RedirectResponse(room_url)


@app.post("/connect")
async def rtvi_connect(request: Request) -> Dict[Any, Any]:
    # Parse the incoming JSON payload
    payload = await request.json()
    # Log the full payload to see what's being received
    logger.info(f"Payload received: {payload}")
    
    # Extract custom parameters
    pathname = payload.get("pathname")
    user_id = payload.get("user_id")
    marketing_data = payload.get("marketingData", {})
    
    logger.info(f"Custom params - pathname: {pathname}, marketing_data: {marketing_data}")

    # Continue with creating room and token
    room_url, token = await create_room_and_token()
    
    # Build command with all parameters
    cmd_parts = [
        f"python3 -m bot",
        f"-u {room_url}",
        f"-t {token}",
        f"-p {pathname}" if pathname else "",
        f"-i {user_id}" if user_id else ""
    ]
    
    # Add marketing data parameters if they exist
    for key, value in marketing_data.items():
        if value:
            cmd_parts.append(f"--{key} {value}")
    
    cmd = " ".join(filter(None, cmd_parts))
    
    try:
        proc = subprocess.Popen(
            [cmd],
            shell=True,
            bufsize=1,
            cwd=os.path.dirname(os.path.abspath(__file__)),
        )
        bot_procs[proc.pid] = (proc, room_url)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to start subprocess: {e}")

    return {"room_url": room_url, "token": token}



@app.get("/status/{pid}")
def get_status(pid: int):
    """Get the status of a specific bot process.

    Args:
        pid (int): Process ID of the bot

    Returns:
        JSONResponse: Status information for the bot

    Raises:
        HTTPException: If the specified bot process is not found
    """
    start_time = time.time()
    
    # Look up the subprocess
    proc = bot_procs.get(pid)

    # If the subprocess doesn't exist, return an error
    if not proc:
        raise HTTPException(status_code=404, detail=f"Bot with process id: {pid} not found")

    # Check the status of the subprocess
    status = "running" if proc[0].poll() is None else "finished"
    elapsed_time = time.time() - start_time
    print(f"get_status latency: {elapsed_time:.2f}s")
    return JSONResponse({"bot_id": pid, "status": status})


@app.post("/")
async def join_existing_room(request: Request) -> Dict[Any, Any]:
    """Endpoint to join an existing Daily room.
    
    Expects a JSON body with a 'room_url' field.
    Starts a bot instance in the specified room.

    Returns:
        Dict[Any, Any]: Status response with room_url and bot_pid
    """
    start_time = time.time()
    
    # Get room URL from request body
    body = await request.json()
    room_url = body.get('room_url')
    
    if not room_url:
        raise HTTPException(status_code=400, detail="room_url is required")

    # Generate token for the existing room
    token = await daily_helpers["rest"].get_token(room_url)
    if not token:
        raise HTTPException(status_code=500, detail=f"Failed to get token for room: {room_url}")

    # Check if there is already a bot in this room
    num_bots_in_room = sum(
        1 for proc in bot_procs.values() if proc[1] == room_url and proc[0].poll() is None
    )
    if num_bots_in_room >= MAX_BOTS_PER_ROOM:
        raise HTTPException(status_code=500, detail=f"Max bot limit reached for room: {room_url}")

    # Start the bot process
    try:
        proc = subprocess.Popen(
            [f"python3 -m bot -u {room_url} -t {token}"],
            shell=True,
            bufsize=1,
            cwd=os.path.dirname(os.path.abspath(__file__)),
        )
        bot_procs[proc.pid] = (proc, room_url)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to start subprocess: {e}")

    elapsed_time = time.time() - start_time
    print(f"join_existing_room latency: {elapsed_time:.2f}s")
    return {
        "status": "success",
        "room_url": room_url,
        "bot_pid": proc.pid
    }




if __name__ == "__main__":
    import uvicorn

    # Parse command line arguments for server configuration
    default_host = os.getenv("HOST", "0.0.0.0")
    default_port = int(os.getenv("FAST_API_PORT", "7860"))

    parser = argparse.ArgumentParser(description="Daily Storyteller FastAPI server")
    parser.add_argument("--host", type=str, default=default_host, help="Host address")
    parser.add_argument("--port", type=int, default=default_port, help="Port number")
    parser.add_argument("--reload", action="store_true", help="Reload code on change")

    config = parser.parse_args()

    # Start the FastAPI server
    uvicorn.run(
        "server:app",
        host=config.host,
        port=config.port,
        reload=config.reload,
    )