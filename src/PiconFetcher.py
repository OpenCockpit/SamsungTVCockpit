# Copyright (C) 2026 by xcentaurix
# Picon management for Samsung TV Plus

import os
import shutil
import threading
import time

from Components.config import config
from Tools.Directories import fileExists, sanitizeFilename
import requests
from twisted.internet import threads

from .Variables import PLUGIN_FOLDER, PLUGIN_ICON, USER_AGENT


class PiconFetcher:
    def __init__(self, parent=None):
        self.parent = parent
        self.piconDir = self.getPiconPath()
        self.pluginPiconDir = os.path.join(self.piconDir, "SamsungTV")
        piconWidth = 220
        piconHeight = 132
        self.resolutionStr = f"?h={piconHeight}&w={piconWidth}"
        self.piconList = []

    def createFolders(self):
        os.makedirs(self.piconDir, exist_ok=True)
        os.makedirs(self.pluginPiconDir, exist_ok=True)
        self.defaultIcon = os.path.join(self.pluginPiconDir, PLUGIN_ICON)
        shutil.copy(os.path.join(PLUGIN_FOLDER, PLUGIN_ICON), self.defaultIcon)

    def addPicon(self, ref, name, url, silent):
        if not config.plugins.samsungtv.picons.value:
            return
        piconname = os.path.join(self.piconDir, ch_name + ".png") if config.plugins.samsungtv.picons.value == "snp" and (ch_name := sanitizeFilename(name.lower())) else os.path.join(self.piconDir, ref.replace(":", "_") + ".png")
        one_week_ago = time.time() - 60 * 60 * 24 * 7
        if not (fileExists(piconname) and (silent or os.path.getmtime(piconname) > one_week_ago)):
            self.piconList.append((url, piconname))

    def fetchPicons(self):
        maxthreads = 100
        self.counter = 0
        failed = []
        self.createFolders()
        if self.piconList:
            picon_threads = [threading.Thread(target=self.downloadURL, args=(url, filename)) for url, filename in self.piconList]
            for thread in picon_threads:
                while threading.active_count() > maxthreads:
                    time.sleep(1)
                try:
                    thread.start()
                except RuntimeError:
                    failed.append(thread)
            for thread in picon_threads:
                if thread not in failed:
                    thread.join()
            print("[SamsungTV PiconFetcher] all fetched")

    def downloadURL(self, url, piconname):
        filepath = os.path.join(self.pluginPiconDir, piconname.removeprefix(self.piconDir).removeprefix(os.sep))
        self.counter += 1
        try:
            # Samsung logos may not support resize params, try direct download
            dl_url = url if "?" in url else f"{url}{self.resolutionStr}"
            response = requests.get(dl_url, timeout=2.50, headers={"User-Agent": USER_AGENT})
            response.raise_for_status()
            content_type = response.headers.get('content-type', '')
            if 'image' in content_type.lower() and len(rc := response.content):
                with open(filepath, "wb") as f:
                    f.write(rc)
        except requests.exceptions.RequestException:
            pass
        if not fileExists(filepath):
            filepath = self.defaultIcon
        self.makesoftlink(filepath, piconname)
        if self.parent:
            threads.deferToThread(self.parent.updateProgressBar, self.counter)

    def makesoftlink(self, filepath, softlinkpath):
        svgpath = softlinkpath.removesuffix(".png") + ".svg"
        islink = os.path.islink(softlinkpath)
        if not islink and os.path.isfile(softlinkpath) or os.path.isfile(svgpath):
            return
        if islink:
            if os.readlink(softlinkpath) == filepath:
                return
            os.remove(softlinkpath)
        os.symlink(filepath, softlinkpath)

    def removeall(self):
        if os.path.exists(self.piconDir):
            for f in os.listdir(self.piconDir):
                item = os.path.join(self.piconDir, f)
                if os.path.islink(item) and self.pluginPiconDir in os.readlink(item):
                    os.remove(item)
        if os.path.exists(self.pluginPiconDir):
            shutil.rmtree(self.pluginPiconDir)

    @staticmethod
    def getPiconPath():
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
        if searchPaths and len(searchPaths) == 1:
            return searchPaths[0]
        return lastPiconPath or "/picon"
