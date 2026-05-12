# FILE: src/utils/logger.py | PURPOSE: Structured logger factory
import logging
import os
from src.config.config import CONFIG

os.makedirs(CONFIG.Paths.logs_dir, exist_ok=True)
log_file_path = os.path.join(CONFIG.Paths.logs_dir, "app.log")

formatter = logging.Formatter('[%(asctime)s] [%(levelname)s] [%(module_name)s] %(message)s')

file_handler = logging.FileHandler(log_file_path)
file_handler.setFormatter(formatter)

console_handler = logging.StreamHandler()
console_handler.setFormatter(formatter)

class ModuleAdapter(logging.LoggerAdapter):
    def process(self, msg, kwargs):
        return msg, {**kwargs, 'extra': {**kwargs.get('extra', {}), 'module_name': self.extra.get('module_name')}}

root_logger = logging.getLogger("newsbot_blogs")
root_logger.setLevel(os.getenv("LOG_LEVEL", "INFO").upper())
root_logger.propagate = False
if not root_logger.handlers:
    root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)

def create_logger(module_name: str):
    return ModuleAdapter(root_logger, {"module_name": module_name})
