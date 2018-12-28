from flask import request

_default = "default"

def paginated_response(id_col, query, order_by=_default):
    start = request.args.get('start') or -1
    if isinstance(start, str):
        start = int(start)
    if start != -1:
        query = query.filter(id_col <= start)
    if order_by is _default:
        records = query.order_by(id_col.desc()).limit(11).all()
    elif order_by is not None:
        records = query.order_by(order_by).limit(11).all()
    if len(records) != 11:
        next_id = None
    else:
        next_id = str(records[-1].id)
        records = records[:10]
    return {
        "next": next_id,
        "results": [record.to_dict() for record in records],
    }
