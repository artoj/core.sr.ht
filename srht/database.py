import hashlib
import sys
from alembic import command, context
from alembic.config import Config, CommandLine
from argparse import ArgumentParser
from datetime import datetime
from logging.config import dictConfig
from prometheus_client import Histogram
from sqlalchemy import create_engine, event, engine_from_config, pool
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import scoped_session, sessionmaker
from flask import request
from srht.config import cfg
from timeit import default_timer
from werkzeug.local import LocalProxy

Base = declarative_base()

_db = None
db = LocalProxy(lambda: _db)

_metrics = type("metrics", tuple(), {
    m.describe()[0].name: m
    for m in [
        Histogram("sql_query_duration", "Duration of SQL queries", ('endpoint',)),
    ]
})

class DbSession():
    def __init__(self, connection_string, assign_global=True):
        global Base, _db
        self.engine = create_engine(connection_string)
        self.session = scoped_session(sessionmaker(
            autocommit=False,
            autoflush=False,
            bind=self.engine))
        Base.query = self.session.query_property()
        if assign_global:
            _db = self

    def init(self):
        @event.listens_for(Base, 'before_insert', propagate=True)
        def before_insert(mapper, connection, target):
            if hasattr(target, '_no_autoupdate'):
                return
            if hasattr(target, 'created'):
                target.created = datetime.utcnow()
            if hasattr(target, 'updated'):
                target.updated = datetime.utcnow()

        @event.listens_for(Base, 'before_update', propagate=True)
        def before_update(mapper, connection, target):
            if hasattr(target, '_no_autoupdate'):
                return
            if hasattr(target, 'updated'):
                target.updated = datetime.utcnow()

        @event.listens_for(self.engine, 'before_cursor_execute')
        def before_cursor_execute(conn, cursor, statement,
                    parameters, context, executemany):
            self._execute_start_time = default_timer()

        @event.listens_for(self.engine, 'after_cursor_execute')
        def after_cursor_execute(conn, cursor, statement,
                    parameters, context, executemany):
            endpoint = ""
            if request:
                endpoint = request.endpoint
            _metrics.sql_query_duration.labels(endpoint=endpoint).observe(
                max(default_timer() - self._execute_start_time, 0))

    def create(self):
        Base.metadata.create_all(bind=self.engine)

def alembic(site, alembic_module, argv=None):
    """
    Automatically rigs up the Alembic config and shells out to it.
    """
    cmdline = CommandLine()
    cmdline.parser.add_argument("-a", "--auto",
        action="store_true",
        help="Specify -a to check config for automatic migrations and abort if "
            "unset (generally only package post-upgrade scripts will specify "
            "this)")
    if argv == None:
        argv = sys.argv[1:]
    options = cmdline.parser.parse_args(argv)
    if options.auto:
        if cfg(site, "migrate-on-upgrade", default="no") != "yes":
            print("Skipping automatic database migrations")
            print(f"Set [{site}]migrate-on-upgrade=yes in config.ini to enable")
            sys.exit(0)

    config = Config()
    script_location = list(alembic_module.__path__)[0]
    config.set_main_option("script_location", script_location)
    if site != "core.sr.ht":
        config.set_main_option("sqlalchemy.url", cfg(site, "connection-string"))

    dictConfig({
        "root": { "level": "WARN", "handlers": ["console"] },
        "loggers": {
            "sqlalchemy": { "level": "WARN", "handlers": [] },
            "alembic": { "level": "INFO", "handlers": [] },
        },
        "handlers": {
            "console": {
                "class": "logging.StreamHandler",
                "level": "NOTSET",
                "stream": "ext://sys.stderr",
                "formatter": "generic",
            }
        },
        "formatters": {
            "generic": {
                "format": "%(levelname)-5.5s [%(name)s] %(message)s",
                "datefmt": "%H:%M:%S",
            }
        },
        "version": 1,
    })

    cmdline.run_cmd(config, options)

def alembic_env(version_table="alembic_version"):
    target_metadata = Base.metadata
    config = context.config

    def run_migrations_offline():
        url = config.get_main_option("sqlalchemy.url")
        context.configure(url=url,
                target_metadata=target_metadata,
                include_schemas=True,
                version_table=version_table)

        with context.begin_transaction():
            context.run_migrations()

    def run_migrations_online():
        engine = engine_from_config(
                config.get_section(config.config_ini_section),
                prefix='sqlalchemy.', poolclass=pool.NullPool)

        connection = engine.connect()
        context.configure(connection=connection,
            target_metadata=target_metadata,
            include_schemas=True,
            version_table=version_table)

        try:
            with context.begin_transaction():
                context.run_migrations()
        finally:
            connection.close()

    if context.is_offline_mode():
        run_migrations_offline()
    else:
        run_migrations_online()
