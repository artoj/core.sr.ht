from bs4 import BeautifulSoup
from collections import namedtuple
from jinja2 import Markup, escape
from urllib.parse import urljoin
from pygments import highlight
from pygments.formatters import HtmlFormatter, ClassNotFound
from pygments.lexers import get_lexer_by_name
from urllib.parse import urlparse, urlunparse
import bleach
import html
import mistletoe as m
import re

SRHT_MARKDOWN_VERSION = 6

class SrhtRenderer(m.HTMLRenderer):
    def __init__(self, link_prefix=None, baselevel=1):
        super().__init__()
        self.baselevel = baselevel
        if isinstance(link_prefix, (tuple, list)):
            # If passing a 2 item list/tuple than assume the second
            # item is to be used to fetch raw_blob url's (ie, images)
            try:
                self.link_prefix, self.blob_prefix = link_prefix
            except ValueError:
                self.link_prefix = link_prefix[0]
                self.blob_prefix = link_prefix[0]
        else:
            self.link_prefix = link_prefix
            self.blob_prefix = link_prefix

    def _relative_url(self, url, use_blob=False):
        p = urlparse(url)
        link_prefix = self.link_prefix if not use_blob else self.blob_prefix
        if not link_prefix:
            return url
        if not link_prefix.endswith("/"):
            link_prefix += "/"
        if not p.netloc and not p.scheme and link_prefix:
            path = urljoin(link_prefix, p.path)
            url = urlunparse(('', '', path, p.params, p.query, p.fragment))
        return url

    def render_link(self, token):
        template = '<a href="{target}"{title}>{inner}</a>'
        url = token.target
        if token.title:
            title = ' title="{}"'.format(self.escape_html(token.title))
        else:
            title = ''
        if not url.startswith("#"):
            url = self._relative_url(url)
        target = self.escape_url(url)
        inner = self.render_inner(token)
        return template.format(target=target, title=title, inner=inner)
        if not url.startswith("#"):
            url = self._relative_url(url)
        return f'<a href="{url}"{maybe_title}>{content}</a>'

    def render_image(self, token):
        template = '<img src="{}" alt="{}"{} />'
        url = self._relative_url(token.src, use_blob=True)
        if token.title:
            title = ' title="{}"'.format(self.escape_html(token.title))
        else:
            title = ''
        alt = self.render_to_plain(token)
        return template.format(url, alt, title)

    def render_block_code(self, token):
        template = '<pre><code{attr}>{inner}</code></pre>'
        if token.language:
            try:
                lexer = get_lexer_by_name(token.language, stripall=True)
            except ClassNotFound:
                lexer = None
            if lexer:
                formatter = HtmlFormatter()
                return highlight(token.children[0].content, lexer, formatter)
            else:
                attr = ' class="{}"'.format('language-{}'.format(self.escape_html(token.language)))
        else:
            attr = ''
        inner = html.escape(token.children[0].content)
        return template.format(attr=attr, inner=inner)

    def render_heading(self, token):
        template = '<h{level} id="{_id}">{inner}</h{level}>'
        level = token.level + self.baselevel
        if level > 6:
            level = 6
        inner = self.render_inner(token)
        _id = re.sub(r'[^a-z0-9-_]', '', inner.lower().replace(" ", "-"))
        return template.format(level=level, inner=inner, _id=_id)

def _img_filter(tag, name, value):
    if name in ["alt", "height", "width"]:
        return True
    if name == "src":
        p = urlparse(value)
        return p.scheme in ["http", "https", ""]
    return False

def _input_filter(tag, name, value):
    if name in ["checked", "disabled"]:
        return True
    return name == "type" and value in ["checkbox"]

def _wildcard_filter(tag, name, value):
    return name in ["style", "class", "colspan", "rowspan"]

def add_noopener(html):
    soup = BeautifulSoup(str(html), 'html.parser')
    for a in soup.findAll('a'):
        a['rel'] = 'nofollow noopener'
    return str(soup)

def markdown(text, baselevel=1, link_prefix=None):
    attrs = {
        "h1": ["id"],
        "h2": ["id"],
        "h3": ["id"],
        "h4": ["id"],
        "h5": ["id"],
        "h6": ["id"],
        "img": _img_filter,
        "input": _input_filter,
        "*": _wildcard_filter,
    }
    attrs.update(bleach.sanitizer.ALLOWED_ATTRIBUTES)
    cleaner = bleach.sanitizer.Cleaner(
        tags=bleach.sanitizer.ALLOWED_TAGS + [
            "p", "div", "span", "pre", "hr",
            "dd", "dt", "dl",
            "table", "thead", "tbody", "tr", "th", "td",
            "input",
            "img",
            "q",
            "h1", "h2", "h3", "h4", "h5", "h6",
        ],
        attributes=attrs,
        protocols=[
            'ftp',
            'gemini',
            'gopher',
            'http',
            'https',
            'irc',
            'ircs',
            'mailto',
        ],
        styles=bleach.sanitizer.ALLOWED_STYLES + [
            "margin", "padding",
            "text-align", "font-weight", "text-decoration"
        ]
        + ["padding-{}".format(p) for p in ["left", "right", "bottom", "top"]]
        + ["margin-{}".format(p) for p in ["left", "right", "bottom", "top"]],
        strip=True)
    with SrhtRenderer(link_prefix, baselevel) as renderer:
        html = renderer.render(m.Document(text))
    html = cleaner.clean(html)
    formatter = HtmlFormatter()
    style = formatter.get_style_defs('.highlight') + " .highlight { background: inherit; }"
    return Markup(f"<style>{style}</style>"
            + "<div class='markdown'>"
            + add_noopener(html)
            + "</div>")

Heading = namedtuple("Header", ["level", "name", "id", "children", "parent"])

def extract_toc(markup):
    soup = BeautifulSoup(str(markup), "html5lib")
    cur = top = Heading(
        level=0, children=list(),
        name=None, id=None, parent=None
    )
    for el in soup.descendants:
        try:
            level = ["h1", "h2", "h3", "h4", "h5", "h6"].index(el.name)
        except ValueError:
            continue
        while cur.level >= level:
            cur = cur.parent
        heading = Heading(
            level=level, name=el.text,
            id=el.attrs.get("id"),
            children=list(),
            parent=cur
        )
        cur.children.append(heading)
        cur = heading
    return top.children
