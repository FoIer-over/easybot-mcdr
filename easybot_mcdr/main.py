from mcdreforged.api.all import *
import websockets
from easybot_mcdr.api.player import get_data_map, init_player_api
from easybot_mcdr.config import get_config, load_config, save_config
from easybot_mcdr.utils import is_white_list_enable
from easybot_mcdr.websocket.ws import EasyBotWsClient
import easybot_mcdr.impl.cross_server_chat
import re
import json
import os
import asyncio

wsc: EasyBotWsClient = None
player_data_map = {}
rcon_initialized = False  # 添加RCON连接状态标志

help_msg = '''--------§a EasyBot V1.1.2§r--------
§b!!ez help §f- §c显示帮助菜单
§b!!ez reload §f- §c重载配置文件

§c绑定类
§b!!ez bind §f- §c触发绑定
§b!!bind §f- §c同上

§c消息发送类
§b!!ez say <message> §f- §c发送消息
§b!!esay <message> §f- §c同上
§b!!say <message> §f- §c同上

§c跨服聊天
§b!!ez ssay <message> §f- §c发送跨服消息
§b!!essay <message> §f- §c同上
§b!!ssay <message> §f- §c同上

§c假人过滤设置(需MCDR 3级权限及以上)
§b!!ez bot toggle §f- §c开启/关闭假人过滤
§b!!ez bot add <prefix> §f- §c添加假人过滤前缀
§b!!ez bot remove <prefix> §f- §c移除假人过滤前缀
§b!!ez bot list §f- §c显示假人过滤前缀列表
---------------------------------------------
'''


def is_bot_player(player: str) -> bool:
    config = get_config()
    bot_filter = config.get("bot_filter", {"enabled": True, "prefixes": ["Bot_", "BOT_", "bot_"]})
    if not bot_filter.get("enabled", True):
        return False
    prefixes = bot_filter.get("prefixes", ["Bot_", "BOT_", "bot_"])
    return any(player.startswith(prefix) for prefix in prefixes)


