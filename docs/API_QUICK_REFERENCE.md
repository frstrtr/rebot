# Rebot API Quick Reference

## Base URL
```
http://localhost:8000
```

## Authentication
```http
X-API-KEY: your_api_key_here
```

## Endpoints Overview

| Endpoint | Method | Purpose | Performance |
|----------|--------|---------|-------------|
| `/check-address` | POST | Full address validation + all memos | Comprehensive |
| `/scam-report` | POST | Get existing scam analysis | Fast (read-only) |
| `/report-scam` | POST | Create new scam analysis | Slower (AI analysis) |

## Quick Examples

### 1. Check Address (Full Details)
```bash
curl -X POST "http://localhost:8000/check-address" \
  -H "X-API-KEY: your_key" \
  -H "Content-Type: application/json" \
  -d '{
    "crypto_address": "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t",
    "request_by_telegram_id": 123456789,
    "provided_by_telegram_id": 123456789,
    "blockchain_type": "tron"
  }'
```

### 2. Get Scam Report (Existing Analysis)
```bash
curl -X POST "http://localhost:8000/scam-report" \
  -H "X-API-KEY: your_key" \
  -H "Content-Type: application/json" \
  -d '{
    "crypto_address": "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t",
    "request_by_telegram_id": 123456789,
    "blockchain_type": "tron"
  }'
```

### 3. Create Scam Analysis (New Analysis)
```bash
curl -X POST "http://localhost:8000/report-scam" \
  -H "X-API-KEY: your_key" \
  -H "Content-Type: application/json" \
  -d '{
    "crypto_address": "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t",
    "request_by_telegram_id": 123456789,
    "blockchain_type": "tron"
  }'
```

## Common Response Patterns

### Success Response
```json
{
  "status": "OK",
  "message": "Operation successful",
  "request_datetime": "2025-07-08T18:24:13.003248Z",
  // ... additional fields
}
```

### Error Response
```json
{
  "status": "ERROR",
  "message": "Error description",
  "request_datetime": "2025-07-08T18:24:13.003248Z"
}
```

### Clarification Needed
```json
{
  "status": "CLARIFICATION_NEEDED",
  "message": "Address is ambiguous",
  "possible_blockchains": ["bitcoin", "ethereum"],
  "request_datetime": "2025-07-08T18:24:13.003248Z"
}
```

## Supported Blockchains

- `bitcoin` - Bitcoin
- `ethereum` - Ethereum
- `bsc` - Binance Smart Chain
- `tron` - TRON
- `litecoin` - Litecoin
- `dogecoin` - Dogecoin
- `bitcoin_cash` - Bitcoin Cash

## Common Error Codes

| Code | Meaning |
|------|---------|
| 200 | Success (check `status` field) |
| 403 | Invalid/missing API key |
| 422 | Validation error |
| 500 | Server error |

## Validation Rules

- **Telegram IDs**: 1 to 10,000,000,000
- **Addresses**: Must be valid crypto address format
- **API Key**: Required in all requests

## Python Quick Start

```python
import requests

def api_request(endpoint, payload):
    url = f"http://localhost:8000/{endpoint}"
    headers = {
        "X-API-KEY": "your_api_key",
        "Content-Type": "application/json"
    }
    response = requests.post(url, headers=headers, json=payload)
    return response.json()

# Check address
result = api_request("check-address", {
    "crypto_address": "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t",
    "request_by_telegram_id": 123456789,
    "provided_by_telegram_id": 123456789,
    "blockchain_type": "tron"
})

print(f"Status: {result['status']}")
print(f"Risk Score: {result.get('risk_score', 'N/A')}")
```

## JavaScript Quick Start

```javascript
async function apiRequest(endpoint, payload) {
    const response = await fetch(`http://localhost:8000/${endpoint}`, {
        method: 'POST',
        headers: {
            'X-API-KEY': 'your_api_key',
            'Content-Type': 'application/json'
        },
        body: JSON.stringify(payload)
    });
    return await response.json();
}

// Get scam report
const result = await apiRequest('scam-report', {
    crypto_address: 'TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t',
    request_by_telegram_id: 123456789,
    blockchain_type: 'tron'
});

console.log(`Analysis Available: ${result.address_analyzed}`);
console.log(`Risk Score: ${result.risk_score || 'N/A'}`);
```

## Tips

1. **Use specific blockchain types** when possible to avoid ambiguity
2. **Check `address_analyzed`** field before using scam report data
3. **Handle `CLARIFICATION_NEEDED`** responses by retrying with blockchain_type
4. **Cache results** on your side to reduce API calls
5. **Use `/scam-report`** for quick checks, `/check-address` for full details

## Interactive Documentation

Visit `http://localhost:8000/docs` for full interactive API documentation with test interface.
