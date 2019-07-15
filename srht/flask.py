DATE_FORMAT = "%Y-%m-%dT%H:%M:%S+00:00"
from flask import Flask, Response, request, url_for, render_template, redirect
from flask import Blueprint, current_app, g, abort, session as flask_session
from flask_login import LoginManager, current_user
from functools import wraps
from enum import Enum
from srht.config import cfg, cfgi, cfgkeys, config, get_origin
from srht.email import mail_exception
from srht.database import db
from srht.markdown import markdown
from srht.validation import Validation
from datetime import datetime, timedelta
from jinja2 import Markup, FileSystemLoader, ChoiceLoader, contextfunction
from jinja2 import escape
from urllib.parse import urlparse, quote_plus
from werkzeug.local import LocalProxy
from werkzeug.routing import UnicodeConverter
from werkzeug.urls import url_quote
import binascii
import hashlib
import inspect
import humanize
import decimal
import bleach
import json
import locale
import sys
import os

class NamespacedSession:
    def __getitem__(self, key):
        return flask_session[f"{current_app.site}:{key}"]

    def __setitem__(self, key, value):
        flask_session[f"{current_app.site}:{key}"] = value

    def __delitem__(self, key):
        del flask_session[f"{current_app.site}:{key}"]

    def get(self, key, *args, **kwargs):
        return flask_session.get(f"{current_app.site}:{key}", *args, **kwargs)

    def set(self, key, *args, **kwargs):
        return flask_session.set(f"{current_app.site}:{key}", *args, **kwargs)

    def setdefault(self, key, *args, **kwargs):
        return flask_session.setdefault(
                f"{current_app.site}:{key}", *args, **kwargs)

    def pop(self, key, *args, **kwargs):
        return flask_session.pop(f"{current_app.site}:{key}", *args, **kwargs)

_session = NamespacedSession()
session = LocalProxy(lambda: _session)

humanize.time._now = lambda: datetime.utcnow()

try:
    locale.setlocale(locale.LC_ALL, 'en_US')
except:
    pass

def date_handler(obj):
    if hasattr(obj, 'strftime'):
        return obj.strftime(DATE_FORMAT)
    if isinstance(obj, decimal.Decimal):
        return "{:.2f}".format(obj)
    if isinstance(obj, Enum):
        return obj.name
    return obj

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
    if '_csrf_token_v2' not in flask_session:
        flask_session['_csrf_token_v2'] = binascii.hexlify(os.urandom(64)).decode()
    return Markup("""<input
        type='hidden'
        name='_csrf_token'
        value='{}' />""".format(escape(flask_session['_csrf_token_v2'])))

_csrf_bypass_views = set()
_csrf_bypass_blueprints = set()

def csrf_bypass(f):
    if isinstance(f, Blueprint):
        _csrf_bypass_blueprints.update([f])
    else:
        view = '.'.join((f.__module__, f.__name__))
        _csrf_bypass_views.update([view])
    return f

def paginate_query(query, results_per_page=15):
    page = request.args.get("page")
    total_results = query.count()
    total_pages = total_results // results_per_page + 1
    if total_results % results_per_page == 0:
        total_pages -= 1
    if page is not None:
        try:
            page = int(page) - 1
            query = query.offset(page * results_per_page)
        except:
            page = 0
    else:
        page = 0
    query = query.limit(results_per_page).all()
    return query, {
        "total_pages": total_pages,
        "page": page + 1,
        "total_results": total_results
    }

class LoginConfig:
    def __init__(self, client_id, client_secret, base_scopes):
        self.client_id = client_id
        self.client_secret = client_secret
        self.base_scopes = base_scopes

    def oauth_url(self, return_to, scopes=[]):
        meta_sr_ht = get_origin("meta.sr.ht", external=True)
        return "{}/oauth/authorize?client_id={}&scopes={}&state={}".format(
            meta_sr_ht, self.client_id, ','.join(self.base_scopes + scopes),
            quote_plus(return_to))

