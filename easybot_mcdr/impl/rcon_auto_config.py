import re
import os
import random
import string
from mcdreforged.api.all import *
from easybot_mcdr.config import get_config, save_config

# 用于记录RCON配置是否正在进行中，避免循环触发
_rcon_config_in_progress = False

def generate_secure_password(length=16):
    """
    生成高强度随机密码
    :param length: 密码长度
    :return: 生成的密码字符串
    """
    # 包含大小写字母、数字和特殊字符
    characters = string.ascii_letters + string.digits + string.punctuation
    # 确保密码包含至少一个大写字母、一个小写字母、一个数字和一个特殊字符
    password = [
        random.choice(string.ascii_uppercase),
        random.choice(string.ascii_lowercase),
        random.choice(string.digits),
        random.choice(string.punctuation)
    ]
    # 填充剩余长度
    password += [random.choice(characters) for _ in range(length - 4)]
    # 打乱密码顺序
    random.shuffle(password)
    return ''.join(password)

def get_server_properties_path(server: PluginServerInterface):
    """
    获取服务器properties文件路径
    :param server: 服务器接口
    :return: properties文件路径
    """
    # 尝试获取服务器工作目录
    server_dir = server.get_server_directory()
    if server_dir:
        return os.path.join(server_dir, 'server.properties')
    # 如果无法获取，尝试默认路径
    return os.path.join(os.getcwd(), 'server.properties')

def read_server_properties(properties_path):
    """
    读取服务器properties文件
    :param properties_path: properties文件路径
    :return: 配置字典
    """
    config = {}
    if not os.path.exists(properties_path):
        return config
    
    with open(properties_path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#'):
                parts = line.split('=', 1)
                if len(parts) == 2:
                    key, value = parts
                    config[key.strip()] = value.strip()
    return config

def write_server_properties(properties_path, config):
    """
    写入服务器properties文件
    :param properties_path: properties文件路径
    :param config: 配置字典
    """
    # 先读取原始文件内容，保留注释和格式
    original_lines = []
    if os.path.exists(properties_path):
        with open(properties_path, 'r', encoding='utf-8') as f:
            original_lines = f.readlines()
    
    # 更新或添加配置项
    new_lines = []
    updated_keys = set()
    
    for line in original_lines:
        stripped = line.strip()
        if stripped and not stripped.startswith('#'):
            parts = stripped.split('=', 1)
            if len(parts) == 2:
                key = parts[0].strip()
                if key in config:
                    new_lines.append(f"{key}={config[key]}\n")
                    updated_keys.add(key)
                    continue
        new_lines.append(line)
    
    # 添加未在原始文件中的配置项
    for key, value in config.items():
        if key not in updated_keys:
            new_lines.append(f"{key}={value}\n")
    
    # 写入文件
    with open(properties_path, 'w', encoding='utf-8') as f:
        f.writelines(new_lines)

def update_plugin_rcon_config(server: PluginServerInterface, host='127.0.0.1', port=25575, password=''):
    """
    更新插件的RCON配置
    :param server: 服务器接口
    :param host: RCON主机
    :param port: RCON端口
    :param password: RCON密码
    """
    config = get_config()
    if 'rcon' not in config:
        config['rcon'] = {}
    
    config['rcon']['host'] = host
    config['rcon']['port'] = port
    config['rcon']['password'] = password
    config['rcon']['enabled'] = True
    
    save_config(server)
    server.logger.info(f"已更新插件RCON配置: {host}:{port}")

async def check_and_configure_rcon(server: PluginServerInterface):
    """
    检查并配置RCON连接
    :param server: 服务器接口
    :return: 是否成功配置并连接RCON
    """
    global _rcon_config_in_progress
    
    # 避免重复执行
    if _rcon_config_in_progress:
        server.logger.info("RCON配置过程正在进行中，跳过重复调用")
        return False
    
    try:
        _rcon_config_in_progress = True
        
        # 检查RCON是否已连接
        if server.is_rcon_running():
            return True
        
        server.logger.info("RCON未连接，开始自动配置流程")
        
        # 获取服务器properties文件路径
        properties_path = get_server_properties_path(server)
        if not os.path.exists(properties_path):
            server.logger.error(f"找不到服务器配置文件: {properties_path}")
            return False
        
        # 读取服务器配置
        server_config = read_server_properties(properties_path)
        rcon_enabled = server_config.get('enable-rcon', 'false').lower() == 'true'
        rcon_password = server_config.get('rcon.password', '')
        rcon_port = int(server_config.get('rcon.port', 25575))
        
        server.logger.info(f"读取服务器RCON配置: enabled={rcon_enabled}, password_set={len(rcon_password) > 0}, port={rcon_port}")
        
        # 情况1: RCON已启用且有密码
        if rcon_enabled and rcon_password:
            server.logger.info("RCON已启用且有密码配置，更新插件配置并尝试连接")
            update_plugin_rcon_config(server, '127.0.0.1', rcon_port, rcon_password)
            
            # 热重载插件配置
            server.logger.info("热重载插件以应用新配置")
            server.connect_rcon()
            
            # 检查连接是否成功
            if server.is_rcon_running():
                server.logger.info("RCON连接成功")
                return True
            else:
                server.logger.error("更新配置后RCON连接失败")
                return False
        
        # 情况2: RCON未启用但有密码
        elif not rcon_enabled and rcon_password:
            server.logger.info("RCON未启用但有密码配置，启用RCON并重启服务器")
            
            # 更新服务器配置
            server_config['enable-rcon'] = 'true'
            write_server_properties(properties_path, server_config)
            server.logger.info("已启用服务器RCON")
            
            # 更新插件配置
            update_plugin_rcon_config(server, '127.0.0.1', rcon_port, rcon_password)
            
            # 重启服务器
            server.logger.info("准备重启服务器以应用RCON设置")
            server.stop()
            # 这里需要等待服务器完全停止，然后再启动
            # 注意：由于MCDR的限制，这里可能需要用户手动重启，或者使用更复杂的逻辑
            server.logger.warning("服务器已停止，请手动重启以应用RCON设置。重启后插件将自动尝试连接RCON")
            return False
        
        # 情况3: RCON未启用且无密码
        else:
            server.logger.info("RCON未启用且无密码配置，生成随机密码并配置")
            
            # 生成高强度随机密码
            new_password = generate_secure_password()
            server.logger.info("已生成高强度随机RCON密码")
            
            # 更新服务器配置
            server_config['enable-rcon'] = 'true'
            server_config['rcon.password'] = new_password
            write_server_properties(properties_path, server_config)
            server.logger.info("已更新服务器RCON配置")
            
            # 更新插件配置
            update_plugin_rcon_config(server, '127.0.0.1', rcon_port, new_password)
            
            # 重启服务器
            server.logger.info("准备重启服务器以应用RCON设置")
            server.stop()
            server.logger.warning("服务器已停止，请手动重启以应用RCON设置。重启后插件将自动尝试连接RCON")
            return False
    
    except Exception as e:
        server.logger.error(f"RCON自动配置过程中出错: {str(e)}")
        return False
    finally:
        _rcon_config_in_progress = False