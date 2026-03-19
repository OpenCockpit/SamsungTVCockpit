# Copyright (C) 2026 by xcentaurix

from Components.config import ConfigSelection, ConfigSubsection, config

from . import _
from .Variables import NUMBER_OF_LIVETV_BOUQUETS
from Tools.CountryCodes import ISO3166


# Regions available on Samsung TV Plus (via i.mjh.nz)
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

REGION_NAMES = {cc: country[0].split("(")[0].strip() for country in sorted(ISO3166) if (cc := country[1].lower()) in REGIONS}  # ISO3166 is sorted in English, sorted will sort by locale.


TSIDS = {cc: f"{i:X}" for i, cc in enumerate(REGION_NAMES, 0x160)}


# --- Config subsection ---------------------------------------------------

config.plugins.samsungtv = ConfigSubsection()
config.plugins.samsungtv.region = ConfigSelection(default="de", choices=list(REGION_NAMES.items()))
config.plugins.samsungtv.picons = ConfigSelection(default="snp", choices=[("snp", _("service name")), ("srp", _("service reference")), ("", _("None"))])
config.plugins.samsungtv.silentmode = ConfigSelection(default="yes", choices=[("yes", _("Yes")), ("no", _("No"))])


# --- Helper functions -----------------------------------------------------

def getselectedregions(skip=0):
    return [getattr(config.plugins.samsungtv, "live_tv_region" + str(n)).value for n in range(1, NUMBER_OF_LIVETV_BOUQUETS + 1) if n != skip]


def autoregion(_configElement):
    for idx in range(1, NUMBER_OF_LIVETV_BOUQUETS + 1):
        selected_regions = getselectedregions(idx)
        getattr(config.plugins.samsungtv, "live_tv_region" + str(idx)).setChoices([x for x in [("", _("None"))] + list(REGION_NAMES.items()) if x[0] and x[0] not in selected_regions or not x[0] and (idx == NUMBER_OF_LIVETV_BOUQUETS or not getattr(config.plugins.samsungtv, "live_tv_region" + str(idx + 1)).value)])


# --- LiveTV region config items -----------------------------------------

for n in range(1, NUMBER_OF_LIVETV_BOUQUETS + 1):
    setattr(config.plugins.samsungtv, "live_tv_region" + str(n), ConfigSelection(default="" if n > 1 else "de", choices=[("", _("None"))] + list(REGION_NAMES.items())))

for n in range(1, NUMBER_OF_LIVETV_BOUQUETS + 1):
    getattr(config.plugins.samsungtv, "live_tv_region" + str(n)).addNotifier(autoregion, initial_call=n == NUMBER_OF_LIVETV_BOUQUETS)
