# Copyright (C) 2026 by xcentaurix

import requests
from Components.config import config

from .Variables import RESUMEPOINTS_FILE, USER_AGENT
from .Version import PLUGIN
from .CockpitTVUtils import MountedDataFolder, ResumePoints, downloadPoster as _sharedDownloadPoster


# --- Data folder management -----------------------------------------------

_dataFolder = MountedDataFolder(config.plugins.samsungtv, PLUGIN)


def getDataFolder():
    return _dataFolder.get()


# --- Resume points --------------------------------------------------------

resumePointsInstance = ResumePoints(RESUMEPOINTS_FILE)


# --- Poster downloading ---------------------------------------------------

_poster_session = requests.Session()
_poster_session.headers.update({"User-Agent": USER_AGENT})


def downloadPoster(url, name, callback):
    _sharedDownloadPoster(_poster_session, getDataFolder(), url, name, callback)
