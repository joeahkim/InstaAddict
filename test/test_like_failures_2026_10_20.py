"""Regression tests for the 10/20 like failures.

1. IG reuses id/like_button for the Notes heart ("Tap to like note") on
   profile grids. Every reel-heart lookup must filter by content-desc so a
   note is never mistaken for a post heart (12:52:28 / 12:52:36 failures).
2. The opened-post viewer keeps slivers of scrolled posts that match
   MEDIA_CONTAINER; the double tap must target the biggest container
   (12:46:05 failure).
3. The like Button can lose its resource-id entirely; _get_post_like_button
   must fall through to the desc-paired heart instead of returning None.

Run: PYTHONPATH=. python -m pytest test/test_like_failures_2026_10_20.py -q
"""

import re
from types import SimpleNamespace

from InstaAddict.core import views

views.ResourceID = views.resources("com.instagram.android")

LIKE_BUTTON_ID = views.ResourceID.LIKE_BUTTON


class FakeView:
    def __init__(self, exists=True, selected=False, desc=""):
        self._exists = exists
        self._selected = selected
        self._desc = desc
        self.clicks = 0

    def exists(self, *_):
        return self._exists

    def get_selected(self):
        return self._selected

    def get_desc(self):
        return self._desc

    def get_bounds(self):
        return self._bounds

    def click(self, *_, **__):
        self.clicks += 1


def _device_returning(by_query):
    """by_query: dict mapping kwargs-tuples to FakeView lists.

    The real uiautomator2 selector applies descriptionMatches server-side;
    the fake emulates that by full-matching the view's desc against the
    pattern, exactly like UiSelector.descriptionMatches does."""

    def find(**kw):
        key = tuple(sorted(kw.items()))
        candidates = by_query.get(key, [])
        if not isinstance(candidates, list):
            candidates = [candidates]
        pattern = kw.get("descriptionMatches")
        for view in candidates:
            if pattern is None:
                return view
            if re.fullmatch(pattern, view.get_desc() or "", re.IGNORECASE):
                return view
        return FakeView(exists=False)

    return SimpleNamespace(find=find)


def test_reels_like_finder_ignores_the_notes_heart():
    note_heart = FakeView(desc="Tap to like note", exists=True)
    device = _device_returning(
        {
            (
                ("descriptionMatches", views.case_insensitive_re("^(Like|Liked)$")),
                ("resourceIdMatches", views.case_insensitive_re(LIKE_BUTTON_ID)),
            ): note_heart,
        }
    )
    found = views.find_reels_like_button(device)
    assert not found.exists(), "matched the Notes heart"

    reel_heart = FakeView(desc="Like", exists=True)
    device = _device_returning(
        {
            (
                ("descriptionMatches", views.case_insensitive_re("^(Like|Liked)$")),
                ("resourceIdMatches", views.case_insensitive_re(LIKE_BUTTON_ID)),
            ): reel_heart,
        }
    )
    assert views.find_reels_like_button(device).exists()


def test_is_post_opened_ignores_note_heart_on_grid():
    obj = views.OpenedPostView.__new__(views.OpenedPostView)
    note_heart = FakeView(desc="Tap to like note", exists=True)

    def find(**kw):
        pattern = kw.get("descriptionMatches")
        if pattern is not None:
            if re.fullmatch(pattern, note_heart.get_desc(), re.IGNORECASE):
                return note_heart
            return FakeView(exists=False)
        return FakeView(exists=False)

    obj.device = SimpleNamespace(find=find)
    assert obj.is_post_opened() is False


def test_is_post_opened_accepts_reel_sidebar_heart():
    obj = views.OpenedPostView.__new__(views.OpenedPostView)
    reel_heart = FakeView(desc="Like", exists=True)

    def find(**kw):
        pattern = kw.get("descriptionMatches")
        if pattern is not None:
            if re.fullmatch(pattern, reel_heart.get_desc(), re.IGNORECASE):
                return reel_heart
            return FakeView(exists=False)
        return FakeView(exists=False)

    obj.device = SimpleNamespace(find=find)
    assert obj.is_post_opened() is True


def test_get_media_view_picks_biggest_container_not_sliver():
    obj = views.OpenedPostView.__new__(views.OpenedPostView)
    sliver = SimpleNamespace(
        exists=lambda *_: True,
        count_items=lambda: 2,
        get_bounds=lambda: {"left": 0, "top": 2438, "right": 1440, "bottom": 2759},
    )
    media = SimpleNamespace(
        exists=lambda *_: True,
        get_bounds=lambda: {"left": 0, "top": 492, "right": 1440, "bottom": 2412},
    )
    calls = {"index": 0}

    def find(**kw):
        if kw.get("index") is not None:
            return sliver if kw["index"] == 0 else media
        return sliver

    obj.device = SimpleNamespace(find=find)
    best = obj._get_media_view()
    assert best is media, "picked the sliver instead of the real media"


def test_get_post_like_button_falls_back_when_paired_lookup_fails():
    obj = views.OpenedPostView.__new__(views.OpenedPostView)
    media = SimpleNamespace(exists=lambda *a, **k: True)
    failed_paired = SimpleNamespace(viewV2=None, exists=lambda *a, **k: False)
    heart_no_id = FakeView(exists=True, desc="Like")

    state = {"flat_lookup_done": False}

    def find(**kw):
        rid = kw.get("resourceIdMatches", "")
        if rid == views.ResourceID.MEDIA_CONTAINER:
            return media
        if "index" in kw:
            return failed_paired
        if rid and views.ResourceID.ROW_FEED_BUTTON_LIKE in rid:
            if "Timeout" in str(kw):
                pass
            # flat fallback: first call fails (exists False), then desc heart
            return SimpleNamespace(exists=lambda *a, **k: False)
        if kw.get("descriptionMatches") and "Like" in kw["descriptionMatches"]:
            return heart_no_id
        return FakeView(exists=False)

    def down(**kw):
        return failed_paired

    media.down = down
    obj.device = SimpleNamespace(find=find)

    class FakeUniversalActions:
        def __init__(self, device):
            pass

        def _swipe_points(self, **kw):
            pass

    views.UniversalActions = FakeUniversalActions
    found = obj._get_post_like_button()
    assert found is heart_no_id, "did not fall through to the desc-paired heart"
