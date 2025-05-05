import time
from easybot_mcdr.config import get_config
from easybot_mcdr.websocket.context import ExecContext
from easybot_mcdr.websocket.ws import EasyBotWsClient
from mcdreforged.api.all import *

@EasyBotWsClient.listen_exec_op("SEND_TO_CHAT")
async def sync_message(ctx: ExecContext, data:dict, _):
    # 输入验证
    if not isinstance(data, dict):
        ServerInterface.get_instance().logger.error("无效的消息数据格式")
        return
    
    # 安全获取text
    text = str(data.get("text", ""))
    
    # 处理extra数据
    extra_data = []
    if isinstance(data.get("extra"), list):
        extra_data = data["extra"]
    elif data.get("extra") is not None:
        ServerInterface.get_instance().logger.warning(f"无效的extra格式: {type(data['extra'])}")

    if not extra_data:
        ServerInterface.get_instance().broadcast(text)
        ServerInterface.get_instance().logger.info(text)
        return
    
    text_list = RTextList()
    at_players = []
    current_text = ""
    has_at_all = False

    def append_current_text():
        nonlocal current_text
        if current_text:
            text_list.append(RText(current_text))
            current_text = ""

    # 确保extra_data是可迭代的
    extra_data = extra_data if isinstance(extra_data, list) else []
    for segment in extra_data:
        if not isinstance(segment, dict):
            continue
            
        seg_type = segment.get("type", 0)
        
        # 处理text类型
        if seg_type == 2:
            text = str(segment.get("text", ""))
            current_text += text
            
        else:
            append_current_text()  # 遇到非text类型时先提交暂存文本
            
            # 处理image类型
            if seg_type == 3:
                url = str(segment.get("url", ""))
                image_text = RText("[图片]")
                image_text.set_hover_text("点击预览")
                if url:
                    image_text.set_click_event(RAction.open_url, url)
                image_text.set_color(RColor.green)
                text_list.append(image_text)
                
            # 处理at类型
            elif seg_type == 4:
                at_names = segment.get("at_player_names", []) or []
                if not isinstance(at_names, list):
                    at_names = []
                
                user_id = str(segment.get('at_user_id', ""))
                user_name = str(segment.get('at_user_name', ""))
                
                if user_id == "0":
                    at_text = RText("@全体成员")
                    has_at_all = True
                elif not at_names:
                    at_text = RText(user_name)
                else:
                    at_text = RText("@" + ",".join(at_names))
                
                at_text.set_color(RColor.gold)
                at_text.set_hover_text(f"社交账号: {user_name}({user_id})")
                for player in at_names:
                    if isinstance(player, str):
                        at_players.append(player)
                text_list.append(at_text)
                
            # 处理file类型
            elif seg_type == 5:
                file_text = RText("[文件]")
                file_text.set_color(RColor.green)
                text_list.append(file_text)
                
            # 处理reply类型
            elif seg_type == 6:
                reply_text = RText("[回复某条消息]")
                reply_text.set_color(RColor.gray)
                text_list.append(reply_text)
    append_current_text()
    ServerInterface.get_instance().broadcast(text_list)

    config = get_config()["events"]["message"]["on_at"]
    logger = ServerInterface.get_instance().logger
    # @判断
    if config["exec_command"] and "comamnds" in config:
        commands = config["comamnds"]
        if not isinstance(commands, list):
            logger.warning("命令列表格式无效，已跳过执行")
            return
            
        if has_at_all:
            for command in commands:
                if not isinstance(command, str):
                    continue
                try:
                    cmd = command.replace("#player", "@a")
                    ServerInterface.get_instance().execute(cmd)
                except Exception as e:
                    logger.error(f"执行命令失败: {cmd} ({str(e)})")
        else:
            for player in at_players:
                from easybot_mcdr.api.player import check_online
                if check_online(player):
                    for command in commands:
                        if not isinstance(command, str):
                            continue
                        try:
                            cmd = command.replace("#player", player)
                            ServerInterface.get_instance().execute(cmd)
                        except Exception as e:
                            logger.error(f"执行命令失败: {cmd} ({str(e)})")

    def play_sound(count, interval, sound_command, player):
        for i in range(count):
            logger.info(command.replace("#player", player))
            ServerInterface.get_instance().execute(sound_command.replace("#player", player))
            time.sleep(interval / 1000)

    if "sound" in config and config["sound"]["play_sound"]:
        if "run" not in config["sound"] or not isinstance(config["sound"]["run"], str):
            logger.warning("音效命令配置无效，已跳过")
            return
            
        command = config["sound"]["run"]
        if has_at_all:
            play_sound(
                config["sound"].get("count", 1),
                config["sound"].get("interval_ms", 1000),
                command,
                "@a"
            )
        else:
            for player in at_players:
                from easybot_mcdr.api.player import check_online
                if check_online(player):
                    play_sound(
                        config["sound"].get("count", 1),
                        config["sound"].get("interval_ms", 1000),
                        command,
                        player
                    )