from bs4 import BeautifulSoup
from collections import namedtuple
from jinja2 import Markup, escape
from urllib.parse import urljoin
from pygments import highlight
from pygments.formatters import HtmlFormatter, ClassNotFound
from pygments.lexers import get_lexer_by_name
from urllib.parse import urlparse, urlunparse
import bleach
import misaka as m
import re

SRHT_MARKDOWN_VERSION = 3

class RelativeLinkPrefixRenderer(m.HtmlRenderer):
    def __init__(self, *args, link_prefix=None, **kwargs):
        super().__init__(args, **kwargs)
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

    def image(self, link, title='', alt=''):
        url = self._relative_url(link, use_blob=True)
        maybe_title = f' title="{m.escape_html(title)}"' if title else ''
        maybe_alt = f' title="{m.escape_html(alt)}"' if alt else ''
        return f'<img src="{url}"{maybe_title}{maybe_alt}></img>'

    def link(self, content, url, title=''):
        maybe_title = f' title="{m.escape_html(title)}"' if title else ''
        if not url.startswith("#"):
            url = self._relative_url(url)
        return f'<a href="{url}"{maybe_title}>{content}</a>'

class HighlighterRenderer(m.HtmlRenderer):
    def __init__(self, *args, baselevel=1, **kwargs):
        super().__init__(*args, **kwargs)
        self.baselevel = 1

    def blockcode(self, text, lang):
        try:
            lexer = get_lexer_by_name(lang, stripall=True)
        except ClassNotFound:
            lexer = None
        if lexer:
            formatter = HtmlFormatter()
            return highlight(text, lexer, formatter)
        # default
        return '\n<pre><code>{}</code></pre>\n'.format(
                escape(text.strip()))

    def header(self, content, level):
        level += self.baselevel
        if level > 6:
            level = 6
        _id = re.sub(r'[^a-z0-9-_]', '', content.lower().replace(" ", "-"))
        return f'''\n<h{str(level)} id="{_id}">
            {content}
        </h{str(level)}>\n'''

class CustomRenderer(RelativeLinkPrefixRenderer, HighlighterRenderer):
    pass

urlregex = re.compile(r'(?i)\b((?:https?://|www\d{0,3}[.]|[a-z0-9.\-]+[.][a-z]{2,4}/)(?:[^\s()<>]|\(([^\s()<>]+|(\([^\s()<>]+\)))*\))+(?:\(([^\s()<>]+|(\([^\s()<>]+\)))*\)|[^\s`!()\[\]{};:\'".,<>?\xab\xbb\u201c\u201d\u2018\u2019]))')

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

def markdown(text, tags=[], baselevel=1, link_prefix=None):
    attrs = {
        "h1": ["id"],
        "h2": ["id"],
        "h3": ["id"],
        "h4": ["id"],
        "h5": ["id"],
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
        ] + tags,
        attributes=attrs,
        styles=bleach.sanitizer.ALLOWED_STYLES + [
            "margin", "padding",
            "text-align", "font-weight", "text-decoration"
        ]
        + ["padding-{}".format(p) for p in ["left", "right", "bottom", "top"]]
        + ["margin-{}".format(p) for p in ["left", "right", "bottom", "top"]],
        strip=True)
    renderer = md = m.Markdown(
        CustomRenderer(baselevel=baselevel, link_prefix=link_prefix),
        extensions=(
            'tables', 'fenced-code', 'footnotes', 'strikethrough', 'highlight',
            'quote', 'autolink'))
    html = renderer(text)
    html = cleaner.clean(html)
    formatter = HtmlFormatter()
    style = formatter.get_style_defs('.highlight') + " .highlight { background: inherit; }"
    return Markup(f"<style>{style}</style>" + add_noopener(html))

Heading = namedtuple("Header", ["level", "name", "id", "children", "parent"])

def extract_toc(markup):
    soup = BeautifulSoup(str(markup), "html5lib")
    cur = top = Heading(
        level=0, children=list(),
        name=None, id=None, parent=None
    )
    for el in soup.descendants:
        try:
            level = ["h1", "h2", "h3", "h4", "h5"].index(el.name)
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
