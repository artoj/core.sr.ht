from flask import Blueprint, current_app, redirect
from flask_login import current_user
from functools import wraps
from werkzeug.local import LocalProxy

_csrf_bypass_views = set()
_csrf_bypass_blueprints = set()

csrf_bypass_views = LocalProxy(lambda: _csrf_bypass_views)
csrf_bypass_blueprints = LocalProxy(lambda: _csrf_bypass_blueprints)

def csrf_bypass(f):
    if isinstance(f, Blueprint):
        _csrf_bypass_blueprints.update([f])
    else:
        view = '.'.join((f.__module__, f.__name__))
        _csrf_bypass_views.update([view])
    return f

def loginrequired(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not current_user:
            return redirect(current_app.oauth_service.oauth_url(request.url))
        else:
            return f(*args, **kwargs)
    return wrapper
