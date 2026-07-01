# Copyright (C) 2026 by xcentaurix
# Common picon download/management base class shared across FAST channel plugins.
# Each plugin subclasses PiconFetcherBase and supplies its own plugin_name,
# picons_config, plugin_folder, plugin_icon and user_agent.

import concurrent.futures
import os
import shutil
import time
from itertools import count as _count

import requests
from twisted.internet import reactor
from Tools.Directories import fileExists, sanitizeFilename

_PNG_SIG = b'\x89PNG\r\n\x1a\n'
_DEFAULT_USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
_PICON_WIDTH = 220
_PICON_HEIGHT = 132


class PiconFetcherBase:
    def __init__(self, plugin_name, picons_config, plugin_folder, plugin_icon, user_agent=None, parent=None):
        """
        plugin_name    : subfolder name and log tag, e.g. "RakutenTV"
        picons_config  : config element for the picons setting, e.g. config.plugins.rakutentv.picons
        plugin_folder  : absolute path to the plugin's source folder (for the default icon)
        plugin_icon    : filename of the default/fallback icon inside plugin_folder
        user_agent     : HTTP User-Agent header; defaults to a generic browser UA
        parent         : optional parent widget that receives updateProgressBar(counter) callbacks
        """
        self.plugin_name = plugin_name
        self._picons_config = picons_config
        self._plugin_folder = plugin_folder
        self._plugin_icon = plugin_icon
        self._user_agent = user_agent or _DEFAULT_USER_AGENT
        self.parent = parent
        self.piconDir = self.getPiconPath()
        self.pluginPiconDir = os.path.join(self.piconDir, plugin_name)
        self.resolutionStr = f"?h={_PICON_HEIGHT}&w={_PICON_WIDTH}"
        self.piconList = []

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def addPicon(self, ref, name, url, silent):
        """Queue a picon for download.  Call before fetchPicons()."""
        if not self._picons_config.value or not url:
            return
        if self._picons_config.value == "snp" and (ch_name := sanitizeFilename(name.lower())):
            piconname = os.path.join(self.piconDir, ch_name + ".png")
        else:
            piconname = os.path.join(self.piconDir, ref.replace(":", "_") + ".png")
        one_week_ago = time.time() - 60 * 60 * 24 * 7
        if not (fileExists(piconname) and (silent or os.path.getmtime(piconname) > one_week_ago)):
            self.piconList.append((url, piconname))

    def fetchPicons(self):
        """Download all queued picons in a thread pool."""
        _PICON_WORKERS = 10
        _PICON_BATCH_TIMEOUT = 60
        self._counter = _count()
        self.createFolders()
        if self.piconList:
            with concurrent.futures.ThreadPoolExecutor(max_workers=_PICON_WORKERS) as executor:
                futures = {executor.submit(self.downloadURL, url, fn): (url, fn)
                           for url, fn in self.piconList}
                done, _ = concurrent.futures.wait(futures, timeout=_PICON_BATCH_TIMEOUT)
            print(f"[{self.plugin_name} PiconFetcher] fetched {len(done)}/{len(futures)} picons")

    def removeall(self):
        """Remove all symlinks and downloaded picons created by this plugin."""
        if os.path.exists(self.piconDir):
            for f in os.listdir(self.piconDir):
                item = os.path.join(self.piconDir, f)
                if os.path.islink(item) and self.pluginPiconDir in os.readlink(item):
                    os.remove(item)
        if os.path.exists(self.pluginPiconDir):
            shutil.rmtree(self.pluginPiconDir)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def createFolders(self):
        os.makedirs(self.piconDir, exist_ok=True)
        os.makedirs(self.pluginPiconDir, exist_ok=True)
        self.defaultIcon = os.path.join(self.pluginPiconDir, self._plugin_icon)
        shutil.copy(os.path.join(self._plugin_folder, self._plugin_icon), self.defaultIcon)

    def downloadURL(self, url, piconname):
        filepath = os.path.join(self.pluginPiconDir, piconname.removeprefix(self.piconDir).removeprefix(os.sep))
        counter = next(self._counter)
        try:
            dl_url = url if "?" in url else f"{url}{self.resolutionStr}"
            response = requests.get(dl_url, timeout=2.50, headers={"User-Agent": self._user_agent})
            response.raise_for_status()
            content_type = response.headers.get('content-type', '')
            if 'image' in content_type.lower() and len(rc := response.content):
                if rc[:8] == _PNG_SIG:
                    with open(filepath, "wb") as f:
                        f.write(rc)
                else:
                    self._convertToPng(rc, filepath, self.plugin_name)
        except requests.exceptions.RequestException:
            pass
        if not fileExists(filepath):
            filepath = self.defaultIcon
        self.makesoftlink(filepath, piconname)
        if self.parent:
            reactor.callFromThread(self.parent.updateProgressBar, counter)

    @staticmethod
    def _convertToPng(data, filepath, tag="PiconFetcher"):
        """Convert image data of any format to PNG using Pillow."""
        try:
            from PIL import Image
            import io
            with Image.open(io.BytesIO(data)) as img:
                img.save(filepath, "PNG")
        except Exception as e:
            print(f"[{tag} PiconFetcher] image conversion failed: {e}")

    def makesoftlink(self, filepath, softlinkpath):
        svgpath = softlinkpath.removesuffix(".png") + ".svg"
        islink = os.path.islink(softlinkpath)
        # Don't touch a real file (not ours) or skip if an SVG picon already exists.
        if not islink and os.path.isfile(softlinkpath) or os.path.isfile(svgpath):
            return
        if islink:
            if os.readlink(softlinkpath) == filepath:
                return
            os.remove(softlinkpath)
        os.symlink(filepath, softlinkpath)

    @staticmethod
    def getPiconPath():
        _SYSTEM = "/usr/share/enigma2/picon"
        try:
            from Components.Renderer.Picon import lastPiconPath, searchPaths
        except ImportError:
            try:
                from Components.Renderer.Picon import piconLocator
                lastPiconPath = piconLocator.activePiconPath
                searchPaths = piconLocator.searchPaths
            except ImportError:
                lastPiconPath = None
                searchPaths = None
        for p in (searchPaths or []):
            if p != _SYSTEM and os.path.isdir(p) and os.access(p, os.W_OK):
                return p
        return lastPiconPath or _SYSTEM
