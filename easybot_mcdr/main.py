from mcdreforged.api.all import *
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

help_msg = '''--------§a EasyBot V1.0.3§r--------
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
    global server_interface
    server_interface = server

    from easybot_mcdr.api.player import PlayerInfo
    if os.path.exists("easybot_cache.json"):
        with open("easybot_cache.json", "r") as f:
            saved_data = json.load(f)
        init_player_api(server, {
            "online_players": {k: PlayerInfo(**v) for k, v in saved_data["online_players"].items()},
            "uuid_map": saved_data["uuid_map"],
            "cache": {k: PlayerInfo(**v) for k, v in saved_data["cache"].items()}
        })
        # Clear the file after loading
        os.remove("easybot_cache.json")
    else:
        init_player_api(server, None)
    await load()

    # Sync online_players with actual online players using RCON
    if server.is_rcon_running():
        try:
            result = server.rcon_query('list')
            # Example output: "There are 2 of a max 20 players online: player1, player2"
            match = re.search(r'There are (\d+) of a max (\d+) players online: (.*)', result)
            if match:
                player_list_str = match.group(3)
                actual_online = [p.strip() for p in player_list_str.split(',') if p.strip()]
                # Update online_players by removing players who are no longer online
                for player in list(online_players.keys()):
                    if player not in actual_online:
                        online_players.pop(player)
                        server.logger.info(f"从在线玩家列表移除了{player} ,因为他们不再在线")
            else:
                server.logger.warning("解析列表输出失败")
        except Exception as e:
            server.logger.warning(f"RCON查询失败: {e}")
    else:
        server.logger.warning("RCON未启用,无法同步玩家列表")
    
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
    wsc = EasyBotWsClient(get_config()["ws"])
    asyncio.create_task(wsc.start())

    server.register_help_message('!!ez', '显示EasyBot的帮助菜单')

async def show_help(source: CommandSource):
    for line in help_msg.splitlines():
        source.reply(line)

async def on_unload(server: PluginServerInterface):
    global player_data_map, wsc
    player_data_map = get_data_map()
    # Save to file
    data_to_save = {
        "online_players": {k: v.__dict__ for k, v in player_data_map["online_players"].items()},
        "uuid_map": player_data_map["uuid_map"],
        "cache": {k: v.__dict__ for k, v in player_data_map["cache"].items()}
    }
    with open("easybot_cache.json", "w") as f:
        json.dump(data_to_save, f)
    await close()
    server.logger.info("插件卸载完成")

async def close():
    global wsc
    if wsc is not None:
        await wsc.stop()
        wsc = None

async def load():
    global wsc, server_interface
    load_config(server_interface)
    wsc = EasyBotWsClient(get_config()["ws"])
    try:
        await wsc.start()
    except Exception as e:
        server_interface.logger.error(f"连接失败: {e}")
        server_interface.logger.error("请检查配置文件ws地址是否正确!")

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
        if is_bot_player(player):
            ip = "unknown"
            if match := re.search(r'\d+\.\d+\.\d+\.\d+', info.raw_content):
                ip = match.group()
            from easybot_mcdr.api.player import cached_data
            # 获取 PlayerInfo 对象，如果不存在则使用默认值
            player_info = cached_data.get(player)
            uuid = player_info.uuid if player_info else "unknown"
            server.logger.info(f"假人 {player} 已加入: UUID={uuid}, IP={ip}")
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
    if match := re.search(
        r"UUID of player (\w+) is ([0-9a-fA-F]{8}-(?:[0-9a-fA-F]{4}-){3}[0-9a-fA-F]{12})",
        raw,
    ):
        name = match.group(1)
        if is_bot_player(name):
            server.logger.info(f"检测到假人 {name}，跳过白名单和绑定检查")
            return
        if is_white_list_enable():
            bind_info = await wsc.get_social_account(name)
            if bind_info["uuid"] is not None and bind_info["uuid"] != "":
                server.execute("whitelist add " + name)

async def on_player_left(server: PluginServerInterface, player: str):
    if player in kick_map:
        kick_map.remove(player)
        return
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