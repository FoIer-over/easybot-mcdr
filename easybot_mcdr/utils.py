from mcdreforged.api.all import *

from easybot_mcdr.config import get_config
def is_white_list_enable():
    return get_config()["enable_white_list"]

    """ # 不准确
    import os
    import re
    server = ServerInterface.get_instance()
    working_directory = server.get_mcdr_config()["working_directory"]
    properties_path = os.path.join(working_directory, "server.properties")
    with open(properties_path, "r") as f:
        res = re.search(r"white-list=(.*)", f.read()).group(1)
        return str(res).lower().strip() == "true"
    return False
    """