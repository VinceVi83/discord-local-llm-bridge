import discord, asyncio, threading, queue, traceback, os, subprocess, requests
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from discord.ext import commands
from config_loader import cfg
from ollama_config import OllamaConfig
from ollama_service import llm
from discord_janitor import DiscordJanitor
from pathlib import Path
import importlib
import logging
logger = logging.getLogger(__name__)

class DiscordBot(commands.Bot):
    """Discord Bot for AI-powered chat interactions
    
    Role: Manages Discord bot operations, LLM integration, and multiroom messaging.
    
    Methods:
        __init__(self, *args, **kwargs) : Initialize the Discord bot client.
        load_plugins(self) : Load and register plugin handlers and scheduled tasks.
        on_ready(self) : Handle bot startup and send notification.
        clean_channel(self, channel) : Clone and clean a channel, migrating settings.
        command_help(self, m) : Send help text to the message channel.
        execute_command(self, m) : Execute bot commands like !archive_clean, !restart, !reboot.
        on_message(self, m) : Handle incoming messages from users.
        handle_channel(self, m) : Process messages in configured channels with memory.
        handle_channel_no_memory(self, m) : Alias for handle_channel without memory.
        llm_worker(self, loop) : Worker thread for LLM request processing.
        get_config_from_topic(self, topic) : Parse topic string into OllamaConfig.
        send_smart_split(self, channel, text, limit, files) : Split and send large messages.
    """
    def __init__(self, *args, **kwargs):
        intents = discord.Intents.default()
        intents.guilds = True
        intents.messages = True
        intents.message_content = True
        
        super().__init__(command_prefix="!", intents=intents, *args, **kwargs)
        self.initialized = False
        self.llm_queue = queue.Queue()
        self.worker_thread = None
        self.pending_autostarts = []
        self.janitor = None

        self.scheduler = AsyncIOScheduler()
        self.plugin_name_list = []

    def load_plugins(self):
        plugins_path = Path("plugins")
        if not plugins_path.exists():
            return

        for plugin_dir in plugins_path.iterdir():
            service_file = plugin_dir / "service.py"
            if not plugin_dir.is_dir() or not service_file.exists():
                continue
            try:
                module_path = f"plugins.{plugin_dir.name}.service"
                module = importlib.import_module(module_path)

                for item in dir(module):
                    func = getattr(module, item)
                    if item.startswith("handle_"):
                        setattr(self, item, func.__get__(self, self.__class__))
                        if plugin_dir.name not in self.plugin_name_list:
                            self.plugin_name_list.append(plugin_dir.name)
                        logger.info(f"Plugin loaded: {plugin_dir.name} -> {item}")

                    elif item.startswith("task_") and hasattr(func, "schedule_config"):
                        config = func.schedule_config
                        bound_func = func.__get__(self, self.__class__)
                        async def task_wrapper(f=bound_func):
                            await asyncio.to_thread(f)
                            
                        scheduler_config = {k: v for k, v in config.items() if k != "autostart"}
                        self.scheduler.add_job(task_wrapper, **scheduler_config)
                        logger.info(f"Task scheduled (Threaded): {plugin_dir.name} -> {item}")

                        if config.get("autostart", False):
                            self.pending_autostarts.append(bound_func)
                            logger.info(f"Task queued for autostart: {plugin_dir.name}")

            except Exception as e:
                logger.error(f"Failed to load plugin {plugin_dir.name}: {e}")

    async def on_ready(self):
        logger.info(f"Logged in as {self.user}")
        if not self.initialized:
            self.load_plugins()
            if not self.get_cog("DiscordJanitor"):
                try:
                    await self.add_cog(DiscordJanitor(self))
                    logger.info("DiscordJanitor Cog loaded successfully.")
                except Exception as e:
                    logger.error(f"Could not load DiscordJanitor: {e}")

            loop = asyncio.get_running_loop()
            if not self.worker_thread:
                self.worker_thread = threading.Thread(target=self.llm_worker, args=(loop,), daemon=True)
                self.worker_thread.start()
                logger.info("LLM Worker thread started.")

            if not self.scheduler.running:
                self.scheduler._eventloop = loop 
                self.scheduler.start()

            for func in self.pending_autostarts:
                logger.info(f"Autostart launch: {func.__name__}")
                asyncio.create_task(asyncio.to_thread(func))
            
            self.pending_autostarts.clear()
            self.initialized = True
        else:
            logger.info("Reconnection detected, skipping initialization.")

        try:
            channel_name = cfg.bot.notification
            channel = discord.utils.get(self.get_all_channels(), name=channel_name)
            if channel:
                await channel.send(f"**A.L.I.S.U : System restarted**\nNotification server is back online.")
            else:
                logger.info(f"Unable to send notification: channel '{channel_name}' not found.")
        except Exception as e:
            logger.info(f"Error sending startup message: {e}")
        logger.info(f"{self.user} connected.")

    async def clean_channel(self, channel):
        try:
            old_ch = channel
            settings = {
                "name": old_ch.name,
                "topic": old_ch.topic,
                "position": old_ch.position,
                "nsfw": old_ch.nsfw,
                "slowmode_delay": old_ch.slowmode_delay,
                "category": old_ch.category,
                "overwrites": old_ch.overwrites
            }

            new_ch = await old_ch.clone(reason="Channel Clean & Parameter Migration")
            await new_ch.edit(
                topic=settings["topic"],
                position=settings["position"],
                nsfw=settings["nsfw"],
                slowmode_delay=settings["slowmode_delay"]
            )

            await old_ch.delete()
            logger.info(f"Channel cleaned: '{settings['name']}'. Parameters successfully migrated from {old_ch.id} to {new_ch.id}.")
            return
        except Exception as e:
            logger.error(f"Error during channel clean/migration for {channel.id}: {e}")
            return

    async def command_help(self, m):
        await self.send_smart_split(
            channel=m.channel,
            text=cfg.agents.help
        )

    async def execute_command(self, m):
        if m.content == '!archive_clean':
            await self.clean_channel(m.channel)
        elif m.content == '!restart':
            await subprocess.Popen(["sudo", "/usr/local/bin/multiroom-restart"])
        elif m.content == '!reboot':
            await subprocess.Popen(["sudo", "reboot"])
        else:
            await self.command_help(m)

    async def on_message(self, m):
        if m.content.startswith('!'):
            await self.execute_command(m)
            return

        if m.author == self.user:
            return

        for plugin_name in self.plugin_name_list:
            if m.channel.name.startswith(plugin_name):
                method_name = f"handle_{plugin_name}"
                if hasattr(self, method_name):
                    await getattr(self, method_name)(m)
                    return

        ignore_prefixes = tuple(vars(cfg.bot.ignore_channel).values())
        if m.channel.name.startswith(ignore_prefixes):
            return

        if m.channel.name.startswith(cfg.bot.channels.os_prefix):
            await self.handle_channel_no_memory(m)
        else:
            await self.handle_channel(m)

    async def handle_channel(self, m):
        done = asyncio.Event()
        async with m.channel.typing():
            self.llm_queue.put({
                "channel_name": m.channel.name,
                "topic": getattr(m.channel, 'topic', ''),
                "content": m.content,
                "author_id": m.author.id,
                "message_id": m.id,
                "done_event": done
            })
            try:
                await asyncio.wait_for(done.wait(), timeout=90.0)
            except asyncio.TimeoutError:
                logger.info(f"Timeout: {m.id}")

    async def handle_channel_no_memory(self, m):
        await self.handle_channel(m)

    def llm_worker(self, loop):
        while True:
            task = self.llm_queue.get()
            if not task:
                break
            try:
                conf = self.get_config_from_topic(task['topic'])
                conf.set_content(task['content'])
                res = llm.generate(conf).get('content', "")

                if not res:
                    conf.model = 'qwen2.5:3b'
                    res = llm.generate(conf).get('content', "Generation error")

                loop.call_soon_threadsafe(task['done_event'].set)

                payload = {
                    "channel_name": task['channel_name'],
                    "msg": f"<@!{task['author_id']}> {res}",
                    "reply_to": task['message_id']
                }
                requests.post(f"http://127.0.0.1:{cfg.system.port}/send", json=payload, timeout=15)
            except:
                traceback.print_exc()
            finally:
                self.llm_queue.task_done()

    
    def get_config_from_topic(self, topic: str) -> OllamaConfig:
        config = OllamaConfig()
        if not topic:
            return config

        header, _, system_prompt = topic.partition('---')
        
        if system_prompt:
            config.system_prompt = system_prompt.strip()

        raw_pairs = [item.split(':', 1) for item in header.split('|') if ':' in item]
        settings = {k.strip().lower(): v.strip() for k, v in raw_pairs}

        if 'model' in settings:
            config.model = settings.pop('model')
        
        if 'soul' in settings:
            config.personality = settings.pop('soul')
            
        if 'profile' in settings:
            config.set_profile(settings.pop('profile'))

        for key, value in settings.items():
            if key in config.options:
                orig_type = type(config.options[key])
                try:
                    if orig_type == bool:
                        config.options[key] = value.lower() == 'true'
                    else:
                        config.options[key] = orig_type(value)
                except (ValueError, TypeError):
                    pass 
            else:
                config.options[key] = value

        return config

    async def send_smart_split(self, channel, text, limit=1900, files=None):
        in_code = False
        lang = ""
        remaining_text = text if text else ""
        chunks = []

        while remaining_text:
            if len(remaining_text) <= limit:
                chunk, remaining_text = remaining_text, ""
            else:
                cut = remaining_text.rfind('\n\n', 0, limit)
                if cut < limit * 0.5:
                    cut = remaining_text.rfind('\n', 0, limit)
                if cut < limit * 0.5:
                    cut = remaining_text.rfind(' ', 0, limit)
                cut = cut if cut != -1 else limit
                chunk, remaining_text = remaining_text[:cut], remaining_text[cut:].lstrip()

            ticks = chunk.count('```')
            if in_code:
                if ticks % 2 != 0:
                    in_code = False
                else:
                    chunk += "\n```"
                    remaining_text = f"```{lang}\n" + remaining_text
            elif ticks % 2 != 0:
                in_code = True
                last = chunk.rfind('```')
                nl = chunk.find('\n', last)
                lang = chunk[last+3:nl].strip() if nl != -1 else ""
                chunk += "\n```"
                remaining_text = f"```{lang}\n" + remaining_text
            
            chunks.append(chunk)

            discord_files = files if files else []

        if not chunks:
            if discord_files:
                await channel.send(files=discord_files)
            return

        for i, chunk in enumerate(chunks):
            is_last = (i == len(chunks) - 1)
            
            if is_last and discord_files:
                await channel.send(content=chunk, files=discord_files)
            else:
                await channel.send(content=chunk)
