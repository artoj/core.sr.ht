from srht.config import cfg, cfgi
import os.path
import sys
import argparse
import importlib

_auto_set_static_folder = object()

def configure_static_folder(app, static_folder=_auto_set_static_folder):
    if static_folder:
        if static_folder is _auto_set_static_folder:
            mod = sys.modules[app.__module__]
            app.static_folder = os.path.join(
                os.path.dirname(os.path.dirname(mod.__file__)),
                "static")
        else:
            app.static_folder = static_folder

def configure_static_arguments(parser):
    parser.add_argument(
        '--static',
        action='store_true',
        help="Serve static assets through the development server.")

def configure_static_serving(app, args):
    if args.static and app.static_folder:
        try:
            from werkzeug.wsgi import SharedDataMiddleware
        except ImportError:
            from werkzeug.middleware.shared_data import SharedDataMiddleware

        print("Serving static assets from: {}".format(app.static_folder))
        app.wsgi_app = SharedDataMiddleware(app.wsgi_app, {
            '/static': app.static_folder
        })

def build_parser(app):
    parser = argparse.ArgumentParser(
        description='Development server for %s' % app.site)
    return parser

def run_app(app):
    cfg_section = app.site
    app.run(host=cfg(cfg_section, "debug-host"),
            port=cfgi(cfg_section, "debug-port"),
            debug=True)

def run_service(app, *, static_folder=_auto_set_static_folder):
    configure_static_folder(app, static_folder)
    parser = build_parser(app)
    configure_static_arguments(parser)
    args = parser.parse_args()
    configure_static_serving(app, args)
    run_app(app)
