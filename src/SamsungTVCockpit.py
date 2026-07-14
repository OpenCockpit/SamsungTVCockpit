# Copyright (C) 2026 by xcentaurix

import os
from time import strftime, gmtime, localtime
from urllib.parse import quote
from twisted.internet import threads

from Components.ActionMap import HelpableActionMap
from Components.config import config
from Components.Label import Label
from Components.Pixmap import Pixmap
from Components.ScrollLabel import ScrollLabel
from Components.Sources.StaticText import StaticText
from Screens.HelpMenu import HelpableScreen
from Screens.MessageBox import MessageBox
from Screens.Screen import Screen
from Tools.Directories import fileExists, isPluginInstalled
from Tools.LoadPixmap import LoadPixmap
from enigma import BT_KEEP_ASPECT_RATIO, BT_SCALE, BT_HALIGN_CENTER, BT_VALIGN_CENTER, eServiceReference, eTimer
from skin import parameters

from . import _
from .SamsungTVConfig import getselectedregions
from .SamsungTVRequest import samsungRequest
from .SamsungTVDownload import SamsungTVDownload, Silent
from .SamsungTVUtils import downloadPoster
from .Variables import TIMER_FILE, BOUQUET_FILE
from .SamsungList import SamsungList
from .SamsungSetup import SamsungSetup
from .SamsungPlayer import Samsung_Player


class SamsungTVCockpit(Screen, HelpableScreen):

    def __init__(self, session):
        self.session = session
        Screen.__init__(self, session)
        self.skinName = "SamsungTVCockpit"
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
            print("[SamsungTVCockpit] showPoster, ERROR", ex)

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
