from bot.handlers.admin.stats import build_metrics_text
from bot.services.subscription import _xui_error
from bot.services.xui_client import XuiError
from bot.utils import metrics


def test_admin_stats_renders_operational_metrics() -> None:
    metrics.reset()
    metrics.inc(metrics.PAYMENTS_SUCCEEDED, 2)
    metrics.inc(metrics.PAYMENTS_FAILED)
    metrics.inc(metrics.XUI_ERRORS, 3)

    text = build_metrics_text(metrics.snapshot())

    assert "Операционные метрики" in text
    assert "Успешных платежей: 2" in text
    assert "Ошибок платежей: 1" in text
    assert "Ошибок 3x-ui: 3" in text


def test_xui_error_increments_metric_counter() -> None:
    metrics.reset()

    err = _xui_error("add_client", XuiError(500, "boom"))

    assert "VPN-сервером" in err.user_message
    assert metrics.snapshot()[metrics.XUI_ERRORS] == 1
