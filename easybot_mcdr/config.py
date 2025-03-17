import json
import os
from mcdreforged.api.all import *

config = {}

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
    
    # 如果缺少 bot_filter，动态添加默认值
    if "bot_filter" not in config:
        config["bot_filter"] = {
            "enabled": True,
            "prefixes": ["Bot_", "BOT_", "bot_"]
        }
        save_config(server)

def save_config(server: PluginServerInterface):
    config_path = server.get_data_folder()
    config_file_path = os.path.join(config_path, "config.json")
    with open(config_file_path, "w", encoding="utf-8", newline='') as f:
        json.dump(config, f, indent=4, ensure_ascii=False)
    server.logger.info("配置文件已保存")

def get_config() -> dict:
    return config