async def on_load(server: PluginServerInterface, prev_module):
    global server_interface, wsc
    server_interface = server
    server.logger.info("开始加载EasyBot插件...")

    try:
        from easybot_mcdr.api.player import PlayerInfo
        if os.path.exists("easybot_cache.json"):
            server.logger.info("检测到缓存文件，加载玩家数据...")
            with open("easybot_cache.json", "r") as f:
                saved_data = json.load(f)
            # 处理可能的列表或字典格式的online_players
            online_players = {}
            if isinstance(saved_data["online_players"], list):
                server.logger.warning("检测到旧版列表格式的online_players，正在转换...")
                for player_info in saved_data["online_players"]:
                    if isinstance(player_info, dict):
                        name = player_info.get("name")
                        if name:
                            online_players[name] = PlayerInfo(**player_info)
            elif isinstance(saved_data["online_players"], dict):
                online_players = {k: PlayerInfo(**v) for k, v in saved_data["online_players"].items()}
            else:
                server.logger.error(f"未知的online_players格式: {type(saved_data['online_players'])}")
                online_players = {}

            # 处理cache数据
            cache = {}
            if isinstance(saved_data["cache"], list):
                server.logger.warning("检测到旧版列表格式的cache，正在转换...")
                for player_info in saved_data["cache"]:
                    if isinstance(player_info, dict):
                        name = player_info.get("name")
                        if name:
                            cache[name] = PlayerInfo(**player_info)
            elif isinstance(saved_data["cache"], dict):
                cache = {k: PlayerInfo(**v) for k, v in saved_data["cache"].items()}
            else:
                server.logger.error(f"未知的cache格式: {type(saved_data['cache'])}")
                cache = {}

            init_player_api(server, {
                "online_players": online_players,
                "uuid_map": saved_data["uuid_map"],
                "cache": cache
            })
            # Clear the file after loading
            os.remove("easybot_cache.json")
            server.logger.info("玩家数据加载完成")
        else:
            server.logger.info("未找到缓存文件，初始化空玩家数据")
            init_player_api(server, None)
        
        server.logger.info("初始化WebSocket连接...")
        await load()
        
        # 确保WebSocket连接已启动
        wsc = EasyBotWsClient(get_config()["ws"])
        asyncio.create_task(wsc.start())
        
        # 注册事件监听器
        server.logger.info("注册事件监听器...")
        server.register_event_listener('server_started', on_server_started)
        # 注册假人相关事件
        server.register_event_listener('player_death', on_player_death)
        server.register_event_listener('player_left', on_player_left)
        server.logger.info(f"已注册事件监听器: player_death={on_player_death}, player_left={on_player_left}")
        
        server.logger.info("EasyBot插件加载完成")
    except Exception as e:
        server.logger.error(f"插件加载过程中发生错误: {str(e)}")
        raise

    if server.is_rcon_running():
        try:
            result = server.rcon_query('list')
        # 检查 RCON 查询结果是否有效
            if result is None:
                server.logger.warning("RCON 查询返回空结果，请检查 RCON 连接状态")
                return
        # 增强正则表达式兼容性
            match = re.search(
                r'There are (\d+) of a max (\d+) players online[^\d]*?(?:[:]?\s*(.*))?$',
                result,
                re.IGNORECASE
            )
            actual_online = []  # 初始化默认值
            if match:
                online_count = int(match.group(1))
                max_players = int(match.group(2))
                player_list_str = match.group(3) or ''  # 处理可能的 None
                actual_online = [p.strip() for p in player_list_str.split(',') if p.strip()]
            
            # 更新在线玩家列表
            player_data_map = get_data_map()
            if "online_players" in player_data_map:
                online_players = player_data_map["online_players"]
                for player in list(online_players.keys()):
                    if player not in actual_online:
                        online_players.pop(player)
                        server.logger.info(f"从在线玩家列表移除了 {player}，因为他们不再在线")
            else:
                server.logger.warning(f"解析列表输出失败，原始输出: {result}")
        except Exception as e:
            server.logger.warning(f"RCON 查询失败: {e}")
    else:
        server.logger.warning("RCON 未启用，无法同步玩家列表")
    
    builder = SimpleCommandBuilder()
    # 定义参数
    builder.arg("message", Text)  
    builder.arg("prefix", Text)   

    # 注册命令
    builder.command("!!ez help", show_help)
    builder.command("!!ez", show_help)
    builder.command("!!ez reload", reload)
    builder.command("!!ez bind", bind)
    builder.command("!!bind", bind)
    builder.command("!!say <message>", say)
    builder.command("!!esay <message>", say)
    builder.command("!!ez say <message>", say)
    builder.command("!!ez ssay <message>", cross_server_say)
    builder.command("!!essay <message>", cross_server_say)
    builder.command("!!ssay <message>", cross_server_say)

    # 假人过滤命令
    builder.command("!!ez bot toggle", toggle_bot_filter)
    builder.command("!!ez bot add <prefix>", add_bot_prefix)
    builder.command("!!ez bot remove <prefix>", remove_bot_prefix)
    builder.command("!!ez bot list", list_bot_prefixes)

    builder.register(server)
    server.logger.info("插件加载完成")
    server.register_help_message('!!ez', '显示EasyBot的帮助菜单')

async def show_help(source: CommandSource):
    for line in help_msg.splitlines():
        source.reply(line)

async def on_unload(server: PluginServerInterface):
    global player_data_map, wsc, server_interface
    
    try:
        # 保存玩家数据
        player_data_map = get_data_map()
        
        # 安全处理所有数据字段
        def safe_convert(data):
            if isinstance(data, list):
                return data
            elif isinstance(data, dict):
                return {k: v.__dict__ if hasattr(v, '__dict__') else v for k, v in data.items()}
            return {}
            
        data_to_save = {
            "online_players": safe_convert(player_data_map.get("online_players", [])),
            "uuid_map": safe_convert(player_data_map.get("uuid_map", {})),
            "cache": safe_convert(player_data_map.get("cache", []))
        }
        
        server.logger.debug(f"准备保存的数据: {data_to_save}")
        
        with open("easybot_cache.json", "w") as f:
            json.dump(data_to_save, f, indent=2)
        
        # 关闭连接和清理资源
        await close()
        
        # 清理全局变量
        player_data_map = {}
        server_interface = None
        
        server.logger.info("插件已完全卸载")
    except Exception as e:
        server.logger.error(f"卸载插件时出错: {e}")
        raise

