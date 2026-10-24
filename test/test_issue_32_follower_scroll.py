"""Regression check for issue #32: when every follower visible in the first
screen was already interacted with, the own-followers traversal stopped with
"Scrolled to top, finish." on the very first screen because the followers list
always opens at the top (search bar visible). The fix removes that early exit
and makes own-account lists scroll DOWN like every other list, relying on
ScrollEndDetector page fingerprints to stop at the real end.

Run: .venv/Scripts/python test/test_issue_32_follower_scroll.py
"""

from types import SimpleNamespace

from InstaAddict.core.device_facade import Direction
from InstaAddict.core.handle_sources import iterate_over_followers
from InstaAddict.core.scroll_end_detector import ScrollEndDetector


class FakeView:
    def __init__(self, visible=True):
        self.visible = visible

    def exists(self, *_):
        return self.visible

    def wait(self, *_):
        return self.visible

    def get_height(self):
        return 252

    def get_text(self):
        return "some_username"

    def click_retry(self):
        return False


class FakeRow:
    def __init__(self, username):
        self.username = username

    def wait(self, *_):
        return True

    def get_height(self):
        return 252

    def child(self, index=0):
        return FakeNameView(self.username)


class FakeNameView:
    def __init__(self, username):
        self.username = username

    def exists(self, *_):
        return True

    def get_text(self):
        return self.username

    def child(self, index=0):
        return self

    def click_retry(self):
        return False


class FakeUserList:
    """user_list container: iterates the rows of the current screen."""

    def __init__(self, rows):
        self.rows = rows

    def wait(self, *_):
        return True

    def __iter__(self):
        return iter(self.rows)


class FakeListView:
    def __init__(self):
        self.scrolls = []

    def exists(self, *_):
        return True

    def scroll(self, direction):
        self.scrolls.append(("scroll", direction))

    def fling(self, direction):
        self.scrolls.append(("fling", direction))


class FakeDevice:
    def __init__(self, screens, list_view):
        self.screens = screens
        self.screen_idx = 0
        self.list_view = list_view
        self.backs = 0

    def find(self, resourceId=None, resourceIdMatches=None, className=None, **_):
        if resourceIdMatches is not None:
            return FakeUserList(self.screens[self.screen_idx])
        if resourceId is not None and resourceId.endswith("android:id/list"):
            return self.list_view
        return FakeView(visible=False)

    def back(self):
        self.backs += 1


class FakeStorage:
    def __init__(self, interacted):
        self.interacted = interacted

    def is_user_in_blacklist(self, username):
        return False

    def check_user_was_interacted(self, username):
        if username in self.interacted:
            from datetime import datetime

            return True, datetime(2026, 1, 1)
        return False, None

    def can_be_reinteract(self, last_interaction, hours):
        return hours == 0


def _run_case(screen_rows, interacted, repeats_to_end=5):
    list_view = FakeListView()
    device = FakeDevice(screen_rows, list_view)
    storage = FakeStorage(interacted)
    detector = ScrollEndDetector(repeats_to_end=repeats_to_end)

    # The device advances one screen per DOWN scroll; when the list stops
    # changing (same rows fingerprinted repeatedly) the detector ends the job.
    original_scroll = list_view.scroll

    def scroll(direction):
        original_scroll(direction)
        if direction == Direction.DOWN and device.screen_idx < len(device.screens) - 1:
            device.screen_idx += 1

    list_view.scroll = scroll

    args = SimpleNamespace(can_reinteract_after=None)
    self = SimpleNamespace(
        ResourceID=SimpleNamespace(
            FOLLOW_LIST_CONTAINER="com.instagram.android:id/follow_list_container",
            USER_LIST_CONTAINER="com.instagram.android:id/follow_list_container",
            ROW_LOAD_MORE_BUTTON="com.instagram.android:id/row_load_more_button",
            SEE_ALL_BUTTON="com.instagram.android:id/see_all_button",
            ACTION_BAR_SEARCH_EDIT_TEXT="com.instagram.android:id/action_bar_search_edit_text",
            LIST="android:id/list",
        ),
        args=args,
    )

    iterate_over_followers(
        self,
        device,
        interaction=lambda **_: (True, False, False, False, False, 0, 0, 0),
        is_follow_limit_reached=lambda: False,
        storage=storage,
        on_interaction=lambda **_: True,
        is_myself=True,
        scroll_end_detector=detector,
        session_state=SimpleNamespace(my_username="me"),
        current_job="blogger-followers",
        target="me",
    )
    return device, list_view


def test_first_screen_all_skipped_still_scrolls():
    # Issue #32: first screen fully interacted -> must NOT stop, must scroll DOWN.
    screens = [
        [FakeRow(f"user{i}") for i in range(8)],
        [FakeRow(f"user{i}") for i in range(8, 16)],
        [FakeRow(f"user{i}") for i in range(16, 24)],
    ]
    interacted = {f"user{i}" for i in range(8)}
    device, list_view = _run_case(screens, interacted)

    assert list_view.scrolls, "bot must scroll when the first screen is fully skipped"
    assert all(d in (Direction.DOWN,) for _, d in list_view.scrolls), list_view.scrolls
    assert device.screen_idx > 0, "bot must advance past the first screen"


def test_repeating_screens_terminate():
    # Same screen forever -> ScrollEndDetector ends the job after repeats.
    screens = [[FakeRow(f"user{i}") for i in range(8)]]
    device, list_view = _run_case(screens, set(), repeats_to_end=5)

    assert device.screen_idx == 0
    assert list_view.scrolls, "bot scrolls while looking for new users"
    # job finished (returned) without crashing


def main():
    test_first_screen_all_skipped_still_scrolls()
    test_repeating_screens_terminate()
    print("OK")


if __name__ == "__main__":
    main()
