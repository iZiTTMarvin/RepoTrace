import sys
import types

import pytest

from app.services.tracing import LangfuseExporter


class _ObservationContext:
    def __init__(self, *, fail_enter: bool = False, fail_exit: bool = False):
        self.fail_enter = fail_enter
        self.fail_exit = fail_exit
        self.observation = object()

    def __enter__(self):
        if self.fail_enter:
            raise RuntimeError("exporter enter failed")
        return self.observation

    def __exit__(self, exc_type, exc, tb):
        if self.fail_exit:
            raise RuntimeError("exporter exit failed")
        return False


class _Client:
    def __init__(self, context):
        self.context = context

    def start_as_current_observation(self, **_kwargs):
        return self.context


def _install_fake_langfuse(monkeypatch, context):
    module = types.ModuleType("langfuse")
    module.get_client = lambda: _Client(context)
    monkeypatch.setitem(sys.modules, "langfuse", module)


def test_exporter_setup_failure_falls_back_to_local_trace(monkeypatch):
    _install_fake_langfuse(monkeypatch, _ObservationContext(fail_enter=True))

    with LangfuseExporter(enabled=True).trace("test", {"q": "x"}) as observation:
        assert observation is None


def test_exporter_cleanup_failure_does_not_break_business(monkeypatch):
    _install_fake_langfuse(monkeypatch, _ObservationContext(fail_exit=True))

    with LangfuseExporter(enabled=True).trace("test", {"q": "x"}) as observation:
        assert observation is not None


def test_business_exception_is_not_swallowed_by_exporter(monkeypatch):
    _install_fake_langfuse(monkeypatch, _ObservationContext(fail_exit=True))

    with pytest.raises(ValueError, match="business failed"):
        with LangfuseExporter(enabled=True).trace("test", {"q": "x"}):
            raise ValueError("business failed")
