# Copyright (C) 2018-2026 by xcentaurix
# License: GNU General Public License v3.0

"""Service references for playing a FAST-channel from the plugin's own browse
screen with the same identity its bouquet entry has.

The bouquet download writes each channel as
    #SERVICE 4097:0:1:<sid>:<tsid>:1:2:0:0:0:<stream url>:<channel name>
and the guide import files the channel's events under the first ten fields
of that reference. Playing a channel under that identity (instead of the
anonymous 4097:0:0:0... reference) is what makes the enigma2 EPG - and with it
session.Event_Now and the CockpitLivePlayer infobar - know the current event.
"""

import os
from urllib.parse import quote

from enigma import eServiceReference

from .Debug import logger

ANONYMOUS_IDENT = "4097:0:0:0:0:0:0:0:0:0"
BOUQUET_DIR = "/etc/enigma2"


def findChannelIdent(bouquet_file, name):
    """Return the first ten fields (the EPG identity) of the bouquet entry
    for the channel called *name*, or None if the bouquet has no such entry."""
    path = os.path.join(BOUQUET_DIR, bouquet_file)
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                if not line.startswith("#SERVICE 4097:"):
                    continue
                parts = line[len("#SERVICE "):].strip().split(":")
                if len(parts) >= 12 and ":".join(parts[11:]) == name:
                    return ":".join(parts[:10])
    except OSError as exc:
        logger.debug("cannot read %s: %s", path, exc)
    return None


def liveReference(bouquet_file, name, url):
    """eServiceReference playing *url* as the bouquet's channel *name*."""
    ident = findChannelIdent(bouquet_file, name)
    if ident is None:
        logger.debug("no bouquet entry for %s in %s - playing without EPG identity", name, bouquet_file)
        ident = ANONYMOUS_IDENT
    return eServiceReference(f"{ident}:{quote(url)}:{quote(name)}")
