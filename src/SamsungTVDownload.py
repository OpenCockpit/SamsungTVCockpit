# Copyright (C) 2026 by xcentaurix
# License: GNU General Public License v3.0

import calendar
import os
import re
import time
import zlib

from Components.ActionMap import ActionMap
from Components.config import config
from Components.Label import Label
from Components.ProgressBar import ProgressBar
from Screens.MessageBox import MessageBox
from Screens.Screen import Screen
from Plugins.SystemPlugins.StreamProxyCockpit.LiveProxyUnmuxed import PROXY_HOST, PROXY_PORT
from enigma import eTimer
from twisted.internet import threads

from . import _
from .ConfigInit import REGION_NAMES, TSIDS, getselectedregions
from .SamsungTVRequest import samsungRequest
from .Variables import TIMER_FILE, NODATA_FILE, BOUQUET_FILE, BOUQUET_NAME, CHANNELLIST_FILE, XMLTV_FILE
from .CockpitTVDownload import TVDownloadBase, TVDownloadScreenMixin, TVDownloadSilentMixin, importXMLTVGuide, FAIL_GEO, FAIL_NETWORK, FAIL_NOSTREAM
from .M3UPlaylist import writeM3UPlaylist
from .Debug import logger


# Data paths for ignore/replace lists
DATA_PATH = os.path.join(os.path.dirname(os.path.realpath(__file__)), "data")
SAMSUNG_IGNORE = "samsungtvplus.ignore"


SAMSUNG_REPLACE = "samsungtvplus.replace"

# External EPG XML source
EXT_SAMSUNG_XML = "https://i.mjh.nz/SamsungTVPlus/%s.xml"

# i.mjh.nz only ever publishes the rest of the current day (UTC): the guide it holds shrinks through the day and
# is longer again once the file of the next day is published. Refresh just the EPG on its own, faster cadence than
# the 5h full bouquet-rebuild cycle so events don't run dry between full rebuilds; and when the guide that was
# fetched runs out within EPG_LOW_HOURS, look for the new file every EPG_REFRESH_LOW_MINUTES.
EPG_REFRESH_MINUTES = 90
EPG_REFRESH_LOW_MINUTES = 30
EPG_LOW_HOURS = 3


