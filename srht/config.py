from configparser import ConfigParser
from werkzeug.local import LocalProxy

_config = None
_throw = 1

config = LocalProxy(lambda: _config)

def load_config():
    global _config
    _config = ConfigParser()
    paths = ["config.ini", "/etc/sr.ht/config.ini"]
    for path in paths:
        try:
            with open(path) as f:
                _config.read_file(f)
            break
        except FileNotFoundError:
            pass

load_config()

def cfg(section, key, default=_throw):
    if _config:
        if section in _config and key in _config[section]:
            return _config.get(section, key)
    if default is _throw:
        raise Exception("Config option [{}] {} not found".format(
            section, key))
    return default

def cfgi(section, key, default=_throw):
    v = cfg(section, key, default)
    if not v or v is default:
        return v
    return int(v)

def cfgb(section, key, default=_throw):
    v = cfg(section, key, default)
    if not v or v is default:
        return v
    if v.lower() in ['true', 'yes', 'on', '1']:
        return True
    if v.lower() in ['false', 'no', 'off', '0']:
        return False
    if default is _throw:
        raise Exception("Config option [{}] {} isn't a boolean value.".format(
            section, key))
    return default

def cfgkeys(section):
    for key in _config[section]:
        yield key

def get_origin(service, external=False, default=_throw):
    """
    Fetches the URL for the requested service.

    external: if true, force the use of the external URL. Otherwise,
    internal-origin is preferred. This is designed for allowing installations
    to access sr.ht services over a different network than the external net.
    """
    if external:
        return cfg(service, "origin", default=default)
    return cfg(service, "internal-origin", default=
            cfg(service, "origin", default=default))
