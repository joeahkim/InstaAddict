"""Regression checks for the flattened IG 4xx opened-post layout.

The heart (row_feed_button_like) is no longer a descendant of a media
container: it is a flat sibling of the media inside the buttons row, and it
reports its state via selected=true and content-desc "Liked". The old code
found no like button (MEDIA_CONTAINER absent) and the blind heart click in
like_post unliked already-liked posts.

Run: PYTHONPATH=. python test/test_flat_post_layout.py
"""

from types import SimpleNamespace

from InstaAddict.core import views

views.ResourceID = views.resources("com.instagram.android")

MEDIA_IDS = set(views.ResourceID.MEDIA_CONTAINER.split("|"))
LIKE_ID = views.ResourceID.ROW_FEED_BUTTON_LIKE


class FakeView:
    """Minimal stand-in for DeviceFacade.View."""

    def __init__(self, rid=None, desc=None, selected=False, exists=True):
        self.rid = rid
        self.desc = desc
        self._selected = selected
        self._exists = exists

    def exists(self, *_a, **_kw):
        return self._exists

    def get_desc(self):
        return self.desc

    def get_selected(self):
        return self._selected


class JsonRpcCrashView(FakeView):
    def get_selected(self):
        raise views.DeviceFacade.JsonRpcError("boom")

    def get_desc(self):
        raise views.DeviceFacade.JsonRpcError("boom")


def _opened_post_view(find):
    obj = views.OpenedPostView.__new__(views.OpenedPostView)
    obj.device = SimpleNamespace(find=find)
    return obj


def _flat_find(like_button):
    """device.find(): no MEDIA_CONTAINER anywhere, flat like button."""

    def find(**kw):
        pattern = kw.get("resourceIdMatches", "")
        if any(rid in pattern for rid in MEDIA_IDS):
            return FakeView(exists=False)
        if LIKE_ID in pattern:
            return like_button
        return FakeView(exists=False)

    return find


def test_flat_layout_liked_via_selected_flag():
    like_button = FakeView(rid=LIKE_ID, desc="Liked", selected=True)
    obj = _opened_post_view(_flat_find(like_button))
    assert obj._get_post_like_button() is like_button
    liked, button = obj._is_post_liked()
    assert liked is True and button is like_button


def test_flat_layout_liked_via_desc_when_flag_missing():
    like_button = FakeView(rid=LIKE_ID, desc="Liked", selected=False)
    obj = _opened_post_view(_flat_find(like_button))
    assert obj._like_button_is_liked(like_button) is True


def test_flat_layout_not_liked_desc_like():
    like_button = FakeView(rid=LIKE_ID, desc="Like", selected=False)
    obj = _opened_post_view(_flat_find(like_button))
    liked, _ = obj._is_post_liked()
    assert liked is False


def test_liked_detection_survives_rpc_errors():
    like_button = JsonRpcCrashView(rid=LIKE_ID, desc="Liked")
    obj = _opened_post_view(_flat_find(like_button))
    assert obj._like_button_is_liked(like_button) is False


def test_no_like_button_at_all():
    obj = _opened_post_view(_flat_find(FakeView(exists=False)))
    assert obj._get_post_like_button() is None
    liked, button = obj._is_post_liked()
    assert liked is False and button is None


def test_classic_layout_still_preferred():
    """When the media container exists the descendant path is kept."""
    like_button = FakeView(rid=LIKE_ID, desc="Like", selected=False)
    like_button.viewV2 = object()  # descendant hit on first attempt

    def find(**kw):
        pattern = kw.get("resourceIdMatches", "")
        if any(rid in pattern for rid in MEDIA_IDS):
            container = FakeView(exists=True)
            container.down = lambda **_kw: like_button
            return container
        return FakeView(exists=False)

    obj = _opened_post_view(find)
    assert obj._get_post_like_button() is like_button


def test_like_post_does_not_unlike():
    """like_post on an already-liked flat post must not press the heart."""
    like_button = FakeView(rid=LIKE_ID, desc="Liked", selected=True)
    clicked = []
    like_button.click = lambda *a, **kw: clicked.append(1)
    obj = _opened_post_view(_flat_find(like_button))

    def find(**kw):
        pattern = kw.get("resourceIdMatches", "")
        if any(rid in pattern for rid in MEDIA_IDS):
            return FakeView(exists=False)
        if LIKE_ID in pattern:
            return like_button
        return FakeView(exists=False)

    obj.device = SimpleNamespace(find=find)
    assert obj.like_post() is True
    assert clicked == [], "heart was pressed on an already-liked post"


def test_grid_cell_desc_falls_back_to_inner_image_button():
    """navigateToPost reads a silent grid cell but finds the inner desc."""
    inner = FakeView(desc="Photo by Hidden Hand at Row 3, Column 1")
    cell = FakeView()
    cell.ui_info = lambda: {"contentDescription": ""}
    cell.get_bounds = lambda: {"left": 0, "top": 2654, "right": 476, "bottom": 2759}
    cell.click = lambda *a, **kw: None
    row = FakeView()
    row.child = lambda **kw: cell if "index" in kw else FakeView(exists=False)
    post_list = FakeView()
    post_list.child = lambda **kw: (
        row if kw.get("index") == 1 else FakeView(exists=False)
    )
    post_list.wait = lambda *a, **kw: None

    holder = SimpleNamespace(count_items=lambda: 1)

    def find(**kw):
        pattern = kw.get("resourceIdMatches", "")
        if "image_button" in pattern:
            if kw.get("index") == 0:
                inner.get_bounds = lambda: {
                    "left": 0,
                    "top": 2654,
                    "right": 476,
                    "bottom": 2759,
                }
                return inner
            return holder
        return post_list

    obj = views.PostsGridView.__new__(views.PostsGridView)
    obj.device = SimpleNamespace(find=find)

    def patched_open(self):
        return True

    def patched_still_on_profile(self):
        return False

    orig_open = views.OpenedPostView.is_post_opened
    orig_profile = views.PostsGridView._is_still_on_profile
    views.OpenedPostView.is_post_opened = patched_open
    views.PostsGridView._is_still_on_profile = patched_still_on_profile
    try:
        opened, media_type, _ = obj.navigateToPost(0, 1)
    finally:
        views.OpenedPostView.is_post_opened = orig_open
        views.PostsGridView._is_still_on_profile = orig_profile

    assert opened is not None
    assert media_type == views.MediaType.PHOTO, media_type


def main():
    test_flat_layout_liked_via_selected_flag()
    test_flat_layout_liked_via_desc_when_flag_missing()
    test_flat_layout_not_liked_desc_like()
    test_liked_detection_survives_rpc_errors()
    test_no_like_button_at_all()
    test_classic_layout_still_preferred()
    test_like_post_does_not_unlike()
    test_grid_cell_desc_falls_back_to_inner_image_button()
    print("OK")


if __name__ == "__main__":
    main()
