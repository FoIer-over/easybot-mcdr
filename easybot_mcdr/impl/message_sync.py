import time
from easybot_mcdr.config import get_config
from easybot_mcdr.websocket.context import ExecContext
from easybot_mcdr.websocket.ws import EasyBotWsClient
from mcdreforged.api.all import *

@EasyBotWsClient.listen_exec_op("SEND_TO_CHAT")
async def sync_message(ctx: ExecContext, data:dict, _):
    if "extra" not in data:
        ServerInterface.get_instance().broadcast(data["text"])
        ServerInterface.get_instance().logger.info(data["text"])
        return
    
    text_list = RTextList()
    at_players = []
    current_text = ""  # 用于暂存连续的text内容
    has_at_all = False

    def append_current_text():
        nonlocal current_text
        if current_text:
            text_list.append(RText(current_text))
            current_text = ""

    for segment in data["extra"]:
        if segment["type"] == 2:  # text类型
            current_text += segment["text"]
        else:
            append_current_text()  # 遇到非text类型时先提交暂存文本
            if segment["type"] == 3:  # image
                image_text = RText("[图片]")
                image_text.set_hover_text("点击预览")
                image_text.set_click_event(RAction.open_url, segment["url"])
                image_text.set_color(RColor.green)
                text_list.append(image_text)
            elif segment["type"] == 4:  # at
                at_text = RText("@" + ",".join(segment["at_player_names"]))
                if segment['at_user_id'] == "0":
                    at_text = RText("@全体成员")
                    has_at_all = True
                elif(len(segment["at_player_names"]) == 0):
                    at_text = RText(segment['at_user_name'])
                at_text.set_color(RColor.gold)
                at_text.set_hover_text(f"社交账号: {segment['at_user_name']}({segment['at_user_id']})")
                for player in segment["at_player_names"]:
                    at_players.append(player)
                text_list.append(at_text)
            elif segment["type"] == 5:  # file
                file_text = RText("[文件]")
                file_text.set_color(RColor.green)
                text_list.append(file_text)
            elif segment["type"] == 6:  # reply
                reply_text = RText("[回复某条消息]")
                reply_text.set_color(RColor.gray)
                text_list.append(reply_text)
    append_current_text()
    ServerInterface.get_instance().broadcast(text_list)

    config = get_config()["events"]["message"]["on_at"]
    logger = ServerInterface.get_instance().logger
    # @判断
    if config["exec_command"]:
        commands = config["comamnds"]
        if has_at_all:
            for command in commands:
                ServerInterface.get_instance().execute(command.replace("#player", "@a"))
        else:
            for player in at_players:
                from easybot_mcdr.api.player import check_online
                if check_online(player):
                    for command in commands:
                        logger.info(command.replace("#player", player))
                        ServerInterface.get_instance().execute(command.replace("#player", player))

    def play_sound(count, interval, sound_command, player):
        for i in range(count):
            logger.info(command.replace("#player", player))
            ServerInterface.get_instance().execute(sound_command.replace("#player", player))
            time.sleep(interval / 1000)

    if config["sound"]["play_sound"]:
        command = config["sound"]["run"]
        if has_at_all:
            play_sound(
                config["sound"]["count"],
                config["sound"]["interval_ms"],
                command,
                "@a"
            )
        else:
            for player in at_players:
                from easybot_mcdr.api.player import check_online
                if check_online(player):
                    play_sound(
                        config["sound"]["count"],
                        config["sound"]["interval_ms"],
                        command,
                        player
                    )

