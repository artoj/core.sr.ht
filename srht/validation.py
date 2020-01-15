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
        self.errors = []
        self.status = 400
        if isinstance(request, dict):
            self.source = request
        else:
            contentType = request.headers.get("Content-Type")
            if contentType and contentType == "application/json":
                try:
                    self.source = json.loads(request.data.decode('utf-8'))
                except json.JSONDecodeError:
                    self.error("Invalid JSON provided")
                    self.source = {}
            else:
                self.source = request.form
                self.files = request.files
            self.request = request
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
        if value is None:
            if name in self.source and not allow_none:
                self.error('{} may not be null'.format(name), field=name)
            elif name in self.source and allow_none:
                pass
            else:
                value = default
        if value is not None:
            if cls and issubclass(cls, IntEnum):
                if not isinstance(value, int):
                    self.error('{} should be an int'.format(name), field=name)
                else:
                    try:
                        value = cls(value)
                    except ValueError:
                        self.error('{} is not a valid {}'.format(
                            value, cls.__name__), field=name)
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
        if not isinstance(value, bool) and not value:
            self.error('{} is required'.format(friendly_name), field=name)
        return value

    def expect(self, condition, message, field=None, **kwargs):
        if not condition:
            self.error(message, field, **kwargs)

    def copy(self, valid, field=None):
        for err in self.errors:
            valid.error(err.message, field + "." + err.field)

    def error_for(self, *fields):
        for error in self.errors:
            if error.field in fields:
                return True
        return False

    def __contains__(self, value):
        return value in self.source or value in self.files

def valid_url(url):
    try:
        u = parse.urlparse(url)
        return bool(u.scheme and u.netloc and u.scheme in ['http', 'https'])
    except:
        return False
