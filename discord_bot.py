import discord, asyncio, threading, queue, traceback, os, subprocess, requests
from config_loader import cfg
from ollama_config import OllamaConfig
from ollama_service import llm
import logging
logger = logging.getLogger(__name__)

class DiscordBot(discord.Client):
    """Discord Bot for AI-powered chat interactions
    
    Role: Manages Discord bot operations, LLM integration, and multiroom messaging.
    
    Methods:
        __init__(self, *args, **kwargs) : Initialize the Discord bot client.
        on_ready(self) : Handle bot startup and send notification.
        on_message(self, m) : Handle incoming messages from users.
        handle_channel(self, m) : Process messages in configured channels.
        handle_channel_no_memory(self, m) : Alias for handle_channel.
        llm_worker(self, loop) : Worker thread for LLM request processing.
        get_config_from_topic(self, topic) : Parse topic string into OllamaConfig.
        handle_multiroom(self, m) : Handle multiroom message forwarding.
        send_smart_split(self, channel, text, limit, reply_to_id, files) : Split and send large messages.
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.llm_queue = queue.Queue()
        self.worker_thread = None

    async def on_ready(self):
        logger.info(f"on_ready")
        if not self.worker_thread:
            loop = asyncio.get_running_loop()
            self.worker_thread = threading.Thread(target=self.llm_worker, args=(loop,), daemon=True)
            self.worker_thread.start()

        try:
            channel_name = cfg.bot.channels.notify
            channel = discord.utils.get(self.get_all_channels(), name=channel_name)
            
            if channel:
                await channel.send(f"**A.L.I.S.U : System restarted**\nNotification server is back online.")
            else:
                logger.info(f"Unable to send notification: channel '{channel_name}' not found.")
                
        except Exception as e:
            logger.info(f"Error sending startup message: {e}")
        logger.info(f"{self.user} connected.")

    async def clean_current_channel(self, m):
        try:
            old_ch = m.channel
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
            logger.error(f"Error during channel clean/migration for {m.channel.id}: {e}")
            return
            
    async def on_message(self, m):
        if m.author == self.user:
            return

        if m.content == "!archive_clean" and m.author.guild_permissions.manage_channels:
            await self.clean_current_channel(m)
            return

        if m.channel.name == cfg.bot.channels.multiroom:
            await self.handle_multiroom(m)
        elif m.channel.name.startswith(cfg.bot.channels.os_prefix):
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
                    conf.model = 'qwen2.5:7b'
                    res = llm.generate(conf).get('content', "Erreur de génération")

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

    async def handle_multiroom(self, m):
        try:
            is_v = any(a.filename.endswith('.ogg') for a in m.attachments)
            path = f"/tmp/{m.id}.ogg"
            if is_v:
                await m.attachments[0].save(path)
            cmd = [cfg.multiroom.python_bin, "-m", "tools.hub_messenger"]
            if is_v:
                cmd.append("--ptt")
                cmd.append(path)
            else:
                cmd.append(m.content.strip())
            subprocess.Popen(cmd, cwd=cfg.multiroom.working_dir)
            await m.add_reaction("✅")
        except Exception as e:
            logger.info(f'handle_multiroom {e}')
            await m.add_reaction("❌")

    async def send_smart_split(self, channel, text, limit=1900, reply_to_id=None, files=None):
        target = None
        if reply_to_id:
            try:
                target = await channel.fetch_message(reply_to_id)
            except:
                pass

        in_code = False
        lang = ""
        while text:
            if len(text) <= limit:
                chunk, text = text, ""
            else:
                cut = text.rfind('\n\n', 0, limit)
                if cut < limit * 0.5:
                    cut = text.rfind('\n', 0, limit)
                if cut < limit * 0.5:
                    cut = text.rfind(' ', 0, limit)
                cut = cut if cut != -1 else limit
                chunk, text = text[:cut], text[cut:].lstrip()

            ticks = chunk.count('```')
            if in_code:
                if ticks % 2 != 0:
                    in_code = False
                else:
                    chunk += "\n```"
                    text = f"```{lang}\n" + text
            elif ticks % 2 != 0:
                in_code = True
                last = chunk.rfind('```')
                nl = chunk.find('\n', last)
                lang = chunk[last+3:nl].strip() if nl != -1 else ""
                chunk += "\n```"
                text = f"```{lang}\n" + text

            if target:
                await target.reply(content=chunk, files=files or [])
                target, files = None, None
            else:
                await channel.send(content=chunk)
