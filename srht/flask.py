DATE_FORMAT = "%Y-%m-%dT%H:%M:%S+00:00"
from bs4 import BeautifulSoup
from flask import Flask, Response, request, url_for, render_template, redirect
from flask import Blueprint, current_app, g, abort, session as flask_session
from enum import Enum
from srht.config import cfg, cfgi, cfgkeys, config, get_origin, get_global_domain
from srht.crypto import fernet
from srht.email import mail_exception
from srht.database import db
from srht.markdown import markdown
from srht.validation import Validation
from datetime import datetime, timedelta
from jinja2 import Markup, FileSystemLoader, ChoiceLoader, contextfunction
from jinja2 import escape
from prometheus_client import Histogram, CollectorRegistry, REGISTRY, make_wsgi_app
from prometheus_client.multiprocess import MultiProcessCollector
from timeit import default_timer
from urllib.parse import urlparse, quote_plus
from werkzeug.local import LocalProxy
from werkzeug.routing import UnicodeConverter
from werkzeug.urls import url_quote
try:
    from werkzeug.middleware.dispatcher import DispatcherMiddleware
except ImportError:
    from werkzeug.wsgi import DispatcherMiddleware
import binascii
import bleach
import decimal
import hashlib
import humanize
import inspect
import json
import locale
import os
import psycopg2.errors
import secrets
import sqlalchemy.exc
import sqlalchemy.orm.exc
import sys
import unicodedata

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
            f'{d.seconds} seconds', humanize.naturaldelta(d)))
    return Markup('<span title="{}">{}</span>'.format(
        d.strftime('%Y-%m-%d %H:%M:%S UTC'),
        humanize.naturaltime(d)))

icon_cache = {}

def icon(i, cls=""):
    if i in icon_cache:
        svg = icon_cache[i]
        return Markup(f'<span class="icon icon-{i} {cls}" aria-hidden="true">{svg}</span>')
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
    return Markup(f'<span class="icon icon-{i} {cls}" aria-hidden="true">{svg}</span>')

@contextfunction
def coalesce_search_terms(context):
    ret = ""
    for key in ["search"] + (context.get("search_keys") or []):
        val = context.get(key)
        if val:
            val = quote_plus(val)
            ret += f"&{key}={val}"
    return ret

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
    if page < 0:
        abort(400)
    query = query.limit(results_per_page).all()
    return query, {
        "total_pages": total_pages,
        "page": page + 1,
        "total_results": total_results
    }

def inject_rtl_direction(resp):
    if resp.mimetype == 'text/html':
        html_doc = resp.data.decode('utf8')
        soup = BeautifulSoup(html_doc, 'html.parser')
        if not soup.body:
            return resp
        for el in soup.body.find_all():
            if el.name == 'input' or el.name == 'textarea':
                el.attrs['dir'] = "auto"
                continue
            for ch in el.text:
                if unicodedata.bidirectional(ch) in ('R', 'AL'):
                    el.attrs['dir'] = "auto"
                    break
        resp.data = soup.encode('utf8')
    return resp

class ModifiedUnicodeConverter(UnicodeConverter):
    """Added ~ and ^ to safe URL characters, otherwise no changes."""
    def to_url(self, value):
        return url_quote(value, charset=self.map.charset, safe='/:~^')

