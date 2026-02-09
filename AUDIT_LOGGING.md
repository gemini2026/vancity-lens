# Audit Logging for Admin Operations (VCL-35 / SEC-012)

This document describes the structured audit logging system implemented for all admin endpoint access in the VanCity Lens API.

## Overview

The audit logging system provides comprehensive logging of all administrative operations with:
- **Structured JSON format** for easy parsing and analysis
- **Non-blocking logging** that doesn't affect request processing
- **Security-conscious design** that hashes sensitive credentials
- **Complete request/response metadata** for compliance and debugging

## Architecture

### Components

#### 1. `api/audit.py` - Core Audit Module

Contains three main components:

**AuditLogger Class**
- Logs admin operations in structured JSON format
- Uses a dedicated "audit" logger separate from application logs
- Provides both synchronous and asynchronous logging methods
- Silently handles logging errors to prevent request interruption

**AuditMiddleware Class**
- ASGI middleware that wraps all requests/responses
- Intercepts admin endpoint calls (`/api/v1/admin/*`)
- Extracts request metadata and captures response status
- Calls audit logger asynchronously

**Helper Functions**
- `_hash_admin_key_tail()`: Hashes the last 4 characters of admin keys
- `_get_client_ip()`: Extracts client IP respecting X-Forwarded-For headers
- `audit_log_dependency()`: FastAPI dependency for extracting audit info

#### 2. `api/main.py` - Application Configuration

Updates the FastAPI application to:
- Import `AuditMiddleware`
- Configure the audit logger during lifespan startup
- Register the middleware in the middleware chain

#### 3. `api/admin.py` - Admin Router Integration

Imports audit utilities for potential future enhancements (e.g., endpoint-specific audit context).

## Logged Fields

Each audit event is a JSON object with these fields:

```json
{
  "timestamp": 1707388800.123456,
  "operation": "load-bca",
  "endpoint": "/api/v1/admin/load-bca",
  "method": "POST",
  "client_ip": "192.168.1.100",
  "user_agent": "curl/7.68.0",
  "admin_key_hash": "a1b2c3d4",
  "status_code": 200,
  "duration_ms": 1234.56,
  "request_id": "550e8400-e29b-41d4-a716-446655440000"
}
```

### Field Descriptions

- **timestamp**: Unix timestamp (seconds since epoch) when the operation completed
- **operation**: Human-readable operation name extracted from endpoint path
- **endpoint**: Full HTTP request line (METHOD + path)
- **method**: HTTP method (GET, POST, etc.)
- **client_ip**: Client IP address (respects X-Forwarded-For proxy headers)
- **user_agent**: Client User-Agent header
- **admin_key_hash**: SHA256 hash of the last 4 characters of the admin API key
  - Returns "none" if no key provided
  - Returns "short" if key is less than 4 characters
  - Never logs the full key for security
- **status_code**: HTTP response status code
- **duration_ms**: Request processing time in milliseconds
- **request_id**: Unique UUID for correlating requests across logs

## Configuration

### Environment Variables

- **AUDIT_LOG_PATH** (default: `logs/audit.log`)
  - File path where audit events are written
  - Directory is created automatically if it doesn't exist
  - Format: JSON lines (one JSON object per line)

- **ADMIN_API_KEY**
  - Required to protect admin endpoints
  - If not set, admin endpoints are unrestricted (development only)

### Logger Configuration

The audit logger is automatically configured during application startup in the lifespan context:

```python
def _configure_audit_logger():
    audit_logger = logging.getLogger("audit")
    # Set up file handler with JSON formatter
    handler = logging.FileHandler(audit_log_path)
    handler.setFormatter(logging.Formatter("%(message)s"))
    audit_logger.addHandler(handler)
    audit_logger.setLevel(logging.INFO)
    audit_logger.propagate = False
```

## Usage Examples

### Reading Audit Logs

Audit logs are written as JSON lines (one JSON object per line):

```bash
# View recent audit events
tail -f logs/audit.log

# Parse and pretty-print audit events
cat logs/audit.log | jq .

# Filter for failed operations (status code 4xx/5xx)
cat logs/audit.log | jq 'select(.status_code >= 400)'

# Find operations by admin key hash
cat logs/audit.log | jq 'select(.admin_key_hash == "a1b2c3d4")'

# Calculate average operation duration
cat logs/audit.log | jq '.duration_ms' | awk '{sum+=$1} END {print sum/NR}'
```

