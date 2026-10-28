import argparse
import json
import os
from http.cookiejar import Cookie, CookieJar
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import HTTPCookieProcessor, Request, build_opener


GRAPHQL_URL = "https://leetcode.com/graphql/"
QUESTION_QUERY = """
query questionData($titleSlug: String!) {
  question(titleSlug: $titleSlug) {
    questionId
    title
    content
    difficulty
    topicTags {
      name
      slug
    }
    isPaidOnly
    stats
  }
}
"""


def _cookie_jar(cookies: dict[str, str]) -> CookieJar:
    jar = CookieJar()
    for name, value in cookies.items():
        jar.set_cookie(
            Cookie(
                version=0,
                name=name,
                value=value,
                port=None,
                port_specified=False,
                domain="leetcode.com",
                domain_specified=True,
                domain_initial_dot=False,
                path="/",
                path_specified=True,
                secure=True,
                expires=None,
                discard=True,
                comment=None,
                comment_url=None,
                rest={},
                rfc2109=False,
            )
        )
    return jar


def scrape_question(
    title_slug: str,
    cookies: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Fetch one LeetCode question through GraphQL.

    Cookies are optional for public questions and should be supplied at runtime
    for authenticated or paid content; they are never persisted by this module.
    """
    if not title_slug or "/" in title_slug or " " in title_slug:
        raise ValueError("title_slug must be a non-empty URL slug.")

    payload = json.dumps(
        {
            "operationName": "questionData",
            "query": QUESTION_QUERY,
            "variables": {"titleSlug": title_slug},
        }
    ).encode("utf-8")
    request = Request(
        GRAPHQL_URL,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Origin": "https://leetcode.com",
            "Referer": f"https://leetcode.com/problems/{title_slug}/",
            "User-Agent": "CodeTracker/1.0",
        },
        method="POST",
    )

    opener = build_opener(HTTPCookieProcessor(_cookie_jar(cookies or {})))
    try:
        with opener.open(request, timeout=30) as response:
            result = json.load(response)
    except HTTPError as exc:
        raise RuntimeError(f"LeetCode GraphQL request failed with HTTP {exc.code}.") from exc
    except URLError as exc:
        raise RuntimeError(f"Could not reach LeetCode GraphQL: {exc.reason}.") from exc

    if result.get("errors"):
        raise RuntimeError(f"LeetCode GraphQL returned errors: {result['errors']}")
    question = result.get("data", {}).get("question")
    if not question:
        raise RuntimeError(f"No question was found for slug {title_slug!r}.")

    return {
        "question_id": int(question["questionId"]),
        "question_title": question["title"],
        "question_url": f"https://leetcode.com/problems/{title_slug}/",
        "difficulty": question["difficulty"],
        "tags": [tag["slug"] for tag in question["topicTags"]],
        "description": question["content"],
        "is_paid_only": question["isPaidOnly"],
        "stats": json.loads(question["stats"]),
    }


def cookies_from_environment() -> dict[str, str]:
    """Load a JSON cookie object from LEETCODE_COOKIES without storing it."""
    raw_cookies = os.environ.get("LEETCODE_COOKIES")
    if not raw_cookies:
        return {}
    try:
        cookies = json.loads(raw_cookies)
    except json.JSONDecodeError as exc:
        raise ValueError("LEETCODE_COOKIES must contain a JSON object.") from exc
    if not isinstance(cookies, dict) or not all(
        isinstance(name, str) and isinstance(value, str)
        for name, value in cookies.items()
    ):
        raise ValueError("LEETCODE_COOKIES must map string names to string values.")
    return cookies


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Fetch and print a LeetCode question through GraphQL."
    )
    parser.add_argument(
        "title_slug",
        help="LeetCode problem slug, such as two-sum",
    )
    args = parser.parse_args()

    question = scrape_question(
        args.title_slug,
        cookies=cookies_from_environment(),
    )
    print(json.dumps(question, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
