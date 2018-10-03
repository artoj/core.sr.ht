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

def cfgkeys(section):
    for key in _config[section]:
        yield key