### Log Analysis Examples

**Find all load-bca operations:**
```bash
cat logs/audit.log | jq 'select(.operation == "load-bca")'
```

**Find operations from a specific IP:**
```bash
cat logs/audit.log | jq 'select(.client_ip == "192.168.1.1")'
```

**Find slow operations (> 5 seconds):**
```bash
cat logs/audit.log | jq 'select(.duration_ms > 5000)'
```

**Group operations by status code:**
```bash
cat logs/audit.log | jq -s 'group_by(.status_code) | map({status: .[0].status_code, count: length})'
```

## Middleware Chain

The middleware is registered in this order (innermost to outermost):

1. **CORSMiddleware** - Handles CORS headers
2. **SecurityHeadersMiddleware** - Adds security headers (X-Frame-Options, etc.)
3. **AuditMiddleware** - Logs admin operations (VCL-35)

This order ensures:
- Audit logging happens before security headers are added
- Audit logging captures the actual request/response cycle
- Logging failures don't affect CORS or security headers

## Non-Blocking Design

The audit logger is designed to never block request processing:

1. **Asynchronous logging**: Uses `asyncio.create_task()` to submit logs in the background
2. **Silent failure**: Any logging errors are caught and ignored
3. **Independent logger**: Uses separate logger instance with dedicated handlers
4. **No propagation**: `propagate=False` prevents interference with application logging

Example error handling:

```python
try:
    # Attempt to log
    self.log_admin_operation(...)
except Exception:
    # Silently fail - request processing not affected
    pass
```

## Security Considerations

### Admin Key Hashing

Admin keys are never logged in plaintext. Only the last 4 characters are hashed:

```python
# Input: "my-secret-admin-key-1234"
# Logged: "a1b2c3d4" (SHA256 hash of "1234")
```

This allows identifying which admin account performed operations while protecting the secret key.

### Client IP Extraction

The implementation respects X-Forwarded-For headers for proxied environments:

```
X-Forwarded-For: 203.0.113.195, 70.41.3.18, 150.172.238.178
# Extracted: 203.0.113.195 (leftmost = original client)
```

### Log File Permissions

Ensure audit log files have restricted permissions:

```bash
chmod 640 logs/audit.log
```

## Testing

Comprehensive tests are included in `tests/test_audit_logging.py`:

```bash
pytest tests/test_audit_logging.py -v
```

Test coverage includes:
- Admin key hashing with various inputs
- Client IP extraction from multiple sources
- JSON serialization and format validation
- Timestamp accuracy
- Error handling and graceful degradation
- Integration with various admin operations

## Compliance

This implementation satisfies the requirements of:
- **VCL-35 [SEC-012]**: Audit logging for admin operations
- **Bill 47 Entitlement Engine**: Security audit trails for regulatory compliance

Audit logs should be:
- Retained for regulatory compliance periods
- Protected from unauthorized access
- Monitored for suspicious activity patterns
- Included in security incident investigations

## Future Enhancements

Potential improvements for future versions:

1. **Structured logging to database**: Store audit events in PostgreSQL for easier querying
2. **Real-time alerting**: Alert on suspicious patterns (e.g., rapid failures)
3. **Request/response bodies**: Optionally log request/response data for detailed audits
4. **Custom fields**: Allow endpoints to add operation-specific audit context
5. **Log encryption**: Encrypt audit logs in transit and at rest
6. **Distributed tracing**: Integrate with OpenTelemetry for full request tracing

## Troubleshooting

### Audit logs not appearing

1. Check that `ADMIN_API_KEY` is set (endpoints require authentication)
2. Verify `logs/` directory is writable:
   ```bash
   touch logs/test.log && rm logs/test.log
   ```
3. Check application logs for any startup errors:
   ```bash
   grep "Audit logger" logs/application.log
   ```

### Performance issues

The audit logging is designed to be non-blocking. If you see performance issues:

1. Check disk write speed (most common bottleneck)
2. Consider log rotation for large files:
   ```bash
   logrotate -f /etc/logrotate.d/audit
   ```
3. Monitor async task queue:
   ```python
   import asyncio
   print(len(asyncio.all_tasks()))
   ```

### Debugging audit logging

Enable debug logging:

```python
logging.getLogger("audit").setLevel(logging.DEBUG)
```

Check that middleware is registered:

```bash
curl -H "X-Admin-Key: test" http://localhost:8000/api/v1/admin/data-status
tail logs/audit.log | jq .
```
