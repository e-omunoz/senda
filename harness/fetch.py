"""Descarga y normalización de fuentes (solo biblioteca estándar).

- RSS/Atom, listados HTML (siguiendo enlaces), foros Discourse (JSON público) y carpetas locales.
- Caché en disco de páginas (para comprobar citas sin volver a descargar).
"""
from __future__ import annotations

import gzip
import hashlib
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path

from .config import CACHE, ROOT, Source

USER_AGENT = "SendaHarness/0.1"
TIMEOUT = 30


@dataclass
class Item:
    id: str
    url: str
    title: str
    text: str
    date: str = ""
    tier: str | None = None       # si es None, se usa el de la fuente
    author: str = ""
    truncated: bool = False
    meta: dict = field(default_factory=dict)

    @property
    def hash(self) -> str:
        return hashlib.sha1(self.text.encode("utf-8")).hexdigest()[:16]


class FetchError(Exception):
    pass


def http_get(url: str, *, headers: dict | None = None, timeout: int = TIMEOUT, user_agent: str | None = None):
    req = urllib.request.Request(url, headers={
        "User-Agent": user_agent or USER_AGENT,
        "Accept": "*/*",
        "Accept-Encoding": "gzip",
        **(headers or {}),
    })
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            body = r.read()
            if r.headers.get("Content-Encoding") == "gzip":
                body = gzip.decompress(body)
            return r.status, dict(r.headers), body
    except urllib.error.HTTPError as e:
        if e.code == 304:
            return 304, dict(e.headers or {}), b""
        raise FetchError(f"HTTP {e.code} en {url}") from e
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise FetchError(f"{type(e).__name__}: {e} en {url}") from e


def _decode(body: bytes, headers: dict | None = None) -> str:
    ct = (headers or {}).get("Content-Type", "")
    m = re.search(r"charset=([\w-]+)", ct)
    for enc in ([m.group(1)] if m else []) + ["utf-8", "latin-1"]:
        try:
            return body.decode(enc)
        except (LookupError, UnicodeDecodeError):
            continue
    return body.decode("utf-8", "replace")


