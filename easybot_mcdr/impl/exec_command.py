from easybot_mcdr.websocket.context import ExecContext
from easybot_mcdr.websocket.ws import EasyBotWsClient
from mcdreforged.api.all import *

@EasyBotWsClient.listen_exec_op("RUN_COMMAND")
async def exec_bind_success_notify(ctx: ExecContext, data:dict, _):
    server = ServerInterface.get_instance()
    logger = server.logger

    if not server.is_rcon_running():
        logger.error(f"RCON未开启,无法执行命令 -> {data['command']}")
        ctx.callback({
            "success": False,
            "text": "目标MCDR未开启未开启RCON,无法执行命令!"
        })
        return
    command = data["command"]
    if data["enable_papi"]:
        from easybot_mcdr.impl.papi import run_placeholder
        command = await run_placeholder(command, data["player_name"])
    try:
        if not server.is_rcon_running():
            raise Exception("RCON未启用")
            
        resp = server.rcon_query(command)
        logger.debug(f"执行命令 -> {command}")
        logger.debug(f"执行结果 -> {resp}")
        await ctx.callback({
            "success": True,
            "text": resp
        })
    except Exception as e:
        logger.warning(f"RCON查询失败: {str(e)}")
        await ctx.callback({
            "success": False,
            "text": f"RCON查询失败: {str(e)}"
        })