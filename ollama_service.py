import json
from typing import Any, Dict
from ollama_config import OllamaConfig
from ollama import AsyncClient
from ollama import Client
import json
import requests
from config_loader import cfg
import threading
import logging
logger = logging.getLogger(__name__)


def _extract_json_from_content(content: str) -> Dict[str, Any] | None:
    if not content:
        return None
    
    start = content.find('{')
    end = content.rfind('}')
    
    if start != -1 and end != -1:
        try:
            return json.loads(content[start:end + 1])
        except Exception:
            pass
    
    return None


def _process_response(data: Dict[str, Any] | None, raw_content: str) -> Dict[str, Any]:
    if data is not None and isinstance(data, dict):
        result = {}
        for key, value in data.items():
            result[str(key).lower()] = value
        return result
    
    return {"content": raw_content}


def _process_llm_result(response):
    logger.debug(response)
    content = response.message.content.strip()
    data = _extract_json_from_content(content)
    return _process_response(data, content)


class OllamaServiceAsync:
    """Async Ollama Service for LLM interactions
    
    Role: Provides asynchronous LLM generation with Ollama API.
    
    Methods:
        __init__(self) : Initialize async client with local URL.
        generate(self, config) : Generate response asynchronously.
    """
    
    def __init__(self):
        self.local_url = getattr(cfg.ollama, 'local_url', "http://127.0.0.1:11434")
        self.client = AsyncClient(host=self.local_url)
    
    async def generate(self, config):
        try:
            response = await self.client.chat(**config.get_payload())
            return _process_llm_result(response)
        except Exception as e:
            return {"content": str(e), "error": f"LLM_CALL_FAILED: {str(e)}"}


class OllamaService:
    """Sync Ollama Service with WAN/LAN fallback
    
    Role: Manages LLM generation with automatic WAN/LAN routing and health monitoring.
    
    Methods:
        __init__(self) : Initialize sync client with local and WAN URLs.
        generate(self, config_obj) : Generate response with WAN/LAN fallback.
        _monitor_loop(self) : Monitor WAN/LAN availability in background thread.
    """
    
    def __init__(self):
        self.local_url = getattr(cfg.ollama, 'local_url', "http://127.0.0.1:11434")
        self.wan_url = getattr(cfg.ollama, 'wan_url', None)
        
        self.client_local = Client(host=self.local_url)
        self.client_wan = Client(host=self.wan_url) if self.wan_url else None
        
        self.is_ready = False
        self.wan_available = False

        self._interrupt_monitor = threading.Event()
        threading.Thread(target=self._monitor_loop, daemon=True).start()

    def _monitor_loop(self):
        last_wan_state = None
        while True:
            wait_time = 600
            if self.wan_url:
                try:
                    self.wan_available = requests.get(f"{self.wan_url}/api/version", timeout=1.5).status_code == 200
                except:
                    self.wan_available = False
            try:
                self.is_ready = requests.get(f"{self.local_url}/api/version", timeout=1.0).status_code == 200
            except:
                self.is_ready = False
            
            if not self.is_ready or not self.wan_available:
                wait_time = 60

            if self.wan_available != last_wan_state:
                if not self.wan_available:
                    logger.warning(f"WAN DISCONNECTED | Switching to 1min monitoring")
                else:
                    logger.info(f"WAN CONNECTED | Standard monitoring (10min)")
                last_wan_state = self.wan_available

            self._interrupt_monitor.wait(timeout=wait_time)
            self._interrupt_monitor.clear()

    def generate(self, config_obj):
        payload = config_obj.get_payload()
        
        if self.wan_available and self.client_wan:
            client = self.client_wan
            target_model = getattr(cfg.ollama, 'default_model_wan', payload['model'])
            network_type = "WAN"
        else:
            client = self.client_local
            target_model = getattr(cfg.ollama, 'default_model_lan', payload['model'])
            network_type = "LAN"

        try:
            logger.info(f"🚀 Dispatching to {network_type} | Model: {config_obj.model}")
            resp = client.chat(**config_obj.get_payload())
            return _process_llm_result(resp)
        
        except Exception as e:
            logger.error(f"❌ {network_type} Failed: {e}")
            if client == self.client_wan:
                resp = client.chat(**config_obj.get_payload())
                return _process_llm_result(resp)
            raise e


llm = OllamaService()
llm_async = OllamaServiceAsync()
