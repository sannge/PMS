# Load Testing for PM Desktop API

Load testing suite using Locust to validate the API can handle 5,000 concurrent users.

## Prerequisites

1. **Install Locust:**
   ```bash
   pip install -r requirements.txt
   ```

2. **Start the backend server:**
   ```bash
   cd fastapi-backend
   uvicorn app.main:app --host 0.0.0.0 --port 8001 --workers 4
   ```

3. **Ensure database is running** with test data or empty (users will be created dynamically)

## Running Load Tests

### Interactive Mode (with Web UI)

```bash
cd fastapi-backend/tests/load
locust -f locustfile.py --host=http://localhost:8001
```

Then open http://localhost:8089 in your browser to configure and start the test.

### Headless Mode (CLI only)

**Quick test (100 users):**
```bash
locust -f locustfile.py --host=http://localhost:8001 -u 100 -r 10 --headless -t 2m
```

**Medium test (1,000 users):**
```bash
locust -f locustfile.py --host=http://localhost:8001 -u 1000 -r 50 --headless -t 5m
```

**Full scale test (5,000 users):**
```bash
locust -f locustfile.py --host=http://localhost:8001 -u 5000 -r 100 --headless -t 10m
```

### Parameters

| Parameter | Description |
|-----------|-------------|
| `-u` / `--users` | Total number of concurrent users |
| `-r` / `--spawn-rate` | Users spawned per second |
| `-t` / `--run-time` | Test duration (e.g., 5m, 1h) |
| `--headless` | Run without web UI |
| `--csv=results` | Export results to CSV files |
| `--html=report.html` | Generate HTML report |

## User Behavior Profiles

The test suite includes three user types with different weights:

| User Type | Weight | Behavior |
|-----------|--------|----------|
| **BrowsingUser** | 60% | Mostly reads, occasional writes |
| **ActiveUser** | 30% | Creates and updates frequently |
| **PowerUser** | 10% | Admin tasks, member management |

## Endpoint Coverage

The load test covers all major API endpoints:

### Applications
- `GET /api/applications` - List applications
- `GET /api/applications/{id}` - Get application details
- `POST /api/applications` - Create application
- `PATCH /api/applications/{id}` - Update application

### Projects
- `GET /api/applications/{id}/projects` - List projects
- `GET /api/projects/{id}` - Get project details
- `POST /api/applications/{id}/projects` - Create project
- `PATCH /api/projects/{id}` - Update project

### Tasks
- `GET /api/projects/{id}/tasks` - List tasks (highest traffic)
- `GET /api/tasks/{id}` - Get task details
- `POST /api/projects/{id}/tasks` - Create task
- `PATCH /api/tasks/{id}` - Update task / change status

### Comments
- `GET /api/tasks/{id}/comments` - List comments
- `POST /api/tasks/{id}/comments` - Create comment
- `PATCH /api/comments/{id}` - Update comment

### Checklists
- `GET /api/tasks/{id}/checklists` - List checklists
- `POST /api/tasks/{id}/checklists` - Create checklist
- `PATCH /api/checklist-items/{id}` - Toggle checklist item

### Notifications
- `GET /api/notifications` - List notifications
- `GET /api/notifications/unread-count` - Get unread count
- `PATCH /api/notifications/{id}/read` - Mark as read

### Members
- `GET /api/applications/{id}/members` - List app members
- `GET /api/projects/{id}/members` - List project members

### Notes
- `GET /api/applications/{id}/notes` - List notes
- `GET /api/applications/{id}/notes/tree` - Get note tree
- `GET /api/notes/{id}` - Get note details
- `POST /api/applications/{id}/notes` - Create note
- `PUT /api/notes/{id}` - Update note

### Users
- `GET /api/users/me` - Get current user
- `PATCH /api/users/me` - Update profile

## Target Metrics

| Metric | Target | Critical |
|--------|--------|----------|
| Median Response Time (API) | < 100ms | < 200ms |
| 95th Percentile (API) | < 300ms | < 500ms |
| 99th Percentile (API) | < 500ms | < 1000ms |
| Error Rate | < 0.1% | < 1% |
| Requests/Second | > 1000 | > 500 |

**Note on Auth Response Times:**
- Registration and login involve bcrypt password hashing
- bcrypt is intentionally CPU-intensive for security
- Expected time: 3-5 seconds per auth operation with default work factor
- This is normal and expected behavior, not a performance issue

## Generating Reports

```bash
# CSV report
locust -f locustfile.py --host=http://localhost:8001 -u 1000 -r 50 --headless -t 5m --csv=load_test_results

# HTML report
locust -f locustfile.py --host=http://localhost:8001 -u 1000 -r 50 --headless -t 5m --html=load_test_report.html
```

## Distributed Testing

For testing with more than 5,000 users, use distributed mode:

**Master:**
```bash
locust -f locustfile.py --master --host=http://localhost:8001
```

**Workers (run on multiple machines):**
```bash
locust -f locustfile.py --worker --master-host=<master-ip>
```

## Troubleshooting

### High error rate during ramp-up
- Increase spawn rate more gradually (`-r 20` instead of `-r 100`)
- Check database connection pool limits
- Ensure Redis is running for WebSocket pub/sub

### Connection refused errors
- Verify backend is running and accessible
- Check firewall settings
- Increase uvicorn worker count

### Memory issues
- Use multiple uvicorn workers (`--workers 4`)
- Enable connection pooling in database
- Consider running distributed Locust workers
