# Copyright (C) 2026 by xcentaurix

import os
import re
import time

from Screens.MessageBox import MessageBox
from Tools.Directories import fileExists
from enigma import eDVBDB, eEPGCache
from twisted.internet import threads, reactor

from .PiconFetcher import PiconFetcher


class TVDownloadBase:
    """Shared bouquet/EPG download workflow for FAST-channel TV Cockpit plugins
    (Pluto TV, Rakuten TV, Samsung TV Plus, ...).

    A concrete plugin subclasses this (redeclaring ``downloadActive`` on its own
    class so the flag is shared between that plugin's interactive and silent
    download instances, but independent from other plugins) and provides:

    Required class attributes:
        downloadActive (bool)   -- must be redeclared, not inherited, per plugin
        LOG_PREFIX (str)        -- tag used in internal (untranslated) log prints
        TIMER_FILE (str)        -- from the plugin's own Variables.py
        BOUQUET_FILE (str)      -- from the plugin's own Variables.py
        TSIDS (dict)            -- from the plugin's own Config.py
        SILENT_IN_PROGRESS_TEXT, PICONS_LABEL, FETCHING_PICONS_TEXT,
        UPDATE_COMPLETED_TEXT, PROCESSING_TEXT, WAITING_FOR_CHANNEL_TEXT
                                 -- translated (via the plugin's own `_`) strings
        FINALIZE_DELAY (float)  -- optional pause after writing a bouquet, before
                                    the next country/region starts; defaults to 0
        EPGIMPORT_MISSING_TEXT (str) -- shown once at completion (interactive) or
                                    logged (silent) if a plugin's _importGuide sets
                                    self.epgimport_missing = True; defaults to a
                                    plain, untranslated message - override with a
                                    translated (via the plugin's own `_`) string

    Required hook methods:
        _selectedLocations(self) -> list[str]
        _defaultLocation(self) -> str
        _picons_config(self) -> ConfigElement
        _fetchChannels(self, cc) -> list[dict]
        buildM3U(self, channel)
        _bouquetName(self, cc) -> str
        _buildBouquetEntry(self, key, chitem) -> (ref, stream_url, ch_name, ch_logourl)

    Optional hooks:
        _importGuide(self, cc)   -- called once per country/region before the
                                     per-channel loop; no-op by default
        _clearPluginState(self)  -- called whenever channelsList/categories are
                                     reset; no-op by default
        _afterBouquetWritten(self, cc, bouquet_name, bouquet_file) -- called
                                     once per country/region right after its
                                     bouquet file is written; no-op by default
    """

    downloadActive = False
    FINALIZE_DELAY = 0
    EPGIMPORT_MISSING_TEXT = "EPGImport plugin not installed - no EPG data was imported."

    def __init__(self, silent=False):
        self.channelsList = {}
        self.categories = []
        self.state = 1  # this is a hack
        self.silent = silent
        self.epgcache = eEPGCache.getInstance()
        self.epgimport_missing = False  # set by importXMLTVGuide() callers; persists for the whole
        #                                 run (not reset per-region) so it can be surfaced once at
        #                                 completion instead of only ever appearing in the debug log
        self._setDownloadActive(False)

    # ------------------------------------------------------------------
    # downloadActive is shared between a plugin's interactive and silent
    # download instances, so it must live on the plugin-level base class
    # (whichever ancestor first declares it), not on `type(self)`.
    # ------------------------------------------------------------------

    def _downloadActiveOwner(self):
        for klass in type(self).__mro__:
            if "downloadActive" in klass.__dict__:
                return klass
        return TVDownloadBase

    def _isDownloadActive(self):
        return self._downloadActiveOwner().downloadActive

    def _setDownloadActive(self, value):
        self._downloadActiveOwner().downloadActive = value

    # ------------------------------------------------------------------
    # Optional hooks
    # ------------------------------------------------------------------

    def _importGuide(self, cc):
        pass

    def _clearPluginState(self):
        pass

    def _afterBouquetWritten(self, cc, bouquet_name, bouquet_file):
        pass

    # ------------------------------------------------------------------
    # Workflow
    # ------------------------------------------------------------------

    def cc(self):
        locations = [x for x in self._selectedLocations() if x] or [self._defaultLocation()]
        # Delete bouquets of not selected locations. Don't delete the ones we are updating so they retain their current position.
        eDVBDB.getInstance().removeBouquet(re.escape(self.BOUQUET_FILE) % f"(?!{'|'.join(locations)}).+")
        yield from locations

    def download(self):
        if self._isDownloadActive():
            if not self.silent:
                self.session.openWithCallback(self.close, MessageBox, self.SILENT_IN_PROGRESS_TEXT, MessageBox.TYPE_INFO, timeout=30)
            print(f"[{self.LOG_PREFIX}] A silent download is in progress.")
            return
        if not self.silent:
            # A manual (green-key/menu) update starts from a clean slate so
            # stale picons/channels from a previous config don't linger -
            # the silent timer refresh must not do this, it just updates
            # the existing bouquets/picons in place.
            eDVBDB.getInstance().removeBouquet(re.escape(self.BOUQUET_FILE) % ".*")
            PiconFetcher(self._picons_config()).removeall()
        self.ccGenerator = self.cc()
        self.piconFetcher = PiconFetcher(self._picons_config(), self)
        threads.deferToThread(self._downloadThread)

    def _downloadThread(self):
        """Run the entire download workflow in a background thread."""
        try:
            self._managerThread()
        except Exception as e:
            print(f"[{self.LOG_PREFIX}] Error in download thread: {e}")
            self._setDownloadActive(False)

    def _managerThread(self):
        self._setDownloadActive(True)
        if cc := next(self.ccGenerator, None):
            self._downloadBouquetThread(cc)
        else:
            self.channelsList.clear()
            self.categories.clear()
            self._clearPluginState()
            self._setDownloadActive(False)
            self.ccGenerator = None
            if self.piconFetcher.piconList:
                self.total = len(self.piconFetcher.piconList)
                reactor.callFromThread(self.updateProgressBar, 0)
                reactor.callFromThread(self.updateAction, self.PICONS_LABEL)
                reactor.callFromThread(self.updateStatus, self.FETCHING_PICONS_TEXT)
                self.piconFetcher.fetchPicons()
                reactor.callFromThread(self.updateProgressBar, self.total)
            self.piconFetcher = None
            if self.epgimport_missing:
                # Surfaced once here instead of only as a per-region debug-log
                # print: otherwise bouquets/channels update fine and nothing
                # ever indicates *why* the guide stayed empty.
                reactor.callFromThread(self.updateStatus, self.EPGIMPORT_MISSING_TEXT)
                time.sleep(5)
            reactor.callFromThread(self.updateStatus, self.UPDATE_COMPLETED_TEXT)
            time.sleep(3)
            reactor.callFromThread(self.exitOk)
            reactor.callFromThread(self.start)

    def manager(self):
        """Legacy entry point - redirects to threaded version."""
        threads.deferToThread(self._managerThread)

    def _downloadBouquetThread(self, cc):
        self.bouquet = []
        self.bouquetCC = cc
        self.tsid = self.TSIDS.get(cc, "0")
        self.usedServiceIds = set()
        reactor.callFromThread(self.stop)
        self.channelsList.clear()
        self.categories.clear()
        self._clearPluginState()
        reactor.callFromThread(self.updateAction, cc)
        reactor.callFromThread(self.updateProgressBar, 0)
        reactor.callFromThread(self.updateStatus, self.PROCESSING_TEXT)

        channels = sorted(self._fetchChannels(cc), key=lambda x: x["number"])
        for channel in channels:
            self.buildM3U(channel)

        # Sort categories alphabetically, and channels within each category by name
        self.categories.sort(key=str.casefold)
        for _group, channels_in_group in self.channelsList.items():
            channels_in_group.sort(key=lambda ch: ch[2].casefold())

        self.total = len(channels)

        if len(self.categories) == 0:
            reactor.callFromThread(self.noCategories)
        else:
            if self.categories[0] in self.channelsList:
                self.subtotal = len(self.channelsList[self.categories[0]])
            else:
                self.subtotal = 0
            self.key = 0
            self.chitem = 0

            self._importGuide(cc)

            for i in range(self.total + 1):
                self.updateprogress(param=i)

    def updateprogress(self, param):
        if hasattr(self, "state") and self.state == 1:  # hack for exit before end
            reactor.callFromThread(self.updateProgressBar, param)
            if param < self.total:
                key = self.categories[self.key]
                if self.chitem == self.subtotal:
                    self.chitem = 0
                    found = False
                    while not found:
                        self.key += 1
                        key = self.categories[self.key]
                        found = key in self.channelsList
                    self.subtotal = len(self.channelsList[key])

                if self.chitem == 0:
                    self.bouquet.append(f"1:64:{self.key}:0:0:0:0:0:0:0::{self.categories[self.key]}")

                ref, stream_url, ch_name, ch_logourl = self._buildBouquetEntry(key, self.chitem)
                self.bouquet.append(f"{ref}:{stream_url}:{ch_name}")
                self.chitem += 1
                reactor.callFromThread(self.updateStatus, self.WAITING_FOR_CHANNEL_TEXT + ch_name)

                self.piconFetcher.addPicon(ref, ch_name, ch_logourl, self.silent)
            else:
                bouquet_name = self._bouquetName(self.bouquetCC)
                bouquet_file = self.BOUQUET_FILE % self.bouquetCC
                reactor.callFromThread(eDVBDB.getInstance().addOrUpdateBouquet, bouquet_name, bouquet_file, self.bouquet, False)
                # addOrUpdateBouquet doesn't update #NAME for existing bouquets, so patch the file
                bouquet_path = "/etc/enigma2/" + bouquet_file
                if os.path.isfile(bouquet_path):
                    with open(bouquet_path, "r", encoding="utf-8") as f:
                        lines = f.readlines()
                    if lines and lines[0].startswith("#NAME"):
                        lines[0] = f"#NAME {bouquet_name}\r\n"
                        with open(bouquet_path, "w", encoding="utf-8") as f:
                            f.writelines(lines)
                self._afterBouquetWritten(self.bouquetCC, bouquet_name, bouquet_file)
                os.makedirs(os.path.dirname(self.TIMER_FILE), exist_ok=True)  # create config folder recursive if not exists
                with open(self.TIMER_FILE, "w", encoding="utf-8") as f:
                    f.write(str(time.time()))
                time.sleep(self.FINALIZE_DELAY)  # let the reactor paint 100% before the next phase resets it to 0%
                self._managerThread()

    # ------------------------------------------------------------------
    # No-op defaults, overridden by the interactive Screen and the silent timer
    # ------------------------------------------------------------------

    def start(self):
        pass

    def stop(self):
        pass

    def exitOk(self, answer=None):
        pass

    def updateProgressBar(self, param):
        pass

    def updateStatus(self, name):
        pass

    def updateAction(self, cc=""):
        pass

    def noCategories(self):
        pass