class SrhtFlask(Flask):
    def __init__(self, site, name,
            oauth_service=None, oauth_provider=None, *args, **kwargs):
        super().__init__(name, *args, **kwargs)

        self.site = site
        if os.environ.get("prometheus_multiproc_dir"):
            self.metrics_registry = CollectorRegistry()
            MultiProcessCollector(self.metrics_registry)
        else:
            self.metrics_registry = REGISTRY
        self.wsgi_app = DispatcherMiddleware(self.wsgi_app, {
            "/metrics": make_wsgi_app(registry=self.metrics_registry),
        })
        self.metrics = type("metrics", tuple(), {
            m.describe()[0].name: m
            for m in [
                Histogram("request_time", "Duration of HTTP requests", [
                    "method", "route", "status"
                ]),
            ]
        })

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

            try:
                with open(os.path.join(path, "schema.graphqls")) as f:
                    self.graphql_schema = f.read()
                with open(os.path.join(path, "default_query.graphql")) as f:
                    self.graphql_query = f.read()
            except:
                pass

        self.jinja_env.filters['date'] = datef
        self.jinja_env.globals['pagination'] = pagination
        self.jinja_env.globals['icon'] = icon
        self.jinja_env.globals['csrf_token'] = csrf_token
        self.jinja_loader = ChoiceLoader(choices)
        self.secret_key = cfg("sr.ht", "service-key", default=
                cfg("sr.ht", "secret-key", default=None))
        if self.secret_key is None:
            raise Exception("[sr.ht]service-key missing from config")

        self.oauth_service = oauth_service
        self.oauth_provider = oauth_provider

        if self.oauth_service:
            from srht.oauth import oauth_blueprint
            self.register_blueprint(oauth_blueprint)

            from srht.oauth.scope import set_client_id
            set_client_id(self.oauth_service.client_id)

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
            if not token:
                abort(403)
            if not secrets.compare_digest(token, request.form.get('_csrf_token')):
                abort(403)

        @self.teardown_appcontext
        def expire_db(err):
            db.session.expire_all()

        @self.errorhandler(500)
        def handle_500(e):
            if isinstance(e.original_exception, sqlalchemy.exc.InternalError):
                e = e.original_exception.orig
                if isinstance(e, psycopg2.errors.ReadOnlySqlTransaction):
                    return render_template("read_only.html")
            # shit
            try:
                from srht.oauth import current_user
                user = None
                if hasattr(db, 'session'):
                    db.session.rollback()
                    if current_user:
                        user = f"{current_user.canonical_name} " + \
                                f"<{current_user.email}>"
                    db.session.close()
                mail_exception(e, user=user)
            except Exception as e2:
                # shit shit
                raise e2.with_traceback(e2.__traceback__)
            return render_template("internal_error.html"), 500

        @self.errorhandler(401)
        def handle_401(e):
            if request.path.startswith("/api"):
                return { "errors": [ { "reason": "401 unauthorized" } ] }, 401
            return render_template("unauthorized.html"), 401

        @self.errorhandler(404)
        def handle_404(e):
            if request.path.startswith("/api"):
                return { "errors": [ { "reason": "404 not found" } ] }, 404
            return render_template("not_found.html"), 404

        @self.context_processor
        def inject():
            root = get_origin(self.site, external=True)
            ctx = {
                'root': root,
                'domain': urlparse(root).netloc,
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
                'static_resource': self.static_resource,
                'coalesce_search_terms': coalesce_search_terms,
            }
            try:
                from srht.oauth import current_user
                user_class = (current_user._get_current_object().__class__
                        if current_user else None)
                ctx = {
                    **ctx,
                    'current_user': (user_class.query
                        .filter(user_class.id == current_user.id)
                    ).one_or_none() if current_user else None,
                }
            except sqlalchemy.orm.exc.DetachedInstanceError:
                pass # Can happen while cleaning up from 500 errors
            except sqlalchemy.exc.InvalidRequestError:
                pass # Can happen while cleaning up from 500 errors
            if self.oauth_service:
                ctx.update({
                    "oauth_url": self.oauth_service.oauth_url(
                        request.full_path),
                    "logout_url": "{}/logout?return_to={}{}".format(
                        get_origin("meta.sr.ht", external=True),
                        root, quote_plus(request.full_path)),
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
            return markdown(text, baselevel)

        @self.before_request
        def get_session_cookie():
            # TODO: We could probably speed things up by skipping the
            # round-trip until we actually need any user info which isn't
            # present in the user's info cookie
            cookie = request.cookies.get("sr.ht.unified-login.v1")
            if not cookie:
                return
            user_info = json.loads(fernet.decrypt(cookie.encode()).decode())
            g.current_user = self.oauth_service.lookup_user(user_info["name"])

        @self.before_request
        def begin_track_request():
            request._srht_start_time = default_timer()

        @self.after_request
        def track_request(resp):
            if not hasattr(request, "_srht_start_time"):
                return resp
            self.metrics.request_time.labels(
                method=request.method,
                route=request.endpoint,
                status=resp.status_code,
            ).observe(max(default_timer() - request._srht_start_time, 0))
            return inject_rtl_direction(resp)

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

        global_domain = get_global_domain(self.site)
        if "set_current_user" in g and g.set_current_user:
            cookie_key = f"sr.ht.unified-login.v1"
            if not g.current_user:
                # Clear user info cookie
                response.set_cookie(cookie_key, "",
                        domain=global_domain, max_age=0)
            else:
                # Set user info cookie
                user_info = g.current_user.to_dict(first_party=True)
                user_info = json.dumps(user_info)
                response.set_cookie(cookie_key,
                        fernet.encrypt(user_info.encode()).decode(),
                        domain=global_domain,
                        max_age=60 * 60 * 24 * 365)

        path = request.path
        return response

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
        return [
                s for s in config
                if s.endswith(".sr.ht") and s not in [
                    "paste.sr.ht",
                    "pages.sr.ht",
                    "dispatch.sr.ht",
                ]
            ]
