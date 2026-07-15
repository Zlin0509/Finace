import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable, Optional

import pandas as pd
import requests


NEWS_COLUMNS = ["query", "title", "summary", "published_at", "source", "url"]


@dataclass
class NewsSearchResult:
    items: pd.DataFrame
    query: str
    from_cache: bool = False
    stale: bool = False
    warning: str = ""


class NewsService:
    def __init__(
        self,
        cache_dir: str = "data/cache/news",
        cache_ttl_minutes: int = 30,
        keyword_fetcher: Optional[Callable[[str], pd.DataFrame]] = None,
        global_fetcher: Optional[Callable[[], pd.DataFrame]] = None,
        request_timeout: float = 10.0,
    ):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.cache_ttl = timedelta(minutes=cache_ttl_minutes)
        self.request_timeout = request_timeout
        self.keyword_fetcher = keyword_fetcher or self._fetch_keyword_news
        self.global_fetcher = global_fetcher or self._fetch_global_news

    def search(self, query: str, scope: str = "keyword", limit: int = 20) -> NewsSearchResult:
        query = query.strip()
        if not query:
            return NewsSearchResult(pd.DataFrame(columns=NEWS_COLUMNS), query, warning="请输入检索关键词")
        if scope not in {"keyword", "global"}:
            raise ValueError("scope 必须是 keyword 或 global")
        if limit <= 0:
            raise ValueError("limit 必须大于 0")

        cache_path = self._cache_path(query, scope)
        cached, fetched_at = self._read_cache(cache_path)
        if cached is not None and fetched_at and datetime.now() - fetched_at <= self.cache_ttl:
            return NewsSearchResult(cached.head(limit), query, from_cache=True)

        try:
            raw = self.keyword_fetcher(query) if scope == "keyword" else self.global_fetcher()
            items = self._normalize(raw, query, scope)
            if scope == "global":
                mask = (
                    items["title"].str.contains(query, case=False, na=False, regex=False)
                    | items["summary"].str.contains(query, case=False, na=False, regex=False)
                )
                items = items[mask]
            items = items.sort_values("published_at", ascending=False, na_position="last")
            self._write_cache(cache_path, items)
            return NewsSearchResult(items.head(limit).reset_index(drop=True), query)
        except Exception as exc:
            if cached is not None:
                return NewsSearchResult(
                    cached.head(limit),
                    query,
                    from_cache=True,
                    stale=True,
                    warning=f"实时新闻获取失败，当前展示历史缓存: {exc}",
                )
            return NewsSearchResult(
                pd.DataFrame(columns=NEWS_COLUMNS),
                query,
                warning=f"新闻获取失败: {exc}",
            )

    def _cache_path(self, query: str, scope: str) -> Path:
        digest = hashlib.sha256(f"{scope}:{query}".encode("utf-8")).hexdigest()[:16]
        return self.cache_dir / f"{scope}_{digest}.json"

    def _read_cache(self, path: Path):
        if not path.exists():
            return None, None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            fetched_at = datetime.fromisoformat(payload["fetched_at"])
            frame = pd.DataFrame(payload["items"], columns=NEWS_COLUMNS)
            frame["published_at"] = pd.to_datetime(frame["published_at"], errors="coerce")
            return frame, fetched_at
        except (OSError, ValueError, KeyError, TypeError):
            return None, None

    def _write_cache(self, path: Path, items: pd.DataFrame) -> None:
        serializable = items.copy()
        serializable["published_at"] = serializable["published_at"].apply(
            lambda value: value.isoformat() if pd.notna(value) else None
        )
        payload = {
            "fetched_at": datetime.now().isoformat(),
            "items": serializable.to_dict(orient="records"),
        }
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    @staticmethod
    def _clean_text(value) -> str:
        text = "" if pd.isna(value) else str(value)
        text = re.sub(r"<[^>]+>", "", text)
        return re.sub(r"\s+", " ", text).strip()

    def _fetch_keyword_news(self, query: str) -> pd.DataFrame:
        callback = "fundMasterNewsCallback"
        inner_param = {
            "uid": "",
            "keyword": query,
            "type": ["cmsArticleWebOld"],
            "client": "web",
            "clientType": "web",
            "clientVersion": "curr",
            "param": {
                "cmsArticleWebOld": {
                    "searchScope": "default",
                    "sort": "default",
                    "pageIndex": 1,
                    "pageSize": 50,
                    "preTag": "",
                    "postTag": "",
                }
            },
        }
        response = requests.get(
            "https://search-api-web.eastmoney.com/search/jsonp",
            params={"cb": callback, "param": json.dumps(inner_param, ensure_ascii=False)},
            headers={
                "User-Agent": "Mozilla/5.0 FundMaster/0.1",
                "Referer": f"https://so.eastmoney.com/news/s?keyword={query}",
            },
            timeout=self.request_timeout,
        )
        response.raise_for_status()
        body = response.text.strip()
        prefix = f"{callback}("
        if not body.startswith(prefix) or not body.endswith(")"):
            raise ValueError("东方财富新闻接口返回了无法识别的数据")
        payload = json.loads(body[len(prefix) : -1])
        rows = payload.get("result", {}).get("cmsArticleWebOld", [])
        frame = pd.DataFrame(rows)
        if frame.empty:
            return frame
        frame["新闻链接"] = frame["code"].map(
            lambda code: f"https://finance.eastmoney.com/a/{code}.html"
        )
        frame = frame.rename(
            columns={
                "date": "发布时间",
                "mediaName": "文章来源",
                "title": "新闻标题",
                "content": "新闻内容",
            }
        )
        return frame[["新闻标题", "新闻内容", "发布时间", "文章来源", "新闻链接"]]

    def _fetch_global_news(self) -> pd.DataFrame:
        response = requests.get(
            "https://np-weblist.eastmoney.com/comm/web/getFastNewsList",
            params={
                "client": "web",
                "biz": "web_724",
                "fastColumn": "102",
                "sortEnd": "",
                "pageSize": "200",
            },
            headers={"User-Agent": "Mozilla/5.0 FundMaster/0.1"},
            timeout=self.request_timeout,
        )
        response.raise_for_status()
        rows = response.json().get("data", {}).get("fastNewsList", [])
        frame = pd.DataFrame(rows)
        if frame.empty:
            return frame
        frame["链接"] = frame["code"].map(
            lambda code: f"https://finance.eastmoney.com/a/{code}.html"
        )
        frame = frame.rename(
            columns={"title": "标题", "summary": "摘要", "showTime": "发布时间"}
        )
        return frame[["标题", "摘要", "发布时间", "链接"]]

    def _normalize(self, raw: pd.DataFrame, query: str, scope: str) -> pd.DataFrame:
        if raw is None or raw.empty:
            return pd.DataFrame(columns=NEWS_COLUMNS)

        if scope == "keyword":
            mapping = {
                "新闻标题": "title",
                "新闻内容": "summary",
                "发布时间": "published_at",
                "文章来源": "source",
                "新闻链接": "url",
            }
        else:
            mapping = {
                "标题": "title",
                "摘要": "summary",
                "发布时间": "published_at",
                "链接": "url",
            }

        items = raw.rename(columns=mapping).copy()
        for column in ["title", "summary", "published_at", "source", "url"]:
            if column not in items:
                items[column] = ""
        if scope == "global":
            items["source"] = "东方财富快讯"

        items["query"] = query
        items["title"] = items["title"].map(self._clean_text)
        items["summary"] = items["summary"].map(self._clean_text)
        items["source"] = items["source"].map(self._clean_text)
        items["url"] = items["url"].map(self._clean_text)
        items["published_at"] = pd.to_datetime(items["published_at"], errors="coerce")
        return items[NEWS_COLUMNS].reset_index(drop=True)
