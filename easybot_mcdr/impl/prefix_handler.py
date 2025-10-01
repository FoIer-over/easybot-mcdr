import re

from mcdreforged.handler.impl import VanillaHandler


class PrefixNameHandler(VanillaHandler):
    """
    A server handler that parses chat lines with player name prefixes, e.g.
    "<[Builder]Steve> Hello" -> player="Steve", content="Hello"
    
    Compatible with vanilla-like output. Falls back to VanillaHandler parsing first
    and only post-processes when player is None.
    """

    def get_name(self) -> str:
        return 'easybot_prefix_handler'

    def parse_server_stdout(self, text: str):
        info = super().parse_server_stdout(text)
        # Only try to parse when VanillaHandler didn't recognize a player
        if info.player is None:
            # Match like: <[AnyWord]PlayerName> Message
            # prefix group is optional capture for readability; only name+message used
            m = re.fullmatch(r'<\[(?P<prefix>[^\]]+)\](?P<name>[^>]+)> (?P<message>.*)', info.content)
            if m is not None and self._verify_player_name(m['name']):
                info.player = m['name']
                info.content = m['message']
        return info
