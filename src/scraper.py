"""Safe, bounded article fetching and metadata-aware HTML extraction."""
from __future__ import annotations

import ipaddress
import json
import socket
from dataclasses import dataclass, field
from typing import Optional
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from . import config


class ScrapeError(Exception):
    """A safe fetch or useful article extraction could not be completed."""


@dataclass
class ScrapedArticle:
    url: str
    headline: str
    body_text: str
    author: str = ""
    published_at: str = ""
    publisher: str = ""
    description: str = ""
    canonical_url: str = ""
    language: str = ""
    extraction_note: str = ""


HEADERS = {"User-Agent": config.USER_AGENT, "Accept": "text/html,application/xhtml+xml"}
MAX_RESPONSE_BYTES = 2_000_000
MAX_REDIRECTS = 5


def validate_public_url(url: str) -> str:
    """Validate syntax and reject local/private destinations before each request."""
    try:
        parsed = urlparse(url.strip())
        if parsed.scheme.lower() not in ("http", "https") or not parsed.hostname:
            raise ValueError
        if parsed.username or parsed.password:
            raise ValueError
        host = parsed.hostname.rstrip(".").encode("idna").decode("ascii").lower()
        if host in {"localhost", "localhost.localdomain"} or host.endswith(".localhost"):
            raise ScrapeError("Local and internal network addresses cannot be analyzed.")
        try:
            addresses = [ipaddress.ip_address(host)]
        except ValueError:
            try:
                addresses = [ipaddress.ip_address(item[4][0]) for item in socket.getaddrinfo(host, parsed.port or (443 if parsed.scheme == "https" else 80), type=socket.SOCK_STREAM)]
            except OSError as exc:
                raise ScrapeError("The article host could not be resolved.") from exc
        if not addresses or any(not address.is_global for address in addresses):
            raise ScrapeError("Local and internal network addresses cannot be analyzed.")
        # Accessing .port catches malformed/out-of-range ports.
        _ = parsed.port
        return parsed.geturl()
    except ScrapeError:
        raise
    except (ValueError, UnicodeError):
        raise ScrapeError("Please enter a valid public HTTP or HTTPS article URL.")


def _metadata(soup: BeautifulSoup, *keys: str) -> str:
    for key in keys:
        tag = soup.find("meta", attrs={"property": key}) or soup.find("meta", attrs={"name": key})
        if tag and tag.get("content"):
            return tag["content"].strip()[:500]
    return ""


def _jsonld(soup: BeautifulSoup) -> dict:
    for tag in soup.find_all("script", type="application/ld+json"):
        try:
            raw = json.loads(tag.string or tag.get_text())
            objects = raw if isinstance(raw, list) else [raw]
            for item in objects:
                if isinstance(item, dict) and ("Article" in str(item.get("@type", "")) or "NewsArticle" in str(item.get("@type", ""))):
                    return item
        except (ValueError, TypeError):
            continue
    return {}


def extract_article(url: str, html: str) -> ScrapedArticle:
    soup = BeautifulSoup(html, "html.parser")
    ld = _jsonld(soup)
    headline = (ld.get("headline") if isinstance(ld.get("headline"), str) else "") or _metadata(soup, "og:title", "twitter:title")
    headline = headline or (soup.find("h1").get_text(" ", strip=True) if soup.find("h1") else "") or (soup.title.get_text(" ", strip=True) if soup.title else "")
    if not headline:
        raise ScrapeError("The page loaded, but no article headline was found. Try pasting the article text.")
    for tag in soup(["script", "style", "noscript", "nav", "footer", "header", "aside", "form", "svg"]):
        tag.decompose()
    candidates = soup.find_all("article") + soup.select('[itemprop="articleBody"], [class*="article-body"], [class*="article-content"], [class*="story-body"], [class*="post-content"], [class*="entry-content"]')
    candidates.append(soup.body or soup)
    best = ""
    for candidate in candidates:
        paragraphs = [p.get_text(" ", strip=True) for p in candidate.find_all("p")]
        text = "\n".join(p for p in paragraphs if len(p) >= config.MIN_PARAGRAPH_LENGTH)
        if len(text) > len(best):
            best = text
    if len(best) < 120:
        raise ScrapeError("The page loaded, but it did not expose enough article text. It may require JavaScript or a subscription; paste the text to continue.")
    author = ld.get("author", "")
    if isinstance(author, dict):
        author = author.get("name", "")
    elif isinstance(author, list):
        author = ", ".join(a.get("name", "") if isinstance(a, dict) else str(a) for a in author)
    canonical = soup.find("link", rel="canonical")
    return ScrapedArticle(url, headline[:500], best[:500_000], str(author)[:300], str(ld.get("datePublished", "") or _metadata(soup, "article:published_time", "date"))[:100], str(ld.get("publisher", {}).get("name", "") if isinstance(ld.get("publisher"), dict) else ld.get("publisher", ""))[:300], _metadata(soup, "description", "og:description"), urljoin(url, canonical.get("href")) if canonical and canonical.get("href") else "", (soup.html.get("lang", "") if soup.html else "")[:30])


def scrape_article(url: str, timeout: Optional[int] = None) -> ScrapedArticle:
    current = validate_public_url(url)
    timeout = timeout or config.REQUEST_TIMEOUT_SECONDS
    session = requests.Session()
    session.trust_env = False
    try:
        for _ in range(MAX_REDIRECTS + 1):
            current = validate_public_url(current)
            with session.get(current, headers=HEADERS, timeout=(3.05, timeout), allow_redirects=False, stream=True) as response:
                if response.is_redirect or response.is_permanent_redirect:
                    location = response.headers.get("Location")
                    if not location:
                        raise ScrapeError("The publisher returned an invalid redirect.")
                    current = urljoin(current, location)
                    continue
                if response.status_code in (401, 403, 404, 429) or response.status_code >= 500:
                    message = {401: "The publisher requires authorization.", 403: "The publisher blocked automated access.", 404: "The article page was not found.", 429: "The publisher is temporarily rate limiting requests."}.get(response.status_code, "The publisher is temporarily unavailable.")
                    raise ScrapeError(f"{message} You can paste the article text instead.")
                response.raise_for_status()
                if "text/html" not in response.headers.get("Content-Type", "").lower():
                    raise ScrapeError("This URL does not return an HTML article page.")
                if int(response.headers.get("Content-Length", "0") or 0) > MAX_RESPONSE_BYTES:
                    raise ScrapeError("The page is too large to analyze safely.")
                chunks, size = [], 0
                for chunk in response.iter_content(32_768):
                    size += len(chunk)
                    if size > MAX_RESPONSE_BYTES:
                        raise ScrapeError("The page is too large to analyze safely.")
                    chunks.append(chunk)
                response._content = b"".join(chunks)
                response.encoding = response.apparent_encoding or "utf-8"
                return extract_article(current, response.text)
        raise ScrapeError("The page redirected too many times.")
    except ScrapeError:
        raise
    except requests.exceptions.SSLError as exc:
        raise ScrapeError("A secure connection to the publisher could not be established.") from exc
    except requests.exceptions.Timeout as exc:
        raise ScrapeError("The publisher took too long to respond. Paste the article text to continue.") from exc
    except requests.exceptions.RequestException as exc:
        raise ScrapeError("The article could not be fetched. Check the URL or paste the article text.") from exc
    finally:
        session.close()
