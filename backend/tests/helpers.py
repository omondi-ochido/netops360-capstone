"""Shared test helpers."""
from app.utils.timeutil import now_iso


def ping_result(status="Online", latency=1.0, loss=0.0):
    sent = 3
    received = round(sent * (100 - loss) / 100) if loss is not None else None
    return {"status": status, "latency_ms": latency, "packet_loss": loss, "packets_sent": sent,
            "packets_received": received, "error_message": None, "check_type": "icmp",
            "checked_at": now_iso()}
