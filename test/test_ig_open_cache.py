from types import SimpleNamespace
from unittest.mock import Mock, patch

from InstaAddict.core import device_facade
from InstaAddict.core.device_facade import DeviceFacade


def _make_device(package="com.instagram.android"):
    backend = Mock()
    backend.app_current.return_value = {"package": package}
    with patch.object(device_facade.uiautomator2, "connect", return_value=backend):
        return DeviceFacade(None, "com.instagram.android")


def test_healthy_result_is_cached_until_scaled_ttl():
    for scale in (1, 2, 3, 0.5):
        device = _make_device()
        clock = Mock(return_value=0.0)
        with (
            patch.object(device_facade, "args", SimpleNamespace(timeout_scale=scale)),
            patch.object(device_facade.time, "monotonic", clock),
        ):
            assert device._ig_is_opened()
            ttl = 30.0 / scale
            clock.return_value = ttl - 0.1
            assert device._ig_is_opened()
            assert device.deviceV2.app_current.call_count == 1
            clock.return_value = ttl
            assert device._ig_is_opened()
            assert device.deviceV2.app_current.call_count == 2


def test_invalid_or_missing_scale_uses_default_ttl():
    device = _make_device()
    for config_args in (
        None,
        SimpleNamespace(),
        *(
            SimpleNamespace(timeout_scale=value)
            for value in (None, "bad", 0, -1, "nan", "inf", "-inf")
        ),
    ):
        with patch.object(device_facade, "args", config_args):
            assert device._ig_open_check_ttl() == 30.0


def test_crash_invalidates_cache_and_recovery_checks_fresh():
    device = _make_device()
    clock = Mock(return_value=0.0)
    with (
        patch.object(device_facade, "args", SimpleNamespace(timeout_scale=2)),
        patch.object(device_facade.time, "monotonic", clock),
    ):
        device.find(text="healthy")
        device.deviceV2.app_current.return_value = {"package": "launcher"}
        clock.return_value = 14.0
        device.find(text="cached")
        assert device.deviceV2.app_current.call_count == 1
        selector_calls = device.deviceV2.call_count
        clock.return_value = 15.0
        try:
            device.find(text="crashed")
        except DeviceFacade.AppHasCrashed:
            pass
        else:
            raise AssertionError("Expected AppHasCrashed")
        assert device._last_ig_open_check == float("-inf")
        assert device.deviceV2.call_count == selector_calls

        def check_if_crash_popup_is_there():
            return device.find(text="crash popup")

        check_if_crash_popup_is_there()
        assert device.deviceV2.app_current.call_count == 3
        device.deviceV2.app_current.return_value = {"package": device.app_id}
        device.find(text="reopened")
        assert device.deviceV2.app_current.call_count == 4
        device.find(text="cached again")
        assert device.deviceV2.app_current.call_count == 4


def main():
    test_healthy_result_is_cached_until_scaled_ttl()
    test_invalid_or_missing_scale_uses_default_ttl()
    test_crash_invalidates_cache_and_recovery_checks_fresh()
    print("OK")


if __name__ == "__main__":
    main()
