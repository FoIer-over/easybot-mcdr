import asyncio
from collections import defaultdict
import json
from types import SimpleNamespace
import websockets
from websockets.exceptions import ConnectionClosed, ConnectionClosedError
from mcdreforged.api.all import *
from easybot_mcdr.config import get_config
from easybot_mcdr.meta import get_plugin_version
from easybot_mcdr.websocket.context import ExecContext

class SessionInfo:
    def __init__(self, version: str, system: str, dotnet: str, session_id:str, token: str, interval: int):
        self.version = version
        self.system = system
        self.dotnet = dotnet
        self.session_id = session_id
        self.token = token
        self.interval = interval
        self.server_name = None

    def from_dict(data: dict):
        return SessionInfo(
            version=data["version"],
            system=data["system"],
            dotnet=data["dotnet"],
            session_id=data["session_id"],
            token=data["token"],
            interval=data["interval"]
        )
    
    def get_version(self):
        return self.version
    
    def get_system(self):
        return self.system
    
    def get_dotnet(self):
        return self.dotnet
    
    def get_session_id(self):
        return self.session_id
    
    def get_token(self):
        return self.token
    
    def get_interval(self):
        return self.interval
    
    def set_server_name(self, server_name: str):
        self.server_name = server_name

    def get_server_name(self):
        return self.server_name

