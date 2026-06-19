# Small shared helper used by a few stages, not a stage on its own.
# DBpedia and the gold queries don't always spell a URI the same way (one side
# might percent-encode a character that the other leaves plain), so before we
# compare two URIs we send them both through here to put them in one common form.

from urllib.parse import unquote


def canonical_uri(uri: str) -> str:
    """
    Return a canonical comparison form of a DBpedia URI.
    """
    return unquote(uri.strip())
