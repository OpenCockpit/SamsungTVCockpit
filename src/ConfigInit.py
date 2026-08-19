# Copyright (C) 2026 by xcentaurix

from Components.config import ConfigDirectory, ConfigSelection, ConfigSubsection, config

from . import _
from .CountryCodes import ISO3166
from .Variables import NUMBER_OF_LIVETV_BOUQUETS
from .CockpitTVConfig import setupLocationSlots


REGIONS = [
    "at",
    "ca",
    "ch",
    "de",
    "es",
    "fr",
    "gb",
    "in",
    "it",
    "kr",
    "us",
]

REGION_NAMES = {cc: country[0].split("(")[0].strip() for country in sorted(ISO3166) if (cc := country[1].lower()) in REGIONS}

TSIDS = {cc: f"{i:X}" for i, cc in enumerate(REGION_NAMES, 0x160)}


config.plugins.samsungtv = ConfigSubsection()
config.plugins.samsungtv.region = ConfigSelection(default="de", choices=list(REGION_NAMES.items()))
config.plugins.samsungtv.picons = ConfigSelection(default="snp", choices=[("snp", _("service name")), ("srp", _("service reference")), ("", _("None"))])
config.plugins.samsungtv.silentmode = ConfigSelection(default="yes", choices=[("yes", _("Yes")), ("no", _("No"))])
config.plugins.samsungtv.auto_update_check = ConfigSelection(default="yes", choices=[("yes", _("Yes")), ("no", _("No"))])
config.plugins.samsungtv.config_folder = ConfigDirectory(default="/etc/enigma2")


getselectedregions = setupLocationSlots(config.plugins.samsungtv, "live_tv_region", REGION_NAMES, NUMBER_OF_LIVETV_BOUQUETS, _("None"), first_default="de")
