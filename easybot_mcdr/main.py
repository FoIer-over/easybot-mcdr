from mcdreforged.api.all import *
import websockets
from easybot_mcdr.api.player import get_data_map, init_player_api
from easybot_mcdr.config import get_config, load_config, save_config
from easybot_mcdr.utils import is_white_list_enable
from easybot_mcdr.websocket.ws import EasyBotWsClient
from easybot_mcdr.impl.get_server_info import get_online_mode  # 添加这行导入
import easybot_mcdr.impl.cross_server_chat
from easybot_mcdr.impl.prefix_handler import PrefixNameHandler
import re
import json
import os
import asyncio
import time

wsc: EasyBotWsClient = None
player_data_map = {}
rcon_initialized = False  # 添加RCON连接状态标志
exit_reported_at = {} 
debounce_time = 5 
from easybot_mcdr.meta import get_plugin_version

help_msg = '''--------§a EasyBot §r(版本: §e{0}§r)--------
§b!!ez help §f- §c显示帮助菜单
§b!!ez reload §f- §c重载配置文件

§c绑定类
§b!!ez bind §f- §c触发绑定
§b!!bind §f- §c同上

§c消息发送类
§b!!ez say <message> §f- §c发送消息
§b!!esay <message> §f- §c同上
§b!!say <message> §f- §c同上

§c假人过滤设置(需MCDR 3级权限及以上)
§b!!ez bot toggle §f- §c开启/关闭假人过滤
§b!!ez bot add <prefix> §f- §c添加假人过滤前缀
§b!!ez bot remove <prefix> §f- §c移除假人过滤前缀
§b!!ez bot list §f- §c显示假人过滤前缀列表

§c插件信息
§b!!ez §f- §c显示插件详情
---------------------------------------------'''.format(get_plugin_version())


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
    server.register_server_handler(PrefixNameHandler())

    import threading
    uuid_check_thread = threading.Thread(target=periodic_uuid_check, daemon=True)
    uuid_check_thread.start()
    server.logger.info("UUID同步检查线程已启动")

    try:
        from easybot_mcdr.api.player import PlayerInfo
        if os.path.exists("easybot_cache.json"):
            server.logger.info("检测到缓存文件，加载玩家数据...")
            with open("easybot_cache.json", "r") as f:
                saved_data = json.load(f)
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
            os.remove("easybot_cache.json")
            server.logger.info("玩家数据加载完成")
        else:
            server.logger.info("未找到缓存文件，初始化空玩家数据")
            init_player_api(server, None)
            server.logger.info("玩家数据加载完成")
        
        server.logger.info("初始化WebSocket连接...")
        await load()
        
        # 确保WebSocket连接已启动
        wsc = EasyBotWsClient(get_config()["ws"])
        asyncio.create_task(wsc.start())
        
        # 注册事件监听器
        server.logger.info("注册事件监听器...")
        server.register_event_listener('server_started', on_server_started)
        server.register_event_listener('mcdr.general_info', on_info, priority=1)
        # 注册假人相关事件
        server.register_event_listener('player_death', on_player_death)
        # 兼容不同事件名的玩家退出事件
        server.register_event_listener('mcdr.player_left', on_player_left)
        server.register_event_listener('player_left', on_player_left)
        server.logger.info(f"已注册事件监听器: player_death={on_player_death}, mcdr.player_left={on_player_left}, player_left={on_player_left}")
        
        server.logger.info("EasyBot插件加载完成")
    except Exception as e:
        server.logger.error(f"插件加载过程中发生错误: {str(e)}")
        raise

    builder = SimpleCommandBuilder()
    # 定义参数
    builder.arg("message", Text)  
    builder.arg("prefix", Text)   

    # 注册命令
    builder.command("!!ez help", show_help)
    builder.command("!!ez", show_plugin_info)
    builder.command("!!ez reload", reload)
    builder.command("!!ez bind", bind)
    builder.command("!!bind", bind)
    builder.command("!!say <message>", say)
    builder.command("!!esay <message>", say)
    builder.command("!!ez say <message>", say)

    # 假人过滤命令
    builder.command("!!ez bot toggle", toggle_bot_filter)
    builder.command("!!ez bot add <prefix>", add_bot_prefix)
    builder.command("!!ez bot remove <prefix>", remove_bot_prefix)
    builder.command("!!ez bot list", list_bot_prefixes)

    builder.register(server)
    server.logger.info("插件加载完成")
    server.register_help_message('!!ez', '显示EasyBot的帮助菜单')


