# VCL-54 Supply Pipeline API Reference

Quick reference guide for all API endpoints.

## Base URL

```
/api/v1/intel
/api/v1/admin
```

## Public Endpoints (No Authentication)

### GET /api/v1/intel/pipeline

List pipeline entries with optional filters.

**Query Parameters:**
- `neighborhood` (string, optional): Filter by neighborhood
- `stage` (string, optional): Filter by pipeline stage
- `limit` (integer, default 50, max 100): Results per page
- `offset` (integer, default 0): Pagination offset

**Response:**
```json
{
  "entries": [
    {
      "id": 1,
      "parcel_pid": "00012345",
      "address": "1234 Main Street",
      "neighborhood": "Downtown",
      "pipeline_stage": "rezoning_application",
      "current_zoning": "RS-1",
      "proposed_zoning": "CD-1",
      "proposed_storeys": 25,
      "proposed_units": 300,
      "proposed_sqft": 150000.0,
      "developer": "Developer Corp",
      "estimated_completion": "2026-06-30",
      "signal_ids": [1, 2, 3],
      "metadata": {"project_name": "Main Street Tower"},
      "created_at": "2024-01-01T12:00:00",
      "updated_at": "2024-01-01T12:00:00"
    }
  ],
  "total_count": 1,
  "has_more": false,
  "offset": 0,
  "limit": 50
}
```

**Example:**
```bash
curl "http://localhost:8000/api/v1/intel/pipeline?neighborhood=Downtown&stage=rezoning_application&limit=10"
```

---

### GET /api/v1/intel/pipeline/{pipeline_id}

Get a single pipeline entry by ID.

**Response:**
```json
{
  "id": 1,
  "parcel_pid": "00012345",
  "address": "1234 Main Street",
  ...
}
```

**Status Codes:**
- 200: Success
- 404: Entry not found
- 500: Database error

---

### GET /api/v1/intel/pipeline/{pipeline_id}/history

Get stage transition history for an entry.

**Response:**
```json
{
  "pipeline_id": 1,
  "history": [
    {
      "id": 1,
      "pipeline_id": 1,
      "from_stage": null,
      "to_stage": "rezoning_application",
      "changed_at": "2024-01-01T10:00:00",
      "signal_id": null,
      "notes": "Initial entry"
    },
    {
      "id": 2,
      "pipeline_id": 1,
      "from_stage": "rezoning_application",
      "to_stage": "public_hearing",
      "changed_at": "2024-02-01T14:00:00",
      "signal_id": 1,
      "notes": "Hearing scheduled"
    }
  ]
}
```

---

### GET /api/v1/intel/pipeline/summary

Get high-level overview of entire pipeline.

**Response:**
```json
{
  "total_entries": 150,
  "total_units": 35000,
  "total_sqft": 21000000.0,
  "by_stage": [
    {
      "stage": "rezoning_application",
      "count": 25,
      "total_units": 5000,
      "total_sqft": 3000000.0
    },
    {
      "stage": "public_hearing",
      "count": 30,
      "total_units": 7500,
      "total_sqft": 4500000.0
    },
    {
      "stage": "council_decision",
      "count": 20,
      "total_units": 4500,
      "total_sqft": 2700000.0
    },
    {
      "stage": "development_permit",
      "count": 15,
      "total_units": 3500,
      "total_sqft": 2100000.0
    },
    {
      "stage": "building_permit",
      "count": 35,
      "total_units": 8000,
      "total_sqft": 4800000.0
    },
    {
      "stage": "under_construction",
      "count": 20,
      "total_units": 5000,
      "total_sqft": 3000000.0
    },
    {
      "stage": "completed",
      "count": 5,
      "total_units": 1500,
      "total_sqft": 900000.0
    }
  ],
  "by_neighborhood": {
    "Downtown": {
      "count": 40,
      "units": 10000,
      "sqft": 6000000.0
    },
    "Kitsilano": {
      "count": 35,
      "units": 8000,
      "sqft": 4800000.0
    },
    "Mount Pleasant": {
      "count": 30,
      "units": 7500,
      "sqft": 4500000.0
    }
  }
}
```

---

### GET /api/v1/intel/pipeline/neighborhood/{neighborhood}

Get detailed supply analysis for a neighborhood.

**Path Parameters:**
- `neighborhood` (string): Neighborhood name (e.g., "Downtown", "Kitsilano")

