# Copyright (C) 2026 by xcentaurix

import os
import re
from time import strftime, gmtime, localtime
from urllib.parse import quote

from Components.ActionMap import ActionMap, HelpableActionMap
from Components.config import config
from Components.Label import Label
from Components.MenuList import MenuList
from Components.MultiContent import MultiContentEntryText, MultiContentEntryPixmapAlphaBlend
from Components.Pixmap import Pixmap
from Components.ScrollLabel import ScrollLabel
from Components.ServiceEventTracker import ServiceEventTracker
from Components.Sources.StaticText import StaticText
from Plugins.Plugin import PluginDescriptor
from Screens.HelpMenu import HelpableScreen
from Screens.InfoBar import MoviePlayer
from Screens.MessageBox import MessageBox
from Screens.Screen import Screen
from Screens.Setup import Setup
from Tools.Directories import fileExists, isPluginInstalled, resolveFilename, SCOPE_CURRENT_SKIN
from Tools.LoadPixmap import LoadPixmap
from Tools import Notifications
from twisted.internet import threads

from enigma import BT_KEEP_ASPECT_RATIO, BT_SCALE, BT_HALIGN_CENTER, BT_VALIGN_CENTER, eListboxPythonMultiContent, eServiceReference, eTimer, gFont, iPlayableService
from skin import applySkinFactor, findSkinScreen, fonts, parameters

from . import _
from .SamsungTVConfig import getselectedregions, NUMBER_OF_LIVETV_BOUQUETS
from .SamsungTVRequest import samsungRequest
from .SamsungTVDownload import SamsungTVDownload, Silent
from .PiconFetcher import PiconFetcher
from .SamsungTVUtils import resumePointsInstance, downloadPoster
from .Variables import TIMER_FILE, BOUQUET_FILE, PLUGIN_ICON
from .SkinUtils import loadPluginSkin


if findSkinScreen("SamsungTV") is None:
    loadPluginSkin()


class SamsungList(MenuList):
    def __init__(self, entries):
        self.menu_png = LoadPixmap(x if fileExists(x := resolveFilename(SCOPE_CURRENT_SKIN, "icons/samsung_menu.png")) else "/usr/lib/enigma2/python/Plugins/Extensions/SamsungTV/skin/images/menu.png") if fileExists("/usr/lib/enigma2/python/Plugins/Extensions/SamsungTV/skin/images/menu.png") else None

        MenuList.__init__(self, entries, content=eListboxPythonMultiContent)
        font = fonts.get("SamsungList", applySkinFactor("Regular", 19, 35))
        self.l.setFont(0, gFont(font[0], font[1]))
        self.l.setItemHeight(font[2])

    def listentry(self, name, data, _id, epid=0):
        res = [(name, data, _id, epid)]

        png = self.menu_png
        res.append(MultiContentEntryText(pos=applySkinFactor(45, 7), size=applySkinFactor(533, 35), font=0, text=name))
        if png:
            res.append(MultiContentEntryPixmapAlphaBlend(pos=applySkinFactor(7, 9), size=applySkinFactor(20, 20), png=png, flags=BT_SCALE | BT_KEEP_ASPECT_RATIO))
        return res


