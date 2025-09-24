from smart_display.config import DisplaySettings
from smart_display.display.layout import LayoutManager


def test_layout_areas_cover_display():
    settings = DisplaySettings(width=800, height=480)
    layout = LayoutManager(settings)

    agenda = layout.area("agenda")
    news = layout.area("news")
    market = layout.area("market")

    margin = agenda.left

    assert margin == agenda.top
    assert settings.width - agenda.right == margin
    assert settings.height - news.bottom == margin

    gutter = news.top - agenda.bottom
    assert gutter == market.top - agenda.bottom
    assert gutter == market.left - news.right

    assert news.bottom == market.bottom
    assert agenda.right == market.right
