from datetime import datetime, timedelta

import pandas as pd

from src.news.service import NEWS_COLUMNS, NewsService


def keyword_news():
    return pd.DataFrame(
        [
            {
                "新闻标题": "<em>沪深300</em> ETF 资金净流入",
                "新闻内容": "  市场资金持续流入。\r\n",
                "发布时间": "2026-07-15 09:30:00",
                "文章来源": "测试财经",
                "新闻链接": "https://example.com/news/1",
            }
        ]
    )


def test_keyword_search_normalizes_and_caches_results(tmp_path):
    calls = []

    def fetcher(query):
        calls.append(query)
        return keyword_news()

    service = NewsService(cache_dir=tmp_path, keyword_fetcher=fetcher)
    first = service.search("510300")
    second = service.search("510300")

    assert calls == ["510300"]
    assert list(first.items.columns) == NEWS_COLUMNS
    assert first.items.iloc[0]["title"] == "沪深300 ETF 资金净流入"
    assert second.from_cache is True


def test_network_failure_falls_back_to_stale_cache(tmp_path):
    service = NewsService(cache_dir=tmp_path, keyword_fetcher=lambda _query: keyword_news())
    service.search("黄金")

    cache_path = service._cache_path("黄金", "keyword")
    payload = cache_path.read_text(encoding="utf-8")
    old_time = (datetime.now() - timedelta(days=2)).isoformat()
    cache_path.write_text(
        payload.replace(payload.split('"fetched_at": "')[1].split('"')[0], old_time),
        encoding="utf-8",
    )

    def fail(_query):
        raise RuntimeError("upstream unavailable")

    offline = NewsService(cache_dir=tmp_path, keyword_fetcher=fail)
    result = offline.search("黄金")

    assert result.stale is True
    assert len(result.items) == 1
    assert "历史缓存" in result.warning


def test_global_search_filters_title_and_summary(tmp_path):
    global_frame = pd.DataFrame(
        [
            {"标题": "黄金价格上涨", "摘要": "避险需求增加", "发布时间": "2026-07-15", "链接": "a"},
            {"标题": "原油价格下跌", "摘要": "需求回落", "发布时间": "2026-07-14", "链接": "b"},
        ]
    )
    service = NewsService(cache_dir=tmp_path, global_fetcher=lambda: global_frame)
    result = service.search("黄金", scope="global")

    assert result.items["title"].tolist() == ["黄金价格上涨"]
