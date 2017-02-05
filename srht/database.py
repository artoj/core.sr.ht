from sqlalchemy import create_engine, event
from sqlalchemy.orm import scoped_session, sessionmaker
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime
from functools import partial
from werkzeug.local import LocalStack, LocalProxy
from srht.config import cfg

Base = declarative_base()

_db = None
db = LocalProxy(lambda: _db)

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
            if hasattr(target, 'created'):
                target.created = datetime.utcnow()
            if hasattr(target, 'updated'):
                target.updated = datetime.utcnow()

        @event.listens_for(Base, 'before_update', propagate=True)
        def before_update(mapper, connection, target):
            if hasattr(target, 'updated'):
                target.updated = datetime.utcnow()

        Base.metadata.create_all(bind=self.engine)
