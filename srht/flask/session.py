from flask import current_app, session as flask_session
from werkzeug.local import LocalProxy

class NamespacedSession:
    def __getitem__(self, key):
        return flask_session[f"{current_app.site}:{key}"]

    def __setitem__(self, key, value):
        flask_session[f"{current_app.site}:{key}"] = value

    def __delitem__(self, key):
        del flask_session[f"{current_app.site}:{key}"]

    def get(self, key, **kwargs):
        return flask_session.get(f"{current_app.site}:{key}", **kwargs)

    def set(self, key, *args, **kwargs):
        return flask_session.set(f"{current_app.site}:{key}", *args, **kwargs)

    def setdefault(self, key, *args, **kwargs):
        return flask_session.setdefault(
                f"{current_app.site}:{key}", *args, **kwargs)

_session = NamespacedSession()
session = LocalProxy(lambda: _session)
