import discord
from discord.ext import tasks, commands
from datetime import datetime, timezone, timedelta
import logging
logger = logging.getLogger(__name__)

INACTIVE_WARNING_THRESHOLD = timedelta(minutes=50)
INACTIVE_DELETE_THRESHOLD = timedelta(hours=1)
WARNING_MESSAGE = "will be deleted in 10 minutes"

class DiscordJanitor(commands.Cog):
    """Discord Channel Cleanup Bot
    
    Role: Automatically cleans up inactive temporary channels in Discord guilds.
    
    Methods:
        __init__(self, bot) : Initialize the cog with the bot instance.
        janitor_loop(self) : Main cleanup loop that runs every 5 minutes to check and clean tmp channels.
        process_channel(self, channel) : Process a single channel to determine if it should be cleaned.
        before_janitor(self) : Before loop hook to wait for bot ready state.
    """
    def __init__(self, bot):
        self.bot = bot
        logger.info("DiscordJanitor initialized.")

    async def cog_load(self):
        self.janitor_loop.start()
        logger.info("Janitor loop started.")

    @tasks.loop(minutes=10)
    async def janitor_loop(self):
        try:
            for guild in self.bot.guilds:
                for channel in guild.text_channels:
                    if "tmp" in channel.name.lower():
                        await self.process_channel(channel)
        except Exception as e:
            logger.error(f"Janitor Error: {e}")

    async def process_channel(self, channel):
        last_message = None
        async for message in channel.history(limit=5):
            if message.author != self.bot.user:
                last_message = message
                break
        
        if not last_message:
            last_message = await self._get_last_message(channel)

        if not last_message:
            return

        now = datetime.now(timezone.utc)
        inactive_duration = now - last_message.created_at

        if inactive_duration >= INACTIVE_DELETE_THRESHOLD:
            await self.bot.clean_channel(channel)
        elif inactive_duration >= INACTIVE_WARNING_THRESHOLD:
            await self._check_and_send_warning(channel)

    async def _get_last_message(self, channel):
        last_message = None
        async for message in channel.history(limit=1):
            last_message = message
        return last_message

    async def _check_and_send_warning(self, channel):
        already_warned = await self._check_already_warned(channel)

        if not already_warned:
            await channel.send(
                f"**Warning**: {channel.mention} has been inactive for 50 minutes and will be deleted in 10 minutes."
            )

    async def _check_already_warned(self, channel):
        already_warned = False
        async for msg in channel.history(limit=10):
            if msg.author == self.bot.user and WARNING_MESSAGE in msg.content:
                already_warned = True
                break
        return already_warned

    @janitor_loop.before_loop
    async def before_janitor(self):
        await self.bot.wait_until_ready()
