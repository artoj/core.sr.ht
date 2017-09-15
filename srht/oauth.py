_aliases = dict()
_validator = None

def add_alias(name, client_id):
    _aliases[name] = client_id

def set_validator(validator):
    """
    Sets the scope resolver for this application. Provide a function
    fn(self, client_id, scope, access) that returns the human-readable
    description of this scope (if appropriate) and performs any necessarily
    validation. Indicate failure by raising an exception.
    """
    global _validator
    _validator = validator

class OAuthScope:
    def __init__(self, scope):
        client = None
        access = 'read'
        if scope == "*":
            access = 'write'
        if '/' in scope:
            s = scope.split('/')
            if len(s) != 2:
                raise Exception('Invalid OAuth scope syntax')
            client = s[0]
            scope = s[1]
        if ':' in scope:
            s = scope.split(':')
            if len(s) != 2:
                raise Exception('Invalid OAuth scope syntax')
            scope = s[0]
            access = s[1]
        if client in _aliases:
            client = _aliases[client]
        if not access in ['read', 'write']:
            raise Exception('Invalid scope access {}'.format(access))
        self.description = _validator(self, client, scope, access) if _validator else None
        self.client_id = client
        self.scope = scope
        self.access = access

    def __eq__(self, other):
        return self.client_id == other.client_id \
                and self.access == other.access \
                and self.scope == other.scope

    def __repr__(self):
        if self.client_id:
            return '{}/{}:{}'.format(self.client_id, self.scope, self.access)
        return '{}:{}'.format(self.scope, self.access)

    def __hash__(self):
        return hash((self.client_id if self.client_id else None, self.scope, self.access))

    def readver(self):
        if self.client:
            return '{}/{}:{}'.format(self.client_id, self.scope, 'read')
        return '{}:{}'.format(self.scope, 'read')

    def fulfills(self, want):
        if self.scope == "*":
            if want.access == "read":
                return True
            return self.access == "write"
        else:
            return (
                self.scope == want.scope and
                self.client_id == want.client_id and
                self.access == "write" if want.access == "write" else True
            )

    def friendly(self):
        return self.description or ""
