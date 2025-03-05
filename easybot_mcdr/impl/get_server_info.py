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
    with open(properties_path, "r") as f:
        online_mode = re.search(r"online-mode=(.*)", f.read()).group(1)
        online_mode = str(online_mode).lower().strip() == "true"
    packet = {
        "server_name": "mcdr",
        "server_version": f"MCDR {server.get_plugin_metadata("mcdreforged").version}",
        "plugin_version":get_plugin_version(),
        "is_papi_supported":  False,
        "is_command_supported": False,
        "has_geyser": False,
        "is_online_mode": online_mode
    }
    is_online_mode = online_mode
    await ctx.callback(packet)
    ServerInterface.get_instance().logger.info(f"{packet['server_version']} 正版验证: {'是' if online_mode else '否'}")
    return

def is_online_mode():
    return is_online_mode