def sync_online_players_with_rcon(server: PluginServerInterface, max_retries=5, retry_delay=2):
    """
    使用RCON同步在线玩家列表，带重试机制
    """
    for attempt in range(max_retries):
        try:
            if not server.is_rcon_running():
                server.logger.warning(f"RCON未运行 (尝试 {attempt + 1}/{max_retries})")
                if attempt < max_retries - 1:
                    import time
                    time.sleep(retry_delay)
                    continue
                else:
                    server.logger.error("RCON连接失败，无法同步玩家列表")
                    return False

            server.logger.info(f"正在通过RCON同步玩家列表 (尝试 {attempt + 1}/{max_retries})")
            result = server.rcon_query('list')
            
            # 检查 RCON 查询结果是否有效
            if result is None:
                server.logger.warning(f"RCON查询返回空结果 (尝试 {attempt + 1}/{max_retries})")
                if attempt < max_retries - 1:
                    import time
                    time.sleep(retry_delay)
                    continue
                else:
                    server.logger.error("RCON查询持续返回空结果，请检查RCON连接状态")
                    return False
            
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
                
                server.logger.info(f"RCON查询成功: {online_count}/{max_players} 玩家在线")
                if actual_online:
                    server.logger.info(f"在线玩家: {', '.join(actual_online)}")
            else:
                server.logger.warning(f"无法解析RCON列表输出，原始输出: {result}")
                if attempt < max_retries - 1:
                    import time
                    time.sleep(retry_delay)
                    continue
                else:
                    return False
            
            # 更新在线玩家列表
            player_data_map = get_data_map()
            if "online_players" in player_data_map:
                online_players = player_data_map["online_players"]
                removed_players = []
                for player in list(online_players.keys()):
                    if player not in actual_online:
                        online_players.pop(player)
                        removed_players.append(player)
                
                if removed_players:
                    server.logger.info(f"从在线玩家列表移除了: {', '.join(removed_players)}")
                else:
                    server.logger.info("在线玩家列表已同步，无需移除玩家")
            
            server.logger.info("RCON玩家列表同步完成")
            return True
            
        except Exception as e:
            server.logger.warning(f"RCON同步尝试 {attempt + 1}/{max_retries} 失败: {e}")
            if attempt < max_retries - 1:
                import time
                time.sleep(retry_delay)
            else:
                server.logger.error("RCON玩家列表同步最终失败")
                return False
    
    return False


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
    
    # 在服务器启动后进行RCON同步
    def sync_after_connection():
        import time
        # 等待一下确保服务器完全启动
        time.sleep(2)
        server.logger.info("开始同步在线玩家列表...")
        sync_online_players_with_rcon(server)
    
    if wsc is not None:
        try:
            # 先进行RCON同步
            sync_after_connection()
            
            # 然后建立WebSocket连接
            asyncio.run(connect_and_report())
        except Exception as e:
            server.logger.error(f"连接/上报过程中发生未预期错误: {type(e).__name__}: {str(e)}")
    else:
        server.logger.error("无法连接: WebSocket客户端未初始化")
        server.logger.info("建议重新加载插件以初始化客户端")

async def show_help(source: CommandSource):
    for line in help_msg.splitlines():
        source.reply(line)

async def show_plugin_info(source: CommandSource):
    """显示插件详情信息"""
    from easybot_mcdr.meta import get_plugin_version
    from easybot_mcdr.impl.get_server_info import get_online_mode
    
    plugin_info = [
        '--------§a EasyBot 插件详情 §r--------',
        f'§b插件版本: §f{get_plugin_version()}',
        '§b插件名称: §fEasyBot MCDR插件',
        '§b功能介绍: §f跨服务器聊天、玩家数据同步、假人过滤',
        f'§b服务器模式: §f{'正版' if get_online_mode() else '离线'}模式',
        '§b作者: §fEasyBot团队',
        '§bqq群: §f961746627',
        '§b使用帮助: §f!!ez help',
        '---------------------------------------------'
    ]
    
    for line in plugin_info:
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
        from easybot_mcdr.api.player import cached_data
        
        config = get_config()
        bot_filter = config.get("bot_filter", {"enabled": True, "prefixes": ["Bot_", "BOT_", "bot_"]})
        server.logger.debug(f"假人过滤配置: enabled={bot_filter['enabled']}, prefixes={bot_filter['prefixes']}")
        
        if is_bot_player(player):
            ip = "unknown"
            if match := re.search(r'\d+\.\d+\.\d+\.\d+', info.raw_content):
                ip = match.group()
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
            server.logger.info(f"检测到玩家 {player} 需要被踢出，延迟5秒执行...")
            await asyncio.sleep(5) 
            push_kick(player, res["kick_message"])
            return
        await wsc.push_enter(player)
    except Exception as e:
        server.logger.error(f"处理玩家 {player} 加入时出错: {e}")

# 统一的玩家退出上报函数
async def _report_player_exit(server: PluginServerInterface, name: str):
    # 踢出列表过滤
    if name in kick_map:
        server.logger.debug(f"玩家 {name} 是被踢出的，退出事件上报已跳过")
        kick_map.remove(name)
        return

    # 假人过滤
    if is_bot_player(name):
        server.logger.info(f"过滤假人 {name} 的退出事件")
        return

    # 去重
    now = time.time()
    last = exit_reported_at.get(name, 0)
    if now - last < debounce_time:
        server.logger.debug(f"忽略重复退出上报: {name}")
        return
    exit_reported_at[name] = now

    try:
        await wsc.push_exit(name)
        server.logger.debug(f"已上报玩家退出: {name}")
    except Exception as e:
        server.logger.error(f"上报玩家 {name} 退出失败: {e}")

