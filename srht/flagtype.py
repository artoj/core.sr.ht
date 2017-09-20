import sqlalchemy.types as types

class FlagType(types.TypeDecorator):
    """
    Encodes/decodes IntFlags on the fly
    """

    impl = types.Integer()

    def __init__(self, enum):
        self.enum = enum

    def process_bind_param(self, value, dialect):
        return int(value)

    def process_result_value(self, value, dialect):
        return self.enum(value)