class SamsungTV(Screen, HelpableScreen):

    def __init__(self, session):
        self.session = session
        Screen.__init__(self, session)
        self.skinName = "SamsungTV"
        HelpableScreen.__init__(self)

        self.colors = parameters.get("SamsungTvColors", [])

        self.titlemenu = _("Channel Categories")
        self["feedlist"] = SamsungList([])
        self["playlist"] = StaticText(self.titlemenu)
        self["loading"] = Label(_("Loading data... Please wait"))
        self["vtitle"] = StaticText()
        self["key_red"] = StaticText(_("Exit"))
        self["key_yellow"] = StaticText()
        self.mdb = isPluginInstalled("tmdb") and "tmdb" or isPluginInstalled("IMDb") and "imdb"
        self.yellowLabel = _("TMDb Search") if self.mdb == "tmdb" else (_("IMDb Search") if self.mdb else "")
        self["key_green"] = StaticText()
        self["updated"] = StaticText()
        self["key_menu"] = StaticText(_("MENU"))
        self["poster"] = Pixmap()
        self["posterBG"] = Label()
        self["info"] = ScrollLabel()

        self["feedlist"].onSelectionChanged.append(self.update_data)

        self.picname = ""

        self["actions"] = HelpableActionMap(
            self, ["SetupActions", "InfobarChannelSelection", "MenuActions"],
            {
                "ok": (self.action, _("Go forward one level including starting playback")),
                "cancel": (self.exit, _("Go back one level including exiting")),
                "save": (self.green, _("Create or update Samsung TV Plus live bouquets")),
                "historyBack": (self.back, _("Go back one level")),
                "menu": (self.loadSetup, _("Open the plugin configuration screen")),
            }, -1
        )

        self["MDBActions"] = HelpableActionMap(
            self, ["ColorActions"],
            {
                "yellow": (self.MDB, _("Search for information in %s") % (_("The Movie Database") if self.mdb == "tmdb" else _("the Internet Movie Database"))),
            }, -1
        )
        self["MDBActions"].setEnabled(False)

        self["InfoNavigationActions"] = HelpableActionMap(
            self, ["NavigationActions"],
            {
                "pageUp": (self["info"].pageUp, _("Scroll the information field")),
                "pageDown": (self["info"].pageDown, _("Scroll the information field")),
            }, -1
        )

        self.updatebutton()

        if self.updatebutton not in Silent.afterUpdate:
            Silent.afterUpdate.append(self.updatebutton)

        self.updateDataTimer = eTimer()
        self.updateDataTimer.callback.append(self._do_update_data)
        self.initialise()
        self.onLayoutFinish.append(self.getCategories)

    def initialise(self):
        self.region = config.plugins.samsungtv.region.value
        self.films = []
        self.menu = []
        self.history = []
        self.vinfo = ""
        self.description = ""
        self["feedlist"].setList([])
        self["poster"].hide()
        self["posterBG"].hide()
        self["info"].setText("")
        self["vtitle"].setText("")
        self["loading"].show()
        self.title = _("Samsung TV Plus") + " - " + self.titlemenu

    def update_data(self):
        self.updateDataTimer.stop()
        if not (selection := self.getSelection()):
            return
        _index, _name, __type, _id = selection
        self["MDBActions"].setEnabled(False)
        self["key_yellow"].text = ""
        if __type == "menu":
            self["poster"].hide()
            self["posterBG"].hide()
            self.updateInfo()
        else:
            self.updateDataTimer.start(500, 1)

    def _do_update_data(self):
        if not (selection := self.getSelection()):
            return
        index, _name, __type, _id = selection
        if __type in {"movie", "channel"}:
            film = self.films[index]
            self.description = film[2]
            self["vtitle"].text = film[1]
            info = ""
            if film[3]:
                info += film[3] + "       "
            if film[4]:
                info += film[4] + "       "
            self["MDBActions"].setEnabled(True)
            self["key_yellow"].text = self.yellowLabel

            if film[5]:
                info += strftime("%Hh %Mm", gmtime(int(film[5])))
            self.vinfo = info
            self.updateInfo()
            picname = film[0]
            self.picname = picname
            pic = film[6]
            if pic and len(picname) > 5:
                self["poster"].hide()
                self["posterBG"].hide()
                threads.deferToThread(downloadPoster, pic, picname, self.downloadPostersCallback)

    def updateInfo(self):
        spacer = "\n" if self.vinfo or self.description else ""
        self["info"].setText("\n".join([x for x in (self.vinfo, self.description, spacer) if x]))

    def downloadPostersCallback(self, filename, name):
        if name == self.picname:
            self.showPoster(filename, name)

    def showPoster(self, filename, name):
        try:
            if name == self.picname and filename and os.path.isfile(filename):
                self["poster"].instance.setPixmapScale(BT_SCALE | BT_KEEP_ASPECT_RATIO | BT_HALIGN_CENTER | BT_VALIGN_CENTER)
                self["poster"].instance.setPixmap(LoadPixmap(filename))
                self["poster"].show()
                self["posterBG"].show()
        except Exception as ex:
            print("[SamsungTV] showPoster, ERROR", ex)

    def getCategories(self):
        self.lvod = {}
        threads.deferToThread(samsungRequest.getVODCategories, self.region).addCallback(self.getCategoriesCallback)

    def getCategoriesCallback(self, categories):
        if not categories:
            self.session.open(MessageBox, _("There is no data, it is possible that Samsung TV Plus is not available in your region"), type=MessageBox.TYPE_ERROR, timeout=10)
        else:
            for category in categories:
                self.buildlist(category)
            self.menu.sort(key=lambda x: x.casefold())
            for _key, items in self.lvod.items():
                items.sort(key=lambda x: x[1].casefold())
            entries = []
            for key in self.menu:
                entries.append(self["feedlist"].listentry(key, "menu", ""))
            self["feedlist"].setList(entries)
        self["loading"].hide()

    def buildlist(self, category):
        name = category["name"]
        self.lvod[name] = []
        self.menu.append(name)
        items = category.get("items", [])
        for item in items:
            itemid = item.get("_id", "")
            if not itemid:
                continue
            itemname = item.get("name", "")
            itemsummary = item.get("summary", "")
            itemgenre = item.get("genre", "")
            itemrating = item.get("rating", "")
            itemduration = int(item.get("duration", 0) or 0)
            itemtype = item.get("type", "channel")
            stream_url = item.get("stream_url", "")

            itemposter = item.get("logo", "")
            itemimage = itemposter
            self.lvod[name].append((itemid, itemname, itemsummary, itemgenre, itemrating, itemduration, itemposter, itemimage, itemtype, stream_url))

    def getSelection(self):
        index = self["feedlist"].getSelectionIndex()
        if current := self["feedlist"].getCurrent():
            data = current[0]
            return index, data[0], data[1], data[2]
        return None

    def action(self):
        if not (selection := self.getSelection()):
            return
        self.lastAction = self.action
        index, name, __type, _id = selection
        menu = []
        menuact = self.titlemenu
        if __type == "menu":
            self.films = self.lvod[self.menu[index]]
            for x in self.films:
                sname = x[1]
                stype = x[8]
                sid = x[0]
                menu.append(self["feedlist"].listentry(sname, stype, sid))
            self["feedlist"].moveToIndex(0)
            self["feedlist"].setList(menu)
            self.titlemenu = name
            self["playlist"].text = self.titlemenu
            self.title = _("Samsung TV Plus") + " - " + self.titlemenu
            self.history.append((index, menuact))
        elif __type in {"movie", "channel"}:
            film = self.films[index]
            sid = film[0]
            name = film[1]
            url = film[9]
            self.playStream(name, sid, url)

    def back(self):
        if not (selection := self.getSelection()):
            return
        self.lastAction = self.back
        _index, _name, __type, _id = selection
        menu = []
        if self.history:
            hist = self.history[-1][0]
            histname = self.history[-1][1]
            if __type in {"movie", "channel"}:
                for key in self.menu:
                    menu.append(self["feedlist"].listentry(key, "menu", ""))
                self["vtitle"].text = ""
                self.vinfo = ""
                self.description = ""
            self["feedlist"].setList(menu)
            self.history.pop()
            self["feedlist"].moveToIndex(hist)
            self.titlemenu = histname
            self["playlist"].text = self.titlemenu
            self.title = _("Samsung TV Plus") + " - " + self.titlemenu
            if not self.history:
                self["poster"].hide()

    def playStream(self, name, sid, url=None):
        if url and name:
            string = f"4097:0:0:0:0:0:0:0:0:0:{quote(url)}:{quote(name)}"
            reference = eServiceReference(string)
            if "m3u8" in url.lower() or "jmp2" in url.lower() or "127.0.0.1" in url:
                self.session.open(Samsung_Player, service=reference, sid=sid)

    def green(self):
        self.session.openWithCallback(self.endupdateLive, SamsungTVDownload)

    def endupdateLive(self, _ret=None):
        self.session.openWithCallback(self.updatebutton, MessageBox, _("The Samsung TV Plus bouquets in your channel list have been updated.\n\nThey will now be rebuilt automatically every 5 hours."), type=MessageBox.TYPE_INFO, timeout=10)

    def updatebutton(self, _ret=None):
        with open("/etc/enigma2/bouquets.tv", "r", encoding="utf-8") as f:
            bouquets = f.read()
        if fileExists(TIMER_FILE) and all(((BOUQUET_FILE % cc) in bouquets) for cc in [x for x in getselectedregions() if x]):
            with open(TIMER_FILE, "r", encoding="utf-8") as f:
                last = float(f.read().replace("\n", "").replace("\r", ""))
            updated = strftime(" %x %H:%M", localtime(int(last)))
            self["key_green"].text = _("Update LiveTV Bouquet")
            self["updated"].text = _("LiveTV Bouquet last updated:") + updated
        elif "samsungtv" in bouquets:
            self["key_green"].text = _("Update LiveTV Bouquet")
            self["updated"].text = _("LiveTV Bouquet needs updating. Press GREEN.")
        else:
            self["key_green"].text = _("Create LiveTV Bouquet")
            self["updated"].text = ""

    def exit(self, *_args, **_kwargs):
        if self.history:
            self.back()
        else:
            self.close()

    def MDB(self):
        if not (selection := self.getSelection()):
            return
        _index, name, __type, _id = selection
        if __type in {"movie", "channel"} and self.mdb:
            if self.mdb == "tmdb":
                from Plugins.Extensions.tmdb.tmdb import tmdbScreen
                self.session.open(tmdbScreen, name, 2)
            else:
                from Plugins.Extensions.IMDb.plugin import IMDB
                self.session.open(IMDB, name, False)

    def loadSetup(self):
        def loadSetupCallback(_result=None):
            if config.plugins.samsungtv.region.value != self.region:
                self.initialise()
                self.getCategories()
        self.session.openWithCallback(loadSetupCallback, SamsungSetup)

    def close(self, *_args, **_kwargs):
        if self.updatebutton in Silent.afterUpdate:
            Silent.afterUpdate.remove(self.updatebutton)
        Screen.close(self)


