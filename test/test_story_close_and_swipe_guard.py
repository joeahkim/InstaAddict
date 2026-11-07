"""Regression tests for the story-viewer close and profile-grid swipe guard.

Observed on 2026-10-29 (Samsung SM-S918B / Android 14 / IG latest):

1. While watching a profile's stories, IG can auto-advance to *another*
   user's story before the bot finishes. The old close loop only pressed
   back while the viewer still showed the target username, so a foreign
   story left the viewer open and the bot kept tapping the next profile
   on top of it.
2. With a story/media viewer still covering the profile, the grid never
   renders and profile_tabs_container stays unfindable; the swipe calc
   then crashed on a stale/empty bounds object instead of skipping.

Run: PYTHONPATH=. python -m pytest test/test_story_close_and_swipe_guard.py -q
"""

from types import SimpleNamespace
from unittest.mock import patch

from InstaAddict.core import views
from InstaAddict.core.interaction import _close_story_view
from InstaAddict.core.views import ProfileView

views.ResourceID = views.resources("com.instagram.android")


class FakeFrame:
    def __init__(self, exists=True):
        self._exists = exists

    def exists(self, *_a, **_kw):
        return self._exists

    def wait_gone(self, *_a, **_kw):
        return True


class FakeStoryView:
    """CurrentStoryView stand-in. getUsername returns one username per call
    from `usernames`, simulating IG advancing to other users' stories."""

    def __init__(self, usernames):
        self.usernames = list(usernames)
        self.backs = 0
        self.device = SimpleNamespace(back=self._back)

    def _back(self):
        self.backs += 1
        if self.usernames:
            self.usernames.pop()

    def getUsername(self):
        return self.usernames[0] if self.usernames else ""

    def getStoryFrame(self):
        return FakeFrame(exists=bool(self.usernames))


def test_close_story_view_presses_back_on_target_story():
    sv = FakeStoryView(["target_user"])
    _close_story_view(sv, "target_user")
    # old behaviour: back until the target's own story is gone
    assert sv.backs >= 1


def test_close_story_view_on_foreign_user_story():
    sv = FakeStoryView(["someone_else"])
    _close_story_view(sv, "target_user")
    # the viewer advanced to another user: must still be closed
    assert sv.backs >= 1
    assert not sv.usernames


def test_close_story_view_advances_through_foreign_then_target():
    sv = FakeStoryView(["someone_else", "target_user"])
    _close_story_view(sv, "target_user")
    # starts on the target, advances to a foreign story mid-watch
    assert sv.backs >= 2
    assert not sv.usernames


def test_close_story_view_already_closed():
    sv = FakeStoryView([])
    _close_story_view(sv, "target_user")
    assert sv.backs == 0


class FakeFind:
    """device.find stand-in for ProfileView.swipe_to_fit_posts, keyed on
    the resource id being looked up."""

    def __init__(self, tabs_exists):
        self._tabs_exists = tabs_exists

    def __call__(self, resourceIdMatches=None, **_kw):
        rid = resourceIdMatches or ""
        if ResourceID_PROFILE_TABS in rid:
            return SimpleNamespace(
                exists=lambda *a, **k: self._tabs_exists,
                get_bounds=lambda: {"top": 800, "bottom": 850},
            )
        # action bar and anything else
        return SimpleNamespace(
            exists=lambda *a, **k: True,
            get_bounds=lambda: {"top": 100, "bottom": 200},
        )


ResourceID_PROFILE_TABS = "profile_tabs_container"


def test_swipe_to_fit_posts_returns_minus1_when_tabs_missing():
    profile = ProfileView.__new__(ProfileView)
    profile.device = SimpleNamespace(
        find=FakeFind(tabs_exists=False),
        get_info=lambda: {"displayWidth": 1080},
    )
    with patch.object(
        views.UniversalActions, "_swipe_points", return_value=None
    ) as swipe:
        result = profile.swipe_to_fit_posts()
    assert result == -1
    assert swipe.call_count == 2


def test_swipe_to_fit_posts_still_swipes_when_tabs_present():
    profile = ProfileView.__new__(ProfileView)
    profile.device = SimpleNamespace(
        find=FakeFind(tabs_exists=True),
        get_info=lambda: {"displayWidth": 1080},
        swipe_points=lambda *a, **k: None,
    )
    result = profile.swipe_to_fit_posts()
    # tabs found at the first check: no retry swipes, straight to the swipe
    assert result == 800 - 200


def main():
    test_close_story_view_presses_back_on_target_story()
    test_close_story_view_on_foreign_user_story()
    test_close_story_view_advances_through_foreign_then_target()
    test_close_story_view_already_closed()
    test_swipe_to_fit_posts_returns_minus1_when_tabs_missing()
    test_swipe_to_fit_posts_still_swipes_when_tabs_present()
    print("OK")


if __name__ == "__main__":
    main()
