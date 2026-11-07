from types import SimpleNamespace

from InstaAddict.core import views
from InstaAddict.core.views import PostsViewList

APP_ID = "com.instagram.android"
views.ResourceID = views.resources(APP_ID)
views.configs = SimpleNamespace(args=SimpleNamespace(app_id=APP_ID))


class FakeView:
    def __init__(self, exists):
        self._exists = exists

    def exists(self, *_):
        return self._exists


def _device_with(markers, like_count_text=None):
    """find() answers by resource id: reels markers exist only when the
    viewer is showing, like_count carries the count when present."""
    def find(*, resourceId=None, resourceIdMatches=None, **_):
        if resourceId is not None:
            if resourceId.endswith("like_count") and like_count_text is not None:
                view = FakeView(True)
                view.get_text = lambda: like_count_text
                view.click = lambda: None
                return view
            return FakeView(False)
        if resourceIdMatches in markers:
            return FakeView(True)
        return FakeView(False)

    return SimpleNamespace(find=find)


def test_reels_like_count_button_is_parsed():
    parser = PostsViewList.__new__(PostsViewList)
    expected = {
        "Like number is328. View likes": 328,
        "Like number is12.3K. View likes": 12300,
        "Like number is1.2M. View likes": 1200000,
        "Like number is7. View likes": 7,
    }
    for label, count in expected.items():
        assert parser._get_number_of_likers_from_text(label) == count, label


def test_reels_viewer_reports_likers_from_like_count():
    device = _device_with(
        markers={views.ResourceID.CLIPS_AUTHOR_USERNAME},
        like_count_text="Like number is472. View likes",
    )
    obj = PostsViewList.__new__(PostsViewList)
    obj.device = device
    has_likers, count = obj._find_likers_container()
    assert has_likers
    assert count == 472


def test_reels_viewer_without_like_count_reports_no_likers():
    device = _device_with(
        markers={views.ResourceID.CLIPS_VIEWER_CONTAINER},
        like_count_text=None,
    )
    obj = PostsViewList.__new__(PostsViewList)
    obj.device = device
    has_likers, count = obj._find_likers_container()
    assert not has_likers
    assert count == 0


def test_hidden_chrome_viewer_is_still_detected_as_reels():
    device = _device_with(
        markers={views.ResourceID.CLIPS_VIDEO_CONTAINER},
        like_count_text=None,
    )
    obj = PostsViewList.__new__(PostsViewList)
    obj.device = device
    assert obj._is_reels_layout()


def test_feed_layout_is_not_mistaken_for_reels():
    device = _device_with(markers=set(), like_count_text="1,234")
    obj = PostsViewList.__new__(PostsViewList)
    obj.device = device
    assert not obj._is_reels_layout()
