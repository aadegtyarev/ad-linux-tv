"""Reject ambiguous repeated object names in untrusted request JSON."""

import json


class DuplicateJSONError(ValueError):
    pass


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise DuplicateJSONError("duplicate JSON object member")
        result[key] = value
    return result


def loads(data):
    return json.loads(data, object_pairs_hook=_unique_object)