class EasyBotWsClient:
    _listeners = defaultdict(list)

    @classmethod
    def listen_exec_op(cls, exec_op: str):
        """装饰器: 为指定 exec_op 注册处理器"""
        def decorator(func):
            cls._listeners[exec_op].append(func)
            return func
        return decorator

    def __init__(self, url):
        self.ws_url = url
        self._conn_lock = asyncio.Lock()  # 连接锁防止重复连接
        self._ws = None
        self._active = False
        self._manual_stop = False
        self._reconnect_base = 1  # 指数退避基数
        self._max_reconnect_interval = 30  # 最大重连间隔
        self._session_info = None
        self._heartbeat_task = None  # 心跳
        self._pending_requests = {}  # 存储等待中的请求 {callback_id: future}
        self._request_counter = 0    # 用于生成唯一 callback_id
    async def send_and_wait(self, exec_op: str, data: dict, timeout: float = 10.0) -> dict:
            """
            发送请求并等待响应
            :param exec_op: 操作类型
            :param data: 要发送的数据字典
            :param timeout: 超时时间(秒)
            :return: 服务器返回的字典结果
            """
            callback_id = f"req_{self._request_counter}"
            self._request_counter += 1

            # 创建 Future 对象用于等待结果
            loop = asyncio.get_running_loop()
            future = loop.create_future()
            self._pending_requests[callback_id] = future

            try:
                # 构建请求包
                packet = {
                    "op": 4,
                    "exec_op": exec_op,
                    "callback_id": str(callback_id)
                }
                packet.update(data)  # 合并自定义数据
                
                # 发送请求
                await self.send(json.dumps(packet))
                
                # 等待结果或超时
                return await asyncio.wait_for(future, timeout)
            finally:
                # 清理 pending 请求
                self._pending_requests.pop(callback_id, None)
    async def start(self):
        """启动连接循环"""
        async with self._conn_lock:
            if self._active:
                return
            self._active = True
            self._manual_stop = False
            asyncio.create_task(self._connection_manager())

    async def stop(self):
        """停止连接循环"""
        self._active = False
        self._manual_stop = True
        if self._ws:
            await self._ws.close(reason="MCDR插件端主动关闭连接")
    async def _start_heartbeat(self, interval_seconds: int):
            """启动心跳循环"""
            if self._heartbeat_task and not self._heartbeat_task.done():
                self._heartbeat_task.cancel()
                try:
                    await self._heartbeat_task
                except asyncio.CancelledError:
                    pass

            async def heartbeat_loop():
                try:
                    while True:
                        await asyncio.sleep(interval_seconds - 10)  # 减少十秒 因为给的是到期时间，需要在到期之前发送心跳
                        if not (self._active and self._ws and self._ws.state is websockets.State.OPEN):
                            break
                        await self.send(json.dumps({"op": 2}))
                except (ConnectionClosed, asyncio.CancelledError):
                    pass

            self._heartbeat_task = asyncio.create_task(heartbeat_loop())
    async def _connection_manager(self):
        """连接生命周期管理器"""
        reconnect_attempts = 0
        while self._active:
            try:
                # 指数退避计算
                delay = min(self._reconnect_base * (2 ** reconnect_attempts), 
                           self._max_reconnect_interval)
                await asyncio.sleep(delay)
                
                async with websockets.connect(self.ws_url) as websocket:
                    self._ws = websocket
                    reconnect_attempts = 0  # 重置重连计数器
                    await self.on_open()
                    await self._message_pump()
                    
            except (ConnectionRefusedError, ConnectionClosedError) as e:
                reconnect_attempts += 1
                await self.on_error(f"Connection error: {e} (Attempt {reconnect_attempts})")
            except Exception as e:
                await self.on_error(f"Unexpected error: {e}")
                await asyncio.sleep(1)  # 非连接错误短暂等待

        await self._cleanup_connection()

    async def _message_pump(self):
        """消息泵循环"""
        try:
            while self._active and self._ws.state is websockets.State.OPEN:
                try:
                    message = await asyncio.wait_for(
                        self._ws.recv(), 
                        timeout=1.0  # 添加超时以定期检查连接状态
                    )
                    await self.on_message(message)
                except asyncio.TimeoutError:
                    continue  # 正常轮询检查
        except ConnectionClosed as e:
            await self.on_close(e.code, e.reason)

    async def _cleanup_connection(self):
        """清理连接资源"""
        if self._ws and self._ws.state is websockets.State.OPEN:
            await self._ws.close(reason="MCDR端清理连接资源主动关闭")
        self._ws = None

    async def send(self, message):
        """安全消息发送方法"""
        if not (self._active and self._ws and self._ws.state is websockets.State.OPEN):
            raise ConnectionError("当前WebSocket客户端不在线,插件可能还未连接到EasyBot服务!")
        
        if get_config()["debug"]:
            logger = ServerInterface.get_instance().logger
            logger.info(f"发送: {message}")

        await self._ws.send(message)

    # 需要实现的生命周期回调
    async def on_open(self):
        ServerInterface.get_instance().logger.info("已与主程序建立连接。")

    async def on_message(self, message):
        logger = ServerInterface.get_instance().logger
        if get_config()["debug"]:
            logger.info(f"收到: {message}")
        data = json.loads(message)
        op = data["op"]
        if op == 0:
            self._session_info = SessionInfo.from_dict(data)
            info: SessionInfo = self._session_info
            logger.info(f"目标核心版本: {info.get_version()}-{info.get_system()} [{info.get_dotnet()}] 心跳{info.get_interval()}s 会话ID: {info.get_session_id()}")
            logger.info(f"准备发送鉴权,本服令牌: {get_config()['token']}")
            await self.send(json.dumps({
                "op": 1,
                "token": get_config()["token"],
                "plugin_version": get_plugin_version(),
                "server_description": f"MCDR_{ServerInterface.get_instance().get_server_information().version}",
            }))
        elif op == 3:
          self._session_info.set_server_name(
              data["server_name"]
          )
          logger.info(f"身份验证成功,已经成功连接到EasyBot。 [{data["server_name"]}]")
            # 启动心跳
          if self._session_info is not None:
                interval = self._session_info.get_interval()
                await self._start_heartbeat(interval)
        elif op == 4:
            exec_op = data.get("exec_op")
            if exec_op in self._listeners:
                ctx = ExecContext(data["callback_id"], data["exec_op"], self)
                for handler in self._listeners[exec_op]:
                    try:
                        # 自动处理同步/异步函数
                        if asyncio.iscoroutinefunction(handler):
                            await handler(ctx, data, self._session_info)
                        else:
                            handler(ctx, data, self._session_info)
                    except Exception as e:
                        logger.error(f"处理 exec_op={exec_op} 时出错: {str(e)}")
        elif op == 5:  # 新增：处理服务器响应
            callback_id = data.get("callback_id")
            if callback_id and callback_id in self._pending_requests:
                future = self._pending_requests.pop(callback_id)
                # 去除 op 字段后作为结果返回
                result = data.copy()
                result.pop("op", None)
                future.set_result(result)
    async def on_close(self, code, reason):
        ServerInterface.get_instance().logger.info(f"连接关闭: {code} {reason}")

    async def on_error(self, error):
        ServerInterface.get_instance().logger.error(f"遇到错误: {error}")

    async def _send_packet(self, exec_op:str, data:dict):
        if self._active:
            packet = {
                "op": 4,
                "exec_op": exec_op,
                "callback_id": "0"
            }
            packet.update(data)
            await self.send(json.dumps(packet))

    async def login(self, player_name: str):
        from easybot_mcdr.api.player import build_player_info
        data = await self.send_and_wait("PLAYER_JOIN", {
            "player": build_player_info(player_name)
        }, 5)
        return data

    async def report_player(self, player_name: str):
        from easybot_mcdr.api.player import build_player_info
        info = build_player_info(player_name)
        await self._send_packet("REPORT_PLAYER", {
            "player_name": player_name,
            "player_uuid": info["player_uuid"],
            "player_ip": info["ip"],
        })

    async def push_message(self, player_name: str, message: str, use_command:bool):
        from easybot_mcdr.api.player import build_player_info
        info = build_player_info(player_name)
        info['player_name_raw'] = player_name

        await self._send_packet("SYNC_MESSAGE", {
            "player": info,
            "message": message,
            "use_command": use_command
        })

    async def push_death(self, player_name: str, killer: str, message: str):
        from easybot_mcdr.api.player import build_player_info
        info = build_player_info(player_name)
        info['player_name_raw'] = player_name
        await self._send_packet("SYNC_DEATH_MESSAGE", {
            "player": info,
            "raw": message,
            "killer": killer
        })

    async def push_enter(self, player_name: str):
        from easybot_mcdr.api.player import build_player_info
        info = build_player_info(player_name)
        info['player_name_raw'] = player_name
        await self._send_packet("SYNC_ENTER_EXIT_MESSAGE", {
            "player": info,
            "is_enter": True
        })

    async def push_exit(self, player_name: str):
        from easybot_mcdr.api.player import build_player_info
        info = build_player_info(player_name)
        info['player_name_raw'] = player_name
        await self._send_packet("SYNC_ENTER_EXIT_MESSAGE", {
            "player": info,
            "is_enter": False
       })
        
    async def get_social_account(self, player_name: str):
        resp = await self.send_and_wait("GET_SOCIAL_ACCOUNT", {
            "player_name": player_name
        })
        return resp
    
    async def start_bind(self, player_name: str):
        resp = await self.send_and_wait("START_BIND", {
            "player_name": player_name
        })
        return resp