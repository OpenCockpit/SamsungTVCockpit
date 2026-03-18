# Copyright (C) 2026 by xcentaurix


import os
import gettext
from Tools.Directories import resolveFilename, SCOPE_PLUGINS
from Components.Language import language


PluginLanguageDomain = "SamsungTV"
PluginLanguagePath = "Extensions/SamsungTV/locale"


def initLocale():
    os.environ["LANGUAGE"] = language.getLanguage()[:2]
    locale = resolveFilename(SCOPE_PLUGINS, PluginLanguagePath)
    if os.path.exists(locale):
        gettext.bindtextdomain(PluginLanguageDomain, locale)


def _(txt):
    return gettext.dgettext(PluginLanguageDomain, txt)


def __(singular, plural, n):
    return gettext.dngettext(PluginLanguageDomain, singular, plural, n)


initLocale()
language.addCallback(initLocale)