async def close():
    global wsc
    if wsc is not None:
        try:
            await wsc.stop()
            # 确保连接完全关闭
            if hasattr(wsc, '_ws') and wsc._ws is not None:
                await wsc._ws.close()
            # 取消可能的心跳任务
            if hasattr(wsc, '_heartbeat_task') and wsc._heartbeat_task is not None:
                wsc._heartbeat_task.cancel()
                try:
                    await wsc._heartbeat_task
                except asyncio.CancelledError:
                    pass
        except Exception as e:
            server_interface.logger.error(f"关闭连接时出错: {e}")
        finally:
            wsc = None

async def load():
    global wsc, server_interface
    server_interface.logger.info("初始化WebSocket客户端...")
    load_config(server_interface)
    
    # 关闭现有连接
    if wsc is not None:
        server_interface.logger.info("关闭现有WebSocket连接...")
        await wsc.stop()
    
    # 创建新的WebSocket客户端
    server_interface.logger.info("创建新的WebSocket客户端实例...")
    ws_config = get_config().get("ws", {})
    server_interface.logger.info(f"WebSocket配置: {ws_config}")
    if not ws_config:
        server_interface.logger.error("未找到WebSocket配置!")
        return
    
    # 添加连接状态检查方法
    class EnhancedWsClient(EasyBotWsClient):
        async def is_connected(self):
            """检查WebSocket连接状态"""
            try:
                return self._ws is not None and self._ws.state == websockets.State.OPEN
            except Exception as e:
                self._logger.error(f"检查连接状态失败: {str(e)}")
                return False
    
    wsc = EnhancedWsClient(ws_config)
    server_interface.logger.info(f"WebSocket客户端初始化完成: {wsc is not None}")

@new_thread("EasyBot Startup")
def on_server_started(server: PluginServerInterface):
    global wsc
    server.logger.info("检测到服务器启动事件，开始WebSocket连接流程...")
    
    async def connect_and_report():
        max_attempts = 5  # 增加尝试次数
        retry_delay = 3   # 缩短重试间隔
        
        for attempt in range(max_attempts):
            try:
                server.logger.info(f"尝试WebSocket连接 (尝试 {attempt + 1}/{max_attempts})")
                if wsc is None:
                    server.logger.error("WebSocket客户端未初始化")
                    return False
                
                # 检查是否已连接
                if hasattr(wsc, 'is_connected') and await wsc.is_connected():
                    server.logger.info("WebSocket已连接，无需重新连接")
                else:
                    server.logger.info("正在建立新连接...")
                    if not await wsc.start():
                        raise ConnectionError("WebSocket连接失败")
                    server.logger.info("WebSocket连接成功")
                
                # 连接成功后上报服务器信息
                server.logger.info("开始上报服务器信息...")
                server_info = {
                    'name': server.get_server_information().name,
                    'version': server.get_server_information().version,
                    'player_count': len(server.get_online_players()),
                    'max_players': server.get_server_information().max_players,
                    'motd': server.get_server_information().description,
                    'port': server.get_server_information().port
                }
                
                # 上报服务器信息
                await wsc._send_packet("REPORT_SERVER_INFO", server_info)
                server.logger.info("服务器信息上报成功")
                
                # 上报当前在线玩家
                for player in server.get_online_players():
                    try:
                        await wsc.report_player(player)
                        server.logger.debug(f"玩家 {player} 信息上报成功")
                    except Exception as e:
                        server.logger.error(f"上报玩家 {player} 信息失败: {str(e)}")
                
                return True
                
            except Exception as e:
                server.logger.error(f"连接/上报尝试失败: {type(e).__name__}: {str(e)}")
                if attempt < max_attempts - 1:
                    server.logger.info(f"{retry_delay}秒后重试...")
                    await asyncio.sleep(retry_delay)
        
        server.logger.error("WebSocket连接/上报失败，请检查以下内容:")
        server.logger.error("- WebSocket服务端是否运行")
        server.logger.error("- 配置是否正确 (地址: %s)", get_config().get("ws", {}).get("address"))
        server.logger.error("- 网络连接是否正常")
        return False
    
    if wsc is not None:
        try:
            asyncio.run(connect_and_report())
        except Exception as e:
            server.logger.error(f"连接/上报过程中发生未预期错误: {type(e).__name__}: {str(e)}")
    else:
        server.logger.error("无法连接: WebSocket客户端未初始化")
        server.logger.info("建议重新加载插件以初始化客户端")

