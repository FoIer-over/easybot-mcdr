import json
from typing import List
from mcdreforged.api.all import *
import re
import requests

from easybot_mcdr.impl.get_server_info import is_online_mode
from easybot_mcdr.config import get_config


class PlayerInfo:
    ip: str
    name: str
    uuid: str

    def __init__(self, ip: str, name: str, uuid: str):
        self.ip = ip
        self.name = name
        self.uuid = uuid


online_players: dict[str, PlayerInfo] = {}
uuid_map: dict[str, str] = {}
cached_data: dict[str, PlayerInfo] = {}
event_listeners: List = []


def get_data_map():
    global online_players, uuid_map, cached_data
    return {
        "online_players": online_players,
        "uuid_map": uuid_map,
        "cache": cached_data
    }


def load_data_map(data: dict):
    global online_players, uuid_map, cached_data
    online_players = data["online_players"]
    uuid_map = data["uuid_map"]
    cached_data = data["cache"]


def init_player_api(server: PluginServerInterface, old):
    global event_listeners
    reload_player_api(old)
    event_listeners.append(server.register_event_listener("mcdr.server_stop", on_server_stop, 1))
    event_listeners.append(server.register_event_listener("mcdr.player_joined", on_player_joined, 1))
    event_listeners.append(server.register_event_listener("mcdr.player_left", on_player_left, 1))
    event_listeners.append(server.register_event_listener("mcdr.general_info", on_stdout, 1))

    builder = SimpleCommandBuilder()
    builder.command("!!d list", list_player)
    builder.register(server)


def list_player(sender: CommandSource):
    if not sender.has_permission(3):
        sender.reply("§c你没有权限使用这个命令!")
        return
    sender.reply("§a在线玩家列表: ")

    for player in online_players:
        sender.reply(f"§a{player} §eIP:{online_players[player].ip} §6UUID:{online_players[player].uuid}")

    return True


def on_stdout(server, info: Info):
    raw = info.raw_content
    if match := re.search(
        r"UUID of player (\w+) is ([0-9a-fA-F]{8}-(?:[0-9a-fA-F]{4}-){3}[0-9a-fA-F]{12})",
        raw
    ):
        name = match.group(1)
        uuid = match.group(2).lower()
        uuid_map[name] = uuid
        logger = ServerInterface.get_instance().logger
        logger.info("已缓存玩家 %s 的UUID: %s" % (name, uuid))


def reload_player_api(old):
    if old is not None:
        load_data_map(old)


def on_server_stop(server, return_code):
    global online_players, uuid_map, cached_data
    online_players = {}
    uuid_map = {}
    cached_data = []


def on_player_joined(server, player, info: Info):
    logger = ServerInterface.get_instance().logger
    enable_filter = get_config().get("enable_fake_player_filter", False)
    if enable_filter:
        prefix = get_config().get("fake_player_prefix", "")
        if prefix and player.startswith(prefix):
            logger.info(f"检测到假人 {player}，跳过数据获取")
            return

    uuid = uuid_map.get(player)
    if uuid is None and is_online_mode():
        try:
            id = json.loads(requests.get(f"https://api.mojang.com/users/profiles/minecraft/{player}").text)['id']
            uuid = f"{id[:8]}-{id[8:12]}-{id[12:16]}-{id[16:20]}-{id[20:]}"
            logger.info(f"通过MojangApi获取到玩家 {player} 的UUID: {uuid}")
            uuid_map[player] = uuid
        except Exception as e:
            logger.error("获取玩家UUID失败: %s" % e)
            uuid = None
    ip = "127.0.0.1"
    raw = info.raw_content
    if match := re.search(r'\d+\.\d+\.\d+\.\d+', raw):  
        ip = match.group()
    online_players[player] = PlayerInfo(ip, player, uuid)
    cached_data[player] = online_players[player]
    logger.info(f"玩家 {player} 已加入并缓存: UUID={uuid}, IP={ip}")


def build_player_info(player: str):
    logger = ServerInterface.get_instance().logger
    enable_filter = get_config().get("enable_fake_player_filter", False)
    if enable_filter:
        prefix = get_config().get("fake_player_prefix", "")
        if prefix and player.startswith(prefix):
            return {
                "player_name": player,
                "player_uuid": "00000000-0000-0000-0000-000000000000",
                "ip": "0.0.0.0",
                "skin_url": "",
                "bedrock": False,
                "type": "fake"
            }
    if player == "CONSOLE":
        return {
            "player_name": "CONSOLE",
            "player_uuid": "00000000-0000-0000-0000-000000000000",
            "ip": "0.0.0.0",
            "skin_url": "",
            "bedrock": False,
            "type": "console"
        }
    if not check_cache(player):
        logger.warning(f"玩家 {player} 不在缓存中，可能已离线或未正确加入")
        return {
            "player_name": player,
            "player_uuid": uuid_map.get(player, "unknown-uuid"),
            "ip": "unknown-ip",
            "skin_url": "",
            "bedrock": False,
            "type": "player"
        }
    
    return {
        "player_name": player,
        "player_uuid": cached_data[player].uuid,
        "ip": cached_data[player].ip,
        "skin_url": "",
        "bedrock": False,
        "type": "player"
    }


def on_player_left(server, player):
    if player in online_players:
        online_players.pop(player)
    if player in cached_data:
        cached_data.pop(player)


def check_cache(player: str) -> bool:
    return player in cached_data


def check_online(player: str) -> bool:
    return player in online_players


def get_player_list():
    return online_players.copy()


def cleanup_player_api(server: PluginServerInterface):
    global online_players, uuid_map, cached_data, event_listeners
    online_players = {}
    uuid_map = {}
    cached_data = {}
    event_listeners.clear()