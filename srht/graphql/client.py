import requests
from datetime import datetime
from srht.config import get_origin, cfg
from srht.crypto import encrypt_request_authorization

DATE_FORMAT = "%Y-%m-%dT%H:%M:%SZ"

def exec_gql(site, query, user=None, client_id=None, valid=None, **variables):
    """
    Executes a GraphQL query against the given site's GraphQL API. If no user
    is specified, the authenticated user is used. If a validation argument is
    provided, the GraphQL response will be interpreted for errors; otherwise
    any GraphQL error will cause an exception to be thrown.
    """
    origin = cfg(site, "api-origin", default=get_origin(site))
    r = requests.post(f"{origin}/query",
            headers=encrypt_request_authorization(
                user=user, client_id=client_id),
            json={
                "query": query,
                "variables": variables,
            })
    if r.status_code != 200:
        if valid is None:
            raise Exception(r.text)
        else:
            _copy_errors(valid, r.json())
            return r.json().get("data")
    return r.json()["data"]

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
