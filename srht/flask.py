from flask import Flask, Response, request, url_for, render_template, redirect
from flask import current_app
from flask_login import LoginManager, current_user
from functools import wraps
from enum import Enum
from srht.config import cfg, cfgi, cfgkeys
from srht.validation import Validation
from srht.database import db
from srht.markdown import markdown
from srht.oauth import oauth_blueprint
from datetime import datetime
from jinja2 import Markup, FileSystemLoader, ChoiceLoader, contextfunction
from urllib.parse import urlparse, quote_plus
import inspect
import humanize
import decimal
import bleach
import json
import locale
import sys
import os

DATE_FORMAT = "%Y-%m-%dT%H:%M:%S"

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
    return Markup('<span title="{}">{}</span>'.format(
        d.strftime('%Y-%m-%d %H:%M:%S UTC'),
        humanize.naturaltime(d)))

@contextfunction
def pagination(context):
    template = context.environment.get_template("pagination.html")
    return Markup(template.render(**context.parent))

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
    return query, { "total_pages": total_pages, "page": page + 1 }

class LoginConfig:
    def __init__(self, client_id, client_secret, base_scopes):
        self.client_id = client_id
        self.client_secret = client_secret
        self.base_scopes = base_scopes

    def oauth_url(self, return_to, scopes=[]):
        meta_sr_ht = cfg("network", "meta")
        return "{}/oauth/authorize?client_id={}&scopes={}&state={}".format(
            meta_sr_ht, self.client_id, ','.join(self.base_scopes + scopes),
            quote_plus(return_to))

def loginrequired(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not current_user:
            return redirect(current_app.login_config.oauth_url(request.url))
        else:
            return f(*args, **kwargs)
    return wrapper

class SrhtFlask(Flask):
    def __init__(self, site, name, login_config=None, *args, **kwargs):
        super().__init__(name, *args, **kwargs)

        self.site = site

        choices = [FileSystemLoader("templates")]

        mod = __import__(name)
        if hasattr(mod, "__path__"):
            path = list(mod.__path__)[0]
            choices.append(FileSystemLoader(os.path.join(path, "templates")))
            choices.append(FileSystemLoader(os.path.join(
                os.path.dirname(__file__),
                "templates"
            )))

        self.jinja_env.cache = None
        self.jinja_env.filters['date'] = datef
        self.jinja_env.globals['pagination'] = pagination
        self.jinja_loader = ChoiceLoader(choices)
        self.secret_key = cfg("server", "secret-key")

        self.login_manager = LoginManager()
        self.login_manager.init_app(self)
        self.login_manager.anonymous_user = lambda: None
        self.login_config = None

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
            except:
                # shit shit
                sys.exit(1)
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
                'root': cfg("server", "protocol") + "://" + cfg("server", "domain"),
                'domain': cfg("server", "domain"),
                'protocol': cfg("server", "protocol"),
                'app': self,
                'len': len,
                'any': any,
                'str': str,
                'request': request,
                'url_for': url_for,
                'cfg': cfg,
                'cfgi': cfgi,
                'cfgkeys': cfgkeys,
                'valid': Validation(request),
                'site': site,
                'site_name': cfg("sr.ht", "site-name", default=None),
                'history': self.get_site_history(),
                'current_user': (user_class.query
                    .filter(user_class.id == current_user.id)
                ).one_or_none() if current_user else None,
            }
            if self.login_config:
                ctx.update({
                    "oauth_url": self.login_config.oauth_url(request.full_path),
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

    def configure_meta_auth(self,
            meta_client_id, meta_client_secret,
            base_scopes=["profile"]):
        assert hasattr(self, 'lookup_or_register')
        self.login_config = LoginConfig(
                meta_client_id, meta_client_secret, base_scopes)
        self.register_blueprint(oauth_blueprint)

    def get_site_history(self):
        history = request.cookies.get("history")
        if history:
            try:
                history = json.loads(history)
                if (not isinstance(history, list) or
                        not all([isinstance(h, str) for h in history])):
                    history = []
            except:
                history = []
        else:
            history = []
        history = [h for h in history if cfg("network", h, default=None)]
        defaults = cfgkeys("network")
        ndefaults = len(list(cfgkeys("network")))
        try:
            while len(history) < 5 or ndefaults > len(history):
                n = next(defaults)
                if n not in history:
                    history += [n]
        except StopIteration:
            pass
        return history

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
        history = self.get_site_history()
        history = [self.site] + [h for h in history if h != self.site]
        response.set_cookie(
                "history",
                json.dumps(history),
                domain="." + ".".join(cfg("server", "domain").split('.')[1:]))
        return response
