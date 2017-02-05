from configparser import ConfigParser

config = ConfigParser()
config.readfp(open('config.ini'))

def cfg(section, key):
    return config.get(section, key)

def cfgi(section, key):
    return int(cfg(section, key))
