import sqlalchemy.types as types

class FlagType(types.TypeDecorator):
    """
    Encodes/decodes IntFlags on the fly
    """

    impl = types.Integer()
    cache_ok = True

    def __init__(self, enum):
        self.enum = enum

    def process_bind_param(self, value, dialect):
        return int(value) if value != None else None

    def process_result_value(self, value, dialect):
        return self.enum(value) if value != None else None
