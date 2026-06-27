# API Contract: Web Dashboard

**Feature**: 004-web-dashboard

## Endpoints

### `GET /`

Serve the dashboard HTML page.

**Response**: `text/html` — single-page dashboard

---

### `GET /api/requests`

Fetch paginated, filtered request logs.

**Query Parameters:**

| Param    | Type    | Default | Description                    |
| -------- | ------- | ------- | ------------------------------ |
| search   | string  | ""      | Text search on URL/upstream    |
| method   | string  | ""      | Filter by HTTP method          |
| status   | integer | 0       | Filter by status (0 = all)     |
| page     | integer | 1       | Page number                    |
| per_page | integer | 50      | Rows per page                  |

**Response**: `application/json`

```json
{
  "data": [
    {
      "id": 1,
      "timestamp": "2026-06-26T10:00:00Z",
      "method": "POST",
      "url": "/openai/v1/chat/completions",
      "upstream": "https://api.openai.com/v1/chat/completions",
      "response_status": 200,
      "latency_ms": 1234.5
    }
  ],
  "total": 150,
  "page": 1,
  "per_page": 50
}
```

---

### `GET /api/requests/:id`

Fetch full details for a single request.

**Response**: `application/json`

```json
{
  "id": 1,
  "timestamp": "2026-06-26T10:00:00Z",
  "method": "POST",
  "url": "/openai/v1/chat/completions",
  "upstream": "https://api.openai.com/v1/chat/completions",
  "request_headers": {"Authorization": "Bearer sk-...", "Content-Type": "application/json"},
  "request_body": "{\"model\":\"gpt-4\",\"messages\":[...]}",
  "response_status": 200,
  "response_headers": {"content-type": "application/json"},
  "response_body": "{\"choices\":[...]}",
  "latency_ms": 1234.5
}
```

---

### `GET /api/export`

Export filtered requests as CSV or JSON.

**Query Parameters:**

| Param  | Type   | Default | Description         |
| ------ | ------ | ------- | ------------------- |
| format | string | "csv"   | "csv" or "json"     |
| (plus same filter params as /api/requests) |

**Response**: `text/csv` or `application/json` with `Content-Disposition: attachment`

---

### `GET /api/events`

Server-Sent Events stream for real-time updates.

**Response**: `text/event-stream`

```
data: {"id": 2, "method": "POST", "url": "/anthropic/v1/messages", "status": 200, "latency_ms": 567.8}

data: {"id": 3, "method": "GET", "url": "/openai/v1/models", "status": 200, "latency_ms": 45.2}
```
