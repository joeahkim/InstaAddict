"""Regression tests for the 10/29 like failures.

1. The 2026-10 reel viewer never updates the accessibility state of
   id/like_button: selected stays false and the content-desc stays "Like"
   even when the reel is liked (the jsonrpc info is stale). The liked
   state is only visible as an extra filled-heart ImageView child under
   the button (07:52:18 / 07:52:24 "Fail to like post" cascade, where the
   verification miss also made the retry click UNLIKE the reel).
2. The profile grid list now starts with a gap_binder_group spacer View
   before the first post row. Raw child(index=N) selection is shifted by
   one on that build and unshifted on builds without the spacer, so the
   first row must be probed instead of trusting a static offset
   (07:52:30 / 07:52:39 crash dumps: "Open post #2/#3" never opened).

Run: PYTHONPATH=. python -m pytest test/test_like_failures_2026_10_29.py -q
"""

import re
from types import SimpleNamespace

from InstaAddict.core import views

views.ResourceID = views.resources("com.instagram.android")

LIKE_BUTTON_ID = views.ResourceID.LIKE_BUTTON


class FakeHeart:
    """Stand-in for the reel sidebar heart."""

    def __init__(self, desc="Like", selected=False, overlay_child=None):
        self._desc = desc
        self._selected = selected
        self._overlay_child = overlay_child

    def exists(self, *_a, **_kw):
        return True

    def get_selected(self):
        return self._selected

    def get_desc(self):
        return self._desc

    def child(self, **kwargs):
        # child(index=1, classNameMatches=ImageView) only resolves when the
        # filled-heart overlay is present.
        if kwargs.get("index") == 1 and self._overlay_child is not None:
            return self._overlay_child
        return SimpleNamespace(exists=lambda *a, **k: False)


def test_reels_heart_liked_via_selected_flag_still_wins():
    heart = FakeHeart(selected=True)
    assert views._reels_heart_is_liked(heart) is True


def test_reels_heart_liked_via_desc_still_wins():
    heart = FakeHeart(desc="Liked")
    assert views._reels_heart_is_liked(heart) is True


def test_reels_heart_liked_on_new_layout_only_via_overlay_child():
    # 2026-10 layout: desc stays "Like", selected stays False.
    overlay = SimpleNamespace(exists=lambda *a, **k: True)
    heart = FakeHeart(desc="Like", selected=False, overlay_child=overlay)
    assert views._reels_heart_is_liked(heart) is True


def test_reels_heart_unliked_on_new_layout_has_no_overlay_child():
    heart = FakeHeart(desc="Like", selected=False, overlay_child=None)
    assert views._reels_heart_is_liked(heart) is False


def test_reels_heart_jsonrpc_failure_is_not_liked():
    class CrashingHeart(FakeHeart):
        def get_selected(self):
            raise views.DeviceFacade.JsonRpcError("boom")

        def get_desc(self):
            raise views.DeviceFacade.JsonRpcError("boom")

    heart = CrashingHeart(desc="Like")
    assert views._reels_heart_is_liked(heart) is False


def _grid_with_children(first_child_is_row):
    """Build a fake post list whose raw child(0) is either a post row
    (older builds) or a spacer View (2026-10 build)."""

    class FakeChild:
        def __init__(self, is_row):
            self.is_row = is_row

        def exists(self, *_a, **_kw):
            return self.is_row

    class FakeList:
        def child(self, index=0, className=None, **_kw):
            if index == 0:
                return FakeChild(first_child_is_row)
            if index == 1:
                return FakeChild(not first_child_is_row)
            return FakeChild(False)

    return FakeList()


def test_get_grid_row_on_legacy_layout_without_spacer():
    grid = views.PostsGridView(SimpleNamespace())
    row = grid._get_grid_row(_grid_with_children(first_child_is_row=True), 0)
    assert row.exists()


def test_get_grid_row_on_new_layout_with_gap_spacer():
    grid = views.PostsGridView(SimpleNamespace())
    row = grid._get_grid_row(_grid_with_children(first_child_is_row=False), 0)
    # base must have skipped the spacer at raw index 0
    assert row.exists()


def _profile_view_with_grid(first_child_is_row, rows, last_row_children):
    """Model the grid list raw children precisely: an optional spacer View
    at raw index 0 (when first_child_is_row is False), then `rows` post
    rows, the last one holding last_row_children cells."""

    class FakeCell:
        def exists(self, *_a, **_kw):
            return True

    class FakeRow:
        def __init__(self, n_children, exists=True):
            self.n = n_children
            self._exists = exists

        def exists(self, *_a, **_kw):
            return self._exists

        def child(self, index=0, **_kw):
            if index < self.n:
                return FakeCell()
            return SimpleNamespace(exists=lambda *a, **k: False)

    class Spacer:
        def exists(self, *_a, **_kw):
            return False

    raw_children = []
    if not first_child_is_row:
        raw_children.append(Spacer())
    for r in range(rows):
        n = last_row_children if r == rows - 1 else 3
        raw_children.append(FakeRow(n))
    raw_children.append(Spacer())  # past the last row nothing matches

    class FakeGrid:
        def exists(self, *_a, **_kw):
            return True

        def child(self, index=0, className=None, **_kw):
            if className == views.ClassName.LINEAR_LAYOUT:
                if index < len(raw_children):
                    return raw_children[index]
            return SimpleNamespace(exists=lambda *a, **k: False)

    def find(**kw):
        return FakeGrid()

    obj = views.ProfileView.__new__(views.ProfileView)
    obj.device = SimpleNamespace(find=find)
    return obj


def test_count_photo_in_view_legacy_layout():
    obj = _profile_view_with_grid(
        first_child_is_row=True, rows=3, last_row_children=3
    )
    assert obj.count_photo_in_view() == (3, 0)


def test_count_photo_in_view_new_layout_with_spacer():
    obj = _profile_view_with_grid(
        first_child_is_row=False, rows=3, last_row_children=2
    )
    assert obj.count_photo_in_view() == (2, 2)


def main():
    test_reels_heart_liked_via_selected_flag_still_wins()
    test_reels_heart_liked_via_desc_still_wins()
    test_reels_heart_liked_on_new_layout_only_via_overlay_child()
    test_reels_heart_unliked_on_new_layout_has_no_overlay_child()
    test_reels_heart_jsonrpc_failure_is_not_liked()
    test_get_grid_row_on_legacy_layout_without_spacer()
    test_get_grid_row_on_new_layout_with_gap_spacer()
    test_count_photo_in_view_legacy_layout()
    test_count_photo_in_view_new_layout_with_spacer()
    print("OK")


if __name__ == "__main__":
    main()
