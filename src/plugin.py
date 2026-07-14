# Copyright (C) 2026 by xcentaurix

from Plugins.Plugin import PluginDescriptor
from twisted.internet import threads
from skin import findSkinScreen

from . import _
from .SamsungTVRequest import samsungRequest
from .SamsungTVDownload import SamsungTVDownload, Silent
from .SamsungTVCockpit import SamsungTVCockpit
from .Variables import PLUGIN_ICON
from .SkinUtils import loadPluginSkin
from .Version import VERSION
from .Debug import logger


if findSkinScreen("SamsungTVCockpit") is None:
    loadPluginSkin()


def sessionstart(reason, session, **_kwargs):  # pylint: disable=unused-argument
    logger.info("+++ Version: %s starts...", VERSION)
    Silent.init(session)
    threads.deferToThread(samsungRequest._getChannelsJson)


def Download_SamsungTV(session, **_kwargs):
    session.open(SamsungTVDownload)


def system(session, **_kwargs):
    session.open(SamsungTVCockpit)


def Plugins(**_kwargs):
    return [
        PluginDescriptor(
            name=_("SamsungTVCockpit"),
            where=PluginDescriptor.WHERE_PLUGINMENU,
            icon=PLUGIN_ICON,
            description=_("Browse channels, EPG, and on-demand content from Samsung TV Plus"),
            fnc=system,
            needsRestart=True
        ),
        PluginDescriptor(
            name=_("Download Samsung TV Plus bouquet, picons and EPG"),
            where=PluginDescriptor.WHERE_EXTENSIONSMENU,
            fnc=Download_SamsungTV,
            needsRestart=True
        ),
        PluginDescriptor(
            name=_("Silently download Samsung TV Plus"),
            where=PluginDescriptor.WHERE_SESSIONSTART,
            fnc=sessionstart
        ),
    ]
