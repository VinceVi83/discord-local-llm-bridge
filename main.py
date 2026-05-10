import asyncio
import uvicorn
from pathlib import Path
import discord
import os
import traceback
from fastapi import FastAPI
from pydantic import BaseModel
from typing import List, Optional

from config_loader import cfg, setup_logging
from discord_bot import DiscordBot
import logging

setup_logging()
logger = logging.getLogger(__name__)


def get_channel_by_name(bot, channel_name):
    channel = discord.utils.get(bot.get_all_channels(), name=channel_name)
    if not channel:
        logger.info(f"Channel '{channel_name}' not found.")
        return None
    return channel


def check_send_permissions(channel):
    permissions = channel.permissions_for(channel.guild.me)
    if not permissions.send_messages:
        return False
    return True


def handle_attachments(attachments):
    discord_files = []
    opened_files = []
    
    if not attachments:
        return [], []

    for path_str in attachments:
        path = Path(path_str)
        if not path.exists():
            logger.error(f"File not found: {path_str}")
            continue
            
        try:
            f = open(path, 'rb')
            opened_files.append(f)
            discord_files.append(discord.File(f, filename=path.name))
        except Exception as e:
            logger.error(f"Cannot open file {path_str}: {e}")
            
    return discord_files, opened_files


def close_file_handles(opened_files):
    for f in opened_files:
        f.close()


class Notification(BaseModel):
    """Notification API Request Model
    
    Role: Defines the structure for incoming notification requests to the API.
    
    Methods:
        __init__(self, channel_name, msg, attachments=None, reply_to=None) : Initialize notification with channel, message, optional attachments and reply target.
    """
    channel_name: str
    msg: str
    attachments: Optional[List[str]] = []
    reply_to: Optional[int] = None


app = FastAPI(title="A.L.I.S.U API Server")
bot = DiscordBot()


@app.get("/status")
async def get_status():
    return {
        "bot_online": bot.is_ready(),
        "user": str(bot.user) if bot.user else None,
        "latency": f"{round(bot.latency * 1000)}ms" if bot.is_ready() else None
    }


@app.post("/send")
async def send_notification(notif: Notification):
    if not bot.is_ready():
        return {"status": "error", "message": "Discord bot is not ready yet"}

    channel = get_channel_by_name(bot, notif.channel_name)
    if not channel:
        logger.error(f"Could not find channel {notif.channel_id}")
        return
    
    discord_files, opened_files = handle_attachments(notif.attachments)
    
    logger.info(f"Sending notification to {channel.name} with {len(discord_files)} files")

    try:
        await bot.send_smart_split(
            channel=channel,
            text=notif.msg,
            files=discord_files
        )
    except Exception as e:
        logger.error(f"Error in send_notification: {e}")
    finally:
        close_file_handles(opened_files)


async def start_services():
    config = uvicorn.Config(
        app, 
        host=cfg.system.host, 
        port=cfg.system.port, 
        log_level=cfg.system.log_level,
        loop="asyncio"
    )
    server = uvicorn.Server(config)

    logger.info("Starting A.L.I.S.U (Bot + API)...\n")
    await asyncio.gather(
        bot.start(cfg.bot.token),
        server.serve()
    )

if __name__ == "__main__":
    try:
        asyncio.run(start_services())
    except KeyboardInterrupt:
        logger.info("\nSystem stopped by user.")
    except Exception as e:
        logger.info(f"Fatal error on startup: {e}")
        traceback.print_exc()