class SamsungSetup(Setup):
    def __init__(self, session):
        Setup.__init__(self, session, setup=None)
        if "key_yellow" not in self:
            self["key_yellow"] = StaticText()
            self["key_yellowActions"] = HelpableActionMap(self, ["ColorActions"], {
                "yellow": (self.yellow, _("Remove picons")),
            }, prio=1, description=_("Samsung TV Plus Setup Actions"))
        if "key_blue" not in self:
            self["key_blue"] = StaticText()
            self["key_blueActions"] = HelpableActionMap(self, ["ColorActions"], {
                "blue": (self.blue, _("Remove LiveTV Bouquet")),
            }, prio=1, description=_("Samsung TV Plus Setup Actions"))
        self.updateYellowButton()
        self.updateBlueButton()
        self.setTitle(_("Samsung TV Plus Setup"))

    def createSetup(self):
        configList = []
        configList.append((_("Region"), config.plugins.samsungtv.region, _("Select the region for the channel list.")))
        configList.append(("---",))
        for n in range(1, NUMBER_OF_LIVETV_BOUQUETS + 1):
            if n == 1 or getattr(config.plugins.samsungtv, "live_tv_region" + str(n - 1)).value:
                configList.append((_("LiveTV bouquet %s") % n, getattr(config.plugins.samsungtv, "live_tv_region" + str(n)), _("Region for which LiveTV bouquet %s will be created.") % n))
        configList.append(("---",))
        configList.append((_("Picon type"), config.plugins.samsungtv.picons, _("Using service name picons means they will continue to work even if the service reference changes.")))
        configList.append((_("Data location"), config.plugins.samsungtv.datalocation, _("Used for storing video cover graphics, etc.")))
        self["config"].list = configList

    def updateYellowButton(self):
        if os.path.isdir(PiconFetcher().pluginPiconDir):
            self["key_yellow"].text = _("Remove picons")
        else:
            self["key_yellow"].text = ""

    def updateBlueButton(self):
        with open("/etc/enigma2/bouquets.tv", "r", encoding="utf-8") as f:
            bouquets = f.read()
        if "samsungtv" in bouquets:
            self["key_blue"].text = _("Remove LiveTV Bouquet")
        else:
            self["key_blue"].text = ""

    def yellow(self):
        if self["key_yellow"].text:
            PiconFetcher().removeall()
            self.updateYellowButton()

    def blue(self):
        if self["key_blue"].text:
            Silent.stop()
            from enigma import eDVBDB
            eDVBDB.getInstance().removeBouquet(re.escape(BOUQUET_FILE) % ".*")
            self.updateBlueButton()


