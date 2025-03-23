from easybot_mcdr.websocket.ws import EasyBotWsClient
from easybot_mcdr.config import get_config
from mcdreforged.api.all import ServerInterface

@EasyBotWsClient.listen_exec_op("CROSS_SERVER_SAY")
def handle_cross_server_say(ctx, data, session_info):
    server_name = data["server_name"]
    player = data["player"]
    message = data["message"]
    current_server_name = get_config()["server_name"]
    if server_name != current_server_name:
        server_interface = ServerInterface.get_instance()
        server_interface.say(f"{server_name}<{player}>{message}")