# The MIT License (MIT)
# 
# Copyright (c) 2014 Selcuk Ayguney
# 
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
# 
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
# 
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

"""
URLify Extension for Python-Markdown
=====================================
Converts URLs in the markdown text to clickable links.
"""

import re
from markdown.preprocessors import Preprocessor
from markdown.extensions import Extension

urlfinder = re.compile(r'((([A-Za-z]{3,9}:(?:\/\/)?)(?:[\-;:&=\+\$,\w]+@)?[A-Za-z0-9\.\-]+(:[0-9]+)?|'
                       r'(?:www\.|[\-;:&=\+\$,\w]+@)[A-Za-z0-9\.\-]+)((?:/[\+~%/\.\w\-_]*)?\??'
                       r'(?:[\-\+=&;%@\.\w_]*)#?(?:[\.!/\\\w]*))?)')


class URLify(Preprocessor):
    def run(self, lines):
        return [urlfinder.sub(r'<\1>', line) for line in lines]


class URLifyExtension(Extension):
    def extendMarkdown(self, md, md_globals):
        md.preprocessors.add('urlify', URLify(md), '_end')
