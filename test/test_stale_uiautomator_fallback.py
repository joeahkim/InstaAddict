"""Regression tests for the stale-uiautomator2 hierarchy fallbacks.

uiautomator2's selector RPC can go stale (openatx/uiautomator2#689): every
selector query reports not-found / raises UiObjectNotFoundError while
dump_hierarchy keeps returning the real view tree. These tests simulate that
state with fakes and assert the DeviceFacade.View fallbacks:

- exists(): a couple of isolated misses cost nothing (no dump); after the
  miss threshold (or inside an already-proven stale window) a dump-proven
  match returns True.
- get_bounds(): falls back to bounds parsed from the dump node.
- click(): taps the absolute coordinates when the selector click raises.

Run: python -m pytest test/test_stale_uiautomator_fallback.py -q
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from InstaAddict.core.device_facade import DeviceFacade

# Minimal hierarchy around IG's tab bar (resource IDs as shipped in
# com.instagram.android 440.0.0.46.86; trimmed from a crash dump).
HIERARCHY = """<?xml version='1.0' encoding='UTF-8'?>
<hierarchy rotation="0">
  <node index="0" text="" resource-id="" class="android.widget.FrameLayout"
        package="com.instagram.android" content-desc="" checkable="false"
        checked="false" clickable="false" enabled="true" focusable="false"
        focused="false" scrollable="false" long-clickable="false"
        password="false" selected="false" bounds="[0,0][1440,2960]">
    <node index="1" text="" resource-id="com.instagram.android:id/tab_bar"
          class="android.widget.LinearLayout" package="com.instagram.android"
          content-desc="" checkable="false" checked="false" clickable="false"
          enabled="true" focusable="false" focused="false" scrollable="false"
          long-clickable="false" password="false" selected="false"
          bounds="[0,2704][1440,2759]">
      <node index="2" text=""
            resource-id="com.instagram.android:id/profile_tab"
            class="android.widget.FrameLayout" package="com.instagram.android"
            content-desc="Profile" checkable="false" checked="false"
            clickable="true" enabled="true" focusable="true" focused="false"
            scrollable="false" long-clickable="false" password="false"
            selected="false" bounds="[1152,2704][1440,2759]"/>
    </node>
  </node>
</hierarchy>
"""

TAB_BAR_BOUNDS = {"left": 0, "top": 2704, "right": 1440, "bottom": 2759}


class StaleSelector:
    """Simulates the stale uiautomator2 selector: exists() is always False
    and info/click raise like UiObjectNotFoundError."""

    selector = {
        "resourceIdMatches": "(?i)(com.instagram.android:id/tab_bar)",
        "className": "android.widget.LinearLayout",
    }

    def exists(self, timeout=0):
        return False

    @property
    def count(self):
        return 0

    @property
    def info(self):
        raise RuntimeError("UiObjectNotFoundException (stale selector)")

    def click(self, *args, **kwargs):
        raise RuntimeError("UiObjectNotFoundException (stale selector)")


class FreshSelector(StaleSelector):
    """Healthy selector: the node is found through the normal RPC."""

    def exists(self, timeout=0):
        return True

    @property
    def info(self):
        return {"bounds": dict(TAB_BAR_BOUNDS)}

    def click(self, *args, **kwargs):
        return True


class FakeDevice:
    def __init__(self, hierarchy=HIERARCHY):
        self.hierarchy = hierarchy
        self.dump_count = 0
        self.taps = []

    def dump_hierarchy(self):
        self.dump_count += 1
        return self.hierarchy

    def click(self, x, y):
        self.taps.append((x, y))


def make_view(selector, device):
    view = DeviceFacade.View(view=selector, device=device)
    # neutralize randomized timeout scaling for determinism
    DeviceFacade.View.get_ui_timeout = staticmethod(lambda t: 0)
    DeviceFacade.sleep_mode = staticmethod(lambda s: None)
    return view


@pytest.fixture(autouse=True)
def reset_streak():
    DeviceFacade.View._MISS_STREAK = 0
    DeviceFacade.View._STALE_UNTIL = 0.0
    yield
    DeviceFacade.View._MISS_STREAK = 0
    DeviceFacade.View._STALE_UNTIL = 0.0


def test_healthy_engine_never_dumps():
    device = FakeDevice()
    view = make_view(FreshSelector(), device)
    assert view.exists() is True
    assert device.dump_count == 0
    assert DeviceFacade.View._MISS_STREAK == 0


def test_isolated_misses_do_not_dump():
    device = FakeDevice()
    view = make_view(StaleSelector(), device)
    # below the threshold: plain False, no hierarchy dump
    assert view.exists() is False
    assert view.exists() is False
    assert device.dump_count == 0


def test_stale_engine_falls_back_after_threshold():
    device = FakeDevice()
    view = make_view(StaleSelector(), device)
    assert view.exists() is False
    assert view.exists() is False
    # third consecutive miss: dump proves the node is there
    assert view.exists() is True
    assert device.dump_count == 1


def test_stale_window_skips_threshold():
    device = FakeDevice()
    view = make_view(StaleSelector(), device)
    # open a stale window manually (as a previous dump-proven hit would)
    DeviceFacade.View._STALE_UNTIL = float("inf")
    assert view.exists() is True
    assert device.dump_count == 1
    # fixture resets the streak afterwards


def test_get_bounds_falls_back_to_dump():
    device = FakeDevice()
    view = make_view(StaleSelector(), device)
    assert view.get_bounds() == TAB_BAR_BOUNDS


def test_click_taps_coordinates_when_selector_raises():
    device = FakeDevice()
    view = make_view(StaleSelector(), device)
    view.click()
    assert len(device.taps) == 1
    x, y = device.taps[0]
    assert TAB_BAR_BOUNDS["left"] <= x <= TAB_BAR_BOUNDS["right"]
    assert TAB_BAR_BOUNDS["top"] <= y <= TAB_BAR_BOUNDS["bottom"]
