import shlex
from sqlalchemy import or_

def search(query, terms, default_props, prop_map):
    # TODO: OR, case-sensitivity(?)
    terms = shlex.split(terms)
    for term in terms:
        if ":" in term:
            parts = term.split(":")
            prop = parts[0]
            value = ":".join(parts[1:])
        else:
            prop, value = None, term
        if prop is None:
            query = query.filter(or_(*[
                    p.ilike("%" + value + "%")
                for p in default_props]))
            continue
        if prop in prop_map:
            prop = prop_map[prop]
            if callable(prop):
                query = prop(query, value)
            else:
                query = query.filter(prop.ilike("%" + value + "%"))
        elif None in prop_map:
            query = prop_map[None](query, prop, value)
        else:
            # TODO: Should we let the user know this happened?
            query = query.filter(False)
    return query
