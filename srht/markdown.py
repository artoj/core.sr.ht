from bs4 import BeautifulSoup
from collections import namedtuple
from jinja2 import Markup
from markdown.extensions.toc import TocExtension
from markdown.extensions.codehilite import CodeHiliteExtension
from gfm import AutolinkExtension, SemiSaneListExtension, SpacedLinkExtension
from gfm import StrikethroughExtension, TaskListExtension
from pygments.formatters import HtmlFormatter
from urllib.parse import urlparse
import bleach
import markdown as md
import re

urlregex = re.compile(r'(?i)\b((?:https?://|www\d{0,3}[.]|[a-z0-9.\-]+[.][a-z]{2,4}/)(?:[^\s()<>]|\(([^\s()<>]+|(\([^\s()<>]+\)))*\))+(?:\(([^\s()<>]+|(\([^\s()<>]+\)))*\)|[^\s`!()\[\]{};:\'".,<>?\xab\xbb\u201c\u201d\u2018\u2019]))')

def _img_filter(tag, name, value):
    if name in ["alt", "height", "width"]:
        return True
    if name == "src":
        p = urlparse(value)
        return p.scheme in ["http", "https"]
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

def markdown(text, tags=[], baselevel=1):
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
        ] + tags,
        attributes=attrs,
        styles=bleach.sanitizer.ALLOWED_STYLES + [
            "margin", "padding",
            "text-align", "font-weight", "text-decoration"
        ]
        + ["padding-{}".format(p) for p in ["left", "right", "bottom", "top"]]
        + ["margin-{}".format(p) for p in ["left", "right", "bottom", "top"]],
        strip=True)
    html = md.markdown(text,
        extensions=[
            AutolinkExtension(),
            CodeHiliteExtension(
                css_class="highlight",
                guess_lang=False,
                linenums=False,
                use_pygments=True),
            SemiSaneListExtension(),
            SpacedLinkExtension(),
            StrikethroughExtension(),
            TaskListExtension(),
            TocExtension(baselevel=baselevel, marker=""),
            "fenced_code"
        ])
    html = cleaner.clean(html)
    formatter = HtmlFormatter()
    style = formatter.get_style_defs('.highlight')
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
