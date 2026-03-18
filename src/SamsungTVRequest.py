# Copyright (C) 2026 by xcentaurix

import time

from Components.config import config
import requests

from .Variables import USER_AGENT


class SamsungTVRequest:
    """API handler for Samsung TV Plus channels and VOD content."""

    # i.mjh.nz endpoints
    CHANNELS_JSON_URL = "https://i.mjh.nz/SamsungTVPlus/.channels.json"
    EPG_XML_URL = "https://i.mjh.nz/SamsungTVPlus/%s.xml"

    # JMP2 proxy URL template
    JMP2_URL_TEMPLATE = "https://jmp2.uk/%s"

    # Samsung TV Plus API for VOD content
    SAMSUNG_API_BASE = "https://api.samsungtv.com/browser/v2"

    # Placeholder pattern for runtime URL resolution
    SAMSUNG_PATTERN = "SAMSUNG_SID_"
    SAMSUNG_PLACEHOLDER = f"https://{{{SAMSUNG_PATTERN}%s}}.m3u8"

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": USER_AGENT})
        self.requestCache = {}
        self._channels_json = None
        self._channels_json_time = 0

    def _getChannelsJson(self):
        """Fetch and cache the channels JSON from i.mjh.nz."""
        now = time.time()
        if self._channels_json and now - self._channels_json_time < 4 * 3600:
            return self._channels_json
        try:
            response = self.session.get(self.CHANNELS_JSON_URL, timeout=10)
            response.raise_for_status()
            self._channels_json = response.json()
            self._channels_json_time = now
            return self._channels_json
        except Exception:
            return self._channels_json or {}

    def getChannels(self, region=None):
        """Fetch channels for region. Returns list of channel dicts."""
        region = region or config.plugins.samsungtv.region.value
        app = self._getChannelsJson()
        if not app:
            return []

        region_data = app.get("regions", {}).get(region, {})
        channels_dict = region_data.get("channels", {})
        slug_template = app.get("slug", "")

        result = []
        for ch_id, ch_data in sorted(channels_dict.items(), key=lambda x: x[1].get("chno", 0)):
            if ch_data.get("license_url"):
                continue  # skip DRM channels

            slug = slug_template.format(id=ch_id) if slug_template else ch_id
            stream_url = self.JMP2_URL_TEMPLATE % slug

            result.append({
                "_id": ch_id,
                "name": ch_data.get("name", ""),
                "slug": slug,
                "number": ch_data.get("chno", 0),
                "category": ch_data.get("group", ""),
                "description": ch_data.get("description", ""),
                "logo": ch_data.get("logo", ""),
                "stream_url": stream_url,
            })
        return result

    def getVODCategories(self, region=None):
        """Get VOD categories with content from Samsung TV Plus.

        Since Samsung TV Plus's primary content is live channels (which also
        have on-demand clips), we organize them as VOD categories by group.
        Returns a list of category dicts with items.
        """
        region = region or config.plugins.samsungtv.region.value
        channels = self.getChannels(region)
        if not channels:
            return []

        categories = {}
        for ch in channels:
            group = ch.get("category", "Uncategorized")
            if group not in categories:
                categories[group] = {
                    "name": group,
                    "items": [],
                }
            categories[group]["items"].append({
                "_id": ch["_id"],
                "name": ch["name"],
                "summary": ch.get("description", ""),
                "genre": group,
                "rating": "",
                "duration": 0,
                "type": "channel",
                "stream_url": ch.get("stream_url", ""),
                "logo": ch.get("logo", ""),
                "covers": [{"url": ch.get("logo", "")}] if ch.get("logo") else [],
            })

        # Sort categories alphabetically
        return sorted(categories.values(), key=lambda x: x["name"].casefold())

    def buildStreamURL(self, channel_id, region=None):
        """Build stream URL for a channel using JMP2 proxy."""
        region = region or config.plugins.samsungtv.region.value
        app = self._getChannelsJson()
        if not app:
            return ""
        slug_template = app.get("slug", "")
        slug = slug_template.format(id=channel_id) if slug_template else channel_id
        return self.JMP2_URL_TEMPLATE % slug

    def getURL(self, url, param=None, header=None, life=60 * 15, region=None):
        """Generic cached GET request returning JSON."""
        if header is None:
            header = {"User-Agent": USER_AGENT}
        if param is None:
            param = {}
        now = time.time()
        region = region or config.plugins.samsungtv.region.value
        if region not in self.requestCache:
            self.requestCache[region] = {}
        if url in self.requestCache[region] and self.requestCache[region][url][1] > (now - life):
            return self.requestCache[region][url][0]
        try:
            req = self.session.get(url, params=param, headers=header, timeout=10)
            req.raise_for_status()
            response = req.json()
            req.close()
            self.requestCache[region][url] = (response, now)
            return response
        except Exception:
            return {}


samsungRequest = SamsungTVRequest()
