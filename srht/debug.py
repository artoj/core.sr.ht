from srht.config import cfg, cfgi
import os.path
import sys
import argparse
import importlib


_auto_set_static_folder = object()


def run_service(app, *, static_folder=_auto_set_static_folder):
    if static_folder:
        if static_folder is _auto_set_static_folder:
            mod = sys.modules[app.__module__]
            app.static_folder = os.path.join(
                os.path.dirname(os.path.dirname(mod.__file__)),
                "static")
        else:
            app.static_folder = static_folder

    parser = argparse.ArgumentParser(
        description='Development server for %s' % app.site)
    parser.add_argument(
        '--static',
        action='store_true',
        help="Serve static assets through the development server.")
    args = parser.parse_args()

    if args.static and app.static_folder:
        from werkzeug.wsgi import SharedDataMiddleware

        print("Serving static assets from: {}".format(app.static_folder))
        app.wsgi_app = SharedDataMiddleware(app.wsgi_app, {
            '/static': app.static_folder
        })

    cfg_section = app.site
    app.run(host=cfg(cfg_section, "debug-host"),
            port=cfgi(cfg_section, "debug-port"),
            debug=True)