async def bind(source: CommandSource):
    if source.is_console:
        source.reply("§c这个命令不能在控制台使用!")
        return

    bind_data = await wsc.get_social_account(source.player)
    if bind_data["uuid"] is None or bind_data["uuid"] == "":
        code = await wsc.start_bind(source.player)
        message: str = get_config()["message"]["start_bind"]
        message = message.replace("#code", code["code"])
        message = message.replace("#time", code["time"])
        source.reply(message)
    else:
        source.reply(
            f"§c你已经绑定了账号, ({bind_data['name']}/{bind_data['uuid']}/时间:{bind_data['time']}/{bind_data['platform']})"
        )

async def reload(source: CommandSource):
    if not source.has_permission(3):
        source.reply(f"§c你没有权限使用这个命令!")
        return
    await load()
    source.reply("§a插件重载成功!")

async def say(source: CommandSource, context: CommandContext):
    name = "CONSOLE"
    if source.is_player:
        name = source.player
    await wsc.push_message(name, context["message"], True)
    source.reply("§a消息已发送: §f" + context["message"])

kick_map = []

def push_kick(player: str, reason: str):
    if reason is None or reason.strip() == "":
        reason = "你已被踢出服务器"
    server = ServerInterface.get_instance()
    if not server.is_rcon_running():
        server.logger.error("你的服务器RCON当前并未运行,踢出玩家的原因无法显示多行。")
        server.logger.error(f"即将踢出玩家 {player} 并且只显示踢出原因的第一行!")
        first_line = reason.split("\n")[0]
        server.execute(f"kick {player} {first_line}")
        return
    global kick_map
    server.rcon_query(f"kick {player} {reason}")
    kick_map.append(player)

async def toggle_bot_filter(source: CommandSource):
    if not source.has_permission(3):
        source.reply("§c你没有权限使用这个命令!")
        return
    config = get_config()
    bot_filter = config.setdefault("bot_filter", {"enabled": True, "prefixes": ["Bot_", "BOT_", "bot_"]})
    bot_filter["enabled"] = not bot_filter.get("enabled", True)
    save_config(server_interface)
    state = "启用" if bot_filter["enabled"] else "禁用"
    source.reply(f"§a假人过滤已{state}")

async def add_bot_prefix(source: CommandSource, context: CommandContext):
    if not source.has_permission(3):
        source.reply("§c你没有权限使用这个命令!")
        return
    prefix = context["prefix"]
    config = get_config()
    bot_filter = config.setdefault("bot_filter", {"enabled": True, "prefixes": ["Bot_", "BOT_", "bot_"]})
    prefixes = bot_filter.setdefault("prefixes", ["Bot_", "BOT_", "bot_"])
    if prefix not in prefixes:
        prefixes.append(prefix)
        save_config(server_interface)
        source.reply(f"§a已添加假人前缀: {prefix}")
    else:
        source.reply(f"§c前缀 {prefix} 已存在!")

