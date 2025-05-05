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
    
    try:
        # 加载配置文件
        with open(config_file_path, "r", encoding="utf-8-sig", newline='') as f:
            loaded_config = json.load(f)
            server.logger.info(f"配置文件路径: {config_file_path}")
            
            # 调试打印配置内容
            server.logger.debug(f"原始配置内容: {json.dumps(loaded_config, indent=2)}")
            
            # 验证必要字段
            required_fields = ["ws", "token", "server_name"]
            missing_fields = [field for field in required_fields if field not in loaded_config]
            
            if missing_fields:
                error_msg = f"配置缺少必要字段: {missing_fields}"
                server.logger.error(error_msg)
                raise ValueError(error_msg)
                
            # 更新全局配置
            config.clear()
            config.update(loaded_config)
            
            # 调试打印最终配置
            server.logger.debug(f"最终配置内容: {json.dumps(config, indent=2)}")
            server.logger.info("配置文件加载并验证成功")
            
    except json.JSONDecodeError as e:
        error_msg = f"配置文件解析失败: {str(e)}"
        server.logger.error(error_msg)
        raise ValueError(error_msg)

def save_config(server: PluginServerInterface):
    config_path = server.get_data_folder()
    config_file_path = os.path.join(config_path, "config.json")
    with open(config_file_path, "w", encoding="utf-8", newline='') as f:
        json.dump(config, f, indent=4, ensure_ascii=False)
    server.logger.info("配置文件已保存")

def get_config() -> dict:
    return config