from easybot_mcdr.impl.get_server_info import get_online_mode
from easybot_mcdr.websocket.context import ExecContext
from easybot_mcdr.websocket.ws import EasyBotWsClient
from mcdreforged.api.all import *

def try_get_skin(name):
    if get_online_mode(): # 只有在线模式获取到的皮肤才是正确的
        return f"https://mineskin.eu/download/{name}"
    # 默认尼哥
    return "https://textures.minecraft.net/texture/eee522611005acf256dbd152e992c60c0bb7978cb0f3127807700e478ad97664"

@EasyBotWsClient.listen_exec_op("PLAYER_LIST")
async def on_get_player_list(ctx: ExecContext, data:dict, _):
    logger = ServerInterface.get_instance().logger
    from easybot_mcdr.api.player import get_player_list
    online_list = get_player_list()
    list = []
    for player in online_list:
        list.append({
            "player_name": player,
            "player_uuid": online_list[player].uuid,
            "ip": online_list[player].ip,
            "bedrock": False,
            "skin_url": try_get_skin(player)
        })
    await ctx.callback({
        "list": list
    })