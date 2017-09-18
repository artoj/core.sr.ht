from configparser import ConfigParser

config = None

def load_config(name, paths=None):
    global config
    config = ConfigParser()
    if paths == None:
        paths = [ "config.ini", "/etc/sr.ht/{}.ini".format(name) ]
    for path in paths:
        try:
            with open(path) as f:
                config.readfp(f)
        except FileNotFoundError:
            pass

def loaded():
    return config != None

_throw = 1

def cfg(section, key, default=_throw):
    if not config:
        return None
    v = config.get(section, key) if section in config and key in config[section] else None
    if not v:
        if default is _throw:
            raise Exception("Config option [{}] {} not found".format(section, key))
    return v

def cfgi(section, key, default=_throw):
    return int(cfg(section, key, default))

def cfgkeys(section):
    for key in config[section]:
        yield key