class TVDownloadScreenMixin:
    """Shared UI plumbing for the interactive download-progress Screen.

    The host class (which must also inherit its plugin's TVDownloadBase
    subclass and Screen, in that order) still owns __init__ (skinName, title
    and widget creation need the plugin's own translated strings), and must
    define EXIT_CONFIRM_TEXT plus a _restartSilentTimer() hook.
    """

    def init(self):
        self["progress"].setValue(0)
        threads.deferToThread(self.download)

    def exit(self):
        self.session.openWithCallback(self.cleanup, MessageBox, self.EXIT_CONFIRM_TEXT, MessageBox.TYPE_YESNO, timeout=30)

    def cleanup(self, answer=None):
        if answer:
            self._setDownloadActive(False)
            self.exitOk(answer)

    def exitOk(self, answer=True):
        if answer:
            self._restartSilentTimer()
            self.close(True)

    def updateProgressBar(self, param):
        try:
            progress = min(((param + 1) * 100) // self.total, 100)
        except Exception:
            progress = 0
        self["progress"].setValue(progress)
        self["wait"].text = str(progress) + " %"

    def updateStatus(self, name):
        self["status"].text = name


class TVDownloadSilentMixin:
    """Shared background/silent-timer plumbing for FAST-channel TV Cockpit plugins.

    The host class still owns __init__ (it must call the plugin's
    TVDownloadBase.__init__(self, silent=True) and create self.timer), and
    must define BOUQUET_MARKER, FRIENDLY_NAME and LOCATION_WORD.
    """

    def init(self, session):  # called on session start
        self.session = session
        with open("/etc/enigma2/bouquets.tv", "r", encoding="utf-8") as f:
            bouquets = f.read()
        if self.BOUQUET_MARKER in bouquets:
            self.start(True)

    def start(self, fromSessionStart=False):
        self.stop()
        minutes = 60 * 5
        if fileExists(self.TIMER_FILE):
            with open(self.TIMER_FILE, "r", encoding="utf-8") as f:
                last = float(f.read().strip())
            minutes -= int((time.time() - last) / 60)
            if minutes < 0:
                minutes = 1  # do we want to do this so close to reboot
        self.timer.startLongTimer(minutes * 60)
        if not fromSessionStart:
            self.afterUpdateCallbacks()

    def stop(self):
        self.timer.stop()

    def afterUpdateCallbacks(self):
        for f in self.afterUpdate:
            if callable(f):
                f()

    def noCategories(self):
        print(f"[{self.FRIENDLY_NAME}] There is no data, it is possible that {self.FRIENDLY_NAME} is not available in your {self.LOCATION_WORD}.")
        self.stop()
        os.makedirs(os.path.dirname(self.TIMER_FILE), exist_ok=True)  # create config folder recursive if not exists
        with open(self.TIMER_FILE, "w", encoding="utf-8") as f:
            f.write(str(time.time()))
        self.start()


def importXMLTVGuide(epgcache, log_prefix, tmp_path, xmltv_bytes, channels_map):
    """Import EPG events from an XMLTV byte blob into eEPGCache via EPGImport's
    converter, using a pre-built {channel_id: service_ref} mapping.

    Returns False if the EPGImport plugin itself isn't installed (the import
    was skipped entirely, not just unsuccessful) so callers can surface this
    to the user instead of it only ever showing up as a debug-log print
    nobody reads - this is a hard requirement (there is no fallback path),
    so silently no-op'ing left users with bouquets/channels updating fine
    and no indication at all of why the guide stayed empty. Returns True
    otherwise, regardless of how many events actually matched a channel
    (that part already gets its own "N EPG events imported" print).
    """
    try:
        with open(tmp_path, "wb") as fp:
            fp.write(xmltv_bytes)

        try:
            from Plugins.Extensions.EPGImport.xmltvconverter import XMLTVConverter
        except ImportError:
            print(f"[{log_prefix}] EPGImport not available, skipping EPG import")
            return False

        with open(tmp_path, "rb") as fp:
            xmltv_parser = XMLTVConverter(channels_map, {})
            evt_cnt = 0
            for item in xmltv_parser.enumFile(fp):
                if not item:
                    continue
                sref, event = item
                evt_cnt += 1
                reactor.callFromThread(epgcache.importEvents, sref, [event])
            print(f"[{log_prefix}] {evt_cnt} EPG events imported")
    except Exception as e:
        print(f"[{log_prefix}] EPG import error: {e}")
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
    return True
