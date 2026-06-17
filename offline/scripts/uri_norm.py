from urllib.parse import unquote


def canonical_uri(uri: str) -> str:
    """
    Return a canonical comparison form of a DBpedia URI.
    """
    return unquote(uri.strip())
