from __future__ import annotations

import ipaddress
import re
import socket
from dataclasses import dataclass
from html.parser import HTMLParser
from typing import Callable, Iterable
from urllib.parse import urljoin, urlparse

import requests


MAX_ADDITIONAL_SOURCES = 3
MAX_REDIRECTS = 5
MAX_RESPONSE_BYTES = 1_000_000
MAX_EXTRACTED_TEXT = 6_000
CONNECT_TIMEOUT_SECONDS = 5
READ_TIMEOUT_SECONDS = 10
ALLOWED_CONTENT_TYPES = {"text/html", "application/xhtml+xml", "text/plain"}
USER_AGENT = "CRISPY-BITS-Desktop/Business-Source-Reader"


class SupplementarySourceError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class SupplementarySourceResult:
    url: str
    final_url: str
    status: str
    title: str = ""
    summary: str = ""
    text: str = ""
    error: str = ""

    @property
    def succeeded(self) -> bool:
        return self.status == "retrieved"

    def to_dict(self) -> dict[str, str]:
        return {
            "url": self.url,
            "final_url": self.final_url,
            "status": self.status,
            "title": self.title,
            "summary": self.summary,
            "text": self.text,
            "error": self.error,
        }


class _ReadablePageParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.title_parts: list[str] = []
        self.text_parts: list[str] = []
        self.summary = ""
        self._in_title = False
        self._ignored_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.casefold()
        if tag in {"script", "style", "noscript", "svg", "template"}:
            self._ignored_depth += 1
            return
        if self._ignored_depth:
            return
        if tag == "title":
            self._in_title = True
        if tag == "meta":
            values = {str(key).casefold(): str(value or "") for key, value in attrs}
            name = (values.get("name") or values.get("property") or "").casefold()
            if name in {"description", "og:description", "twitter:description"} and not self.summary:
                self.summary = values.get("content", "")

    def handle_endtag(self, tag: str) -> None:
        tag = tag.casefold()
        if tag in {"script", "style", "noscript", "svg", "template"} and self._ignored_depth:
            self._ignored_depth -= 1
            return
        if tag == "title":
            self._in_title = False

    def handle_data(self, data: str) -> None:
        if self._ignored_depth:
            return
        cleaned = _clean_text(data)
        if not cleaned:
            return
        if self._in_title:
            self.title_parts.append(cleaned)
        else:
            self.text_parts.append(cleaned)


def _clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _validate_public_url(
    url: str,
    resolver: Callable[..., list[tuple]] = socket.getaddrinfo,
) -> str:
    cleaned = str(url or "").strip()
    parsed = urlparse(cleaned)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise SupplementarySourceError("Additional sources must use a complete HTTP or HTTPS URL.")
    if parsed.username or parsed.password:
        raise SupplementarySourceError("Additional source URLs cannot contain credentials.")
    try:
        port = parsed.port
    except ValueError as error:
        raise SupplementarySourceError("Additional source URL contains an invalid port.") from error
    if port is not None and port not in {80, 443}:
        raise SupplementarySourceError("Additional source URLs may use only standard HTTP or HTTPS ports.")
    hostname = parsed.hostname.casefold()
    if hostname == "localhost" or hostname.endswith(".localhost"):
        raise SupplementarySourceError("Additional source URL must resolve to a public host.")
    try:
        addresses = {item[4][0].split("%", 1)[0] for item in resolver(hostname, port or 443, type=socket.SOCK_STREAM)}
    except OSError as error:
        raise SupplementarySourceError("Additional source host could not be resolved.") from error
    if not addresses:
        raise SupplementarySourceError("Additional source host did not resolve to an address.")
    for address in addresses:
        try:
            if not ipaddress.ip_address(address).is_global:
                raise SupplementarySourceError("Additional source URL must resolve only to public addresses.")
        except ValueError as error:
            raise SupplementarySourceError("Additional source host returned an invalid address.") from error
    return cleaned


