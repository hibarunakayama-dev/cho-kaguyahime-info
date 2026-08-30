import json
import re
import urllib.request
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlparse


SOURCE_URL = "https://www.news.cho-kaguyahime.com/"
SOURCE_DOMAIN = "www.news.cho-kaguyahime.com"
DATA_FILE = Path("data.json")


class ArticleLinkParser(HTMLParser):

    def __init__(self):
        super().__init__()
        self.items = []
        self.in_link = False
        self.current_url = ""
        self.current_text = ""

    def handle_starttag(self, tag, attrs):

        if tag != "a":
            return

        attributes = dict(attrs)
        href = attributes.get("href", "")

        if not href:
            return

        absolute_url = urljoin(
            SOURCE_URL,
            href
        )

        parsed = urlparse(absolute_url)

        if parsed.netloc != SOURCE_DOMAIN:
            return

        if not re.fullmatch(
            r"/\d+/?",
            parsed.path
        ):
            return

        self.in_link = True
        self.current_url = absolute_url
        self.current_text = ""

    def handle_data(self, data):

        if self.in_link:
            self.current_text += data

    def handle_endtag(self, tag):

        if tag != "a" or not self.in_link:
            return

        title = re.sub(
            r"\s+",
            " ",
            self.current_text
        ).strip()

        if title:
            self.items.append({
                "title": title,
                "url": self.current_url
            })

        self.in_link = False
        self.current_url = ""
        self.current_text = ""


class MetadataParser(HTMLParser):

    def __init__(self):
        super().__init__()

        self.meta = []
        self.times = []

        self.in_script = False
        self.script_type = ""
        self.script_text = ""

    def handle_starttag(self, tag, attrs):

        attributes = dict(attrs)

        if tag == "meta":

            self.meta.append(attributes)

        elif tag == "time":

            datetime_value = attributes.get(
                "datetime"
            )

            if datetime_value:
                self.times.append(
                    datetime_value
                )

        elif tag == "script":

            script_type = attributes.get(
                "type",
                ""
            ).lower()

            if script_type == "application/ld+json":

                self.in_script = True
                self.script_type = script_type
                self.script_text = ""

    def handle_data(self, data):

        if self.in_script:
            self.script_text += data

    def handle_endtag(self, tag):

        if tag == "script" and self.in_script:

            self.in_script = False


def fetch_page(url):

    request = urllib.request.Request(
        url,
        headers={
            "User-Agent":
                "cho-kaguyahime-info/1.0"
        }
    )

    with urllib.request.urlopen(
        request,
        timeout=30
    ) as response:

        return response.read().decode(
            "utf-8",
            errors="replace"
        )


def clean_date(value):

    if not value:
        return None

    value = value.strip()

    # ISO形式
    match = re.search(
        r"(\d{4}-\d{2}-\d{2})",
        value
    )

    if match:
        return match.group(1)

    # 日本語表記
    match = re.search(
        r"(\d{4})年\s*(\d{1,2})月\s*(\d{1,2})日",
        value
    )

    if match:

        year = int(match.group(1))
        month = int(match.group(2))
        day = int(match.group(3))

        return (
            f"{year:04d}-"
            f"{month:02d}-"
            f"{day:02d}"
        )

    return None


def extract_published_date(html):

    parser = MetadataParser()
    parser.feed(html)

    # ① metaタグを確認
    for item in parser.meta:

        key = (
            item.get("property")
            or item.get("name")
            or item.get("itemprop")
            or ""
        ).lower()

        value = (
            item.get("content")
            or ""
        )

        if key in (
            "article:published_time",
            "datepublished",
            "date"
        ):

            date = clean_date(value)

            if date:
                return date

    # ② timeタグを確認
    for value in parser.times:

        date = clean_date(value)

        if date:
            return date

    # ③ JSON-LDを正規表現で確認
    match = re.search(
        r'"datePublished"\s*:\s*"([^"]+)"',
        html,
        re.IGNORECASE
    )

    if match:

        date = clean_date(
            match.group(1)
        )

        if date:
            return date

    return None