async def remove_bot_prefix(source: CommandSource, context: CommandContext):
    if not source.has_permission(3):
        source.reply("§c你没有权限使用这个命令!")
        return
    prefix = context["prefix"]
    config = get_config()
    bot_filter = config.setdefault("bot_filter", {"enabled": True, "prefixes": ["Bot_", "BOT_", "bot_"]})
    prefixes = bot_filter.setdefault("prefixes", ["Bot_", "BOT_", "bot_"])
    if prefix in prefixes:
        prefixes.remove(prefix)
        save_config(server_interface)
        source.reply(f"§a已移除假人前缀: {prefix}")
    else:
        source.reply(f"§c前缀 {prefix} 不存在!")

async def list_bot_prefixes(source: CommandSource):
    if not source.has_permission(3):
        source.reply("§c你没有权限使用这个命令!")
        return
    config = get_config()
    bot_filter = config.get("bot_filter", {"enabled": True, "prefixes": ["Bot_", "BOT_", "bot_"]})
    prefixes = bot_filter.get("prefixes", ["Bot_", "BOT_", "bot_"])
    state = "启用" if bot_filter.get("enabled", True) else "禁用"
    source.reply(f"§a假人过滤状态: {state}")
    source.reply("§a假人前缀列表: " + ", ".join(prefixes) if prefixes else "§c无前缀")

async def on_player_joined(server: PluginServerInterface, player: str, info: Info):
    try:
        config = get_config()
        bot_filter = config.get("bot_filter", {"enabled": True, "prefixes": ["Bot_", "BOT_", "bot_"]})
        server.logger.debug(f"假人过滤配置: enabled={bot_filter['enabled']}, prefixes={bot_filter['prefixes']}")
        
        if is_bot_player(player):
            ip = "unknown"
            if match := re.search(r'\d+\.\d+\.\d+\.\d+', info.raw_content):
                ip = match.group()
            from easybot_mcdr.api.player import cached_data
            player_info = cached_data.get(player)
            uuid = player_info.uuid if player_info else "unknown"
            server.logger.info(f"检测到假人 {player} (匹配前缀: {bot_filter['prefixes']}), UUID={uuid}, IP={ip}")
            return

        player_info = await wsc.report_player(player)
        if player_info is None:
            server.logger.warning(f"玩家 {player} 的信息未准备好，可能是数据同步延迟")
            return
        server.logger.info(f"玩家 {player} 已加入并缓存: UUID={player_info['player_uuid']}, IP={player_info['ip']}")
        res = await wsc.login(player)
        if res["kick"]:
            push_kick(player, res["kick_message"])
            return
        await wsc.push_enter(player)
    except Exception as e:
        server.logger.error(f"处理玩家 {player} 加入时出错: {e}")

