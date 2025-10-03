import re
from typing import List, Type

# Dynamically collect available handlers in a preferred order
_handler_classes: List[Type] = []
try:
    from mcdreforged.handler.impl import ForgeHandler
    _handler_classes.append(ForgeHandler)
except Exception:
    pass
try:
    from mcdreforged.handler.impl import FabricHandler
    _handler_classes.append(FabricHandler)
except Exception:
    pass
try:
    # Some environments only expose Bukkit/Paper via Spigot-like handler
    from mcdreforged.handler.impl import SpigotHandler
    _handler_classes.append(SpigotHandler)
except Exception:
    pass
try:
    from mcdreforged.handler.impl import PaperHandler
    _handler_classes.append(PaperHandler)
except Exception:
    pass
try:
    from mcdreforged.handler.impl import VanillaHandler
    _handler_classes.append(VanillaHandler)
except Exception:
    pass

# Final fallback: if nothing imported, raise at runtime clearly
if not _handler_classes:
    raise ImportError('No base handlers available from mcdreforged.handler.impl')


class PrefixNameHandler(_handler_classes[0]):
    """
    A server handler that parses chat lines with player name prefixes, e.g.
    "<[Builder]Steve> Hello" -> player="Steve", content="Hello"
    
    Composite approach: try multiple base handlers (Forge/Fabric/Spigot/Paper/Vanilla)
    in order to maximize parse success across server types. If none recognize player,
    apply prefix post-processing.
    """

    def get_name(self) -> str:
        return 'easybot_prefix_handler'

    def parse_server_stdout(self, text: str):
        # Try each underlying handler until one yields a result
        info = None
        last_info = None
        for cls in _handler_classes:
            parser = getattr(self, f'_eb_{cls.__name__}', None)
            if parser is None:
                try:
                    parser = cls()
                except Exception:
                    continue
                setattr(self, f'_eb_{cls.__name__}', parser)
            try:
                last_info = parser.parse_server_stdout(text)
                if last_info is not None:
                    info = last_info
                    # Prefer the first one that recognizes a player name
                    if getattr(info, 'player', None):
                        break
            except Exception:
                continue

        if info is None:
            # As a last resort, call our own base implementation (first class)
            info = super().parse_server_stdout(text)

        # Only try to parse when no parser recognized a player
        if info.player is None:
            # Match like: [Not Secure] <[AnyWord]PlayerName> Message or <[AnyWord]PlayerName> Message
            # prefix group is optional capture for readability; only name+message used
            m = re.fullmatch(r'(?:\[Not Secure\] )?<\[(?P<prefix>[^\]]+)\](?P<name>[^>]+)> (?P<message>.*)', info.content)
            if m is not None and self._verify_player_name(m['name']):
                info.player = m['name']
                info.content = m['message']
        return info
