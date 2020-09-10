import shlex
from sqlalchemy import and_, or_, not_
from collections import namedtuple

Term = namedtuple("Term", ["key", "value", "inverse"])

def search(query, search_string, default_fn, key_fns={}, fallback_fn=None,
        term_map=None):
    """Filters a query according to the given search string.

    The search string is comprised of search terms separated by whitespace.

    A **search term** can be a single word, an expression in quotes, or a
    key:value pair separated by a colon. The key may be inversed by prefixing
    it with an exclamation mark.

    **Filter functions** are function which take a search value and return the
    corresponding SQLAlchemy filter to be applied to the given query.

    Iterates over search terms in the search string, produces a list of
    corresponding filters, AND's them together and filters the queryset using
    the resulting filter. If a key is inversed using !, the filter returned by
    the filter function will be negated before applying.

    Parameters
    ----------

    query : sqlalchemy.orm.query.Query
        Query to be filtered.

    search_string : str
        A search string comprised of values and key:value pairs separated by
        whitespace. Values may be quoted.

    default_fn : function
        Filter function applied to key-less search terms.

    key_fns : map
        Map of filter functions, indexed by key, applied to search terms
        prefixed by the same key.

    fallback_fn : function
        Filter function applied to terms with keys for which no function is
        defined in key_fns. Unlike other search function which only take a
        value argument, this function takes both the key and the value as
        arguments.

    term_map : function
        Filter the terms through this function before parsing.

    Returns
    -------
    sqlalchemy.orm.query.Query
        Query with the search filter applied.

    Raises
    ------
    ValueError
        If the search term cannot be parsed (e.g. mismatched quotes).
        If the query string contains a search term with a key for which no
        filter function is defined in `key_fns` and no `fallback_fn` is given.
    """
    terms = parse_terms(search_string, term_map)
    return apply_terms(query, terms, default_fn, key_fns, fallback_fn)


def search_by(query, search_string, fields, key_fns={}, fallback_fn=None,
        term_map=None):
    """
    Same as `search()`, but instead of taking a default filter function,
    takes a list of fields to search by default.
    """
    def default_fn(value):
        return or_(f.ilike(f"%{value}%") for f in fields)

    return search(query, search_string, default_fn, key_fns, fallback_fn,
            term_map)

def parse_terms(search_string, term_map=None):
    """Splits a search string into search Terms."""
    search_string = search_string or ""
    for term in shlex.split(search_string):
        if term_map:
            term = term_map(term)
        if ":" in term:
            key, value = term.split(":", maxsplit=1)
            if key.startswith("!"):
                yield Term(key[1:], value, True)
            else:
                yield Term(key, value, False)
        else:
            yield Term(None, term, None)


def apply_terms(query, terms, default_fn, key_fns={}, fallback_fn=None):
    """Converts terms to filters, and filters the query."""
    # TODO: OR, case-sensitivity(?)
    if not terms:
        return query

    filters = and_()

    for term in terms:
        if term.key is None:
            filter = default_fn(term.value)
        elif term.key in key_fns:
            filter = key_fns[term.key](term.value)
        elif fallback_fn is not None:
            filter = fallback_fn(term.key, term.value)
        else:
            raise ValueError(f"Invalid search key '{term.key}'")

        filters.append(not_(filter) if term.inverse else filter)

    return query.filter(filters)
