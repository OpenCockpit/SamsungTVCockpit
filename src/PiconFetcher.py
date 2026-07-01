# Copyright (C) 2026 by xcentaurix
# Picon management for Samsung TV Plus

from Components.config import config
from .PiconFetcherBase import PiconFetcherBase
from .Variables import PLUGIN_FOLDER, PLUGIN_ICON, USER_AGENT


class PiconFetcher(PiconFetcherBase):
    def __init__(self, parent=None):
        super().__init__(
            plugin_name="SamsungTV",
            picons_config=config.plugins.samsungtv.picons,
            plugin_folder=PLUGIN_FOLDER,
            plugin_icon=PLUGIN_ICON,
            user_agent=USER_AGENT,
            parent=parent,
        )