def _decode_page(response: requests.Response, content: bytes) -> tuple[str, str, str]:
    encoding = response.encoding or "utf-8"
    decoded = content.decode(encoding, errors="replace")
    content_type = str(response.headers.get("content-type") or "").split(";", 1)[0].strip().casefold()
    if content_type == "text/plain":
        return "", "", _clean_text(decoded)[:MAX_EXTRACTED_TEXT]
    parser = _ReadablePageParser()
    parser.feed(decoded)
    title = _clean_text(" ".join(parser.title_parts))[:300]
    summary = _clean_text(parser.summary)[:1_000]
    text = _clean_text(" ".join(parser.text_parts))[:MAX_EXTRACTED_TEXT]
    return title, summary, text


def retrieve_supplementary_source(
    url: str,
    *,
    session: requests.Session | None = None,
    resolver: Callable[..., list[tuple]] = socket.getaddrinfo,
) -> SupplementarySourceResult:
    source_url = str(url or "").strip()
    current_url = _validate_public_url(source_url, resolver)
    owned_session = session is None
    client = session or requests.Session()
    try:
        for redirect_count in range(MAX_REDIRECTS + 1):
            response = client.get(
                current_url,
                allow_redirects=False,
                stream=True,
                timeout=(CONNECT_TIMEOUT_SECONDS, READ_TIMEOUT_SECONDS),
                headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml,text/plain;q=0.9"},
            )
            try:
                if response.status_code in {301, 302, 303, 307, 308}:
                    if redirect_count >= MAX_REDIRECTS:
                        raise SupplementarySourceError("Additional source exceeded the redirect limit.")
                    location = str(response.headers.get("location") or "").strip()
                    if not location:
                        raise SupplementarySourceError("Additional source returned a redirect without a destination.")
                    current_url = _validate_public_url(urljoin(current_url, location), resolver)
                    continue
                if not 200 <= response.status_code < 300:
                    raise SupplementarySourceError(f"Additional source returned HTTP {response.status_code}.")
                content_type = str(response.headers.get("content-type") or "").split(";", 1)[0].strip().casefold()
                if content_type and content_type not in ALLOWED_CONTENT_TYPES:
                    raise SupplementarySourceError("Additional source did not return readable public text.")
                try:
                    content_length = int(response.headers.get("content-length") or 0)
                except (TypeError, ValueError):
                    content_length = 0
                if content_length > MAX_RESPONSE_BYTES:
                    raise SupplementarySourceError("Additional source response was larger than the safety limit.")
                content = bytearray()
                for chunk in response.iter_content(chunk_size=16_384):
                    if not chunk:
                        continue
                    content.extend(chunk)
                    if len(content) > MAX_RESPONSE_BYTES:
                        raise SupplementarySourceError("Additional source response exceeded the safety limit.")
                title, summary, text = _decode_page(response, bytes(content))
                if not any((title, summary, text)):
                    raise SupplementarySourceError("Additional source did not contain useful readable text.")
                return SupplementarySourceResult(
                    url=source_url,
                    final_url=current_url,
                    status="retrieved",
                    title=title,
                    summary=summary,
                    text=text,
                )
            finally:
                response.close()
        raise SupplementarySourceError("Additional source exceeded the redirect limit.")
    finally:
        if owned_session:
            client.close()


def retrieve_supplementary_sources(
    urls: Iterable[str],
    *,
    session: requests.Session | None = None,
    resolver: Callable[..., list[tuple]] = socket.getaddrinfo,
) -> list[SupplementarySourceResult]:
    configured = [str(url).strip() for url in urls if str(url).strip()]
    if len(configured) > MAX_ADDITIONAL_SOURCES:
        raise SupplementarySourceError(f"No more than {MAX_ADDITIONAL_SOURCES} additional sources can be processed.")
    results: list[SupplementarySourceResult] = []
    owned_session = session is None
    client = session or requests.Session()
    try:
        for url in configured:
            try:
                results.append(retrieve_supplementary_source(url, session=client, resolver=resolver))
            except (SupplementarySourceError, requests.RequestException, LookupError, OSError, UnicodeError) as error:
                results.append(SupplementarySourceResult(
                    url=url,
                    final_url="",
                    status="unavailable",
                    error=_clean_text(str(error))[:300] or "Additional source could not be retrieved.",
                ))
    finally:
        if owned_session:
            client.close()
    return results
