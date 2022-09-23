import json
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
    op = GraphQLOperation(query)
    for key, value in variables.items():
        op.var(key, value)
    return op.execute(site, user=user, client_id=client_id, valid=valid)

class GraphQLUpload:
    def __init__(self, filename, contents, content_type):
        self.filename = filename
        self.contents = contents
        self.content_type = content_type

class GraphQLOperation:
    def __init__(self, query):
        self.query = query
        self.variables = {}
        self.uploads = []
        self.map = {}

    def var(self, key, value):
        assert(key not in self.variables)
        if isinstance(value, GraphQLUpload):
            self.multipart = True
            self.map[str(len(self.uploads))] = [f"variables.{key}"]
            self.uploads.append(value)
            self.variables[key] = None
        elif isinstance(value, list) and all(isinstance(x, GraphQLUpload) for x in value):
            self.multipart = True
            for i, upload in enumerate(value):
                self.map[str(len(self.uploads))] = [f"variables.{key}.{i}"]
                self.uploads.append(upload)
            self.variables[key] = [None] * len(value)
        else:
            self.variables[key] = value

    def execute(self, site, user=None, client_id=None, valid=None, oauth2_token=None):
        """
        Executes a GraphQL query against the given site's GraphQL API. If no user
        is specified, the authenticated user is used. If a validation argument is
        provided, the GraphQL response will be interpreted for errors; otherwise
        any GraphQL error will cause an exception to be thrown.
        """
        origin = cfg(site, "api-origin", default=get_origin(site))

        headers={
            "X-Forwarded-For": ", ".join(request.access_route) if has_request_context() else None,
        }
        if oauth2_token is not None:
            headers={
                **headers,
                "Authorization": f"Bearer {oauth2_token}",
            }
        else:
            headers={
                **headers,
                **encrypt_request_authorization(user=user, client_id=client_id),
            }

        if len(self.uploads) > 0:
            files = {}
            for i, upload in enumerate(self.uploads):
                files[str(i)] = (upload.filename, upload.contents, upload.content_type)

            r = requests.post(f"{origin}/query",
                    headers=headers,
                    files={
                        'operations': (None, json.dumps({
                            "query": self.query,
                            "variables": self.variables,
                        })),
                        'map': (None, json.dumps(self.map)),
                        **files,
                    })
        else:
            r = requests.post(f"{origin}/query",
                    headers=headers,
                    json={
                        "query": self.query,
                        "variables": self.variables,
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
    # Python's strptime does not support nanoseconds, so that's cool.
    nanos = time.rindex(".")
    time = time[:nanos] + "Z"
    return datetime.strptime(time, DATE_FORMAT)

def _copy_errors(valid, response):
    for err in response["errors"]:
        msg = err["message"]
        ext = err.get("extensions")
        field = None
        if ext:
            field = ext.get("field")
        valid.error(msg, field=field)