async def on_info(server, info: Info):
    raw = info.raw_content
    
    # 正版UUID处理
    if match := re.search(
        r"UUID of player ([\w.]+) is ([0-9a-fA-F]{8}-(?:[0-9a-fA-F]{4}-){3}[0-9a-fA-F]{12})",
        raw,
    ):
        name = match.group(1)
        uuid = match.group(2).lower()
        
        if not is_bot_player(name):
            from easybot_mcdr.api.player import update_player_uuid
            update_player_uuid(name, uuid)
            server.logger.info(f"从服务器获取到玩家 {name} 的正版UUID: {uuid}")
        return
    
    # 玩家加入消息处理（用于离线模式UUID同步验证，兼容含前缀名称）
    m_join_pref = re.search(r"^\[[^\]]+\](?P<name>[\w.]+) joined the game$", raw)
    m_join_plain = re.search(r"^(?P<name>[\w.]+) joined the game$", raw)
    if m_join_pref or m_join_plain:
        name = (m_join_pref or m_join_plain).group('name')
        
        if is_bot_player(name):
            server.logger.info(f"检测到假人 {name}，跳过UUID处理")
            return
        
        # 确保UUID已正确设置（双重检查）
        from easybot_mcdr.api.player import uuid_map, generate_offline_uuid, update_player_uuid, online_players, cached_data, PlayerInfo
        
        current_uuid = uuid_map.get(name)
        if not current_uuid or current_uuid == "unknown":
            # 生成或修正UUID
            if not get_online_mode():
                correct_uuid = generate_offline_uuid(name)
                update_player_uuid(name, correct_uuid)
                server.logger.info(f"修正玩家 {name} 的离线UUID: {correct_uuid}")
        
        # 在本地缓存玩家信息（供后续上报退出等使用）
        try:
            ip = "127.0.0.1"
            if match_ip := re.search(r"\d+\.\d+\.\d+\.\d+", raw):
                ip = match_ip.group()
            # 若不存在则创建/更新
            if name not in online_players:
                online_players[name] = PlayerInfo(ip, name, uuid_map.get(name, "unknown"))
            cached_data[name] = online_players[name]
        except Exception as e:
            server.logger.warning(f"写入玩家 {name} 本地缓存失败: {e}")

        # 白名单处理
        if is_white_list_enable():
            try:
                bind_info = await wsc.get_social_account(name)
                if bind_info and bind_info.get("uuid"):
                    server.execute(f"whitelist add {name}")
            except Exception as e:
                server.logger.error(f"获取玩家 {name} 绑定信息失败: {str(e)}")
        return

    # 玩家退出消息处理（兼容含前缀名称与额外前后缀文本）
    m_quit = re.search(r"(?:\[[^\]]+\])?(?P<name>[\w.]+) left the game", raw)
    if m_quit:
        name = m_quit.group('name')
        server.logger.debug(f"检测到退出行，解析玩家: {name} | 原始: {raw}")
        await _report_player_exit(server, name)
        return

    # 兼容 "lost connection:" 形式（有些服务端不打印 left the game）
    m_lost = re.search(r"(?:\[[^\]]+\])?(?P<name>[\w.]+) lost connection:\s*", raw)
    if m_lost:
        name = m_lost.group('name')
        server.logger.debug(f"检测到断开行，解析玩家: {name} | 原始: {raw}")
        await _report_player_exit(server, name)
        return

# 新增：定期UUID同步检查函数
@new_thread("UUID_Sync_Check")
def periodic_uuid_check():
    """定期检查和修复UUID不一致问题"""
    import time
    from easybot_mcdr.api.player import online_players, uuid_map, generate_offline_uuid, update_player_uuid, get_online_mode
    
    while True:
        try:
            time.sleep(30)  # 每30秒检查一次
            
            if not get_online_mode():
                server = ServerInterface.get_instance()
                for player in list(online_players.keys()):
                    current_uuid = online_players[player].uuid
                    expected_uuid = generate_offline_uuid(player)
                    
                    if current_uuid != expected_uuid and current_uuid in ["unknown", "", None]:
                        server.logger.warning(f"检测到玩家 {player} UUID不一致，正在修复...")
                        update_player_uuid(player, expected_uuid)
                        
        except Exception as e:
            ServerInterface.get_instance().logger.error(f"UUID同步检查出错: {e}")
            time.sleep(60)  # 出错后等待更长时间


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
    
    # 避免与 on_info 中的解析重复上报
    now = time.time()
    last = exit_reported_at.get(player, 0)
    if now - last < 2.0:
        server.logger.debug(f"忽略重复退出上报: {player}")
        return
    exit_reported_at[player] = now

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
