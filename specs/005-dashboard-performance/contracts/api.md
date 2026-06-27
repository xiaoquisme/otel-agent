# API Contract: Dashboard Performance Optimization

**Feature**: 005-dashboard-performance

## Changed Endpoints

### `GET /api/requests` (updated)

**Query Parameters (changed):**

| Param    | Type    | Default | Description                    |
| -------- | ------- | ------- | ------------------------------ |
| cursor   | int     | 0       | Last seen request ID (replaces page) |
| limit    | int     | 50      | Rows per page (max 500)        |
| search   | string  | ""      | Text search on URL/upstream    |
| method   | string  | ""      | Filter by HTTP method          |
| status   | integer | 0       | Filter by status (0 = all)     |

**Response** (changed — `page` replaced by `cursor`):

```json
{
  "data": [...],
  "total": 150,
  "cursor": 100,
  "next_cursor": 50,
  "has_more": true
}
```

- `cursor`: The cursor used for this request
- `next_cursor`: The last `id` in `data` (use as next cursor)
- `has_more`: Whether more pages exist

### `GET /api/requests/:id` (unchanged)

Same as before. Performance improvement comes from connection reuse, not API change.

### `GET /api/events` (unchanged)

Same SSE endpoint. Performance improvement comes from connection reuse.

### `GET /api/export` (unchanged)

Same export endpoint.

## New Endpoint

### `POST /api/cache/clear`

Clear the COUNT cache. Useful after bulk deletes.

**Response**: `{"status": "ok"}`
