"""Thin Apollo REST client: accounts, contacts, call records, deals, tasks. Never sequences."""

from .client import ApolloClient
from .errors import ApolloError

__all__ = ["ApolloClient", "ApolloError"]