**Response:**
```json
{
  "neighborhood": "Downtown",
  "total_projects": 40,
  "total_units": 10000,
  "total_sqft": 6000000.0,
  "by_stage": {
    "rezoning_application": {
      "count": 8,
      "units": 1500,
      "sqft": 900000.0
    },
    "public_hearing": {
      "count": 10,
      "units": 2500,
      "sqft": 1500000.0
    },
    ...
  },
  "estimated_completion_range": {
    "2025-03-31": {
      "count": 10,
      "units": 2000
    },
    "2025-06-30": {
      "count": 8,
      "units": 1800
    },
    "2025-09-30": {
      "count": 12,
      "units": 3200
    },
    "2025-12-31": {
      "count": 10,
      "units": 3000
    }
  }
}
```

---

### GET /api/v1/intel/pipeline/stats

Get detailed pipeline statistics.

**Query Parameters:**
- `neighborhood` (string, optional): Filter to specific neighborhood

**Response:**
```json
{
  "total_projects": 150,
  "total_units": 35000,
  "total_sqft": 21000000.0,
  "average_units_per_project": 233.33,
  "average_storeys_per_project": 18.5,
  "projects_by_stage": {
    "rezoning_application": 25,
    "public_hearing": 30,
    "council_decision": 20,
    "development_permit": 15,
    "building_permit": 35,
    "under_construction": 20,
    "completed": 5
  },
  "projects_by_neighborhood": {
    "Downtown": 40,
    "Kitsilano": 35,
    "Mount Pleasant": 30,
    "Marpole": 25,
    "Strathcona": 20
  },
  "near_completion_count": 55
}
```

---

## Admin Endpoints (Authentication Required)

All admin endpoints require valid admin credentials via the `require_admin` dependency.

### POST /api/v1/admin/pipeline

Create a new pipeline entry.

**Request Body:**
```json
{
  "parcel_pid": "00012345",
  "address": "1234 Main Street",
  "neighborhood": "Downtown",
  "pipeline_stage": "rezoning_application",
  "current_zoning": "RS-1",
  "proposed_zoning": "CD-1",
  "proposed_storeys": 25,
  "proposed_units": 300,
  "proposed_sqft": 150000.0,
  "developer": "Developer Corp",
  "estimated_completion": "2026-06-30",
  "metadata": {
    "project_name": "Main Street Tower",
    "amenities": ["public_plaza", "retail"]
  }
}
```

**Response:**
```json
{
  "id": 1,
  "parcel_pid": "00012345",
  "address": "1234 Main Street",
  ...
}
```

**Status Codes:**
- 200: Created
- 409: Duplicate parcel_pid
- 500: Database error

---

### PUT /api/v1/admin/pipeline/{pipeline_id}/stage

Update a project's pipeline stage.

**Path Parameters:**
- `pipeline_id` (integer): ID of pipeline entry

**Query Parameters:**
- `new_stage` (string, required): New stage (rezoning_application, public_hearing, council_decision, development_permit, building_permit, under_construction, completed)
- `signal_id` (integer, optional): Intelligence signal that triggered transition
- `notes` (string, optional): Transition notes

**Response:**
```json
{
  "id": 1,
  "parcel_pid": "00012345",
  "pipeline_stage": "public_hearing",
  ...
}
```

**Status Codes:**
- 200: Updated
- 404: Entry not found
- 500: Database error

**Example:**
```bash
curl -X PUT \
  "http://localhost:8000/api/v1/admin/pipeline/1/stage?new_stage=public_hearing&signal_id=5&notes=Hearing%20scheduled" \
  -H "Authorization: Bearer admin_token"
```

---

### DELETE /api/v1/admin/pipeline/{pipeline_id}

Delete a pipeline entry.

**Path Parameters:**
- `pipeline_id` (integer): ID of entry to delete

**Response:**
```json
{
  "success": true,
  "pipeline_id": 1
}
```

**Status Codes:**
- 200: Deleted
- 404: Entry not found
- 500: Database error

---

### POST /api/v1/admin/pipeline/ingest

Create/update pipeline entry from intelligence signal.

**Request Body:**
```json
{
  "id": 42,
  "addresses": ["555 Cambie Street"],
  "neighborhood": "Marpole",
  "zoning_from": "RM-4",
  "zoning_to": "CD-1",
  "height_after": 20,
  "unit_count": 250,
  "sqft": 120000.0,
  "signal_type": "rezoning_decision",
  "confidence": 0.92,
  "parcel_pid": "00054321"
}
```

**Response:**
```json
{
  "id": 42,
  "parcel_pid": "signal_42",
  "address": "555 Cambie Street",
  "neighborhood": "Marpole",
  "pipeline_stage": "rezoning_application",
  "proposed_units": 250,
  "signal_ids": [42],
  ...
}
```

