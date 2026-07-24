# Copyright (C) 2026 by xcentaurix

import os
import re

from Components.ActionMap import HelpableActionMap
from Components.config import config
from Components.Sources.StaticText import StaticText
from Screens.Setup import Setup

from . import _
from .SamsungTVConfig import NUMBER_OF_LIVETV_BOUQUETS
from .SamsungTVDownload import SamsungTVDownload, Silent
from .PiconFetcher import PiconFetcher
from .Variables import BOUQUET_FILE
from .Version import VERSION


class SamsungTVSetup(Setup):
    def __init__(self, session):
        Setup.__init__(self, session, setup="Samsung TV")
        if "key_yellow" not in self:
            self["key_yellow"] = StaticText()
            self["key_yellowActions"] = HelpableActionMap(self, ["ColorActions"], {
                "yellow": (self.yellow, _("Remove picons")),
            }, prio=1, description=_("Samsung TV Plus Setup Actions"))
        if "key_blue" not in self:
            self["key_blue"] = StaticText()
            self["key_blueActions"] = HelpableActionMap(self, ["ColorActions"], {
                "blue": (self.blue, _("Remove Live-TV Bouquet")),
            }, prio=1, description=_("Samsung TV Plus Setup Actions"))
        self.updateYellowButton()
        self.updateBlueButton()
        self.setTitle(_("Samsung TV Plus Setup") + f" ({VERSION})")

    def createSetup(self):
        configList = []
        configList.append((_("Region"), config.plugins.samsungtv.region, _("Select the region for the channel list.")))
        configList.append(("---",))
        for n in range(1, NUMBER_OF_LIVETV_BOUQUETS + 1):
            if n == 1 or getattr(config.plugins.samsungtv, "live_tv_region" + str(n - 1)).value:
                configList.append((_("Live-TV bouquet %s") % n, getattr(config.plugins.samsungtv, "live_tv_region" + str(n)), _("Region for which Live-TV bouquet %s will be created.") % n))
        configList.append(("---",))
        configList.append((_("Picon type"), config.plugins.samsungtv.picons, _("Using service name picons means they will continue to work even if the service reference changes.")))
        configList.append((_("Automatic update check"), config.plugins.samsungtv.auto_update_check, _("Automatically check for a newer package update when the plugin GUI is opened.")))
        configList.append((_("Data location"), config.plugins.samsungtv.config_folder, _("Location the configuration data are stored in.")))
        self["config"].list = configList

    def _locationConfigChanged(self):
        if config.plugins.samsungtv.region.isChanged():
            return True
        return any(getattr(config.plugins.samsungtv, "live_tv_region" + str(n)).isChanged() for n in range(1, NUMBER_OF_LIVETV_BOUQUETS + 1))

    def keySave(self):
        if self._locationConfigChanged():
            self.session.openWithCallback(lambda *_: Setup.keySave(self), SamsungTVDownload)
        else:
            Setup.keySave(self)

    def updateYellowButton(self):
        if os.path.isdir(PiconFetcher(config.plugins.samsungtv.picons).pluginPiconDir):
            self["key_yellow"].text = _("Remove picons")
        else:
            self["key_yellow"].text = ""

    def updateBlueButton(self):
        with open("/etc/enigma2/bouquets.tv", "r", encoding="utf-8") as f:
            bouquets = f.read()
        if "samsungtv" in bouquets:
            self["key_blue"].text = _("Remove Live-TV Bouquet")
        else:
            self["key_blue"].text = ""

    def yellow(self):
        if self["key_yellow"].text:
            PiconFetcher(config.plugins.samsungtv.picons).removeall()
            self.updateYellowButton()

    def blue(self):
        if self["key_blue"].text:
            Silent.stop()
            from enigma import eDVBDB
            eDVBDB.getInstance().removeBouquet(re.escape(BOUQUET_FILE) % ".*")
            self.updateBlueButton()
