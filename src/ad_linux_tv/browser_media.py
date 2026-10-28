"""Ephemeral, bounded managed-HTML-media snapshots; correlation is not authentication."""

import math
import re
import time
from threading import Lock


class BrowserMedia:
    def __init__(self):
        self.lock = Lock()
        self.sequence = 0
        self.updated = 0.0
        self.media = None
        self.sent_at = 0
        self._capabilities = frozenset()

    def report(self, data):
        if not isinstance(data, dict) or set(data) != {
            "protocol",
            "sequence",
            "sent_at",
            "capabilities",
            "media",
        }:
            raise ValueError("invalid bridge report")
        if (
            type(data["protocol"]) is not int
            or data["protocol"] != 1
            or type(data["sequence"]) is not int
            or not 0 < data["sequence"] < 2**53
            or type(data["sent_at"]) is not int
            or not 0 < data["sent_at"] < 2**53
            or abs(time.time() * 1000 - data["sent_at"]) > 3000
            or not isinstance(data["capabilities"], list)
            or len(data["capabilities"]) > 16
            or any(
                not isinstance(item, str) or re.fullmatch(r"[a-z0-9_]{1,40}", item) is None
                for item in data["capabilities"]
            )
        ):
            raise ValueError("unsupported or stale bridge report")
        media = data["media"]
        if media is not None:
            if "html_media_v1" not in data["capabilities"]:
                raise ValueError("HTML capability missing")
            if not isinstance(media, dict) or set(media) != {
                "media_id",
                "playing",
                "position",
                "duration",
                "can_seek",
            }:
                raise ValueError("invalid media snapshot")
            if (
                not isinstance(media["media_id"], str)
                or re.fullmatch(r"[0-9a-f]{32}", media["media_id"]) is None
                or type(media["playing"]) is not bool
                or type(media["can_seek"]) is not bool
                or type(media["position"]) is not int
                or type(media["duration"]) is not int
                or not 0 <= media["position"] <= media["duration"] <= 86400
                or media["duration"] == 0
            ):
                raise ValueError("invalid media values")
            media = dict(media)
        with self.lock:
            if (
                data["sequence"] <= self.sequence
                or abs(time.time() * 1000 - data["sent_at"]) > 3000
            ):
                raise ValueError("outdated bridge report")
            self.sequence = data["sequence"]
            self.updated = time.monotonic()
            self.sent_at = data["sent_at"]
            self.media = media
            # Additive unknown capabilities are ignored, never executable operations.
            self._capabilities = frozenset(data["capabilities"]) & {
                "html_media_v1",
                "tab_view_v1",
                "video_fullscreen_v1",
            }

    def fresh(self):
        return (
            time.monotonic() - self.updated <= 3 and abs(time.time() * 1000 - self.sent_at) <= 3000
        )

    def capabilities(self):
        with self.lock:
            return sorted(self._capabilities) if self.fresh() else []

    def status(self):
        with self.lock:
            if not self.fresh() or self.media is None:
                return None
            return dict(
                self.media,
                available=True,
                source="html",
                title="Плеер страницы",
                can_play=True,
                can_pause=True,
                can_next=False,
                can_previous=False,
            )


def choose_media(mpris, browser):
    """Prefer complete MPRIS timing; never substitute stale/ambiguous HTML data."""
    complete = (
        mpris.get("available")
        and all(
            type(mpris.get(key)) in (int, float) and math.isfinite(mpris[key])
            for key in ("duration", "position")
        )
        and mpris["duration"] > 0
    )
    return mpris if complete or browser is None else browser