**Status Codes:**
- 200: Created or updated
- 400: Missing required fields (addresses)
- 500: Database error

---

## Pipeline Stages

Valid pipeline stage values:

| Stage | Value | Description |
|-------|-------|-------------|
| Rezoning Application | `rezoning_application` | Initial rezoning request filed |
| Public Hearing | `public_hearing` | Project scheduled for public hearing |
| Council Decision | `council_decision` | Council vote scheduled or completed |
| Development Permit | `development_permit` | Development permit review process |
| Building Permit | `building_permit` | Building permit issued |
| Under Construction | `under_construction` | Active construction phase |
| Completed | `completed` | Project completed and occupied |

---

## Error Responses

All endpoints return error responses in this format:

```json
{
  "detail": "Error message describing what went wrong"
}
```

### Common Status Codes

| Code | Meaning |
|------|---------|
| 200 | Success |
| 404 | Entry not found |
| 409 | Conflict (e.g., duplicate parcel_pid) |
| 500 | Server error (database issue) |

---

## Pagination Examples

### Get first 20 entries
```bash
curl "http://localhost:8000/api/v1/intel/pipeline?limit=20&offset=0"
```

### Get next 20 entries
```bash
curl "http://localhost:8000/api/v1/intel/pipeline?limit=20&offset=20"
```

### Get all Downtown projects in early stages
```bash
curl "http://localhost:8000/api/v1/intel/pipeline?neighborhood=Downtown&stage=rezoning_application&limit=50"
```

---

## Usage Examples

### JavaScript/Fetch

```javascript
// List pipeline entries
async function listPipeline() {
  const response = await fetch('/api/v1/intel/pipeline?neighborhood=Downtown&limit=10');
  const data = await response.json();
  return data.entries;
}

// Get neighborhood supply
async function getNeighborhoodSupply(neighborhood) {
  const response = await fetch(`/api/v1/intel/pipeline/neighborhood/${neighborhood}`);
  return await response.json();
}

// Get statistics
async function getStats() {
  const response = await fetch('/api/v1/intel/pipeline/stats');
  return await response.json();
}

// Create entry (admin only)
async function createEntry(entryData, adminToken) {
  const response = await fetch('/api/v1/admin/pipeline', {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${adminToken}`,
      'Content-Type': 'application/json'
    },
    body: JSON.stringify(entryData)
  });
  return await response.json();
}

// Update stage (admin only)
async function updateStage(pipelineId, newStage, adminToken) {
  const url = new URL('/api/v1/admin/pipeline/' + pipelineId + '/stage', window.location.origin);
  url.searchParams.append('new_stage', newStage);

  const response = await fetch(url, {
    method: 'PUT',
    headers: {
      'Authorization': `Bearer ${adminToken}`
    }
  });
  return await response.json();
}
```

### Python/Requests

```python
import requests

# List pipeline entries
response = requests.get(
    'http://localhost:8000/api/v1/intel/pipeline',
    params={'neighborhood': 'Downtown', 'limit': 10}
)
entries = response.json()['entries']

# Get pipeline summary
response = requests.get('http://localhost:8000/api/v1/intel/pipeline/summary')
summary = response.json()

# Get neighborhood supply
response = requests.get(
    'http://localhost:8000/api/v1/intel/pipeline/neighborhood/Downtown'
)
supply = response.json()

# Create entry (admin only)
headers = {'Authorization': f'Bearer {admin_token}'}
entry_data = {
    'parcel_pid': '00012345',
    'address': '1234 Main Street',
    'neighborhood': 'Downtown',
    'pipeline_stage': 'rezoning_application',
    'proposed_units': 300,
}
response = requests.post(
    'http://localhost:8000/api/v1/admin/pipeline',
    json=entry_data,
    headers=headers
)
created_entry = response.json()
```

---

## Rate Limiting

No explicit rate limiting is implemented. Consider adding rate limiting middleware for production deployments.

---

## Caching

Currently, all endpoints perform live database queries. Future versions may implement caching via the `@cached` decorator for summary and stats endpoints.

---

## Updates and Changes

For the latest API changes and updates, see:
- `/VCL-54_IMPLEMENTATION.md` - Detailed implementation guide
- `/api/intelligence/pipeline_routes.py` - Route definitions with docstrings
- `/api/intelligence/supply_pipeline.py` - Data models and business logic

---

**Last Updated**: February 8, 2026
**API Version**: v1
**Status**: Production Ready
