# Copyright (C) 2026 by xcentaurix
# License: GNU General Public License v3.0

"""Retries a Samsung TV Plus zap once if gstreamer comes up with no playable tracks.

jmp2.uk occasionally serves a connectable-but-empty response for a channel
(observed as eServiceMP3's "async-done - 0 video, 0 audio, 0 subtitle" in the
debug log - see lib/service/servicemp3.cpp's GST_MESSAGE_ASYNC_DONE handler,
which calls stop() itself when n_video + n_audio <= 0) that a simple re-zap to
the same channel reliably clears. This hooks the same evGstreamerPlayStarted
signal enigma2's own InfoBar uses to know playback has begun
(Screens/InfoBarGenerics.py's __evGstreamerPlayStarted), and if there's still
no video and no audio track at that point, forces one automatic re-zap instead
of leaving a black screen until the user notices and zaps back and forth
themselves.

Track presence must be checked via sVideoType/audioTracks(), NOT
sVideoPID/sAudioPID - eServiceMP3::getInfo() (servicemp3.cpp) has no case for
either PID constant, so both fall through to `default: return resNA` and read
the same regardless of whether tracks exist. sVideoType and audioTracks() are
the fields eServiceMP3 actually populates (confirmed against real usage in
Screens/ServiceInfo.py and Screens/AudioSelection.py).

Scoped to Samsung TV Plus channels only (TSID match against SamsungTVConfig's
own range) - other services, including real DVB tuning, never reach this check.
"""

from enigma import iPlayableService, iServiceInformation

from .SamsungTVConfig import TSIDS
from .Debug import logger

_SAMSUNG_TSIDS = set(TSIDS.values())

_last_retried = None
_registered = False


def _is_samsung_ref(sref):
    parts = sref.toString().split(":")
    return len(parts) > 4 and parts[4] in _SAMSUNG_TSIDS


def _onNavEvent(session, ev):
    global _last_retried
    if ev != iPlayableService.evGstreamerPlayStarted:
        return
    ref = session.nav.getCurrentlyPlayingServiceReference()
    if ref is None or not _is_samsung_ref(ref):
        return
    refstr = ref.toString()
    if refstr == _last_retried:
        _last_retried = None
        return
    service = session.nav.getCurrentService()
    info = service and service.info()
    if info is None:
        return
    has_video = info.getInfo(iServiceInformation.sVideoType) != -1
    audio = service.audioTracks()
    has_audio = bool(audio and audio.getNumberOfTracks() > 0)
    if not has_video and not has_audio:
        logger.debug("PlaybackWatchdog: %s came up with no tracks, retrying once", refstr)
        _last_retried = refstr
        session.nav.playService(ref, forceRestart=True)


def start(session):
    global _registered
    if _registered:
        return
    _registered = True
    session.nav.event.append(lambda ev: _onNavEvent(session, ev))
