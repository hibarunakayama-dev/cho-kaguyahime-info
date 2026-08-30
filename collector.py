import json
import re
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin

from bs4 import BeautifulSoup


SOURCE_URL = "https://www.news.cho-kaguyahime.com/"
SOURCE_NAME = "超かぐや姫！公式NEWS"
DATA_FILE = Path("data.json")


DATE_PATTERNS = [
    re.compile(r"(\d{4})年\s*(\d{1,2})月\s*(\d{1,2})日"),
    re.compile(r"(\d{1,2})月\s*(\d{1,2}),\s*(\d{4})"),
    re.compile(r"(\d{1,2})/\s*(\d{1,2})/\s*(\d{4})"),
]


def fetch(url):
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "cho-kaguyahime-info/1.0"
        },
    )

    with urllib.request.urlopen(
        request,
        timeout=30,
    ) as response:
        return response.read().decode(
            "utf-8",
            errors="replace",
        )


def normalize_date(text):
    text = " ".join(text.split())

    for pattern in DATE_PATTERNS:
        match = pattern.search(text)

        if not match:
            continue

        if "年" in match.group(0):
            year, month, day = match.groups()
        else:
            month, day, year = match.groups()

        return f"{year}-{int(month):02d}-{int(day):02d}"

    return None


def extract_articles(html):
    soup = BeautifulSoup(html, "html.parser")

    articles = []
    seen = set()

    for heading in soup.find_all(["h2", "h3"]):
        link = heading.find("a", href=True)

        if not link:
            continue

        title = " ".join(
            link.get_text(" ", strip=True).split()
        )

        if not title or len(title) < 2:
            continue

        url = urljoin(
            SOURCE_URL,
            link["href"],
        )

        if not url.startswith(SOURCE_URL):
            continue

        if url in seen:
            continue

        # 見出し周辺から公開日を探す
        date = None
        node = heading

        for _ in range(6):
            if node is None:
                break

            text = " ".join(
                node.get_text(
                    " ",
                    strip=True,
                ).split()
            )

            date = normalize_date(text)

            if date:
                break

            node = node.parent

        if not date:
            continue

        seen.add(url)

        articles.append(
            {
                "date": date,
                "category": "ニュース",
                "title": title,
                "summary": (
                    "超かぐや姫！公式NEWSに掲載された記事。"
                ),
                "source": SOURCE_NAME,
                "url": url,
            }
        )

    return articles


def load_data():
    if not DATA_FILE.exists():
        return {
            "updated": "",
            "items": [],
        }

    with DATA_FILE.open(
        "r",
        encoding="utf-8",
    ) as f:
        data = json.load(f)

    if not isinstance(data, dict):
        raise RuntimeError(
            "data.jsonの形式が正しくありません。"
        )

    if not isinstance(
        data.get("items"),
        list,
    ):
        raise RuntimeError(
            "data.jsonのitemsが配列ではありません。"
        )

    return data


def save_data(data):
    temporary_file = DATA_FILE.with_suffix(
        ".json.tmp"
    )

    with temporary_file.open(
        "w",
        encoding="utf-8",
    ) as f:
        json.dump(
            data,
            f,
            ensure_ascii=False,
            indent=2,
        )
        f.write("\n")

    temporary_file.replace(DATA_FILE)


def main():
    print("=" * 40)
    print("超かぐや姫！公式NEWS自動収集")
    print("=" * 40)

    print("公式NEWSを取得します")

    try:
        html = fetch(SOURCE_URL)
    except Exception as e:
        raise RuntimeError(
            f"公式NEWSを取得できませんでした: {e}"
        )

    print(
        f"トップページ取得成功: {len(html)} bytes"
    )

    all_articles = []
    seen_urls = set()

    # ページ1から順番に取得
    for page in range(1, 51):

        if page == 1:
            url = SOURCE_URL
        else:
            url = urljoin(
                SOURCE_URL,
                f"page/{page}/",
            )

        print("")
        print(f"--- ページ {page} ---")
        print(url)

        try:
            page_html = fetch(url)
        except Exception as e:
            print(
                f"ページ {page} は終了: {e}"
            )
            break

        articles = extract_articles(page_html)

        print(
            f"記事データ: {len(articles)} 件"
        )

        # 記事がないページに到達したら終了
        if not articles:
            print(
                "記事がないため、ページ取得を終了します。"
            )
            break

        new_count = 0

        for article in articles:
            if article["url"] in seen_urls:
                continue

            seen_urls.add(article["url"])
            all_articles.append(article)
            new_count += 1

        print(
            f"新規URL: {new_count} 件"
        )

    print("")
    print("=" * 40)
    print("公式NEWS取得結果")
    print("=" * 40)

    print(
        f"取得した記事数: {len(all_articles)}"
    )

    if not all_articles:
        raise RuntimeError(
            "公式NEWSの記事を1件も取得できませんでした。"
            "既存データは変更しません。"
        )

    data = load_data()

    existing_items = data["items"]

    existing_urls = {
        item.get("url")
        for item in existing_items
        if isinstance(item, dict)
    }

    added = []

    for article in all_articles:

        if article["url"] in existing_urls:
            continue

        added.append(article)
        existing_urls.add(article["url"])

    print(
        f"既存データ: {len(existing_items)} 件"
    )

    print(
        f"今回取得: {len(all_articles)} 件"
    )

    print(
        f"新しく追加する記事: {len(added)} 件"
    )

    if added:
        # 新しい記事を先頭に追加
        data["items"] = (
            added + existing_items
        )
    else:
        data["items"] = existing_items

    # 更新日時
    data["updated"] = datetime.now(
        timezone.utc
    ).strftime("%Y-%m-%d")

    # JSONとして保存できることを確認
    json.dumps(
        data,
        ensure_ascii=False,
    )

    save_data(data)

    print("")
    print("=" * 40)
    print("更新完了")
    print("=" * 40)

    print(
        f"追加記事数: {len(added)}"
    )

    print(
        f"最終データ件数: {len(data['items'])}"
    )

    print("data.jsonを正常に更新しました。")


if __name__ == "__main__":
    main()
