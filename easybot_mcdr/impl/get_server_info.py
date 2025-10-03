import os
import re
from easybot_mcdr.meta import get_plugin_version
from easybot_mcdr.websocket.context import ExecContext
from easybot_mcdr.websocket.ws import EasyBotWsClient
from mcdreforged.api.all import *

@EasyBotWsClient.listen_exec_op("GET_SERVER_INFO")
async def exec_get_server_info(ctx: ExecContext, data:dict, _):
    global is_online_mode
    server = ServerInterface.get_instance()
    working_directory = server.get_mcdr_config()["working_directory"]
    properties_path = os.path.join(working_directory, "server.properties")
    online_mode = False
    with open(properties_path, "r", encoding='utf-8') as f:
        online_mode = re.search(r"online-mode=(.*)", f.read()).group(1)
        online_mode = str(online_mode).lower().strip() == "true"
    try:
        packet = {
            "server_name": "mcdr",
            "server_version": f"MCDR {server.get_plugin_metadata('mcdreforged').version}",
            "plugin_version": get_plugin_version(),
            "is_papi_supported": False,
            "is_command_supported": True,
            "has_geyser": False,
            "is_online_mode": online_mode
        }
        # 确保所有字符串都是UTF-8编码
        packet = {k: v.encode('utf-8').decode('utf-8') if isinstance(v, str) else v 
                 for k, v in packet.items()}
    except Exception as e:
        server.logger.error(f"构建服务器信息包时出错: {str(e)}")
        raise
    is_online_mode = online_mode
    await ctx.callback(packet)
    ServerInterface.get_instance().logger.info(f"{packet['server_version']} 正版验证: {'是' if online_mode else '否'}")
    return

def get_online_mode():
    global is_online_mode
    return is_online_mode

@new_thread("EasyBot-GetPlayers")
def get_online_players(server: PluginServerInterface):
    try:
        players = server.get_online_players()
        server.logger.debug(f"获取在线玩家列表: {players}")
        return {
            "success": True,
            "players": players,
            "count": len(players)
        }
    except Exception as e:
        server.logger.warning(f"获取在线玩家列表失败: {str(e)}")
        return {
            "success": False,
            "error": str(e)
        }