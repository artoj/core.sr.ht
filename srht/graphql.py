import json
import pygments
import requests
from flask import Blueprint, current_app, render_template, request, abort
from jinja2 import Markup
from pygments import highlight
from pygments.formatters import HtmlFormatter
from pygments.lexers import JsonLexer
from srht.gql_lexer import GraphqlLexer
from srht.config import get_origin
from srht.oauth import loginrequired
from srht.validation import Validation
from urllib.parse import urlparse

gql_blueprint = Blueprint('srht.graphql', __name__)

_schema_html = None

def execute_gql(query):
    origin = get_origin(current_app.site)
    r = requests.post(f"{origin}/query",
            cookies=request.cookies,
            headers={"Content-Type": "application/json"},
            json={"query": query})
    j = json.dumps(r.json(), indent=2)
    lexer = JsonLexer()
    formatter = HtmlFormatter()
    style = formatter.get_style_defs('.highlight')
    html = (f"<style>{style}</style>"
            + highlight(j, lexer, formatter))
    return Markup(html)

@gql_blueprint.route("/graphql")
@loginrequired
def query_explorer():
    schema = current_app.graphql_schema
    query = current_app.graphql_query
    global _schema_html
    if _schema_html is None:
        lexer = GraphqlLexer()
        formatter = HtmlFormatter()
        style = formatter.get_style_defs('.highlight')
        _schema_html = (f"<style>{style}</style>"
                + highlight(schema, lexer, formatter))
        _schema_html = Markup(_schema_html)
    results = execute_gql(query)
    return render_template("graphql.html",
            schema=_schema_html, query=query, results=results)

@gql_blueprint.route("/graphql", methods=["POST"])
@loginrequired
def query_explorer_POST():
    schema = current_app.graphql_schema
    valid = Validation(request)
    query = valid.require("query")
    if not valid.ok:
        abort(400)
    global _schema_html
    if _schema_html is None:
        lexer = GraphqlLexer()
        formatter = HtmlFormatter()
        style = formatter.get_style_defs('.highlight')
        _schema_html = (f"<style>{style}</style>"
                + highlight(schema, lexer, formatter))
        _schema_html = Markup(_schema_html)
    results = execute_gql(query)
    return render_template("graphql.html",
            schema=_schema_html, query=query, results=results)
