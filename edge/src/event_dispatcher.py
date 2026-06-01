import os
import json
import uuid
import logging
from datetime import datetime, timezone
from typing import List, Dict, Optional
from abc import ABC, abstractmethod
from pydantic import BaseModel, Field

# Setup local logger
logger = logging.getLogger("PurpleInsight.Dispatcher")
logger.setLevel(logging.INFO)

# Define Core Event Models
class BaseEvent(BaseModel):
    event_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    event_type: str
    store_id: str
    camera_id: str
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

class PersonEntryEvent(BaseEvent):
    event_type: str = "PEOPLE_ENTRY"
    track_id: int
    confidence: float
    re_entry_detected: bool = False
    correlated_previous_track_id: Optional[int] = None

class PersonExitEvent(BaseEvent):
    event_type: str = "PEOPLE_EXIT"
    track_id: int
    confidence: float

class ZoneDwellEvent(BaseEvent):
    event_type: str = "ZONE_DWELL"
    track_id: int
    zone_id: str
    entered_at: str
    exited_at: str
    dwell_time_seconds: float

class OccupancyUpdateEvent(BaseEvent):
    event_type: str = "OCCUPANCY_UPDATE"
    current_occupancy: int
    active_tracks_count: int
    zone_occupancies: Dict[str, int]

class QueueUpdateEvent(BaseEvent):
    event_type: str = "QUEUE_UPDATE"
    queue_id: str
    current_length: int
    avg_wait_seconds: float
    max_wait_seconds: float

class QueueAlertEvent(BaseEvent):
    event_type: str = "QUEUE_ALERT"
    queue_id: str
    severity: str # LOW | MEDIUM | HIGH
    message: str


# Dispatcher Interface
class EventDispatcher(ABC):
    @abstractmethod
    def dispatch(self, event: BaseEvent) -> None:
        """Dispatches the event to the downstream channel."""
        pass

class ConsoleDispatcher(EventDispatcher):
    """Outputs events cleanly to the standard logger/console."""
    def dispatch(self, event: BaseEvent) -> None:
        event_json = event.model_dump_json(indent=2)
        logger.info(f"== [DISPATCHED EVENT: {event.event_type}] ==\n{event_json}")

class FileDispatcher(EventDispatcher):
    """Saves serialized events as JSON lines to a local file."""
    def __init__(self, file_path: str = "events.jsonl"):
        self.file_path = os.path.abspath(file_path)
        # Ensure directories exist
        os.makedirs(os.path.dirname(self.file_path), exist_ok=True)
        logger.info(f"Initialized FileDispatcher writing to: {self.file_path}")

    def dispatch(self, event: BaseEvent) -> None:
        try:
            line = event.model_dump_json()
            with open(self.file_path, "a") as f:
                f.write(line + "\n")
        except Exception as e:
            logger.error(f"Failed to write event to file: {e}")

class APIDispatcher(EventDispatcher):
    """Streams CV telemetry events directly to the FastAPI server endpoints."""
    def __init__(self, base_url: str = "http://127.0.0.1:8000/api/v1/telemetry"):
        self.base_url = base_url.rstrip("/")
        logger.info(f"Initialized APIDispatcher targetting base URL: {self.base_url}")

    def dispatch(self, event: BaseEvent) -> None:
        import requests
        
        url_map = {
            "PEOPLE_ENTRY": f"{self.base_url}/entry",
            "PEOPLE_EXIT": f"{self.base_url}/exit",
            "ZONE_DWELL": f"{self.base_url}/dwell"
        }
        
        if event.event_type not in url_map:
            # Skip local queue/occupancy updates to conserve network bandwidth
            return
            
        url = url_map[event.event_type]
        try:
            payload = json.loads(event.model_dump_json())
            response = requests.post(url, json=payload, timeout=2.0)
            if response.status_code in [200, 201]:
                logger.info(f"Successfully streamed {event.event_type} event to API server.")
            else:
                logger.warning(f"Failed to stream event. API Status Code: {response.status_code}")
        except Exception as e:
            logger.error(f"Network error trying to stream event to API: {e}")

class CompositeDispatcher(EventDispatcher):
    """Broadcasts events to multiple registered dispatchers."""
    def __init__(self, dispatchers: List[EventDispatcher]):
        self.dispatchers = dispatchers

    def register(self, dispatcher: EventDispatcher) -> None:
        self.dispatchers.append(dispatcher)

    def dispatch(self, event: BaseEvent) -> None:
        for dispatcher in self.dispatchers:
            try:
                dispatcher.dispatch(event)
            except Exception as e:
                logger.error(f"Error executing dispatcher {dispatcher.__class__.__name__}: {e}")
