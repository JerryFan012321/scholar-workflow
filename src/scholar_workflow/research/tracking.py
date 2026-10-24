"""Incremental observations and user dispositions, not a knowledge-content database."""
from __future__ import annotations

from copy import deepcopy

from .models import (
    DIAGNOSTICS,
    MAX_EVENTS,
    MAX_REGISTRY_BYTES,
    MAX_STATE_BYTES,
    ResearchError,
    checked_time,
    digest,
    validate_channel,
    validate_observation,
)
from .store import (
    REGISTRY,
    STATE_FILE,
    dump_state,
    load_registry,
    load_state,
    read_bytes,
    replace_bytes,
    revision,
    root_directory,
    root_path,
    state_directory,
    storage_lock,
)


def _summary(channel, checkpoint=None):
    result = {**channel, "status": "uninitialized" if channel["enabled"] else "disabled",
              "configuration_changed": False, "last_checked_at": None,
              "last_success_at": None, "observed_item_count": 0, "window_item_count": 0}
    if checkpoint is not None:
        changed = checkpoint["config_revision"] != digest(channel)
        result.update(configuration_changed=changed, last_checked_at=checkpoint["last_checked_at"])
        if channel["enabled"]:
            result["status"] = "configuration_changed" if changed else checkpoint["last_status"]
        if not changed:
            result.update(last_success_at=checkpoint["last_success_at"],
                          observed_item_count=len(checkpoint["items"]),
                          window_item_count=checkpoint["window_item_count"])
        if not changed and channel["enabled"]:
            for key in ("etag", "last_modified"):
                if key in checkpoint:
                    result[key] = checkpoint[key]
        if "diagnostic" in checkpoint:
            result["diagnostic"] = checkpoint["diagnostic"]
    return result


def read_updates(root):
    """Return validated events and current source/check states without initialization."""
    result = {"schema_version": 1, "status": "uninitialized", "revision": "absent",
              "channels": [], "events": [], "diagnostics": []}
    try:
        with root_directory(root) as root_fd:
            registry_data = read_bytes(root_fd, REGISTRY, MAX_REGISTRY_BYTES)
            sources = load_registry(registry_data)
            try:
                with state_directory(root_fd) as state_fd:
                    state_data = read_bytes(state_fd, STATE_FILE, MAX_STATE_BYTES)
            except FileNotFoundError:
                state_data = None
            state = load_state(state_data)
            # Avoid presenting a pair collected across a concurrent registration.
            if read_bytes(root_fd, REGISTRY, MAX_REGISTRY_BYTES) != registry_data:
                raise ResearchError("Research registry changed during the read.", 5)
        if registry_data is not None:
            result["status"] = "available"
        if registry_data is None and state_data is not None:
            raise ResearchError("Research tracking state has no source registry.")
        result["revision"] = revision(state_data)
        result["channels"] = [_summary(channel, state["channels"].get(channel["channel_id"]))
                              for channel in sources["channels"]]
        result["events"] = state["events"]
        registered = {channel["channel_id"] for channel in sources["channels"]}
        if set(state["channels"]) - registered:
            result["diagnostics"].append({
                "code": "unregistered_tracking_history",
                "message": "History exists for channels no longer in the current registry.",
            })
        for channel in result["channels"]:
            if channel.get("diagnostic"):
                result["diagnostics"].append({"channel_id": channel["channel_id"],
                                               **channel["diagnostic"]})
            if channel["configuration_changed"]:
                result["diagnostics"].append({
                    "code": "channel_configuration_changed", "channel_id": channel["channel_id"],
                    "message": "The current channel configuration needs a fresh complete baseline.",
                })
    except FileNotFoundError:
        pass
    except (ResearchError, OSError):
        result.update(status="invalid", channels=[], events=[])
        result["diagnostics"] = [{"code": "invalid_research_tracking",
                                  "message": "Research tracking or source state is invalid or unsafe."}]
    return result


