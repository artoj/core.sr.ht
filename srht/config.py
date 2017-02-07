from configparser import ConfigParser

config = ConfigParser()

def load_config(name, paths=None):
    global config
    if paths == None:
        paths = [ "config.ini", "/etc/sr.ht/{}.ini".format(name) ]
    for path in paths:
        try:
            config.readfp(open(path))
        except FileNotFoundError:
            pass

_throw = 1

def cfg(section, key, default=_throw):
    v = config.get(section, key) if section in config else None
    if not v:
        if default is _throw:
            raise Exception("Config option [{}] {} not found".format(section, key))
    return v

def cfgi(section, key, default=_throw):
    return int(cfg(section, key, default))

def cfgkeys(section):
    for key in config[section]:
        yield key
