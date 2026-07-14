# Copyright (C) 2026 by xcentaurix

from Components.MenuList import MenuList
from Components.MultiContent import MultiContentEntryText, MultiContentEntryPixmapAlphaBlend
from Tools.Directories import fileExists, resolveFilename, SCOPE_CURRENT_SKIN
from Tools.LoadPixmap import LoadPixmap
from enigma import BT_KEEP_ASPECT_RATIO, BT_SCALE, eListboxPythonMultiContent, gFont
from skin import applySkinFactor, fonts


class SamsungList(MenuList):
    def __init__(self, entries):
        self.menu_png = LoadPixmap(x if fileExists(x := resolveFilename(SCOPE_CURRENT_SKIN, "icons/samsung_menu.png")) else "/usr/lib/enigma2/python/Plugins/Extensions/SamsungTVCockpit/skin/images/menu.png") if fileExists("/usr/lib/enigma2/python/Plugins/Extensions/SamsungTVCockpit/skin/images/menu.png") else None

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
