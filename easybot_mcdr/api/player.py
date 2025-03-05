import json
from typing import List
from mcdreforged.api.all import *
import re
import requests

from easybot_mcdr.impl.get_server_info import is_online_mode

class PlayerInfo:
    ip: str
    name: str
    uuid: str

    def __init__(self, ip: str, name: str, uuid: str):
        self.ip = ip
        self.name = name
        self.uuid = uuid

online_players:set[str, PlayerInfo] = {}
uuid_map = {}
cached_data:set[str, PlayerInfo] = {}

def get_data_map():
    global online_players
    global uuid_map
    return {
        "online_players": online_players,
        "uuid_map": uuid_map,
        "cache": cached_data
    }

def load_data_map(data:dict):
    global online_players
    global uuid_map
    global cached_data
    online_players = data["online_players"]
    uuid_map = data["uuid_map"]
    cached_data = data["cache"]

def init_player_api(server: PluginServerInterface, old):
    reload_player_api(old)
    server.register_event_listener("mcdr.server_stop", on_server_stop, 1)
    server.register_event_listener("mcdr.player_joined", on_player_joined, 1)
    server.register_event_listener("mcdr.player_left", on_player_left, 1)
    server.register_event_listener("mcdr.general_info", on_stdout, 1)

    builder = SimpleCommandBuilder()
    builder.command("!!d list", list_player)
    builder.register(server)
    pass

def list_player(sender: CommandSource):
    if not sender.has_permission(3):
        sender.reply("§c你没有权限使用这个命令!")
    sender.reply("§a在线玩家列表: ")

    for player in online_players:
        sender.reply(f"§a{player} §eIP:{online_players[player].ip} §6UUID:{online_players[player].uuid}")

    return True

def on_stdout(server, info: Info):
    raw = info.raw_content
    # 正则解析 UUID, 构建UUIDMap
    if match := re.search(
        r"UUID of player (\w+) is ([0-9a-fA-F]{8}-(?:[0-9a-fA-F]{4}-){3}[0-9a-fA-F]{12})",
        raw
    ):
        name = match.group(1)
        uuid = match.group(2).lower()
        uuid_map[name] = uuid
        logger = ServerInterface.get_instance().logger
        logger.info("已缓存玩家 %s 的UUID: %s" % (name, uuid))
    pass

def reload_player_api(old):
    if old is not None:
        load_data_map(old)
        
def on_server_stop(server, return_code):
    global online_players
    global uuid_map
    global cached_data
    online_players = []
    uuid_map = {}
    cached_data = []


def on_player_joined(server, player, info:Info):
    logger = ServerInterface.get_instance().logger
    # logger.info("玩家 %s 加入了服务器" % player)
    # logger.info(info.raw_content)

    # 解析 UUID
    uuid = uuid_map[player]
    if uuid is None and is_online_mode():
        # 如果找不到玩家uuid,但服务器是在线模式,则使用mojang api获取
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
        ip = match.group() # ip
    online_players[player] = PlayerInfo(ip, player, uuid)
    cached_data[player] = online_players[player]

def build_player_info(player: str):
    if not check_cache(player):
        raise Exception("玩家 %s 不在线" % player)
    return {
        "player_name": player,
        "player_uuid": cached_data[player].uuid,
        "ip": cached_data[player].ip,
        "skin_url": "",
        "bedrock": False
    }

def on_player_left(server, player):
    if player in online_players:
        online_players.pop(player)

def check_cache(player:str) -> bool:
    return player in cached_data


def check_online(player: str) -> bool:
    """Check a player is online"""
    return player in online_players


def get_player_list():
    """Get all online player list"""
    return online_players.copy()