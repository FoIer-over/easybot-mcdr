from easybot_mcdr.config import get_config
from easybot_mcdr.utils import is_white_list_enable
from easybot_mcdr.websocket.context import ExecContext
from easybot_mcdr.websocket.ws import EasyBotWsClient
from mcdreforged.api.all import *
@EasyBotWsClient.listen_exec_op("BIND_SUCCESS_NOTIFY")
async def exec_bind_success_notify(ctx: ExecContext, data:dict, _):
    logger = ServerInterface.get_instance().logger
    player_name = data['player_name']
    account_id = data['account_id']
    account_name = data['account_name']
    message = str(get_config()["message"]["bind_success"]).replace("#name", account_name).replace("#account", account_id).replace("#player", player_name)
    logger.info(f"收到广播,玩家{player_name}绑定成功, 即将使用tallraw发送消息到玩家(如果玩家在线)")
    logger.info(message)

    if get_config()["events"]["bind_success"]["add_whitelist"] and is_white_list_enable():
        logger.info(f"尝试添加玩家 {player_name} 到白名单")
        ServerInterface.get_instance().execute("whitelist add " + player_name)

    ServerInterface.get_instance().tell(player_name, message)
    if get_config()["events"]["bind_success"]["exec_command"]:
        commands = get_config()["events"]["bind_success"]["comamnds"]
        logger.info(f"即将执行绑定成功预设指令 ({len(commands)}个)")
        for command in commands:
            ServerInterface.get_instance().execute(command.replace("#name", account_name).replace("#account", account_id).replace("#player", player_name))