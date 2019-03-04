from markupsafe import Markup
from urllib import parse
from enum import Enum, IntEnum
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
        self.files = dict()
        if isinstance(request, dict):
            self.source = request
        else:
            contentType = request.headers.get("Content-Type")
            if contentType and contentType == "application/json":
                self.source = json.loads(request.data.decode('utf-8'))
            else:
                self.source = request.form
                self.files = request.files
            self.request = request
        self.errors = []
        self.status = 400
        self._kwargs = {
            "valid": self
        }

    @property
    def ok(self):
        return len(self.errors) == 0

    def cls(self, name):
        return 'is-invalid' if any([
            e for e in self.errors if e.field == name
        ]) else ""

    def summary(self, name=None):
        errors = [e.message for e in self.errors if e.field == name or name == '@all']
        if len(errors) == 0:
            return ''
        if name is None:
            return Markup('<div class="alert alert-danger">{}</div>'
                    .format('<br />'.join(errors)))
        else:
            return Markup('<div class="invalid-feedback">{}</div>'
                    .format('<br />'.join(errors)))

    @property
    def response(self):
        return { "errors": [ e.json() for e in self.errors ] }, self.status

    @property
    def kwargs(self):
        return self._kwargs

    def error(self, message, field=None, status=None):
        self.errors.append(ValidationError(field, message))
        if status:
            self.status = status
        return self.response

    def optional(self, name, default=None, cls=None,
            max_file_size=-1, allow_none=False):
        value = self.source.get(name)
        if value is None:
            value = self.files.get(name)
            if value and value.filename:
                if max_file_size >= 0:
                    fbytes = value.read(max_file_size + 1)
                    if len(fbytes) == max_file_size + 1:
                        self.error('{} is too large'.format(name), field=name)
                        value = None
                    else:
                        value = fbytes
                else:
                    value = value.read()
        if not value:
            if name in self.source and value is None and not allow_none:
                self.error('{} may not be null'.format(name), field=name)
            elif name in self.source and value is None and allow_none:
                pass
            else:
                value = default
        if value is not None:
            if cls and issubclass(cls, IntEnum):
                if not isinstance(value, int):
                    self.error('{} should be an int'.format(name), field=name)
                else:
                    value = cls(value)
            elif cls and issubclass(cls, Enum):
                if not isinstance(value, str):
                    self.error("{} should be an str".format(name), field=name)
                else:
                    if value not in (m[0] for m in cls.__members__.items()):
                        self.error("{} should be a valid {}".format(name, cls.__name__),
                                field=name)
                    else:
                        value = cls(value)
            elif cls and not isinstance(value, cls):
                self.error('{} should be a {}'.format(name, cls.__name__), field=name)
        self._kwargs[name] = value
        return value

    def require(self, name, cls=None, friendly_name=None):
        value = self.optional(name, None, cls)
        if not friendly_name:
            friendly_name = name
        if not value:
            self.error('{} is required'.format(friendly_name), field=name)
        return value

    def expect(self, condition, message, field=None, **kwargs):
        if not condition:
            self.error(message, field, **kwargs)

    def copy(self, valid, field=None):
        for err in self.errors:
            valid.error(err.message, field + "." + err.field)

    def __contains__(self, value):
        return value in self.source or value in self.files

def valid_url(url):
    try:
        u = parse.urlparse(url)
        return bool(u.scheme and u.netloc and u.scheme in ['http', 'https'])
    except:
        return False
