
import os
import json
from pathlib import Path
from config_loader import cfg
from ollama_service import llm
from ollama_config import OllamaConfig
import sys
import logging
import threading
import requests
logger = logging.getLogger(__name__)


class Utils:
    @staticmethod
    def llm_call(model, system_prompt, user_message):
        conf = OllamaConfig()
        conf.model = model
        conf.system_prompt = system_prompt
        conf.set_content(user_message)
        return llm.generate(conf)

    @staticmethod
    def get_unique_path(dir_path, base_name, extension=".wav"):
        directory = Path(dir_path)
        directory.mkdir(parents=True, exist_ok=True)

        filename = f"{base_name}{extension}"
        dest_path = directory / filename

        counter = 1
        while dest_path.exists():
            filename = f"{base_name}_{counter}{extension}"
            dest_path = directory / filename
            counter += 1

        return dest_path, filename

    @staticmethod
    def format_result(result):
        if isinstance(result, dict):
            try:
                formatted_items = []
                for k, v in result.items():
                    formatted_items.append(f"{k}:{v}")
                return ",".join(formatted_items)
            except Exception:
                return str(result)
        return str(result)

    @staticmethod
    def to_int(data, key):
        try:
            val = data.get(key)
            if val is not None:
                return int(val)
            return -1
        except (ValueError, TypeError):
            return -1
    
    @staticmethod
    def to_str(data, key):
        val = data.get(key)
        if val is None:
            return "ERROR"
        val_str = str(val)
        if val_str.strip() == "":
            return "ERROR"
        return val_str

    @staticmethod
    def send_discord_notification(message, channel=None, files=None):
        def post_request():
            try:
                payload = {
                    "channel_name": channel if channel else 'notify.me',
                    "msg": message,
                    "attachments": files if files else []
                }
                logger.info(f"send_discord_notification. {payload}")
                requests.post(f"http://127.0.0.1:8000/send",
                              json=payload,
                              timeout=5)
            except Exception as e:
                pass

        threading.Thread(target=post_request, daemon=True).start()