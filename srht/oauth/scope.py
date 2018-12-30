from flask import current_app

class OAuthScope:
    def __init__(self, scope, resolve=True):
        client_id = None
        access = 'read'
        if scope == "*":
            access = 'write'
        if '/' in scope:
            s = scope.split('/')
            if len(s) != 2:
                raise Exception('Invalid OAuth scope syntax')
            client_id = s[0]
            scope = s[1]
        if ':' in scope:
            s = scope.split(':')
            if len(s) != 2:
                raise Exception('Invalid OAuth scope syntax')
            scope = s[0]
            access = s[1]
        oauth_provider = current_app.oauth_provider if current_app else None
        alias = oauth_provider and oauth_provider.get_alias(client_id)
        if not access in ['read', 'write']:
            raise Exception('Invalid scope access {}'.format(access))
        self.client_id = alias or client_id
        self.scope = scope
        self.access = access
        if resolve and scope != "*":
            oauth_provider and oauth_provider.resolve_scope(self)

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
        return self.description if hasattr(self, "description") else self.scope
