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

    def child(self, index):
        return self.rows[index]


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