class SamsungTVDownloadBase(TVDownloadBase):
    downloadActive = False
    guideEnds = {}   # region -> time (epoch) the guide fetched last for it ends

    TIMER_FILE = TIMER_FILE
    NODATA_FILE = NODATA_FILE
    BOUQUET_FILE = BOUQUET_FILE
    CHANNELLIST_FILE = CHANNELLIST_FILE
    XMLTV_FILE = XMLTV_FILE
    TSIDS = TSIDS

    FINALIZE_DELAY = 3  # let the reactor paint 100% before the next region resets it to 0%
    SILENT_IN_PROGRESS_TEXT = _("A silent download is in progress.")
    PICONS_LABEL = _("picons")
    FETCHING_PICONS_TEXT = _("Fetching picons...")
    UPDATE_COMPLETED_TEXT = _("Live-TV update completed")
    PROCESSING_TEXT = _("Processing data...")
    WAITING_FOR_CHANNEL_TEXT = _("Waiting for Channel: ")
    EPGIMPORT_MISSING_TEXT = _("EPGImport plugin not found - please install it to get EPG data for Samsung TV Plus.")

    def __init__(self, silent=False, locations=None):
        TVDownloadBase.__init__(self, silent, locations)
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

    def _proxyEnabled(self):
        """True if the bouquet gets the lazy addresses StreamProxyCockpit resolves (setting "Stream proxy"), False for
        the addresses of the streams themselves."""
        return config.plugins.samsungtv.stream_proxy.value

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

    def _fetchFailure(self, cc):
        return samsungRequest.failure("json")   # one file for all regions

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

        # Build channel ref mapping for EPG import
        channels_map = {}
        for cat in self.categories:
            if cat in self.channelsList:
                for ch_sid, _ch_hash, _ch_name, _ch_logourl, _id in self.channelsList[cat]:
                    ref = f"4097:0:1:{ch_sid}:{self.tsid}:1:2:0:0:0"
                    channels_map[_id] = ref
                    channels_map[_id.lower()] = ref

        self.guideEnds[cc] = self._latestStop(xmltv_data)
        path = os.path.join(self._configFolder(), self.XMLTV_FILE % cc)
        if not importXMLTVGuide(self.epgcache, "Samsung TV Plus", path, xmltv_data, channels_map):
            self.epgimport_missing = True

    @staticmethod
    def _latestStop(xmltv_data):
        """The time (epoch) the last programme of the guide ends, 0 if there is none. The feed's times are UTC."""
        stops = re.findall(rb'stop="(\d{14})', xmltv_data)
        return calendar.timegm(time.strptime(max(stops).decode(), "%Y%m%d%H%M%S")) if stops else 0

    @classmethod
    def epgRefreshSeconds(cls):
        """The time to the next guide refresh: shorter while the guide of any region is about to run out."""
        now = time.time()
        low = any(end - now < EPG_LOW_HOURS * 3600 for end in cls.guideEnds.values())
        return (EPG_REFRESH_LOW_MINUTES if low else EPG_REFRESH_MINUTES) * 60

    def _refreshEpgOnly(self, cc):
        """Re-fetch and re-import EPG for *cc* without touching channels/picons/bouquet.

        Rebuilds channelsList/categories/usedServiceIds first purely so
        _importGuide's channels_map lines up with the live bouquet - SID
        allocation in buildM3U is deterministic from the channel list, so this
        reproduces the same SIDs the last full update wrote. Nothing gets
        written to eDVBDB or the picon folder here.
        """
        self.tsid = self.TSIDS.get(cc, "0")
        self.usedServiceIds = set()
        self.channelsList.clear()
        self.categories.clear()
        for channel in sorted(self._fetchChannels(cc), key=lambda x: x["number"]):
            self.buildM3U(channel)
        self._importGuide(cc)

    def _buildBouquetEntry(self, key, chitem):
        ch_sid, _ch_hash, ch_name, ch_logourl, _id = self.channelsList[key][chitem]
        if self.bouquetProxy:
            # lazy address, resolved by StreamProxyCockpit when the channel is played or recorded (see SamsungTVRequest)
            stream_url = samsungRequest.SAMSUNG_SCHEMA + _id
        else:
            # nothing resolves a lazy address without the stream proxy: the address of the stream itself, as before
            stream_url = samsungRequest.buildStreamURL(_id).replace(":", "%3a")
        ref = f"4097:0:1:{ch_sid}:{self.tsid}:1:2:0:0:0"
        return ref, stream_url, ch_name, ch_logourl

    def _afterBouquetWritten(self, cc, bouquet_name):
        if not self.bouquetProxy:
            super()._afterBouquetWritten(cc, bouquet_name)   # the playlist of the real stream addresses
            return
        # The bouquet's own samsungtv:// addresses only mean something to Enigma2 (see _buildBouquetEntry), so the
        # exported playlist points to the stream proxy instead (only reachable from this box itself).
        entries = {
            group: [(chid, name, logo, f"http://{PROXY_HOST}:{PROXY_PORT}/auto/{chid}.m3u8")
                    for _sid, chid, name, logo, _id in self.channelsList.get(group, [])]
            for group in self.categories
        }
        writeM3UPlaylist(os.path.join(self._configFolder(), self.CHANNELLIST_FILE % cc), bouquet_name, self.categories, entries)

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

    def __init__(self, session, locations=None):
        self.session = session
        Screen.__init__(self, session)
        self.skinName = "PRSDownloadProgress"
        self.title = _("Samsung TV Plus updating")
        SamsungTVDownloadBase.__init__(self, locations=locations)
        self.total = 0
        self["progress"] = ProgressBar()
        self["action"] = Label()
        self.updateAction()
        self["status"] = Label(_("Please wait..."))
        self["actions"] = ActionMap(["OkCancelActions"], {"cancel": self.exit}, -1)
        self.onFirstExecBegin.append(self.init)

    def updateAction(self, cc=""):
        self["action"].text = _("Updating: Samsung TV Plus %s") % cc.upper()

    def noCategories(self, cc="", reason=None, detail=None):
        # Informational only - the download continues with the next selected
        # location, so this must not close the screen (openWithCallback would).
        name = REGION_NAMES.get(cc, cc)
        if reason == FAIL_GEO:
            text = _("Samsung TV Plus refused the request for %s (HTTP %s). It may be geo-blocked.") % (name, detail)
        elif reason == FAIL_NETWORK:
            text = _("Samsung TV Plus could not be reached for %s%s. Try again later.") % (name, f" (HTTP {detail})" if detail else "")
        elif reason == FAIL_NOSTREAM:
            text = _("Samsung TV Plus lists channels for %s, but no stream address could be resolved for any of them. The streams may be geo-blocked or unavailable.") % name
        else:
            text = _("Samsung TV Plus has no channels for %s. It may not be available in your region.") % name
        self.session.open(MessageBox, text, type=MessageBox.TYPE_ERROR, timeout=10)

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
        self.epgTimer = eTimer()
        self.epgTimer.timeout.get().append(self.epgRefresh)

    def start(self, fromSessionStart=False):
        TVDownloadSilentMixin.start(self, fromSessionStart)
        self.epgTimer.startLongTimer(EPG_REFRESH_MINUTES * 60)

    def stop(self):
        TVDownloadSilentMixin.stop(self)
        self.epgTimer.stop()

    def epgRefresh(self):
        self.epgTimer.startLongTimer(self.epgRefreshSeconds())
        if not self._isDownloadActive():
            threads.deferToThread(self._epgRefreshThread)

    def _epgRefreshThread(self):
        if self._isDownloadActive():
            return  # a full update won the race - it refreshes EPG too, nothing more to do
        self._setDownloadActive(True)
        try:
            locations = [x for x in self._selectedLocations() if x] or [self._defaultLocation()]
            for cc in locations:
                self._refreshEpgOnly(cc)
        finally:
            self._setDownloadActive(False)


Silent = DownloadSilent()
