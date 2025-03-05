import json
import os
from mcdreforged.api.all import *

def load_config(server: PluginServerInterface):
    global config
    server.logger.info("加载配置中...")
    config_path = server.get_data_folder()
    os.makedirs(config_path, exist_ok=True)
    config_file_path = os.path.join(config_path, "config.json")
    
    if not os.path.exists(config_file_path):
        with server.open_bundled_file("data/config.json") as data:
            with open(config_file_path, "w", encoding="utf-8", newline='') as f:
                f.write(data.read().decode("utf-8"))
                server.logger.info("配置文件不存在，已创建配置文件")
    
    with open(config_file_path, "r", encoding="utf-8", newline='') as f:
        config = json.load(f)
        server.logger.info(f"配置文件路径: {config_file_path}")
        server.logger.info("配置文件加载成功")

def get_config() -> dict:
    return config