from easybot_mcdr.websocket.context import ExecContext
from easybot_mcdr.websocket.ws import EasyBotWsClient
from mcdreforged.api.all import *
import re

def get_placeholders(text: str) -> list[str]:
     return re.findall(r'%\w+%', text)

async def run_placeholder(player, text):
    server = ServerInterface.get_instance()
    logger = server.logger
    dataList = {}
    query_text = text
    for placeholder in get_placeholders(query_text):
         if placeholder.lower() == "%player_name%":
              dataList[placeholder] = player
         else:
              logger.warning(f"不支持的变量: {placeholder} [注意,MCDR仅支持最基础的变量]")
    
    for data in dataList:
         query_text = query_text.replace(data, dataList[data])
    return query_text

@EasyBotWsClient.listen_exec_op("PLACEHOLDER_API_QUERY")
async def on_placeholder_api_query(ctx: ExecContext, data:dict, _):
    server = ServerInterface.get_instance()
    player_name = data["player_name"]
    query_text = data["query_text"]
    query_text = run_placeholder(query_text, player_name)
    await ctx.callback({
         "success": True,
         "text": query_text
    })
    return