# Copyright (C) 2026 by xcentaurix
# License: GNU General Public License v3.0

from Components.config import ConfigDirectory, ConfigSelection, ConfigYesNo, config

from . import _
from . import Debug  # noqa: F401, pylint: disable=unused-import
from .CountryCodes import ISO3166
from .Variables import NUMBER_OF_LIVETV_BOUQUETS
from .CockpitTVConfig import setupLocationSlots


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

# ISO3166 is sorted in English, sorted will sort by locale.
REGION_NAMES = {cc: country[0].split("(")[0].strip() for country in sorted(ISO3166) if (cc := country[1].lower()) in REGIONS}

TSIDS = {cc: f"{i:X}" for i, cc in enumerate(REGION_NAMES, 0x160)}


# --- Config subsection ---------------------------------------------------

# Debug creates config.plugins.samsungtvcockpit (with debug_log_level): the settings below join that subsection, it
# must not be created again here.
# The settings used to be config.plugins.samsungtv: take over what is stored there and drop it, so it isn't saved again.
if oldValues := config.plugins.content.stored_values.pop("samsungtv", None):
    for key, value in oldValues.items():
        config.plugins.samsungtvcockpit.content.stored_values.setdefault(key, value)
config.plugins.samsungtvcockpit.region = ConfigSelection(default="de", choices=list(REGION_NAMES.items()))
config.plugins.samsungtvcockpit.picons = ConfigSelection(default="snp", choices=[("snp", _("service name")), ("srp", _("service reference")), ("", _("None"))])
config.plugins.samsungtvcockpit.silentmode = ConfigSelection(default="yes", choices=[("yes", _("Yes")), ("no", _("No"))])
config.plugins.samsungtvcockpit.auto_update_check = ConfigSelection(default="yes", choices=[("yes", _("Yes")), ("no", _("No"))])
# Read by PRSCockpitPlayer (CockpitPlayer); not offered in the setup screen.
config.plugins.samsungtvcockpit.movie_resume_at_last_pos = ConfigYesNo(default=False)
config.plugins.samsungtvcockpit.movie_start_position = ConfigSelection(default="beginning", choices=[("beginning", _("beginning"))])
config.plugins.samsungtvcockpit.config_folder = ConfigDirectory(default="/etc/enigma2")
config.plugins.samsungtvcockpit.stream_proxy = ConfigYesNo(default=False)


# --- Live-TV region config items -----------------------------------------

getselectedregions = setupLocationSlots(config.plugins.samsungtvcockpit, "live_tv_region", REGION_NAMES, NUMBER_OF_LIVETV_BOUQUETS, _("None"), first_default="de")
