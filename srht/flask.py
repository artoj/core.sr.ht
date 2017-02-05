from flask import Flask, Response, request, url_for, render_template
from enum import Enum
from srht.config import cfg, cfgi, cfgkeys
from srht.validation import Validation
from srht.database import db
from datetime import datetime
from jinja2 import Markup, FileSystemLoader, ChoiceLoader
import humanize
import decimal
import json
import sys
import os

DATE_FORMAT = "%Y-%m-%dT%H:%M:%S"

humanize.time._now = lambda: datetime.utcnow()

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

class SrhtFlask(Flask):
    def __init__(self, site, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.jinja_env.cache = None
        self.jinja_env.filters['date'] = datef
        self.jinja_loader = ChoiceLoader([
            FileSystemLoader(os.path.join(
                os.path.dirname(__file__),
                "..",
                "templates"
            )),
            FileSystemLoader("templates"),
        ])

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
            return {
                'root': cfg("server", "protocol") + "://" + cfg("server", "domain"),
                'domain': cfg("server", "domain"),
                'protocol': cfg("server", "protocol"),
                'len': len,
                'any': any,
                'request': request,
                'url_for': url_for,
                'cfg': cfg,
                'cfgi': cfgi,
                'cfgkeys': cfgkeys,
                'valid': Validation(request),
                'site': site,
                'site_name': cfg("sr.ht", "site-name"),
            }

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
        return super(SrhtFlask, self).make_response(response)