def loginrequired(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not current_user:
            return redirect(current_app.oauth_service.oauth_url(request.url))
        else:
            return f(*args, **kwargs)
    return wrapper

class ModifiedUnicodeConverter(UnicodeConverter):
    """Added ~ and ^ to safe URL characters, otherwise no changes."""
    def to_url(self, value):
        return url_quote(value, charset=self.map.charset, safe='/:~^')

class SrhtFlask(Flask):
    def __init__(self, site, name,
            oauth_service=None, oauth_provider=None, *args, **kwargs):
        super().__init__(name, *args, **kwargs)

        self.site = site

        self.url_map.converters['default'] = ModifiedUnicodeConverter
        self.url_map.converters['string'] = ModifiedUnicodeConverter

        choices = [FileSystemLoader("templates")]

        mod = __import__(name)
        if hasattr(mod, "__path__"):
            path = list(mod.__path__)[0]
            self.mod_path = path
            choices.append(FileSystemLoader(
                os.path.join("/etc", self.site, "templates")))
            choices.append(FileSystemLoader(os.path.join(path, "templates")))
            choices.append(FileSystemLoader(os.path.join(
                os.path.dirname(__file__),
                "templates"
            )))

        self.jinja_env.cache = None
        self.jinja_env.filters['date'] = datef
        self.jinja_env.globals['pagination'] = pagination
        self.jinja_env.globals['icon'] = icon
        self.jinja_env.globals['csrf_token'] = csrf_token
        self.jinja_loader = ChoiceLoader(choices)
        self.secret_key = cfg("sr.ht", "secret-key")

        self.oauth_service = oauth_service
        self.oauth_provider = oauth_provider

        if self.oauth_service:
            from srht.oauth import oauth_blueprint
            self.register_blueprint(oauth_blueprint)

            from srht.oauth.scope import set_client_id
            set_client_id(self.oauth_service.client_id)

        self.login_manager = LoginManager()
        self.login_manager.init_app(self)
        self.login_manager.anonymous_user = lambda: None

        if self.oauth_service and self.oauth_service.User:
            @self.login_manager.user_loader
            def user_loader(username):
                User = self.oauth_service.User
                # TODO: Switch to a session token
                return User.query.filter(
                        User.username == username).one_or_none()

        # TODO: Remove
        self.no_csrf_prefixes = ['/api']

        @self.before_request
        def _csrf_check():
            if request.method != 'POST':
                return
            if request.blueprint in _csrf_bypass_blueprints:
                return
            view = self.view_functions.get(request.endpoint)
            if not view:
                return
            view = "{0}.{1}".format(view.__module__, view.__name__)
            if view in _csrf_bypass_views:
                return
            # TODO: Remove
            for prefix in self.no_csrf_prefixes:
                if request.path.startswith(prefix):
                    return
            token = flask_session.get('_csrf_token_v2', None)
            if not token or token != request.form.get('_csrf_token'):
                abort(403)

        @self.teardown_appcontext
        def expire_db(err):
            db.session.expire_all()

        @self.errorhandler(500)
        def handle_500(e):
            if self.debug:
                raise e
            # shit
            try:
                if hasattr(db, 'session'):
                    db.session.rollback()
                    db.session.close()
                mail_exception(e)
            except Exception as e2:
                # shit shit
                raise e2.with_traceback(e2.__traceback__)
            return render_template("internal_error.html"), 500

        @self.errorhandler(404)
        def handle_404(e):
            if request.path.startswith("/api"):
                return { "errors": [ { "reason": "404 not found" } ] }, 404
            return render_template("not_found.html"), 404

        @self.context_processor
        def inject():
            user_class = (current_user._get_current_object().__class__
                    if current_user else None)
            ctx = {
                'root': cfg(self.site, "origin"),
                'domain': urlparse(cfg(self.site, "origin")).netloc,
                'app': self,
                'len': len,
                'any': any,
                'str': str,
                'request': request,
                'url_for': url_for,
                'cfg': cfg,
                'cfgi': cfgi,
                'cfgkeys': cfgkeys,
                'get_origin': get_origin,
                'valid': Validation(request),
                'site': site,
                'site_name': cfg("sr.ht", "site-name", default=None),
                'environment': cfg("sr.ht", "environment", default="production"),
                'network': self.get_network(),
                'current_user': (user_class.query
                    .filter(user_class.id == current_user.id)
                ).one_or_none() if current_user else None,
                'static_resource': self.static_resource,
            }
            if self.oauth_service:
                ctx.update({
                    "oauth_url": self.oauth_service.oauth_url(
                        request.full_path),
                })
            return ctx

        @self.teardown_appcontext
        def shutdown_session(resp):
            db.session.remove()
            return resp

        @self.template_filter()
        def md(text):
            return markdown(text)

        @self.template_filter()
        def extended_md(text, baselevel=1):
            return markdown(text, ["h1", "h2", "h3", "h4", "h5"], baselevel)

    def static_resource(self, path):
        """
        Given /example.ext, hashes the file and returns /example.hash.ext
        """
        if not hasattr(self, "static_cache"):
            self.static_cache = dict()
        if path in self.static_cache:
            return self.static_cache[path]
        sha256 = hashlib.sha256()
        with open(os.path.join(self.mod_path, path), "rb") as f:
            sha256.update(f.read())
        path, ext = os.path.splitext(path)
        self.static_cache[path] = f"{path}.{sha256.hexdigest()[:8]}{ext}"
        return self.static_cache[path]

    def get_network(self):
        sites = [s for s in config if s.endswith(".sr.ht")]
        categories = dict()
        for site in sites:
            if "servicecategory" in config[site]:
                cat = cfg(site, "servicecategory")
                members = categories.setdefault(cat, list())
                categories[cat].append(site)
        if not hasattr(self, "network_prefs") and len(categories) != 0:
            self.network_prefs = {}
        for cat, members in categories.items():
            prefs = { site: cfgi(site, "serviceweight") for site in members }
            try:
                prefs.update(json.loads(
                    request.cookies.get(f"{cat}-preference", "{}")))
                assert all(isinstance(k, str) for k in prefs.keys())
                assert all(isinstance(v, int) for v in prefs.values())
            except:
                prefs = { site: 0 for site in members }
            if self.site in members:
                prefs[self.site] += 1
                self.network_prefs[cat] = {k: v for k, v in prefs.items()}
                prefs[self.site] = 10000000
            else:
                self.network_prefs[cat] = prefs
            prefs = sorted(((k, v) for k, v in prefs.items()),
                    key=lambda t: t[1], reverse=True)
            sites = [
                site for site in sites
                if site not in members or prefs[0][0] == site
            ]
        return sites

    def make_response(self, rv):
        # Converts responses from dicts to JSON response objects
        response = None

        def jsonify_wrap(obj):
            jsonification = json.dumps(obj, default=date_handler)
            return Response(jsonification, mimetype='application/json')

        if isinstance(rv, tuple) and \
            (isinstance(rv[0], dict) or isinstance(rv[0], list)):
            response = jsonify_wrap(rv[0]), rv[1]
        elif isinstance(rv, dict):
            response = jsonify_wrap(rv)
        elif isinstance(rv, list):
            response = jsonify_wrap(rv)
        else:
            response = rv
        response = super(SrhtFlask, self).make_response(response)

        path = request.path
        if hasattr(self, "network_prefs") and not path.startswith("/api"):
            for key, value in self.network_prefs.items():
                response.set_cookie(f"{key}-preference",
                        json.dumps(value),
                        domain="." + cfg("sr.ht", "site-name"),
                        max_age=60 * 60 * 24 * 365)

        return response
