# Data Governance

Manage Mixpanel data governance programmatically: Lexicon definitions (events, properties, tags), drop filters, custom properties, custom events, and lookup tables. Full CRUD operations with bulk support.

!!! note "Prerequisites"
    Data governance requires **authentication** — service account or OAuth credentials.

    All data governance operations require a **workspace ID** — set via `MP_WORKSPACE_ID` env var, `--workspace-id` CLI flag, or `ws.set_workspace_id()`. Find yours with `mp inspect info` or `ws.info()`.

!!! tip "Read-Only Discovery"
    For read-only Lexicon schema exploration (listing events/properties with descriptions and metadata), see the [Discovery guide — Lexicon Schemas](discovery.md#lexicon-schemas). This guide covers **write operations**: creating, updating, and deleting definitions.

## Lexicon — Event Definitions

### Get Event Definitions

=== "Python"

    ```python
    import mixpanel_data as mp

    ws = mp.Workspace()

    # Get definitions for specific events
    defs = ws.get_event_definitions(names=["Signup", "Login"])
    for d in defs:
        print(f"{d.name}: {d.description}")
        print(f"  hidden={d.hidden}, verified={d.verified}")
        print(f"  tags={d.tags}")
    ```

=== "CLI"

    ```bash
    # Get definitions by name
    mp lexicon events get --names "Signup,Login"

    # Table format for quick scanning
    mp lexicon events get --names "Signup,Login" --format table
    ```

### Update an Event Definition

=== "Python"

    ```python
    definition = ws.update_event_definition(
        "Signup",
        mp.UpdateEventDefinitionParams(
            description="User signed up for an account",
            verified=True,
            tags=["core", "acquisition"],
        ),
    )
    print(f"Updated: {definition.name}")
    ```

=== "CLI"

    ```bash
    mp lexicon events update --name "Signup" \
        --description "User signed up for an account" \
        --verified \
        --tags "core,acquisition"
    ```

### Delete an Event Definition

=== "Python"

    ```python
    ws.delete_event_definition("OldEvent")
    ```

=== "CLI"

    ```bash
    mp lexicon events delete --name "OldEvent"
    ```

### Bulk Update Event Definitions

Update multiple event definitions in a single API call:

=== "Python"

    ```python
    results = ws.bulk_update_event_definitions(
        mp.BulkUpdateEventsParams(events=[
            mp.BulkEventUpdate(name="OldEvent", hidden=True),
            mp.BulkEventUpdate(name="NewEvent", verified=True),
            mp.BulkEventUpdate(
                name="Purchase",
                description="Completed purchase",
                tags=["revenue"],
            ),
        ])
    )
    for d in results:
        print(f"{d.name}: hidden={d.hidden}, verified={d.verified}")
    ```

=== "CLI"

    ```bash
    mp lexicon events bulk-update --data '{
        "events": [
            {"name": "OldEvent", "hidden": true},
            {"name": "NewEvent", "verified": true},
            {"name": "Purchase", "description": "Completed purchase", "tags": ["revenue"]}
        ]
    }'
    ```

---

## Lexicon — Property Definitions

### Get Property Definitions

=== "Python"

    ```python
    # Get property definitions by name
    defs = ws.get_property_definitions(
        names=["plan_type", "country"],
        resource_type="event",  # "event", "user", or "groupprofile"
    )
    for d in defs:
        print(f"{d.name} ({d.resource_type}): {d.description}")
        print(f"  sensitive={d.sensitive}, hidden={d.hidden}")
    ```

=== "CLI"

    ```bash
    # Get property definitions
    mp lexicon properties get --names "plan_type,country"

    # Filter by resource type
    mp lexicon properties get --names "plan_type" --resource-type event
    ```

### Update a Property Definition

=== "Python"

    ```python
    definition = ws.update_property_definition(
        "plan_type",
        mp.UpdatePropertyDefinitionParams(
            description="User subscription tier",
            sensitive=False,
        ),
    )
    ```

=== "CLI"

    ```bash
    mp lexicon properties update --name "plan_type" \
        --description "User subscription tier" \
        --no-sensitive
    ```

### Bulk Update Property Definitions

=== "Python"

    ```python
    results = ws.bulk_update_property_definitions(
        mp.BulkUpdatePropertiesParams(properties=[
            mp.BulkPropertyUpdate(
                name="email",
                resource_type="user",
                sensitive=True,
            ),
            mp.BulkPropertyUpdate(
                name="country",
                resource_type="event",
                description="User country code",
            ),
        ])
    )
    ```

=== "CLI"

    ```bash
    mp lexicon properties bulk-update --data '{
        "properties": [
            {"name": "email", "resource_type": "user", "sensitive": true},
            {"name": "country", "resource_type": "event", "description": "User country code"}
        ]
    }'
    ```

---

## Lexicon — Tags

Organize event and property definitions with tags.

### List Tags

=== "Python"

    ```python
    tags = ws.list_lexicon_tags()
    for tag in tags:
        print(f"{tag.id}: {tag.name}")
    ```

=== "CLI"

    ```bash
    mp lexicon tags list
    mp lexicon tags list --format table
    ```

### Create a Tag

=== "Python"

    ```python
    tag = ws.create_lexicon_tag(mp.CreateTagParams(name="core-events"))
    print(f"Created tag {tag.id}: {tag.name}")
    ```

=== "CLI"

    ```bash
    mp lexicon tags create --name "core-events"
    ```

### Update a Tag

=== "Python"

    ```python
    tag = ws.update_lexicon_tag(5, mp.UpdateTagParams(name="renamed-tag"))
    ```

=== "CLI"

    ```bash
    mp lexicon tags update --id 5 --name "renamed-tag"
    ```

### Delete a Tag

=== "Python"

    ```python
    ws.delete_lexicon_tag("deprecated-tag")
    ```

=== "CLI"

    ```bash
    mp lexicon tags delete --name "deprecated-tag"
    ```

---

## Lexicon — Tracking & History

### Tracking Metadata

Get tracking metadata for an event (sources, SDKs, volume):

=== "Python"

    ```python
    metadata = ws.get_tracking_metadata("Signup")
    print(metadata)  # Raw tracking metadata dictionary
    ```

=== "CLI"

    ```bash
    mp lexicon tracking-metadata --event-name "Signup"
    ```

### Event History

View the change history for an event definition:

=== "Python"

    ```python
    history = ws.get_event_history("Signup")
    for entry in history:
        print(entry)  # Chronological list of changes
    ```

=== "CLI"

    ```bash
    mp lexicon event-history --event-name "Signup"
    ```

### Property History

View the change history for a property definition:

=== "Python"

    ```python
    history = ws.get_property_history("plan_type", entity_type="event")
    for entry in history:
        print(entry)
    ```

=== "CLI"

    ```bash
    mp lexicon property-history --property-name "plan_type" --entity-type "event"
    ```

### Export Lexicon

Export all Lexicon data definitions:

=== "Python"

    ```python
    export = ws.export_lexicon()
    print(export)  # Raw export dictionary

    # Filter by type
    export = ws.export_lexicon(
        export_types=["events", "event_properties"]
    )
    ```

=== "CLI"

    ```bash
    mp lexicon export
    mp lexicon export --types "events,event_properties,user_properties"
    ```

---

## Drop Filters

Drop filters suppress events at ingestion time, preventing them from being stored or counted.

### List Drop Filters

=== "Python"

    ```python
    import mixpanel_data as mp

    ws = mp.Workspace()

    filters = ws.list_drop_filters()
    for f in filters:
        print(f"{f.id}: {f.event_name} (active={f.active})")
    ```

=== "CLI"

    ```bash
    mp drop-filters list
    mp drop-filters list --format table
    ```

### Create a Drop Filter

=== "Python"

    ```python
    filters = ws.create_drop_filter(
        mp.CreateDropFilterParams(
            event_name="Debug Event",
            filters={"property": "env", "value": "test"},
        )
    )
    # Returns full list of drop filters after creation
    ```

=== "CLI"

    ```bash
    mp drop-filters create --event-name "Debug Event" \
        --filters '{"property": "env", "value": "test"}'
    ```

### Update a Drop Filter

=== "Python"

    ```python
    filters = ws.update_drop_filter(
        mp.UpdateDropFilterParams(
            id=42,
            event_name="Debug Event v2",
            active=False,
        )
    )
    ```

=== "CLI"

    ```bash
    mp drop-filters update --id 42 --event-name "Debug Event v2" --no-active
    ```

### Delete a Drop Filter

=== "Python"

    ```python
    remaining = ws.delete_drop_filter(42)
    # Returns full list of remaining drop filters
    ```

=== "CLI"

    ```bash
    mp drop-filters delete --id 42
    ```

### Drop Filter Limits

=== "Python"

    ```python
    limits = ws.get_drop_filter_limits()
    print(f"Drop filter limit: {limits.filter_limit}")
    ```

=== "CLI"

    ```bash
    mp drop-filters limits
    ```

---

## Custom Properties

Custom properties are computed properties defined by formulas or behaviors. They calculate values dynamically from existing event or profile properties.

!!! warning "PUT Semantics"
    Custom property `update` uses **full replacement** (PUT semantics). The `resource_type` and `data_group_id` fields are immutable after creation.

### List Custom Properties

=== "Python"

    ```python
    import mixpanel_data as mp

    ws = mp.Workspace()

    props = ws.list_custom_properties()
    for p in props:
        print(f"{p.name}: {p.display_formula}")
    ```

=== "CLI"

    ```bash
    mp custom-properties list
    mp custom-properties list --format table
    ```

### Get a Custom Property

=== "Python"

    ```python
    prop = ws.get_custom_property("abc123")
    print(f"{prop.name}: {prop.display_formula}")
    print(f"  resource_type={prop.resource_type}")
    ```

=== "CLI"

    ```bash
    mp custom-properties get --id "abc123"
    ```

### Create a Custom Property

Custom properties can be formula-based or behavior-based:

=== "Python"

    ```python
    # Formula-based custom property
    prop = ws.create_custom_property(
        mp.CreateCustomPropertyParams(
            name="Full Name",
            resource_type="events",
            display_formula='concat(properties["first"], " ", properties["last"])',
            composed_properties={
                "first": mp.ComposedPropertyValue(resource_type="event"),
                "last": mp.ComposedPropertyValue(resource_type="event"),
            },
        )
    )
    print(f"Created: {prop.name} (ID: {prop.custom_property_id})")
    ```

=== "CLI"

    ```bash
    mp custom-properties create \
        --name "Full Name" \
        --resource-type events \
        --display-formula 'concat(properties["first"], " ", properties["last"])' \
        --composed-properties '{"first": {"resource_type": "event"}, "last": {"resource_type": "event"}}'
    ```

!!! info "Formula vs Behavior"
    `display_formula` and `behavior` are mutually exclusive. If using `display_formula`, you must also provide `composed_properties` that map the referenced properties.

### Update a Custom Property

=== "Python"

    ```python
    prop = ws.update_custom_property(
        "abc123",
        mp.UpdateCustomPropertyParams(name="Renamed Property"),
    )
    ```

=== "CLI"

    ```bash
    mp custom-properties update --id "abc123" --name "Renamed Property"
    ```

### Delete a Custom Property

=== "Python"

    ```python
    ws.delete_custom_property("abc123")
    ```

=== "CLI"

    ```bash
    mp custom-properties delete --id "abc123"
    ```

### Validate a Custom Property

Check whether a custom property definition is valid before creating it:

=== "Python"

    ```python
    result = ws.validate_custom_property(
        mp.CreateCustomPropertyParams(
            name="Revenue Per User",
            resource_type="events",
            display_formula='number(properties["amount"])',
            composed_properties={
                "amount": mp.ComposedPropertyValue(resource_type="event"),
            },
        )
    )
    print(result)  # Validation result dictionary
    ```

=== "CLI"

    ```bash
    mp custom-properties validate \
        --name "Revenue Per User" \
        --resource-type events \
        --display-formula 'number(properties["amount"])' \
        --composed-properties '{"amount": {"resource_type": "event"}}'
    ```

---

## Custom Events

Custom events are composite events built from combinations of existing events. They share the same `EventDefinition` type as regular events.

### List Custom Events

=== "Python"

    ```python
    import mixpanel_data as mp

    ws = mp.Workspace()

    events = ws.list_custom_events()
    for e in events:
        print(f"{e.name}: {e.description}")
    ```

=== "CLI"

    ```bash
    mp custom-events list
    mp custom-events list --format table
    ```

### Update a Custom Event

=== "Python"

    ```python
    event = ws.update_custom_event(
        "My Custom Event",
        mp.UpdateEventDefinitionParams(
            description="Updated description",
            verified=True,
        ),
    )
    ```

=== "CLI"

    ```bash
    mp custom-events update --name "My Custom Event" \
        --description "Updated description" --verified
    ```

### Delete a Custom Event

=== "Python"

    ```python
    ws.delete_custom_event("My Custom Event")
    ```

=== "CLI"

    ```bash
    mp custom-events delete --name "My Custom Event"
    ```

---

## Lookup Tables

Lookup tables are CSV-based reference data used to enrich event and profile properties. Upload a CSV, and Mixpanel maps its columns to properties for real-time enrichment.

### List Lookup Tables

=== "Python"

    ```python
    import mixpanel_data as mp

    ws = mp.Workspace()

    tables = ws.list_lookup_tables()
    for t in tables:
        print(f"{t.name} (ID: {t.id}, mapped={t.has_mapped_properties})")

    # Filter by data group
    tables = ws.list_lookup_tables(data_group_id=123)
    ```

=== "CLI"

    ```bash
    mp lookup-tables list
    mp lookup-tables list --data-group-id 123
    mp lookup-tables list --format table
    ```

### Upload a Lookup Table

!!! info "3-Step Upload Process"
    `upload_lookup_table()` handles the full workflow automatically:

    1. Obtains a signed upload URL from the API
    2. Uploads the CSV file to the signed URL
    3. Registers the lookup table

    For files >= 5 MB, processing is asynchronous. The method automatically polls for completion with configurable timeout.

=== "Python"

    ```python
    table = ws.upload_lookup_table(
        mp.UploadLookupTableParams(
            name="Country Codes",
            file_path="/path/to/countries.csv",
        ),
        poll_interval=2.0,        # Seconds between polls (async only)
        max_poll_seconds=300.0,   # Max wait time (async only)
    )
    print(f"Created: {table.name} (ID: {table.id})")

    # Replace an existing lookup table
    table = ws.upload_lookup_table(
        mp.UploadLookupTableParams(
            name="Country Codes",
            file_path="/path/to/countries_v2.csv",
            data_group_id=456,  # Existing table's data group ID
        )
    )
    ```

=== "CLI"

    ```bash
    # Upload a new lookup table
    mp lookup-tables upload --name "Country Codes" --file "/path/to/countries.csv"

    # Replace an existing lookup table
    mp lookup-tables upload --name "Country Codes" --file "/path/to/countries_v2.csv" \
        --data-group-id 456
    ```

### Update a Lookup Table

=== "Python"

    ```python
    table = ws.update_lookup_table(
        data_group_id=123,
        params=mp.UpdateLookupTableParams(name="Renamed Table"),
    )
    ```

=== "CLI"

    ```bash
    mp lookup-tables update --data-group-id 123 --name "Renamed Table"
    ```

### Delete Lookup Tables

=== "Python"

    ```python
    # Delete one or more lookup tables
    ws.delete_lookup_tables(data_group_ids=[123, 456])
    ```

=== "CLI"

    ```bash
    mp lookup-tables delete --data-group-ids "123,456"
    ```

### Download a Lookup Table

=== "Python"

    ```python
    # Download as raw CSV bytes
    csv_data = ws.download_lookup_table(data_group_id=123)

    # Save to file
    with open("output.csv", "wb") as f:
        f.write(csv_data)

    # Download with row limit
    csv_data = ws.download_lookup_table(data_group_id=123, limit=100)
    ```

=== "CLI"

    ```bash
    # Download to stdout
    mp lookup-tables download --data-group-id 123

    # Save to file
    mp lookup-tables download --data-group-id 123 > output.csv
    ```

### Advanced: Upload and Download URLs

For manual upload workflows or integration with external tools:

=== "Python"

    ```python
    # Get a signed upload URL
    url_info = ws.get_lookup_upload_url(content_type="text/csv")
    print(url_info.url)  # Signed GCS URL

    # Check async upload status
    status = ws.get_lookup_upload_status("upload-id-123")
    print(status)

    # Get a signed download URL
    download_url = ws.get_lookup_download_url(data_group_id=123)
    print(download_url)
    ```

=== "CLI"

    ```bash
    # Get upload URL
    mp lookup-tables upload-url

    # Get download URL
    mp lookup-tables download-url --data-group-id 123
    ```

---

## Next Steps

- [API Reference — Workspace](../api/workspace.md) — Complete method signatures and docstrings
- [API Reference — Types](../api/types.md) — EventDefinition, DropFilter, CustomProperty, LookupTable, and all parameter types
- [CLI Reference](../cli/index.md) — Full CLI command documentation
- [Entity Management](entity-management.md) — Manage dashboards, reports, cohorts, feature flags, experiments, alerts, annotations, and webhooks
