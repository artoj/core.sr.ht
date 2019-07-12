import binascii
import humanize
import os
from flask import current_app, session, g
from datetime import datetime, timedelta
from jinja2 import Markup, contextfunction, escape

humanize.time._now = lambda: datetime.utcnow()

def datef(d):
    if not d:
        return 'Never'
    if isinstance(d, timedelta):
        return Markup('<span title="{}">{}</span>'.format(
            f'{d.seconds} seconds', humanize.naturaltime(d).rstrip(" ago")))
    return Markup('<span title="{}">{}</span>'.format(
        d.strftime('%Y-%m-%d %H:%M:%S UTC'),
        humanize.naturaltime(d)))

icon_cache = {}

def icon(i, cls=""):
    if i in icon_cache:
        svg = icon_cache[i]
        return Markup(f'<span class="icon icon-{i} {cls}">{svg}</span>')
    fa_license = """<!--
        Font Awesome Free 5.3.1 by @fontawesome - https://fontawesome.com
        License - https://fontawesome.com/license/free (Icons: CC BY 4.0, Fonts: SIL OFL 1.1, Code: MIT License)
    -->"""
    path = os.path.join(current_app.mod_path, 'static', 'icons', i + '.svg')
    with open(path) as f:
        svg = f.read()
    icon_cache[i] = svg
    if g and "fa_license" not in g:
        svg += fa_license
        g.fa_license = True
    return Markup(f'<span class="icon icon-{i} {cls}">{svg}</span>')

@contextfunction
def pagination(context):
    template = context.environment.get_template("pagination.html")
    return Markup(template.render(**context.parent))

def csrf_token():
    if '_csrf_token_v2' not in session:
        session['_csrf_token_v2'] = binascii.hexlify(os.urandom(64)).decode()
    return Markup("""<input
        type='hidden'
        name='_csrf_token'
        value='{}' />""".format(escape(session['_csrf_token_v2'])))