class Samsung_Player(MoviePlayer):

    ENABLE_RESUME_SUPPORT = False

    def __init__(self, session, service, sid):
        self.session = session
        self.mpservice = service
        self.id = sid
        MoviePlayer.__init__(self, self.session, service, sid)
        self.end = False
        self.started = False
        self.skinName = ["MoviePlayer"]

        self._event_tracker = ServiceEventTracker(
            screen=self,
            eventmap={
                iPlayableService.evStart: self.__serviceStarted,
                iPlayableService.evEOF: self.__evEOF,
            }
        )

        self["actions"] = ActionMap(
            ["MoviePlayerActions", "OkActions"],
            {
                "leavePlayerOnExit": self.leavePlayer,
                "leavePlayer": self.leavePlayer,
                "ok": self.toggleShow,
            }, -3
        )
        self.session.nav.playService(self.mpservice)

    def up(self):
        pass

    def down(self):
        pass

    def doEofInternal(self, _playing):
        self.close()

    def __evEOF(self):
        self.end = True

    def __serviceStarted(self):
        service = self.session.nav.getCurrentService()
        seekable = service.seek()
        self.started = True
        last, length = resumePointsInstance.getResumePoint(self.id)
        if last is None or seekable is None:
            return
        length = seekable.getLength() or (None, 0)
        if (last > 900000) and (not length[1] or (last < length[1] - 900000)):
            self.last = last
            last /= 90000
            Notifications.AddNotificationWithCallback(self.playLastCB, MessageBox, _("Do you want to resume this playback?") + "\n" + (_("Resume position at %s") % f"{int(last / 3600)}:{int(last % 3600 / 60):02d}:{int(last % 60):02d}"), timeout=10, default="yes" in config.usage.on_movie_start.value)

    def playLastCB(self, answer):
        if answer is True and self.last:
            self.doSeek(self.last)
        self.hideAfterResume()

    def leavePlayer(self):
        self.is_closing = True
        resumePointsInstance.setResumePoint(self.session, self.id)
        self.close()

    def leavePlayerConfirmed(self, answer):
        pass


def sessionstart(reason, session, **_kwargs):  # pylint: disable=unused-argument
    Silent.init(session)
    threads.deferToThread(samsungRequest._getChannelsJson)


def Download_SamsungTV(session, **_kwargs):
    session.open(SamsungTVDownload)


def system(session, **_kwargs):
    session.open(SamsungTV)


def Plugins(**_kwargs):
    return [
        PluginDescriptor(name=_("Samsung TV Plus"), where=PluginDescriptor.WHERE_PLUGINMENU, icon=PLUGIN_ICON, description=_("Browse channels, EPG, and on-demand content from Samsung TV Plus"), fnc=system, needsRestart=True),
        PluginDescriptor(name=_("Download Samsung TV Plus bouquet, picons and EPG"), where=PluginDescriptor.WHERE_EXTENSIONSMENU, fnc=Download_SamsungTV, needsRestart=True),
        PluginDescriptor(name=_("Silently download Samsung TV Plus"), where=PluginDescriptor.WHERE_SESSIONSTART, fnc=sessionstart),
    ]
