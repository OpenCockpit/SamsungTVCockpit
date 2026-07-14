# Copyright (C) 2026 by xcentaurix

import ipaddress
import random

from Components.config import ConfigSelection, ConfigSubsection, config

from . import _
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

# Geo-spoofing IP ranges per region, used for X-Forwarded-For headers so
# playback requests appear to originate from the selected region instead of
# the box's real location. Each value is a /24 known (via public RIR
# delegation data) to be allocated within that country. pickForwardIP()
# draws a random host from it (cached for the process lifetime) instead of
# always sending one exact address.
X_FORWARD_NETS = {
    "at": "2.18.68.0/24",
    "ca": "192.206.151.0/24",
    "ch": "5.144.31.0/24",
    "de": "85.214.132.0/24",
    "es": "88.26.241.0/24",
    "fr": "176.31.84.0/24",
    "gb": "185.199.220.0/24",
    "in": "1.10.10.0/24",
    "it": "5.133.48.0/24",
    "kr": "1.11.0.0/24",
    "us": "185.236.200.0/24",
}

_forwardIPCache = {}


def pickForwardIP(region):
    """Return an X-Forwarded-For address for *region*, or None if unmapped.

    Picked once per region and cached for the life of the process (not
    re-rolled per call), so a single streaming session doesn't see its
    apparent origin IP change mid-flight. Restarting the plugin re-rolls
    it, spreading requests across the subnet over time.
    """
    net = X_FORWARD_NETS.get(region)
    if net is None:
        return None
    if region not in _forwardIPCache:
        _forwardIPCache[region] = str(random.choice(list(ipaddress.ip_network(net).hosts())))
    return _forwardIPCache[region]


TSIDS = {cc: f"{i:X}" for i, cc in enumerate(REGION_NAMES, 0x160)}


# --- Config subsection ---------------------------------------------------

config.plugins.samsungtv = ConfigSubsection()
config.plugins.samsungtv.region = ConfigSelection(default="de", choices=list(REGION_NAMES.items()))
config.plugins.samsungtv.picons = ConfigSelection(default="snp", choices=[("snp", _("service name")), ("srp", _("service reference")), ("", _("None"))])
config.plugins.samsungtv.silentmode = ConfigSelection(default="yes", choices=[("yes", _("Yes")), ("no", _("No"))])


# --- LiveTV region config items -----------------------------------------

getselectedregions = setupLocationSlots(config.plugins.samsungtv, "live_tv_region", REGION_NAMES, NUMBER_OF_LIVETV_BOUQUETS, _("None"), first_default="de")
