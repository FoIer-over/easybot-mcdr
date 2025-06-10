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

online_players = {} 
uuid_map = {}
cached_data = {} 

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


def is_bot_player(player: str) -> bool:
    """Check if player is a bot by name prefix"""
    return player.startswith(('Bot_', 'BOT_', 'bot_'))

def on_player_joined(server, player, info: Info):
    logger = ServerInterface.get_instance().logger
    
    # Skip bot players
    if is_bot_player(player):
        logger.info(f"检测到假人玩家 {player}，跳过数据处理")
        return
        
    uuid = uuid_map.get(player)
    if uuid is None:
        if is_online_mode():
            try:
                response = requests.get(f"https://api.mojang.com/users/profiles/minecraft/{player}")
                response.raise_for_status()
                id = json.loads(response.text)['id']
                uuid = f"{id[:8]}-{id[8:12]}-{id[12:16]}-{id[16:20]}-{id[20:]}"
                uuid_map[player] = uuid
            except Exception:
                uuid = "unknown"
        else:
            uuid = "unknown"
    ip = "127.0.0.1"
    if match := re.search(r'\d+\.\d+\.\d+\.\d+', info.raw_content):
        ip = match.group()
    player_info = PlayerInfo(ip, player, uuid)
    online_players[player] = player_info
    cached_data[player] = player_info

def build_player_info(player: str):
    logger = ServerInterface.get_instance().logger
    if not check_cache(player):
        if player in online_players:
            return {
                "player_name": player,
                "player_uuid": online_players[player].uuid,
                "ip": online_players[player].ip,
                "skin_url": "",
                "bedrock": False
            }
        logger.warning(f"玩家 {player} 未在线或无缓存数据")
        return None
    return {
        "player_name": player,
        "player_uuid": cached_data[player].uuid,
        "ip": cached_data[player].ip,
        "skin_url": "",
        "bedrock": False
    }

def on_player_left(server, player):
    logger = ServerInterface.get_instance().logger
    if is_bot_player(player):
        logger.info(f"检测到假人玩家 {player} 退出，跳过数据处理")
        return
        
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