def load_data():

    if not DATA_FILE.exists():

        return {
            "updated": "",
            "items": []
        }

    with DATA_FILE.open(
        "r",
        encoding="utf-8"
    ) as file:

        return json.load(file)


def save_data(data):

    temporary_file = DATA_FILE.with_suffix(
        ".json.tmp"
    )

    with temporary_file.open(
        "w",
        encoding="utf-8"
    ) as file:

        json.dump(
            data,
            file,
            ensure_ascii=False,
            indent=2
        )

    temporary_file.replace(DATA_FILE)


def normalize_items(items):

    unique = {}

    for item in items:

        url = item.get(
            "url",
            ""
        ).strip()

        title = item.get(
            "title",
            ""
        ).strip()

        if not url or not title:
            continue

        if url in unique:
            continue

        unique[url] = {
            "title": title,
            "url": url
        }

    return list(
        unique.values()
    )


def main():

    print(
        "===================================="
    )

    print(
        "超かぐや姫！公式NEWS収集"
    )

    print(
        "===================================="
    )

    print(
        f"取得元: {SOURCE_URL}"
    )

    # --------------------------------
    # 1. 一覧ページ取得
    # --------------------------------

    html = fetch_page(
        SOURCE_URL
    )

    print(
        f"一覧ページ取得成功: {len(html):,} bytes"
    )

    parser = ArticleLinkParser()

    parser.feed(html)

    articles = normalize_items(
        parser.items
    )

    print(
        f"検出した記事: {len(articles)} 件"
    )

    # 記事が0件なら絶対に更新しない
    if len(articles) == 0:

        raise RuntimeError(
            "公式NEWSの記事を検出できませんでした。"
            "既存データは変更していません。"
        )

    # --------------------------------
    # 2. 各記事ページから公開日取得
    # --------------------------------

    data = load_data()

    existing_items = data.get(
        "items",
        []
    )

    existing_by_url = {
        item.get("url"): item
        for item in existing_items
        if item.get("url")
    }

    new_count = 0
    date_count = 0

    for index, article in enumerate(
        articles,
        start=1
    ):

        url = article["url"]

        print(
            f"[{index}/{len(articles)}] "
            f"{article['title']}"
        )

        try:

            article_html = fetch_page(
                url
            )

            published_date = (
                extract_published_date(
                    article_html
                )
            )

        except Exception as error:

            print(
                f"  記事取得失敗: {error}"
            )

            published_date = None

        # すでに登録済み
        if url in existing_by_url:

            # 日付が未登録だった場合だけ補完
            if (
                published_date
                and not existing_by_url[url].get(
                    "date"
                )
            ):

                existing_by_url[url]["date"] = (
                    published_date
                )

            continue

        # 新規記事
        item = {

            "date":
                published_date
                or "",

            "category":
                "公式NEWS",

            "title":
                article["title"],

            "summary":
                "超かぐや姫！公式NEWSに掲載された記事です。",

            "source":
                "超かぐや姫！公式NEWS",

            "url":
                url
        }

        existing_items.append(
            item
        )

        existing_by_url[url] = item

        new_count += 1

        if published_date:
            date_count += 1

    # --------------------------------
    # 3. データ更新
    # --------------------------------

    data["items"] = existing_items

    data["updated"] = datetime.now(
        timezone.utc
    ).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )

    save_data(data)

    print(
        "===================================="
    )

    print(
        f"検出記事数: {len(articles)} 件"
    )

    print(
        f"新規追加: {new_count} 件"
    )

    print(
        f"公開日取得: {date_count} 件"
    )

    print(
        f"登録総数: {len(existing_items)} 件"
    )

    print(
        "収集処理成功"
    )

    print(
        "===================================="


    )


if __name__ == "__main__":
    main()
