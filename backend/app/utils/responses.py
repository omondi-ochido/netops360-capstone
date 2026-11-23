from flask import jsonify

from .timeutil import now_iso


def ok(data, status=200):
    return jsonify({"data": data, "timestamp": now_iso()}), status


def ok_list(items, limit, offset):
    return jsonify(
        {
            "data": items,
            "pagination": {"limit": limit, "offset": offset, "count": len(items)},
            "timestamp": now_iso(),
        }
    )


def error_response(status, code, message, details=None):
    body = {"error": {"code": code, "message": message}, "timestamp": now_iso()}
    if details:
        body["error"]["details"] = details
    return jsonify(body), status
