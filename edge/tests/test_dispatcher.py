import json
import os
import pytest
from pydantic import ValidationError
from edge.src.event_dispatcher import (
    PersonEntryEvent,
    PersonExitEvent,
    ZoneDwellEvent,
    OccupancyUpdateEvent,
    FileDispatcher,
    ConsoleDispatcher,
    APIDispatcher
)

def test_person_entry_event_serialization():
    event = PersonEntryEvent(
        store_id="store-xyz",
        camera_id="cam-1",
        track_id=101,
        confidence=0.88,
        re_entry_detected=True,
        correlated_previous_track_id=99
    )
    
    assert event.event_type == "PEOPLE_ENTRY"
    assert event.track_id == 101
    assert event.re_entry_detected is True
    assert event.correlated_previous_track_id == 99

    # Verify JSON round-trip
    dumped = event.model_dump_json()
    loaded = json.loads(dumped)
    
    assert loaded["event_type"] == "PEOPLE_ENTRY"
    assert loaded["track_id"] == 101
    assert loaded["re_entry_detected"] is True
    assert "event_id" in loaded
    assert "timestamp" in loaded

def test_zone_dwell_event_serialization():
    event = ZoneDwellEvent(
        store_id="store-xyz",
        camera_id="cam-1",
        track_id=101,
        zone_id="aisle_1",
        entered_at="2026-05-31T10:00:00Z",
        exited_at="2026-05-31T10:01:30Z",
        dwell_time_seconds=90.0
    )
    
    assert event.dwell_time_seconds == 90.0
    assert event.zone_id == "aisle_1"

    with pytest.raises(ValidationError):
        # Missing required parameter entered_at
        ZoneDwellEvent(
            store_id="store-xyz",
            camera_id="cam-1",
            track_id=101,
            zone_id="aisle_1",
            exited_at="2026-05-31T10:01:30Z",
            dwell_time_seconds=90.0
        )

def test_file_dispatcher(tmp_path):
    events_file = tmp_path / "events.jsonl"
    dispatcher = FileDispatcher(str(events_file))
    
    entry_event = PersonEntryEvent(
        store_id="store-xyz",
        camera_id="cam-1",
        track_id=101,
        confidence=0.92
    )
    
    dwell_event = ZoneDwellEvent(
        store_id="store-xyz",
        camera_id="cam-1",
        track_id=101,
        zone_id="snacks",
        entered_at="2026-05-31T10:00:00Z",
        exited_at="2026-05-31T10:02:00Z",
        dwell_time_seconds=120.0
    )

    # Dispatch events
    dispatcher.dispatch(entry_event)
    dispatcher.dispatch(dwell_event)

    # Verify file content
    assert os.path.exists(str(events_file)) is True
    
    with open(events_file, "r") as f:
        lines = f.readlines()
        
    assert len(lines) == 2
    
    event_1 = json.loads(lines[0])
    event_2 = json.loads(lines[1])
    
    assert event_1["event_type"] == "PEOPLE_ENTRY"
    assert event_1["track_id"] == 101
    
    assert event_2["event_type"] == "ZONE_DWELL"
    assert event_2["zone_id"] == "snacks"
    assert event_2["dwell_time_seconds"] == 120.0

def test_api_dispatcher():
    from unittest.mock import patch, MagicMock
    dispatcher = APIDispatcher(base_url="http://fake-api.com/api/v1/telemetry")
    
    entry_event = PersonEntryEvent(
        store_id="store-xyz",
        camera_id="cam-1",
        track_id=101,
        confidence=0.92
    )
    
    with patch("requests.post") as mock_post:
        # Mock successful response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_post.return_value = mock_response
        
        dispatcher.dispatch(entry_event)
        
        mock_post.assert_called_once()
        args, kwargs = mock_post.call_args
        assert args[0] == "http://fake-api.com/api/v1/telemetry/entry"
        assert kwargs["json"]["track_id"] == 101
        assert kwargs["timeout"] == 2.0
