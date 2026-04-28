from pathlib import Path
from config_loader import cfg
import logging
logger = logging.getLogger(__name__)

DEFAULT_OPTIONS = {
    'temperature': 0,
    "keep_alive": 0,
    'num_predict': 1000,
    'num_ctx': 16384,
    'think': False
}

THINKING_OPTIONS = {
    'num_predict': 8000
}

PROFILES = {
    'default': {
        'temperature': 0.6,
        'top_p': 0.95,
        'top_k': 20,
        'min_p': 0.0,
        'presence_penalty': 1.5,
        'repetition_penalty': 1.0
    },
    'thinking_webdev': {
        'temperature': 0.4,
        'top_p': 0.95,
        'top_k': 20,
        'min_p': 0.0,
        'presence_penalty': 0.0,
        'repetition_penalty': 1.0
    },
    'instruct_general': {
        'temperature': 0.6,
        'top_p': 0.8,
        'top_k': 20,
        'min_p': 0.0,
        'presence_penalty': 1.5,
        'repetition_penalty': 1.0
    },
    'instruct_reasoning': {
        'temperature': 0.6,
        'top_p': 1.0,
        'top_k': 40,
        'min_p': 0.0,
        'presence_penalty': 2.0,
        'repetition_penalty': 1.0
    }
}

SCOPE_MAP = {
    'TECH': ('assistant_tech', 'thinking_webdev'),
    'CONV': ('assistant_default', 'instruct_general'),
    'RESEARCH': ('assistant_search', 'instruct_reasoning')
}

IMAGE_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.webp'}

class OllamaConfig:
    """Ollama Configuration Manager
    
    Role: Manages Ollama model configuration, system prompts, and request payloads.
    
    Methods:
        __init__(self, system_prompt, profile='default', soul=None, content='') : Initialize configuration with model settings.
        set_think(self, active=True) : Enable/disable thinking mode with adjusted prediction limits.
        set_profile(self, name) : Apply a predefined profile configuration.
        set_system(self, prompt, profile=None, soul=None) : Set system prompt and profile.
        apply_agent_from_scope(self, analysis_res) : Apply agent configuration from analysis scope.
        _process_attachments(self, attachments) : Process and attach files to user content.
        set_content(self, text, attachments=None) : Set user content with optional attachments.
        get_payload(self) : Generate the final Ollama API request payload.
    """
    def __init__(self, system_prompt: str = None, profile: str = 'default', soul: str = None, content: str = ''):
        self.model = 'batiai/qwen3.5-9b'
        self.system_prompt = ''
        self.personality = ''
        self.user_content = content
        self.format = None
        self.options = DEFAULT_OPTIONS.copy()
        self.set_system(system_prompt, profile, soul)

    def set_think(self, active: bool = True):
        self.options['think'] = active
        self.options.update(THINKING_OPTIONS)
        return self

    def set_profile(self, name: str):
        profile = PROFILES.get(name)
        if profile:
            self.options.update(profile)
        return self

    def set_system(self, prompt: str = None, profile: str = None, soul: str = None):
        if prompt:
            self.system_prompt = prompt
        if soul:
            self.personality = soul
        if profile:
            self.set_profile(profile)
        return self

    def apply_agent_from_scope(self, analysis_res):
        agent_name, profile_name = SCOPE_MAP.get(analysis_res, ('assistant_default', 'default'))
        prompt = getattr(cfg.agents, agent_name, cfg.agents.assistant_default)
        self.set_system(prompt=prompt, profile=profile_name)
        return self

    def _process_attachments(self, attachments: list):
        for file_path in attachments:
            path = Path(file_path)
            if not path.exists():
                continue

            if path.suffix.lower() in IMAGE_EXTENSIONS:
                self.images.append(str(path.absolute()))
                continue

            try:
                data = path.read_text(encoding='utf-8')
                attachment_header = f'\n\n--- ATTACHMENT: {path.name} ---\n'
                attachment_footer = f'--- END OF FILE ---\n'
                self.user_content += (
                    attachment_header
                    + f'```\n{data}\n```\n'
                    + attachment_footer
                )
            except Exception:
                pass

    def set_content(self, text: str, attachments: list = None):
        self.user_content = text
        self.images = []
        if attachments:
            self._process_attachments(attachments)
        return self
    
    def get_payload(self):
        system_content = f'{self.system_prompt} {self.personality}'.strip()
        return {
            'model': self.model,
            'messages': [
                {'role': 'system', 'content': system_content},
                {'role': 'user', 'content': self.user_content}
            ],
            'format': self.format,
            'options': self.options
        }
