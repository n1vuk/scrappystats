# Placeholder for Service Record system
def add_service_event(member, event_type, **kwargs):
    from datetime import datetime, timezone
    event = {"type": event_type, "timestamp": datetime.now(timezone.utc).isoformat()}
    event.update(kwargs)
    member.service_events.append(event)
