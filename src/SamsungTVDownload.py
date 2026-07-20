# Copyright (C) 2026 by xcentaurix

import os
import re
import zlib

from Components.ActionMap import ActionMap
from Components.config import config
from Components.Label import Label
from Components.ProgressBar import ProgressBar
from Screens.MessageBox import MessageBox
from Screens.Screen import Screen
from enigma import eTimer

from . import _
from .SamsungTVConfig import REGION_NAMES, TSIDS, getselectedregions
from .SamsungTVRequest import samsungRequest
from .Variables import TIMER_FILE, BOUQUET_FILE, BOUQUET_NAME, CHANNELLIST_FILE, XMLTV_FILE
from .CockpitTVDownload import TVDownloadBase, TVDownloadScreenMixin, TVDownloadSilentMixin, importXMLTVGuide
from .Debug import logger


DATA_PATH = os.path.join(os.path.dirname(os.path.realpath(__file__)), "data")
SAMSUNG_IGNORE = "samsungtvplus.ignore"
SAMSUNG_REPLACE = "samsungtvplus.replace"

EXT_SAMSUNG_XML = "https://i.mjh.nz/SamsungTVPlus/%s.xml"


class SamsungTVDownloadBase(TVDownloadBase):
    downloadActive = False

    TIMER_FILE = TIMER_FILE
    BOUQUET_FILE = BOUQUET_FILE
    CHANNELLIST_FILE = CHANNELLIST_FILE
    XMLTV_FILE = XMLTV_FILE
    TSIDS = TSIDS

    SILENT_IN_PROGRESS_TEXT = _("A silent download is in progress.")
    PICONS_LABEL = _("picons")
    FETCHING_PICONS_TEXT = _("Fetching picons...")
    UPDATE_COMPLETED_TEXT = _("Live-TV update completed")
    PROCESSING_TEXT = _("Processing data...")
    WAITING_FOR_CHANNEL_TEXT = _("Waiting for Channel: ")
    EPGIMPORT_MISSING_TEXT = _("EPGImport plugin not found - please install it to get EPG data for Samsung TV Plus.")

    def __init__(self, silent=False):
        TVDownloadBase.__init__(self, silent)
        self.ignore_list = self._get_ignore_list()

    @staticmethod
    def _get_ignore_list():
        """Load channel IDs to ignore from the ignore file."""
        fpath = os.path.join(DATA_PATH, SAMSUNG_IGNORE)
        ignores = set()
        try:
            with open(fpath, "r", encoding="utf-8") as fd:
                for line in fd:
                    line = line.strip()
                    if not line or not line.startswith("#EXTINF:"):
                        continue
                    match = re.search(r'tvg-id="([^"]+)"', line)
                    if match:
                        ignores.add(match.group(1))
        except FileNotFoundError:
            pass
        return ignores

    def _selectedLocations(self):
        return getselectedregions()

    def _defaultLocation(self):
        return config.plugins.samsungtv.region.value

    def _picons_config(self):
        return config.plugins.samsungtv.picons

    def _configFolder(self):
        return config.plugins.samsungtv.config_folder.value

    def _fetchChannels(self, cc):
        return samsungRequest.getChannels(cc)

    def _bouquetName(self, cc):
        return BOUQUET_NAME % REGION_NAMES.get(cc, cc).upper()

    def _importGuide(self, cc):
        """Import EPG events from the i.mjh.nz XML feed."""
        epg_url = EXT_SAMSUNG_XML % cc
        try:
            import requests
            r = requests.get(epg_url, timeout=30)
            r.raise_for_status()
            xmltv_data = r.content
        except Exception as e:
            logger.error("EPG fetch error for %s: %s", cc, e)
            return

        channels_map = {}
        for cat in self.categories:
            if cat in self.channelsList:
                for ch_sid, _ch_hash, _ch_name, _ch_logourl, _id in self.channelsList[cat]:
                    ref = f"4097:0:1:{ch_sid}:{self.tsid}:1:2:0:0:0"
                    channels_map[_id] = ref
                    channels_map[_id.lower()] = ref

        path = os.path.join(self._configFolder(), self.XMLTV_FILE % cc)
        if not importXMLTVGuide(self.epgcache, "Samsung TV Plus", path, xmltv_data, channels_map):
            self.epgimport_missing = True

    def _buildBouquetEntry(self, key, chitem):
        ch_sid, _ch_hash, ch_name, ch_logourl, _id = self.channelsList[key][chitem]
        stream_url = samsungRequest.buildStreamURL(_id, self.bouquetCC).replace(":", "%3a")
        ref = f"4097:0:1:{ch_sid}:{self.tsid}:1:2:0:0:0"
        return ref, stream_url, ch_name, ch_logourl

    def buildM3U(self, channel):
        logo = channel.get("logo", "")
        group = channel.get("category", "")
        _id = channel["_id"]

        if _id in self.ignore_list:
            return False

        if group not in self.channelsList:
            self.channelsList[group] = []
            self.categories.append(group)

        sid = int(channel["number"])
        if sid <= 0:
            sid = (zlib.crc32(_id.encode("utf-8")) & 0xFFFF) or 1
        while sid in self.usedServiceIds:
            sid = (sid + 1) & 0xFFFF or 1
        self.usedServiceIds.add(sid)
        number = f"{sid:X}"

        self.channelsList[group].append((str(number), _id, channel["name"], logo, _id))
        return True


class SamsungTVDownload(TVDownloadScreenMixin, SamsungTVDownloadBase, Screen):

    EXIT_CONFIRM_TEXT = _("The download is in progress. Exit now?")

    def __init__(self, session):
        self.session = session
        Screen.__init__(self, session)
        self.skinName = "DownloadProgress"
        self.title = _("Samsung TV Plus updating")
        SamsungTVDownloadBase.__init__(self)
        self.total = 0
        self["progress"] = ProgressBar()
        self["action"] = Label()
        self.updateAction()
        self["wait"] = Label()
        self["status"] = Label(_("Please wait..."))
        self["actions"] = ActionMap(["OkCancelActions"], {"cancel": self.exit}, -1)
        self.onFirstExecBegin.append(self.init)

    def updateAction(self, cc=""):
        self["action"].text = _("Updating: Samsung TV Plus %s") % cc.upper()

    def noCategories(self):
        self.session.openWithCallback(self.exitOk, MessageBox, _("There is no data, it is possible that Samsung TV Plus is not available in your region"), type=MessageBox.TYPE_ERROR, timeout=10)

    def _restartSilentTimer(self):
        Silent.stop()
        Silent.start()


class DownloadSilent(TVDownloadSilentMixin, SamsungTVDownloadBase):

    BOUQUET_MARKER = "samsungtv"
    FRIENDLY_NAME = "Samsung TV Plus"
    LOCATION_WORD = "region"

    def __init__(self):
        self.afterUpdate = []
        SamsungTVDownloadBase.__init__(self, silent=True)
        self.timer = eTimer()
        self.timer.timeout.get().append(self.download)


Silent = DownloadSilent()
