from flask import Flask, Response, request, url_for
from enum import Enum
from srht.config import cfg, cfgi
from srht.validation import Validation
from datetime import datetime
from jinja2 import Markup, FileSystemLoader, ChoiceLoader
import humanize
import decimal
import json
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
                'valid': Validation(request),
                'site': site,
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
