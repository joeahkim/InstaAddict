from types import SimpleNamespace
from unittest.mock import patch

from InstaAddict.core import views
from InstaAddict.core.views import PostsGridView

views.ResourceID = views.resources("com.instagram.android")


class FakeCell:
    def __init__(self, description):
        self.description = description
        self.clicked = False

    def exists(self, *_):
        return True

    def ui_info(self):
        return {"contentDescription": self.description}

    def click(self):
        self.clicked = True


class FakeRow:
    def __init__(self, *cells):
        self.cells = cells

    def exists(self, *_):
        return True

    def child(self, index):
        return self.cells[index]


class FakePostList:
    def __init__(self, *rows):
        self.rows = rows

    def wait(self, *_):
        return True

    def child(self, index, className=None, **_):
        # _get_grid_row() filters the row children by the LinearLayout
        # class and probes raw child 0 to detect the gap_binder_group
        # spacer some IG builds insert before the first post row. The
        # fake list has no spacer, so row 0 is a LinearLayout row at
        # raw index 0 and the probe resolves it.
        if className == views.ClassName.LINEAR_LAYOUT:
            if 0 <= index < len(self.rows):
                return self.rows[index]
            return SimpleNamespace(exists=lambda *_: False)
        if 0 <= index < len(self.rows):
            return self.rows[index]
        return SimpleNamespace(exists=lambda *_: False)


def test_first_grid_position_uses_first_list_row():
    first_post = FakeCell("Photo by first_user")
    second_post = FakeCell("Photo by second_user")
    post_list = FakePostList(FakeRow(first_post), FakeRow(second_post))
    grid = PostsGridView(SimpleNamespace(find=lambda **_: post_list))

    class OpenedPost:
        def __init__(self, _device):
            pass

        def is_post_opened(self):
            return True

    with patch.object(views, "OpenedPostView", OpenedPost):
        opened, _, _ = grid.navigateToPost(0, 0)

    assert opened is not None
    assert first_post.clicked
    assert not second_post.clicked


def main():
    test_first_grid_position_uses_first_list_row()
    print("OK")


if __name__ == "__main__":
    main()
