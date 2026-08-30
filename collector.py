import json
import re
import urllib.request
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path


SOURCE_URL = "https://www.news.cho-kaguyahime.com/"
DATA_FILE = Path("data.json")


class NewsParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.items = []
        self.in_heading = False
        self.in_link = False
        self.current_title = ""
        self.current_url = ""
        self.current_date = ""
        self.capture_link = False

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)

        if tag in ("h2", "h3"):
            self.in_heading = True
            self.current_title = ""

        if tag == "a" and self.in_heading:
            self.in_link = True
            self.current_url = attrs.get("href", "")

    def handle_data(self, data):
        text = data.strip()

        if self.in_heading and text:
            self.current_title += text

    def handle_endtag(self, tag):

        if tag in ("h2", "h3") and self.in_heading:

            title = re.sub(
                r"\s+",
                " ",
                self.current_title
            ).strip()

            if title and len(title) > 2:

                url = self.current_url

                if url.startswith("/"):
                    url = "https://www.news.cho-kaguyahime.com" + url

                if url:
                    self.items.append({
                        "title": title,
                        "url": url
                    })

            self.in_heading = False
            self.in_link = False
            self.current_title = ""
            self.current_url = ""


def fetch_page():

    request = urllib.request.Request(
        SOURCE_URL,
        headers={
            "User-Agent":
            "cho-kaguyahime-info/1.0"
        }
    )

    with urllib.request.urlopen(
        request,
        timeout=20
    ) as response:

        return response.read().decode(
            "utf-8",
            errors="replace"
        )


def load_data():

    if not DATA_FILE.exists():
        return {
            "updated": "",
            "items": []
        }

    with DATA_FILE.open(
        "r",
        encoding="utf-8"
    ) as f:

        return json.load(f)


def main():

    print("公式NEWSを確認します")

    html = fetch_page()

    parser = NewsParser()
    parser.feed(html)

    data = load_data()

    existing_urls = {
        item.get("url")
        for item in data.get("items", [])
    }

    added = 0

    for article in parser.items:

        if article["url"] in existing_urls:
            continue

        data["items"].append({
            "date": datetime.now(
                timezone.utc
            ).strftime("%Y-%m-%d"),

            "category": "公式NEWS",

            "title": article["title"],

            "summary":
                "公式NEWSで掲載されている記事です。",

            "source":
                "超かぐや姫！公式NEWS",

            "url":
                article["url"]
        })

        existing_urls.add(article["url"])

        added += 1

    data["updated"] = datetime.now(
        timezone.utc
    ).strftime("%Y-%m-%dT%H:%M:%SZ")

    with DATA_FILE.open(
        "w",
        encoding="utf-8"
    ) as f:

        json.dump(
            data,
            f,
            ensure_ascii=False,
            indent=2
        )

    print(
        f"確認した記事数: {len(parser.items)}"
    )

    print(
        f"新規追加: {added}"
    )

    print(
        f"登録総数: {len(data['items'])}"
    )


if __name__ == "__main__":
    main()
