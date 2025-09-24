from smart_display.config import DisplaySettings
from smart_display.display.layout import LayoutManager


def test_layout_areas_cover_display():
    settings = DisplaySettings(width=800, height=480)
    layout = LayoutManager(settings)

    agenda = layout.area("agenda")
    news = layout.area("news")
    market = layout.area("market")

    assert agenda.left == 0 and agenda.top == 0
    assert agenda.right == settings.width
    assert agenda.bottom == news.top
    assert news.bottom == settings.height
    assert market.bottom == settings.height
    assert market.right == settings.width
    assert news.right == market.left
