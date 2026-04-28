import sys
import logging
import yaml
import shutil
from pathlib import Path
from types import SimpleNamespace

logger = logging.getLogger(__name__)

class LocalFilesFilter(logging.Filter):
    """Filters logs to only show messages from your own project files."""
    def __init__(self):
        super().__init__()
        self.local_files = set()
        root_dir = cfg.root if hasattr(cfg, 'root') else Path(__file__).resolve().parent
        for path in root_dir.rglob("*.py"):
            if "__pycache__" in path.parts:
                continue
            for part in path.parts:
                if part.startswith('.'):
                    break
            else:
                self.local_files.add(path.name)

    def filter(self, record):
        return record.filename in self.local_files

def setup_logging():
    log_dir = cfg.config_dir
    log_dir.mkdir(parents=True, exist_ok=True)

    date_format = "%y%m%d:%H:%M:%S"
    
    if getattr(cfg, 'verbose', False):
        log_format = "[%(asctime)s][%(filename)s][%(funcName)s](%(levelname)s): %(message)s"
    else:
        log_format = "[%(asctime)s][%(funcName)s](%(levelname)s): %(message)s"
    
    formatter = logging.Formatter(fmt=log_format, datefmt=date_format)
    local_filter = LocalFilesFilter()

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    console_handler.addFilter(local_filter)

    file_handler = logging.FileHandler(log_dir / "debug.log", mode="a", encoding="utf-8")
    file_handler.setFormatter(formatter)
    file_handler.addFilter(local_filter)
    
    root_logger = logging.getLogger()
    if getattr(cfg, 'debug', False):
        root_logger.setLevel(logging.DEBUG)
    else:
        root_logger.setLevel(logging.INFO)
    
    root_logger.handlers = []
    root_logger.addHandler(console_handler)
    root_logger.addHandler(file_handler)

    logging.getLogger("uvicorn").setLevel(logging.WARNING)

class CfgConfig(SimpleNamespace):
    """
    Enhanced Namespace for dot notation access (cfg.bot.token) 
    with formatted display and dictionary conversion.
    """
    def __repr__(self):
        return self._format_object(self)

    def _format_object(self, obj, indent_level=0):
        spacing = "  " * indent_level
        if isinstance(obj, (SimpleNamespace, CfgConfig)):
            items = vars(obj).items()
            if not items:
                return "{}"
            lines = ["{"]
            for k, v in items:
                formatted_value = self._format_object(v, indent_level + 1)
                lines.append(spacing + "  " + '"' + k + '": ' + formatted_value + ',')
            lines[-1] = lines[-1].rstrip(',')
            lines.append(spacing + "}")
            return "\n".join(lines)
        if isinstance(obj, str):
            return '"' + obj + '"'
        return str(obj)

    def to_dict(self):
        result = {}
        for k, v in vars(self).items():
            if isinstance(v, CfgConfig):
                result[k] = v.to_dict()
            else:
                result[k] = v
        return result

class DiscordBridgeConfig:
    def __init__(self):
        self.BASE_DIR = Path.home() / "Documents" / "DiscordBridge"
        self.CONFIG_FILE = self.BASE_DIR / "config.yaml"
        self.AGENTS_DIR = self.BASE_DIR / "agents"
        self._setup_files()
        self.cfg = self._dict_to_namespace(self._load_yaml())
        self.cfg.agents = self._load_agents()
        self.cfg.config_dir = self.BASE_DIR

    def _setup_files(self):
        self.BASE_DIR.mkdir(parents=True, exist_ok=True)
        self.AGENTS_DIR.mkdir(parents=True, exist_ok=True)
        
        if not self.CONFIG_FILE.exists():
            example = Path(__file__).parent / "config_example.yaml"
            if example.exists():
                shutil.copy(example, self.CONFIG_FILE)
                logger.info("Configuration initialized in " + str(self.CONFIG_FILE))
            else:
                logger.info("config_example.yaml not found in " + str(Path(__file__).parent))

    def _load_yaml(self):
        with open(self.CONFIG_FILE, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f) or {}

    def _load_agents(self):
        agents = CfgConfig()
        for md_file in self.AGENTS_DIR.glob("*.md"):
            with open(md_file, "r", encoding='utf-8') as f:
                content = f.read().strip()
                setattr(agents, md_file.stem, content)
        return agents

    def _dict_to_namespace(self, data):
        if isinstance(data, dict):
            result = {}
            for k, v in data.items():
                converted_value = self._dict_to_namespace(v)
                result[k] = converted_value
            return CfgConfig(**result)
        if isinstance(data, list):
            converted_list = []
            for item in data:
                converted_item = self._dict_to_namespace(item)
                converted_list.append(converted_item)
            return converted_list
        return data
    
    def agent(self):
        if not self.AGENTS_DIR.exists():
            return

        for md_file in self.AGENTS_DIR.glob("*.md"):
            name = md_file.stem 
            with open(md_file, "r", encoding='utf-8') as f:
                content = f.read().strip()
                setattr(self.agents, name, content)
        
        agent_names = list(vars(self.agents).keys())
        logger.info("Agents loaded: " + ", ".join(agent_names))

cfg = DiscordBridgeConfig().cfg
