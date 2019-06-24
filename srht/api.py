import requests
from flask import request

_default = 1

def paginated_response(id_col, query,
        order_by=_default, serialize=_default, per_page=50, **kwargs):
    """
    Returns a standard paginated response for a given SQLAlchemy query result.
    The id_col should be the column to paginate by (generally the primary key),
    which is compared <= the ?start=<n> argument.

    order_by will ordered by the ID column, descending, by default. Otherwise
    provide a SQLAlchemy expression, e.g. SomeType.some_col.desc().

    serialize is a function which will serialize each record into a dict. The
    default is lambda r: r.to_dict().

    per_page is the number of results per page to return. Default is 50.
    """
    total = query.count()
    start = request.args.get('start') or -1
    if isinstance(start, str):
        start = int(start)
    if start != -1:
        query = query.filter(id_col <= start)
    if order_by is _default:
        order_by = id_col.desc()
    if order_by is not None:
        if isinstance(order_by, tuple):
            query = query.order_by(*order_by)
        else:
            query = query.order_by(order_by)
    records = query.limit(per_page + 1).all()
    if len(records) != per_page + 1:
        next_id = None
    else:
        next_id = str(records[-1].id)
        records = records[:per_page]
    if serialize is _default:
        serialize = lambda r: r.to_dict(**kwargs)
    return {
        "next": next_id,
        "results": [serialize(record) for record in records],
        "total": total,
        "results_per_page": per_page,
    }

def get_results(url, token):
    response = {"next": -1}
    while response.get("next") is not None:
        url = f"{url}?start={response['next']}"
        r = requests.get(url, headers={"Authorization": f"token {token}"})
        if r.status_code != 200:
            raise Exception(r.json())
        response = r.json()
        yield from response["results"]