def _checkpoint(channel, checked_at, observation):
    return {"config_revision": digest(channel), "initialized": False,
            "last_checked_at": checked_at, "last_success_at": None, "last_status": "failed",
            "last_observation_digest": digest(observation),
            "last_observation_config_revision": digest(channel), "items": {}, "window_item_count": 0}


def _event(channel, item, sequence, checked_at, kind):
    configuration = digest(channel)
    event_id = "event-" + digest({"channel_id": channel["channel_id"], "item": item,
                                  "sequence": sequence, "config_revision": configuration,
                                  "observed_at": checked_at, "kind": kind}).split(":", 1)[1]
    return {"event_id": event_id, "channel_id": channel["channel_id"], "item_id": item["item_id"],
            "kind": kind, "observed_at": checked_at, "item": item, "disposition": "unread",
            "sequence": sequence, "config_revision": configuration,
            "source": {key: channel[key] for key in ("name", "publisher", "url")}}


def _advance(channel, previous, observation, checked_at, initial_mode):
    current_revision = digest(channel)
    matching = previous is not None and previous["config_revision"] == current_revision
    baseline_exists = matching and previous["initialized"]
    state = deepcopy(previous) if previous is not None else _checkpoint(channel, checked_at, observation)
    events = []
    diagnostics = []
    status = observation["status"]
    if status == "not_modified" and not baseline_exists:
        status = "failed"
        diagnostic = {"code": "baseline_required", "message": DIAGNOSTICS["baseline_required"]}
    else:
        diagnostic = observation.get("diagnostic", {
            "code": "acquisition_failed", "message": DIAGNOSTICS["acquisition_failed"],
        })
    if status == "failed":
        state["last_status"] = "failed"
        state["diagnostic"] = diagnostic
        diagnostics.append(diagnostic)
    elif status == "not_modified":
        state.update(last_status="not_modified", last_success_at=checked_at)
        state.pop("diagnostic", None)
        for key in ("etag", "last_modified"):
            if key in observation:
                state[key] = observation[key]
    else:
        if not matching:
            state = _checkpoint(channel, checked_at, observation)
        initial = not baseline_exists
        for item in observation["items"]:
            prior = state["items"].get(item["item_id"])
            content_fields = ("content_digest", "title", "url", "version")
            if prior is not None and all(prior["item"].get(key) == item.get(key)
                                         for key in content_fields):
                # Publisher timestamps are observation metadata, not content revisions.
                # Keep corrections without notifying or advancing the content sequence.
                state["items"][item["item_id"]] = {"item": item, "sequence": prior["sequence"]}
                continue
            sequence = 1 if prior is None else prior["sequence"] + 1
            if not initial or initial_mode == "report":
                kind = "discovered" if initial else ("new" if prior is None else "updated")
                events.append(_event(channel, item, sequence, checked_at, kind))
            state["items"][item["item_id"]] = {"item": item, "sequence": sequence}
        status = "baseline" if initial and initial_mode == "baseline" else "observed"
        state.update(config_revision=current_revision, initialized=True, last_success_at=checked_at,
                     last_status=status, window_item_count=len(observation["items"]))
        state.pop("diagnostic", None)
        # A successful complete response without validators invalidates older validators.
        for key in ("etag", "last_modified"):
            state.pop(key, None)
            if key in observation:
                state[key] = observation[key]
    state.update(last_checked_at=checked_at, last_observation_digest=digest(observation),
                 last_observation_config_revision=current_revision)
    return state, events, diagnostics