async def on_info(server, info: Info):
    raw = info.raw_content
    import re
    import hashlib
    
    # 尝试获取正版UUID
    if match := re.search(
        r"UUID of player (\w+) is ([0-9a-fA-F]{8}-(?:[0-9a-fA-F]{4}-){3}[0-9a-fA-F]{12})",
        raw,
    ):
        name = match.group(1)
        uuid = match.group(2)
    else:
        # 离线模式处理 - 从玩家加入消息中提取名字
        if match := re.search(r"(\w+) joined the game", raw):
            name = match.group(1)
            # 生成离线模式UUID (根据Mojang规范)
            digest = hashlib.md5(b"OfflinePlayer:" + name.encode('utf-8')).digest()
            # 转换为可变的bytearray
            namespace = bytearray(digest)
            # 设置版本位 (第6字节的高4位为0011)
            namespace[6] = (namespace[6] & 0x0f) | 0x30  # Version 3
            # 设置变体位 (第8字节的高2位为10)
            namespace[8] = (namespace[8] & 0x3f) | 0x80  # Variant RFC 4122
            # 转换回bytes并格式化为UUID字符串
            uuid = '-'.join([
                bytes(namespace[0:4]).hex(),
                bytes(namespace[4:6]).hex(),
                bytes(namespace[6:8]).hex(),
                bytes(namespace[8:10]).hex(),
                bytes(namespace[10:16]).hex()
            ])
        else:
            return
    
    if is_bot_player(name):
        server.logger.info(f"检测到假人 {name}，跳过白名单和绑定检查")
        return
        
    # 确保UUID有效
    if not uuid or uuid == "unknown":
        server.logger.warning(f"玩家 {name} 的UUID无效，尝试重新生成")
        namespace = bytearray(hashlib.md5(b"OfflinePlayer:" + name.encode('utf-8')).digest())
        namespace[6] = (namespace[6] & 0x0f) | 0x30
        namespace[8] = (namespace[8] & 0x3f) | 0x80
        uuid = '-'.join([
            bytes(namespace[0:4]).hex(),
            bytes(namespace[4:6]).hex(),
            bytes(namespace[6:8]).hex(),
            bytes(namespace[8:10]).hex(),
            bytes(namespace[10:16]).hex()
        ])
        server.logger.debug(f"为玩家 {name} 生成离线UUID: {uuid}")

    if is_white_list_enable():
        try:
            bind_info = await wsc.get_social_account(name)
            if bind_info and bind_info.get("uuid"):
                server.execute(f"whitelist add {name}")
        except Exception as e:
            server.logger.error(f"获取玩家 {name} 绑定信息失败: {str(e)}")
            
    # 更新玩家UUID映射
    player_data_map = get_data_map()
    if "uuid_map" not in player_data_map:
        player_data_map["uuid_map"] = {}
    player_data_map["uuid_map"][name] = uuid
    # 获取玩家IP，兼容不同MCDR版本
    ip_address = '127.0.0.1'
    if hasattr(info, 'content') and isinstance(info.content, dict):
        ip_address = info.content.get('ip', ip_address)
    elif hasattr(info, 'ip'):
        ip_address = info.ip
        
    server.logger.info(f"玩家 {name} 已加入并缓存: UUID={uuid}, IP={ip_address}")

async def on_player_death(server: PluginServerInterface, player: str, killer: str = None):
    config = get_config()
    bot_filter = config.get("bot_filter", {"enabled": True, "prefixes": ["Bot_", "BOT_", "bot_"]})
    server.logger.debug(f"处理玩家死亡事件: {player}, 假人过滤状态: enabled={bot_filter['enabled']}")
    
    if is_bot_player(player):
        server.logger.info(f"过滤假人 {player} 的死亡事件 (匹配前缀: {bot_filter['prefixes']})")
        return
    server.logger.debug(f"正常玩家 {player} 死亡事件处理")

async def on_player_left(server: PluginServerInterface, player: str):
    config = get_config()
    bot_filter = config.get("bot_filter", {"enabled": True, "prefixes": ["Bot_", "BOT_", "bot_"]})
    server.logger.debug(f"处理玩家退出事件: {player}, 假人过滤状态: enabled={bot_filter['enabled']}")
    
    if player in kick_map:
        server.logger.debug(f"玩家 {player} 是被踢出的，跳过处理")
        kick_map.remove(player)
        return
        
    if is_bot_player(player):
        server.logger.info(f"过滤假人 {player} 的退出事件 (匹配前缀: {bot_filter['prefixes']})")
        return
        
    server.logger.debug(f"正常玩家 {player} 退出事件处理")
    await wsc.push_exit(player)

async def on_user_info(server: PluginServerInterface, info: Info):
    if info.player is None:
        return
    if (
        info.content.startswith("!!")
        and get_config()["message_sync"]["ignore_mcdr_command"]
    ):
        return
    await wsc.push_message(info.player, info.content, False)

async def cross_server_say(source: CommandSource, context: CommandContext):
    if not source.is_player:
        source.reply("§c这个命令只能由玩家使用!")
        return
    player = source.player
    message = context["message"]
    await wsc.push_cross_server_message(player, message)
    source.reply("§a你的消息已发送到其他服务器.")