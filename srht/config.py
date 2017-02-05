from configparser import ConfigParser

config = ConfigParser()
config.readfp(open('config.ini'))

_throw = 1

def cfg(section, key, default=_throw):
    v = config.get(section, key)
    if not v:
        if default is _throw:
            raise Exception("Config option [{}] {} not found", section, key)
    return v

def cfgi(section, key, default=_throw):
    return int(cfg(section, key, default))

def cfgkeys(section):
    for key in config[section]:
        yield key
