from streamlit.testing.v1 import AppTest


def test_sidebar_groups_and_navigation_work():
    app = AppTest.from_file("src/ui/app.py", default_timeout=30).run()

    assert not app.exception
    sidebar_labels = [button.label for button in app.sidebar.button]
    assert sidebar_labels[:9] == [
        "📊 资产全景看板",
        "🔎 深度个基透视",
        "📈 A股行情分析",
        "🧪 量化回测实验室",
        "🧮 定投复利计算器",
        "⚖️ 智能资产配置",
        "📰 市场新闻检索",
        "🤖 AI 智能诊断",
        "⚙️ 全局系统设置",
    ]

    stock_button = next(
        button for button in app.sidebar.button if button.label == "📈 A股行情分析"
    )
    stock_button.click().run(timeout=30)

    assert not app.exception
    assert app.session_state["active_page"] == "📈 A股行情分析"
    assert any(button.label == "查询行情" for button in app.button)

    quant_button = next(
        button for button in app.sidebar.button if button.label == "🧪 量化回测实验室"
    )
    quant_button.click().run(timeout=30)

    assert not app.exception
    assert app.session_state["active_page"] == "🧪 量化回测实验室"
    assert any("量化回测实验室" in markdown.value for markdown in app.markdown)
    assert [tab.label for tab in app.tabs] == [
        "策略择时",
        "自优化分析",
        "周期定投",
    ]
    assert any(
        button.label == "运行 Walk-Forward 自优化" for button in app.button
    )

    settings_button = next(
        button for button in app.sidebar.button if button.label == "⚙️ 全局系统设置"
    )
    settings_button.click().run(timeout=30)

    assert not app.exception
    assert app.session_state["active_page"] == "⚙️ 全局系统设置"
    assert any(button.label == "读取模型列表" for button in app.button)
