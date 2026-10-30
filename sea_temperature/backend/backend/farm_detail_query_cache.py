"""Reuse insurance SELECT results only within one household-detail request."""
from contextvars import ContextVar
from copy import deepcopy
from functools import wraps


_queries = ContextVar("farm_detail_queries", default=None)


def cache_detail_request(function):
    @wraps(function)
    def handle(*args, **kwargs):
        token = _queries.set({})
        try:
            return function(*args, **kwargs)
        finally:
            _queries.reset(token)
    return handle


def cache_repository_query(function):
    @wraps(function)
    def query(self, sql, params=None):
        cache = _queries.get()
        if cache is None:
            return function(self, sql, params)
        key = (function, self, sql, repr(params))
        if key not in cache:
            cache[key] = function(self, sql, params)
        # Claim parsing mutates rows; keep cached data unchanged for the next scenario.
        return deepcopy(cache[key])
    return query
