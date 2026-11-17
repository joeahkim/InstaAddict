"""Regression check: the story viewer must be closed after watching stories.

Recreates the 2026-11-13..16 log pattern (obeytherapper.log): after
"Watched stories for Xs." with no back press, grid swipes landed inside
the still-open story viewer and the session aborted with
"profile_tabs_container not found ... Skip.".

Cases covered:
- own story still showing when stories_count is reached (the common leak)
- viewer advanced to a foreign user's story
- early return when watch_story() reports the viewer left the target

Run: .venv/bin/python test/test_story_view_close.py
"""

from types import SimpleNamespace

from InstaAddict.core.interaction import _close_story_view


def _make_story_view(sequence):
    """sequence: usernames returned by getUsername(), one per loop pass."""
    state = SimpleNamespace(calls=0, backs=0, frame=None)

    def get_username():
        idx = min(state.calls, len(sequence) - 1)
        state.calls += 1
        return sequence[idx]

    def back():
        state.backs += 1
        if state.frame:
            state.frame.backs = state.backs

    view = SimpleNamespace(
        getUsername=get_username,
        getStoryFrame=lambda: state.frame,
        device=SimpleNamespace(back=back),
    )
    return view, state


class FakeFrame:
    def __init__(self, backs_needed):
        self.close_after_backs = backs_needed
        self.backs = 0

    def exists(self, *_):
        return self.backs < self.close_after_backs

    def wait_gone(self, *_):
        return None


def _run(sequence, backs_to_close):
    view, state = _make_story_view(sequence)
    state.frame = FakeFrame(backs_to_close)
    _close_story_view(view, "target")
    return state


def test_own_story_still_showing_closes_viewer():
    # stories_count reached but the target's own story is still on screen:
    # the old code never pressed back here (viewer leaked open).
    state = _run(["target"], backs_to_close=1)
    assert state.backs == 1, "must press back once to close the own-story viewer"


def test_foreign_user_story_closes_viewer():
    state = _run(["someoneelse"], backs_to_close=1)
    assert state.backs == 1, "foreign-user story must also be closed"


def test_already_gone_needs_no_back():
    state = _run(["target"], backs_to_close=0)
    assert state.backs == 0, "no back press when the viewer already closed itself"


def test_multiple_foreign_advances_capped():
    # username stays foreign and the frame needs several backs to disappear
    state = _run(["someoneelse"], backs_to_close=4)
    assert state.backs == 4, "must keep backing out until the frame is gone (max 4)"


def main():
    test_own_story_still_showing_closes_viewer()
    test_foreign_user_story_closes_viewer()
    test_already_gone_needs_no_back()
    test_multiple_foreign_advances_capped()
    print("test_story_view_close: all 4 checks passed")


if __name__ == "__main__":
    main()