class _TextExtractor(HTMLParser):
    SKIP = {"script", "style", "noscript", "svg", "nav", "footer", "header", "form", "iframe", "template"}
    BLOCK = {"p", "div", "br", "li", "h1", "h2", "h3", "h4", "h5", "tr", "section", "article", "blockquote"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.skip = 0
        self.title = ""
        self._in_title = False
        self.links: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP:
            self.skip += 1
        if tag == "title":
            self._in_title = True
        if tag == "a":
            href = dict(attrs).get("href")
            if href:
                self.links.append(href)
        if tag in self.BLOCK:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in self.SKIP and self.skip:
            self.skip -= 1
        if tag == "title":
            self._in_title = False
        if tag in self.BLOCK:
            self.parts.append("\n")

    def handle_data(self, data):
        if self._in_title:
            self.title += data
        if not self.skip:
            self.parts.append(data)

    def text(self) -> str:
        t = "".join(self.parts)
        t = re.sub(r"[ \t\r\f\v]+", " ", t)
        t = re.sub(r"\n\s*\n+", "\n\n", t)
        return t.strip()


def html_to_text(html: str) -> tuple[str, str, list[str]]:
    """(título, texto, enlaces)."""
    p = _TextExtractor()
    try:
        p.feed(html)
        p.close()
    except Exception:
        pass
    return p.title.strip(), p.text(), p.links


def parse_feed(body: bytes) -> list[Item]:
    """RSS 2.0 o Atom."""
    try:
        root = ET.fromstring(body)
    except ET.ParseError as e:
        raise FetchError(f"feed inválido: {e}") from e
    ns = {"a": "http://www.w3.org/2005/Atom"}
    items: list[Item] = []
    if root.tag.endswith("feed"):
        for e in root.findall("a:entry", ns):
            link = e.find("a:link[@rel='alternate']", ns)
            if link is None:  # ojo: un Element sin hijos es falsy, no usar `or`
                link = e.find("a:link", ns)
            url = link.get("href") if link is not None else ""
            content = (e.findtext("a:content", default="", namespaces=ns)
                       or e.findtext("a:summary", default="", namespaces=ns))
            _, text, _ = html_to_text(content)
            items.append(Item(
                id=e.findtext("a:id", default=url, namespaces=ns) or url, url=url,
                title=e.findtext("a:title", default="", namespaces=ns),
                text=text, date=(e.findtext("a:updated", default="", namespaces=ns)
                                 or e.findtext("a:published", default="", namespaces=ns))[:10],
                author=e.findtext("a:author/a:name", default="", namespaces=ns)))
    else:
        for e in root.iter("item"):
            url = e.findtext("link", default="") or ""
            desc = e.findtext("description", default="") or ""
            enc = e.find("{http://purl.org/rss/1.0/modules/content/}encoded")
            if enc is not None and enc.text:
                desc = enc.text
            _, text, _ = html_to_text(desc)
            items.append(Item(id=e.findtext("guid", default=url) or url, url=url,
                              title=e.findtext("title", default="") or "", text=text,
                              date=_rfc822_to_iso(e.findtext("pubDate", default="") or "")))
    return items


def _rfc822_to_iso(s: str) -> str:
    from email.utils import parsedate_to_datetime
    try:
        return parsedate_to_datetime(s).date().isoformat()
    except Exception:
        return ""


# --------------------------------------------------------------------------- caché de páginas

def cached_page_text(url: str, *, max_age_h: float = 24, user_agent: str | None = None) -> str:
    """Texto de una página (o JSON de Discourse aplanado), con caché en .cache/harness/pages."""
    d = CACHE / "pages"
    d.mkdir(parents=True, exist_ok=True)
    f = d / (hashlib.sha1(url.encode()).hexdigest() + ".txt")
    if f.exists() and time.time() - f.stat().st_mtime < max_age_h * 3600:
        return f.read_text(encoding="utf-8")
    status, headers, body = http_get(url, user_agent=user_agent)
    raw = _decode(body, headers)
    if "json" in headers.get("Content-Type", ""):
        text = raw
    else:
        title, text, _ = html_to_text(raw)
        # Muchos sitios ponen el contenido real en metadatos; se añade sin coste.
        metas = re.findall(r'<meta[^>]+(?:name|property)="(?:description|og:description)"[^>]+content="([^"]*)"', raw)
        text = "\n".join([title] + metas + [text])
    f.write_text(text, encoding="utf-8")
    return text


# --------------------------------------------------------------------------- tipos de fuente

def fetch_source(src: Source, *, user_agent: str | None = None, state: dict | None = None) -> list[Item]:
    kind = src.kind
    if kind in ("rss", "atom"):
        _, headers, body = http_get(src.url, user_agent=user_agent)
        items = parse_feed(body)
    elif kind == "html":
        items = _fetch_html_listing(src, user_agent)
    elif kind == "discourse":
        items = _fetch_discourse(src, user_agent)
    elif kind == "local_dir":
        items = _fetch_local(src)
    else:
        return []
    if src.keywords:
        # Los elementos de listado aún no tienen texto: se filtra por la URL (el slug lleva el título).
        items = [i for i in items if matches_keywords(src, i)]
    for it in items:
        if len(it.text) > src.max_item_chars:
            it.text = it.text[:src.max_item_chars]
            it.truncated = True
    return items


def matches_keywords(src: Source, item: Item) -> bool:
    if not src.keywords:
        return True
    hay = (item.url + " " + item.title + " " + item.text).lower()
    return any(k.lower() in hay for k in src.keywords)


def _fetch_html_listing(src: Source, ua) -> list[Item]:
    _, headers, body = http_get(src.url, user_agent=ua)
    raw = _decode(body, headers)
    title, text, links = html_to_text(raw)
    if not src.link_pattern:
        # La propia página es el elemento (se detectan cambios por hash).
        return [Item(id=src.url, url=src.url, title=title, text=text)]
    pat = re.compile(src.link_pattern)
    urls: list[str] = []
    for href in links:
        full = urllib.parse.urljoin(src.url, href).split("#")[0]
        if pat.search(urllib.parse.urlparse(full).path) and full not in urls:
            urls.append(full)
    items = []
    for u in urls[: max(src.max_items * 3, 10)]:
        items.append(Item(id=u, url=u, title="", text="", meta={"lazy": True}))
    return items


def load_lazy(item: Item, ua=None, max_chars: int = 40000) -> Item:
    """Descarga el contenido de un elemento de listado HTML solo si es nuevo (ahorra peticiones)."""
    if not item.meta.get("lazy"):
        return item
    _, headers, body = http_get(item.url, user_agent=ua)
    title, text, _ = html_to_text(_decode(body, headers))
    item.title, item.text = title, text
    m = re.search(r'"datePublished"\s*:\s*"(\d{4}-\d{2}-\d{2})', _decode(body, headers))
    item.date = m.group(1) if m else ""
    if len(item.text) > max_chars:
        item.text, item.truncated = item.text[:max_chars], True
    item.meta.pop("lazy", None)
    return item


def is_blue_post(post: dict) -> bool:
    """Mensaje de empleado de Blizzard en Discourse."""
    group = (post.get("primary_group_name") or "").lower()
    flair = (post.get("flair_name") or "").lower()
    title = (post.get("user_title") or "").lower()
    return bool(post.get("staff")) or "blizzard" in group or "blizzard" in flair or "blizzard" in title


def _fetch_discourse(src: Source, ua) -> list[Item]:
    base = src.url.rstrip("/")
    parsed = urllib.parse.urlparse(base)
    origin = f"{parsed.scheme}://{parsed.netloc}"
    prefix = parsed.path.split("/c/")[0].split("/t/")[0]  # /en/wow
    if "/t/" in parsed.path:
        topic_ids = [parsed.path.rstrip("/").split("/")[-1]]
    else:
        _, h, body = http_get(base + ".json", user_agent=ua, headers={"Accept": "application/json"})
        data = json.loads(_decode(body, h))
        topics = data.get("topic_list", {}).get("topics", [])
        topic_ids = [str(t["id"]) for t in topics[: src.max_items * 3]]
    items: list[Item] = []
    for tid in topic_ids:
        try:
            _, h, body = http_get(f"{origin}{prefix}/t/{tid}.json", user_agent=ua,
                                  headers={"Accept": "application/json"})
        except FetchError:
            continue
        t = json.loads(_decode(body, h))
        slug = t.get("slug", "")
        for p in t.get("post_stream", {}).get("posts", []):
            blue = is_blue_post(p)
            if src.blue_only and not blue:
                continue
            _, text, _ = html_to_text(p.get("cooked", ""))
            url = f"{origin}{prefix}/t/{slug}/{tid}/{p.get('post_number', 1)}"
            items.append(Item(
                id=f"{tid}/{p.get('id')}", url=url, title=t.get("title", ""), text=text,
                date=(p.get("created_at") or "")[:10], author=p.get("username", ""),
                tier="official" if blue else "community_unverified", meta={"blue": blue}))
        time.sleep(0.5)  # cortesía con el foro
    return items


def _fetch_local(src: Source) -> list[Item]:
    d = (ROOT / src.url).resolve()
    if not d.is_dir():
        return []
    items = []
    for f in sorted(d.rglob("*")):
        if f.suffix.lower() not in (".txt", ".md", ".json") or not f.is_file():
            continue
        raw = f.read_text(encoding="utf-8", errors="replace")
        text = raw
        if f.suffix.lower() == ".json":
            try:
                data = json.loads(raw)
                msgs = data.get("messages", data if isinstance(data, list) else [])
                text = "\n".join(
                    f"[{(m.get('timestamp') or '')[:10]}] {m.get('content', '')}" for m in msgs
                    if isinstance(m, dict))
            except (json.JSONDecodeError, AttributeError):
                pass
        rel = f.relative_to(ROOT).as_posix()
        items.append(Item(id=rel, url=rel, title=f.name, text=text))
    return items
