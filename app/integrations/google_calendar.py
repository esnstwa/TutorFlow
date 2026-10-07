from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class GoogleCalendarState:
    connected: bool = False
    events_visible: bool = False
    last_synced_at: str | None = None
    can_sync: bool = False


class GoogleCalendarGateway:
    """Integration boundary for a future OAuth-backed Google Calendar client."""

    def get_state(self) -> dict[str, bool | str | None]:
        return asdict(GoogleCalendarState())

    def list_events(self, _date_from: str, _date_to: str) -> list[dict[str, str]]:
        return []


google_calendar = GoogleCalendarGateway()