def apply_observation(root, channel, observation, checked_at, initial_mode="baseline"):
    """Commit a complete observation only while its full channel config is still current."""
    channel = validate_channel(channel)
    observation = validate_observation(observation)
    moment = checked_time(checked_at)
    if not isinstance(initial_mode, str) or initial_mode not in {"baseline", "report"}:
        raise ResearchError("Unknown research initial observation mode.")
    path = root_path(root)
    try:
        with root_directory(path) as root_fd, storage_lock(root_fd) as lock_fd:
            registry_data = read_bytes(root_fd, REGISTRY, MAX_REGISTRY_BYTES)
            sources = load_registry(registry_data)
            current = next((row for row in sources["channels"]
                            if row["channel_id"] == channel["channel_id"]), None)
            if current != channel or not channel["enabled"]:
                raise ResearchError("Research channel is disabled, unregistered or changed; check it again.", 5)
            try:
                with state_directory(root_fd) as state_fd:
                    data = read_bytes(state_fd, STATE_FILE, MAX_STATE_BYTES)
            except FileNotFoundError:
                data = None
            document = load_state(data)
            previous = document["channels"].get(channel["channel_id"])
            if previous is not None:
                last = checked_time(previous["last_checked_at"])
                if moment < last:
                    raise ResearchError("A newer research observation already exists.", 5)
                if moment == last:
                    if (previous["last_observation_digest"] != digest(observation)
                            or previous["last_observation_config_revision"] != digest(channel)):
                        raise ResearchError("A different research observation already uses this timestamp.", 5)
                    return {"schema_version": 1, "channel_id": channel["channel_id"],
                            "status": "unchanged", "events": [], "diagnostics": [],
                            "revision": revision(data), "channel": _summary(channel, previous)}
            checkpoint, events, diagnostics = _advance(
                channel, previous, observation, checked_at, initial_mode,
            )
            if len(document["events"]) + len(events) > MAX_EVENTS:
                raise ResearchError("Research event capacity reached; no events were discarded.", 6)
            document["channels"][channel["channel_id"]] = checkpoint
            document["events"].extend(events)
            output = dump_state(document)
            # Network acquisition happened outside this lock. Recheck even cooperative
            # registrations and direct edits before a state checkpoint is accepted.
            if read_bytes(root_fd, REGISTRY, MAX_REGISTRY_BYTES) != registry_data:
                raise ResearchError("Research channel configuration changed during observation commit.", 5)
            with state_directory(root_fd, create=True) as state_fd:
                replace_bytes(path, root_fd, state_fd, STATE_FILE, data, output, lock_fd, state=True,
                              registry_expected=registry_data)
            return {"schema_version": 1, "channel_id": channel["channel_id"],
                    "status": checkpoint["last_status"], "events": events,
                    "diagnostics": diagnostics, "revision": revision(output),
                    "channel": _summary(channel, checkpoint)}
    except FileNotFoundError:
        raise ResearchError("Research channel is not registered.", 5) from None


def mark_event(root, event_id, disposition):
    """Record a selection, not ingestion; repeat choices leave durable bytes unchanged."""
    import re
    if not isinstance(event_id, str) or not re.fullmatch(r"event-[0-9a-f]{64}", event_id):
        raise ResearchError("Invalid research event ID.")
    if not isinstance(disposition, str) or disposition not in {"unread", "read", "selected", "ignored"}:
        raise ResearchError("Unknown research event disposition.")
    path = root_path(root)
    try:
        with (root_directory(path) as root_fd, storage_lock(root_fd) as lock_fd,
              state_directory(root_fd) as state_fd):
            data = read_bytes(state_fd, STATE_FILE, MAX_STATE_BYTES)
            document = load_state(data)
            event = next((row for row in document["events"] if row["event_id"] == event_id), None)
            if event is None:
                raise ResearchError("Research event was not found.", 5)
            if event["disposition"] == disposition:
                return {"schema_version": 1, "status": "unchanged", "event": event,
                        "revision": revision(data)}
            event["disposition"] = disposition
            output = dump_state(document)
            replace_bytes(path, root_fd, state_fd, STATE_FILE, data, output, lock_fd, state=True)
            return {"schema_version": 1, "status": "updated", "event": event,
                    "revision": revision(output)}
    except FileNotFoundError:
        raise ResearchError("Research event was not found.", 5) from None
