import requests
from datetime import datetime
from flask import request, has_request_context
from srht.config import get_origin, cfg
from srht.crypto import encrypt_request_authorization

DATE_FORMAT = "%Y-%m-%dT%H:%M:%SZ"

class GraphQLError(Exception):
    def __init__(self, body):
        self.body = body
        self.errors = body["errors"]

def exec_gql(site, query, user=None, client_id=None, valid=None, **variables):
    """
    Executes a GraphQL query against the given site's GraphQL API. If no user
    is specified, the authenticated user is used. If a validation argument is
    provided, the GraphQL response will be interpreted for errors; otherwise
    any GraphQL error will cause an exception to be thrown.
    """
    origin = cfg(site, "api-origin", default=get_origin(site))

    r = requests.post(f"{origin}/query",
            headers={
                "X-Forwarded-For": ", ".join(request.access_route) if has_request_context() else None,
                **encrypt_request_authorization(user=user, client_id=client_id),
            },
            json={
                "query": query,
                "variables": variables,
            })
    resp = r.json()
    if r.status_code != 200 or "errors" in resp:
        if valid is None:
            raise GraphQLError(r.json())
        else:
            _copy_errors(valid, resp)
            return resp.get("data")
    return resp["data"]

def gql_time(time):
    """
    Parses a timestamp from a GraphQL response.
    """
    return datetime.strptime(time, DATE_FORMAT)

def _copy_errors(valid, response):
    for err in response["errors"]:
        msg = err["message"]
        ext = err.get("extensions")
        field = None
        if ext:
            field = ext.get("field")
        valid.error(msg, field=field)
