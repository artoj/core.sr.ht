import abc
from werkzeug.local import LocalProxy

class AbstractOAuthService(abc.ABC):
    """
    Implements hooks that sr.ht can use to authorize clients to an
    OAuth-enabled API.
    """

    @abc.abstractmethod
    def get_client_id(self):
        """
        Used to add your client ID to scopes with no client ID set.
        """
        pass

    @abc.abstractmethod
    def get_token(self, token, token_hash, scopes):
        """
        Get or create an OAuthToken object. We don't do anything with it but
        hand it back to you; the type can be anything that you find useful.
        """
        pass

class AbstractOAuthProvider(abc.ABC):
    """
    Implements hooks that sr.ht can use to resolve OAuth tokens issued by a
    provider.
    """

    @abc.abstractmethod
    def resolve_scope(self, scope):
        """
        Given a parsed scope, validate its correctness (possibly against your
        database of valid clients, etc) and add any extra metadata you wish.
        Throw exceptions if anything is wrong.
        """
        pass

    @abc.abstractmethod
    def get_alias(self, client_id):
        """
        Given a client_id alias, return the actual client_id (or None).
        """
        pass

_base_service = None
base_service = LocalProxy(lambda: _base_service)
_base_provider = None
base_provider = LocalProxy(lambda: _base_provider)

def set_base_service(base_service):
    global _base_service
    _base_service = base_service

def set_base_provider(base_provider):
    global _base_provider
    _base_provider = base_provider
