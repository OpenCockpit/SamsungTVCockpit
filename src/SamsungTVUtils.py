# Copyright (C) 2026 by xcentaurix

import os
from pickle import load as pickle_load, dump as pickle_dump
from time import time

import requests
from Components.config import config, ConfigSelection
from Components.Harddisk import harddiskmanager
from Tools.Directories import fileExists
from twisted.internet.reactor import callFromThread

from .Variables import RESUMEPOINTS_FILE, USER_AGENT


# --- Data folder management -----------------------------------------------

_data_folder = ""


def getDataFolder():
    return _data_folder


def _getMountChoices():
    choices = []
    for p in harddiskmanager.getMountedPartitions():
        if os.path.exists(p.mountpoint):
            d = os.path.normpath(p.mountpoint)
            if p.mountpoint != "/":
                choices.append((p.mountpoint, d))
    choices.sort()
    return choices


def _getMountDefault(choices):
    choices = {x[1]: x[0] for x in choices}
    return choices.get("/media/hdd") or choices.get("/media/usb") or ""


def _onPartitionChange(*_args, **_kwargs):
    choices = _getMountChoices()
    config.plugins.samsungtv.datalocation.setChoices(choices=choices, default=_getMountDefault(choices))
    updateDataFolder()


def updateDataFolder(*_args, **_kwargs):
    global _data_folder
    _data_folder = ""
    if v := config.plugins.samsungtv.datalocation.value:
        if os.path.exists(v):
            _data_folder = os.path.join(v, "SamsungTV")
            os.makedirs(_data_folder, exist_ok=True)


def initMountChoices():
    choices = _getMountChoices()
    if not choices:
        choices = [("/tmp", "/tmp")]
    config.plugins.samsungtv.datalocation = ConfigSelection(choices=choices, default=_getMountDefault(choices))
    harddiskmanager.on_partition_list_change.append(_onPartitionChange)
    config.plugins.samsungtv.datalocation.addNotifier(updateDataFolder, immediate_feedback=False)


initMountChoices()


# --- Resume points --------------------------------------------------------

class ResumePoints:
    def __init__(self):
        self.resumePointFile = RESUMEPOINTS_FILE
        self.resumePointCache = {}
        self.loadResumePoints()
        self.cleanCache()

    def loadResumePoints(self):
        self.resumePointCache.clear()
        if fileExists(self.resumePointFile):
            with open(self.resumePointFile, "rb") as f:
                self.resumePointCache.update(pickle_load(f, encoding="utf8"))

    def saveResumePoints(self):
        os.makedirs(os.path.dirname(self.resumePointFile), exist_ok=True)
        with open(self.resumePointFile, "wb") as f:
            pickle_dump(self.resumePointCache, f, protocol=5)

    def setResumePoint(self, session, sid):
        service = session.nav.getCurrentService()
        if service and session.nav.getCurrentlyPlayingServiceOrGroup():
            if seek := service.seek():
                pos = seek.getPlayPosition()
                if not pos[0]:
                    lru = int(time())
                    duration = sl[1] if (sl := seek.getLength()) else None
                    position = pos[1]
                    self.resumePointCache[sid] = [lru, position, duration]
                    self.saveResumePoints()

    def getResumePoint(self, sid):
        last = None
        length = 0
        if sid and (entry := self.resumePointCache.get(sid)):
            entry[0] = int(time())
            last = entry[1]
            length = entry[2]
        return last, length

    def cleanCache(self):
        changed = False
        now = int(time())
        for sid, v in list(self.resumePointCache.items()):
            if now > v[0] + 30 * 24 * 60 * 60:
                del self.resumePointCache[sid]
                changed = True
        if changed:
            self.saveResumePoints()


resumePointsInstance = ResumePoints()


# --- Poster downloading ---------------------------------------------------

_poster_session = requests.Session()
_poster_session.headers.update({"User-Agent": USER_AGENT})


def downloadPoster(url, name, callback):
    data_folder = getDataFolder()
    if not name or not data_folder:
        return
    base = os.path.join(data_folder, name)
    # check cache - verify magic bytes match extension
    for ext in ('.png', '.jpg'):
        filename = base + ext
        if fileExists(filename):
            try:
                with open(filename, "rb") as f:
                    header = f.read(2)
                is_png = header == b'\x89P'
                if (ext == '.png') == is_png:
                    callFromThread(callback, filename, name)
                    return
                os.remove(filename)  # stale: wrong format for extension
            except OSError:
                pass
    # download and determine extension from actual file content (CDN content-type can be wrong)
    try:
        response = _poster_session.get(url, timeout=5)
        response.raise_for_status()
        rc = response.content
        if len(rc) > 2:
            ext = '.png' if rc[:2] == b'\x89P' else '.jpg'
            filename = base + ext
            with open(filename, "wb") as f:
                f.write(rc)
            callFromThread(callback, filename, name)
            return
    except requests.exceptions.RequestException:
        pass
    callFromThread(callback, "", name)


# --- Image helper ---------------------------------------------------------

def pickBestImage(imgs):
    """Pick poster and best available image from a covers list."""
    poster = ""
    image = ""
    if len(imgs) > 2:
        image = imgs[2].get("url", "")
    if len(imgs) > 1 and not image:
        image = imgs[1].get("url", "")
    if len(imgs) > 0:
        poster = imgs[0].get("url", "")
    return poster, image
