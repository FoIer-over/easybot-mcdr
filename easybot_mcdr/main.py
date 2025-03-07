from mcdreforged.api.all import *
from easybot_mcdr.api.player import get_data_map, init_player_api
from easybot_mcdr.config import get_config, load_config
from easybot_mcdr.utils import is_white_list_enable
from easybot_mcdr.websocket.ws import EasyBotWsClient

import easybot_mcdr.impl

wsc: EasyBotWsClient = None
player_data_map = {}


async def on_load(server: PluginServerInterface, prev_module):
    global server_interface
    server_interface = server  # 历史遗留代码

    # 用于继承上一代的意志((
    if prev_module is not None and hasattr(prev_module, "player_data_map"):
        init_player_api(server, prev_module.player_data_map)
    else:
        init_player_api(server, None)
    await load()
    builder = SimpleCommandBuilder()

    # 管理员命令
    builder.command("!!ez reload", reload)

    # 绑定命令
    builder.command("!!ez bind", bind)
    builder.command("!!bind", bind)

    # 消息同步
    builder.arg("message", Text)
    builder.command("!!say <message>", say)
    builder.command("!!esay <message>", say)
    builder.command("!!ez say <message>", say)

    builder.register(server)
    server.logger.info("插件加载完成")


async def on_unload(server: PluginServerInterface):
    global player_data_map
    player_data_map = get_data_map()
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


# 统一踢出接口
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


async def on_player_joined(server: PluginServerInterface, player: str, info: Info):
    await wsc.report_player(player)
    res = await wsc.login(player)
    if res["kick"]:
        push_kick(player, res["kick_message"])
        return
    await wsc.push_enter(player)


async def on_info(server, info: Info):
    raw = info.raw_content
    # 正则解析 UUID 一般出现uuid的时候 表示玩家正在加入服务器，这个时候需要检查白名单服务器的玩家
    # 如果玩家绑定了账号 需要将这个玩家加入白名单
    import re

    if match := re.search(
        r"UUID of player (\w+) is ([0-9a-fA-F]{8}-(?:[0-9a-fA-F]{4}-){3}[0-9a-fA-F]{12})",
        raw,
    ):
        name = match.group(1)
        if is_white_list_enable():
            bind_info = await wsc.get_social_account(name)
            if bind_info["uuid"] is not None and bind_info["uuid"] != "":
                server.execute("whitelist add " + name)
    pass


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
