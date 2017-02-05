from markupsafe import Markup
from urllib import parse
import json

class ValidationError:
    def __init__(self, field, message):
        self.field = field
        self.message = message

    def json(self):
        j = dict()
        if self.field:
            j['field'] = self.field
        if self.message:
            j['reason'] = self.message
        return j

class Validation:
    def __init__(self, request):
        contentType = request.headers.get("Content-Type")
        if contentType and contentType == "application/json":
            self.source = json.loads(request.data.decode('utf-8'))
        else:
            self.source = request.form
        self.request = request
        self.errors = []

    @property
    def ok(self):
        return len(self.errors) == 0

    def cls(self, name):
        return 'has-danger' if any([e for e in self.errors if e.field == name]) else ""

    def summary(self, name=None):
        errors = [e.message for e in self.errors if e.field == name or name == '@all']
        if len(errors) == 0:
            return ''
        if name is None:
            return Markup('<div class="alert alert-danger">{}</div>'
                    .format('<br />'.join(errors)))
        else:
            return Markup('<div class="form-control-feedback">{}</div>'
                    .format('<br />'.join(errors)))

    @property
    def response(self):
        return { "errors": [ e.json() for e in self.errors ] }, 400

    def error(self, message, field=None):
        self.errors.append(ValidationError(field, message))

    def optional(self, name, default=None):
        return self.source.get(name) or default

    def require(self, name, friendly_name=None):
        value = self.source.get(name)
        if not friendly_name:
            friendly_name = name
        if not value:
            self.error('{} is required'.format(friendly_name), field=name)
        return value

    def expect(self, condition, message, field=None):
        if not condition:
            self.error(message, field)

def valid_url(url):
    try:
        u = parse.urlparse(url)
        return bool(u.scheme and u.netloc and u.scheme in ['http', 'https'])
    except:
        return False
