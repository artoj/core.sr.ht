from bs4 import BeautifulSoup
from collections import namedtuple
from jinja2 import Markup
from markdown.extensions.toc import TocExtension
import bleach
import markdown as md
import re

urlregex = re.compile(r'(?i)\b((?:https?://|www\d{0,3}[.]|[a-z0-9.\-]+[.][a-z]{2,4}/)(?:[^\s()<>]|\(([^\s()<>]+|(\([^\s()<>]+\)))*\))+(?:\(([^\s()<>]+|(\([^\s()<>]+\)))*\)|[^\s`!()\[\]{};:\'".,<>?\xab\xbb\u201c\u201d\u2018\u2019]))')

def _input_filter(tag, name, value):
    return name == "type" and value in ["check"]

def _wildcard_filter(tag, name, value):
    if name == "style":
        return True
    if name == "class":
        return value in [
            "row",
            "form-control"
        ] + ["col-md-{}".format(c) for c in range(1, 13)]

def add_noopener(html):
    soup = BeautifulSoup(str(html), "html5lib")
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
        "input": _input_filter,
        "*": _wildcard_filter,
    }
    attrs.update(bleach.sanitizer.ALLOWED_ATTRIBUTES)
    html = bleach.clean(md.markdown(text, extensions=[
            TocExtension(baselevel=baselevel, marker="")
        ]),
        tags=bleach.sanitizer.ALLOWED_TAGS + [
            "p", "div", "span", "pre",
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
    return Markup(add_noopener(html))

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
