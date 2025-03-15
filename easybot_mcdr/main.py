import asyncio
import re
from mcdreforged.api.all import *
from easybot_mcdr.api.player import get_data_map, init_player_api, build_player_info
from easybot_mcdr.config import get_config, load_config
from easybot_mcdr.utils import is_white_list_enable
from easybot_mcdr.websocket.ws import EasyBotWsClient

import easybot_mcdr.impl

wsc: EasyBotWsClient = None
player_data_map = {}
server_interface: PluginServerInterface = None
temp_player_list = []  # 临时存储 list 命令解析的玩家


async def on_load(server: PluginServerInterface, prev_module):
    global server_interface, wsc, player_data_map
    server_interface = server

    # 如果有之前的模块数据，恢复缓存
    if prev_module is not None and hasattr(prev_module, "player_data_map"):
        init_player_api(server, prev_module.player_data_map)
        player_data_map = prev_module.player_data_map
    else:
        init_player_api(server, None)
        # 如果是首次加载或无缓存，同步当前在线玩家
        await sync_online_players(server)
    
    await load(server)
    builder = SimpleCommandBuilder()
    builder.command("!!ez reload", reload)
    builder.command("!!ez bind", bind)
    builder.command("!!bind", bind)
    builder.arg("message", Text)
    builder.command("!!say <message>", say)
    builder.command("!!esay <message>", say)
    builder.command("!!ez say <message>", say)
    builder.register(server)
    server.logger.info("插件加载完成")


async def on_unload(server: PluginServerInterface):
    global player_data_map, wsc
    player_data_map = get_data_map()  # 保存当前缓存
    if wsc is not None:
        await wsc.stop()
        wsc = None
    server.logger.info("插件卸载完成")


async def load(server: PluginServerInterface):
    global wsc
    load_config(server)
    wsc = EasyBotWsClient(get_config()["ws"])
    try:
        await wsc.start()
    except Exception as e:
        server.logger.error(f"连接失败: {e}")
        server.logger.error("请检查配置文件ws地址是否正确!")


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
    await load(server_interface)
    source.reply("§a插件重载成功!")


async def say(source: CommandSource, context: CommandContext):
    global server_interface
    name = "CONSOLE" if source.is_console else source.player
    message = context["message"]
    try:
        await wsc.push_message(name, message, True)
        server_interface.say(RText(f"[{name}] {message}", color=RColor.gray))
        source.reply("§a消息已发送: §f" + message)
    except Exception as e:
        server_interface.logger.error(f"消息推送失败: {str(e)}")
        source.reply("§c消息发送失败，请检查日志！")


kick_map = []


def push_kick(player: str, reason: str):
    if reason is None or reason.strip() == "":
        reason = "你已被踢出服务器"
    server = ServerInterface.get_instance()
    if not server.is_rcon_running():
        server.logger.error("你的服务器RCON当前并未运行,踢出玩家的原因无法显示多行。")
        server.logger.error(f"即将踢出玩家 {player} 并且只显示踢出原因的第一行!")
        start_line = reason.split("\n")[0]
        server.execute(f"kick {player} {start_line}")
        return
    global kick_map
    server.rcon_query(f"kick {player} {reason}")
    kick_map.append(player)


async def sync_online_players(server: PluginServerInterface):
    """同步当前在线玩家到缓存"""
    from easybot_mcdr.api.player import online_players, cached_data, PlayerInfo
    global temp_player_list
    logger = server.logger
    temp_player_list = []  # 清空临时列表
    server.execute("list")  # 触发 list 命令
    await asyncio.sleep(1)  # 等待输出
    # 同步解析到的玩家
    for player in temp_player_list:
        if player not in online_players:
            uuid = uuid_map.get(player, "unknown-uuid")
            ip = "127.0.0.1"  # 默认 IP
            online_players[player] = PlayerInfo(ip, player, uuid)
            cached_data[player] = online_players[player]
            logger.info(f"同步在线玩家 {player} 到缓存: UUID={uuid}, IP={ip}")
    temp_player_list = []  # 重置临时列表


async def on_player_joined(server: PluginServerInterface, player: str, info: Info):
    player_info = build_player_info(player)
    if player_info.get("type") == "fake":
        server.logger.info(f"检测到假人 {player}，跳过上报")
    else:
        await wsc.report_player(player)
        res = await wsc.login(player)
        if res["kick"]:
            push_kick(player, res["kick_message"])
            return
    await wsc.push_enter(player)


async def on_info(server: PluginServerInterface, info: Info):
    global temp_player_list
    raw = info.raw_content
    # 解析 list 命令输出
    if match := re.search(r"There are (\d+) of a max of (\d+) players online: (.*)", raw):
        player_count = int(match.group(1))
        if player_count > 0:
            players = match.group(3).split(", ")
            temp_player_list.extend(players)
    # 解析 UUID 输出
    if match := re.search(
        r"UUID of player (\w+) is ([0-9a-fA-F]{8}-(?:[0-9a-fA-F]{4}-){3}[0-9a-fA-F]{12})",
        raw,
    ):
        name = match.group(1)
        if is_white_list_enable():
            bind_info = await wsc.get_social_account(name)
            if bind_info["uuid"] is not None and bind_info["uuid"] != "":
                server.execute("whitelist add " + name)


async def on_player_left(server: PluginServerInterface, player: str):
    if player in kick_map:
        kick_map.remove(player)
        return
    try:
        await wsc.push_exit(player)
    except Exception as e:
        server.logger.error(f"推送玩家离开消息失败 (player: {player}): {str(e)}")


async def on_user_info(server: PluginServerInterface, info: Info):
    if info.player is None:
        return
    if (
        info.content.startswith("!!")
        and get_config()["message_sync"]["ignore_mcdr_command"]
    ):
        return
    try:
        await wsc.push_message(info.player, info.content, False)
    except Exception as e:
        server.logger.error(f"推送玩家消息失败 (player: {info.player}): {str(e)}")