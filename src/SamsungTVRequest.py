# Copyright (C) 2026 by xcentaurix
# License: GNU General Public License v3.0

import time

from Components.config import config
from Plugins.SystemPlugins.StreamProxyCockpit import LiveProxyUnmuxed, StreamProxy
import requests

from .Variables import USER_AGENT
from .CockpitTVDownload import FailureTracker


class SamsungTVRequest(FailureTracker):
    """API handler for Samsung TV Plus channels and VOD content."""

    # i.mjh.nz endpoints
    CHANNELS_JSON_URL = "https://i.mjh.nz/SamsungTVPlus/.channels.json"
    EPG_XML_URL = "https://i.mjh.nz/SamsungTVPlus/%s.xml"

    # JMP2 proxy URL template
    JMP2_URL_TEMPLATE = "https://jmp2.uk/%s"

    # The bouquets address a channel as samsungtv://<id>, StreamProxyCockpit resolves it when it is played or recorded
    SCHEME = "samsungtv"
    SAMSUNG_SCHEMA = SCHEME + "%3a//"

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
        self._stream_headers = {}

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
            self.clearFailure("json")
            return self._channels_json
        except Exception as e:
            self.recordFailure("json", e)
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
            stream_url = self.JMP2_URL_TEMPLATE % slug + self._headerSuffix(app)

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

    def streamHeaders(self):
        """The request headers the CDN behind the jmp2.uk redirect wants (the ones of the channels feed).

        May wait for the feed, so it is for worker threads; the last headers known if the feed isn't reachable."""
        app = self._getChannelsJson()
        if app:
            self._stream_headers = self._requestHeaders(app)
        return self._stream_headers

    def resolveStreamURL(self, channel_id):
        """The address the stream of a channel really has: the jmp2.uk address after its redirect.

        The stream proxy needs it to find the segments of the playlist, Enigma2 follows the redirect itself. The
        jmp2.uk address if it can't be followed."""
        app = self._getChannelsJson()
        if not app:
            return ""
        slug_template = app.get("slug", "")
        slug = slug_template.format(id=channel_id) if slug_template else channel_id
        url = self.JMP2_URL_TEMPLATE % slug
        try:
            response = self.session.get(url, headers=self.streamHeaders(), timeout=10, stream=True)
            response.close()
            response.raise_for_status()
            return response.url
        except requests.RequestException:
            return url

    def buildStreamURL(self, channel_id):
        """The address of the stream itself (jmp2.uk, with the request headers its CDN wants), for a bouquet that
        doesn't go through the stream proxy."""
        app = self._getChannelsJson()
        if not app:
            return ""
        slug_template = app.get("slug", "")
        slug = slug_template.format(id=channel_id) if slug_template else channel_id
        return self.JMP2_URL_TEMPLATE % slug + self._headerSuffix(app)

    def getProxyURL(self, channel_id):
        """The address of the stream proxy for a channel, to play or record it from.

        The real stream address is not looked up here but by the proxy, on one of its own threads, the first time
        the channel is used (and again when it no longer works): this runs on the main thread while Enigma2 zaps."""
        address = StreamProxy.registerChannel(self.SCHEME, channel_id, url_refresher=lambda: self.resolveStreamURL(channel_id),
                                              headers=self.streamHeaders, refresh_on_failure=True)
        # Enigma2 itself needs the headers only when the proxy hands it over to the real stream (a stream the proxy
        # can't process), and only if the feed is known by now
        return address + LiveProxyUnmuxed.header_suffix(self._stream_headers)

    @staticmethod
    def _requestHeaders(app):
        """The request headers of the channels feed, with the User-Agent spelled the way servers expect it."""
        headers = {}
        for key, value in dict(app.get("headers") or {}).items():
            headers["User-Agent" if key.lower() == "user-agent" else key] = value
        return headers

    @classmethod
    def _headerSuffix(cls, app):
        """The '#Key=Value&...' suffix eServiceMP3 reads as extra HTTP headers.

        The upstream CDN behind the jmp2.uk redirect rejects requests whose User-Agent doesn't match what the
        official app sends, so the required header from the channels feed must travel with the URL.
        """
        return LiveProxyUnmuxed.header_suffix(cls._requestHeaders(app))

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


def resolveStream(channel_id, _sref):
    """StreamProxy provider: the address of the stream proxy for the Samsung TV Plus channel *channel_id*.

    The id of a channel is unique over all regions, so the service reference is not needed."""
    return samsungRequest.getProxyURL(channel_id)
