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
    """Utility Service Plugin
    
    Role: Provides helper functions for LLM calls, file path management, data formatting, and notifications.
    
    Methods:
        llm_call(model, system_prompt, user_message) : Make LLM call with Ollama.
        get_unique_path(dir_path, base_name, extension=".wav") : Generate unique file path to avoid collisions.
        format_result(result) : Format result data (dict or other types) to string.
        to_int(data, key) : Convert data value to integer.
        to_str(data, key) : Convert data value to string.
        send_discord_notification(message, channel=None, files=None) : Send Discord notification.
    """
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
        val = data.get(key)
        if val is not None:
            try:
                return int(val)
            except (ValueError, TypeError):
                return -1
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
                channel_name = channel if channel else 'notify.me'
                attachment_list = files if files else []
                payload = {
                    "channel_name": channel_name,
                    "msg": message,
                    "attachments": attachment_list
                }
                logger.info(f"send_discord_notification. {payload}")
                requests.post(f"http://127.0.0.1:8000/send",
                              json=payload,
                              timeout=5)
            except Exception as e:
                pass

        threading.Thread(target=post_request, daemon=True).start()
