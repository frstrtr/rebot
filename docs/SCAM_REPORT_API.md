# Scam Report API Documentation

## Overview
The `/scam-report` endpoint provides a simplified way to check if a crypto address has been analyzed for scam/fraud activity and retrieve the analysis results.

## Endpoint
```
POST /scam-report
```

## Purpose
- Check if scam analysis has been performed for a specific crypto address
- Retrieve existing public scam analysis reports
- Get risk scores if available
- Provide explorer links and bot deeplinks

## Request Format

### Headers
- `X-API-KEY`: Required API key for authentication
- `Content-Type`: application/json

### Request Body
```json
{
  "crypto_address": "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t",
  "request_by_telegram_id": 123456789,
  "blockchain_type": "tron"  // Optional: helps resolve ambiguous addresses
}
```

### Parameters
- `crypto_address` (string, required): The crypto address to check
- `request_by_telegram_id` (integer, required): Telegram ID of the user making the request (1-10,000,000,000)
- `blockchain_type` (string, optional): Specify blockchain for ambiguous addresses ("ethereum", "tron", "bitcoin", etc.)

## Response Format

### Success Response (200 OK)
```json
{
  "status": "OK",
  "message": "Scam analysis found for this address." | "No scam analysis has been performed for this address yet.",
  "request_datetime": "2025-07-08T18:24:13.003248Z",
  "address_analyzed": true|false,
  "scam_report": "Full scam analysis report text...",  // null if no analysis
  "analysis_date": "2025-07-08T18:24:13.003248Z",      // null if no analysis
  "risk_score": 0.75,                                  // 0.0-1.0 or null
  "blockchain_explorer_link": "https://etherscan.io/address/...",
  "bot_deeplink": "https://t.me/cryptoscamreportbot?start=...",
  "possible_blockchains": null  // Only present if clarification needed
}
```

### Error Response (200 OK with error status)
```json
{
  "status": "ERROR",
  "message": "Error description",
  "request_datetime": "2025-07-08T18:24:13.003248Z",
  "address_analyzed": false,
  "scam_report": null,
  "analysis_date": null,
  "risk_score": null,
  "blockchain_explorer_link": null,
  "bot_deeplink": null,
  "possible_blockchains": null
}
```

### Clarification Needed Response (200 OK)
```json
{
  "status": "CLARIFICATION_NEEDED",
  "message": "Address format is ambiguous and could belong to multiple blockchains. Please clarify by providing a 'blockchain_type'.",
  "request_datetime": "2025-07-08T18:24:13.003248Z",
  "address_analyzed": false,
  "scam_report": null,
  "analysis_date": null,
  "risk_score": null,
  "blockchain_explorer_link": null,
  "bot_deeplink": null,
  "possible_blockchains": ["bitcoin", "ethereum", "bsc"]
}
```

## Response Fields

- `status`: "OK", "ERROR", or "CLARIFICATION_NEEDED"
- `message`: Human-readable status message
- `request_datetime`: UTC timestamp of the request
- `address_analyzed`: Boolean indicating if scam analysis has been performed
- `scam_report`: Full text of the scam analysis report (if available)
- `analysis_date`: When the analysis was performed (if available)
- `risk_score`: AI-generated risk score from 0.0 (low risk) to 1.0 (high risk)
- `blockchain_explorer_link`: Link to blockchain explorer
- `bot_deeplink`: Link to check address with the Telegram bot
- `possible_blockchains`: List of possible blockchains (only for ambiguous addresses)

## Use Cases

### 1. Check if address has been analyzed
```bash
curl -X POST "http://localhost:8000/scam-report" \
  -H "X-API-KEY: your_api_key" \
  -H "Content-Type: application/json" \
  -d '{
    "crypto_address": "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t",
    "request_by_telegram_id": 123456789,
    "blockchain_type": "tron"
  }'
```

### 2. Handle ambiguous addresses
```bash
# First request without blockchain_type
curl -X POST "http://localhost:8000/scam-report" \
  -H "X-API-KEY: your_api_key" \
  -H "Content-Type: application/json" \
  -d '{
    "crypto_address": "1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa",
    "request_by_telegram_id": 123456789
  }'

# If clarification needed, follow up with specific blockchain
curl -X POST "http://localhost:8000/scam-report" \
  -H "X-API-KEY: your_api_key" \
  -H "Content-Type: application/json" \
  -d '{
    "crypto_address": "1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa",
    "request_by_telegram_id": 123456789,
    "blockchain_type": "bitcoin"
  }'
```

## Error Handling

- **401 Unauthorized**: Missing or invalid API key
- **422 Validation Error**: Invalid request parameters
- **500 Internal Server Error**: Server configuration issues

## Differences from `/check-address`

| Feature | `/check-address` | `/scam-report` |
|---------|------------------|----------------|
| **Purpose** | Full address validation & memo retrieval | Simplified scam analysis check |
| **Response** | All public memos | Only scam analysis report |
| **Performance** | Heavier (fetches all memos) | Lighter (focused query) |
| **Use Case** | Complete address details | Quick scam check |

## Integration Examples

### Python
```python
import requests

def check_scam_report(address, user_id, blockchain=None):
    url = "http://localhost:8000/scam-report"
    headers = {
        "X-API-KEY": "your_api_key",
        "Content-Type": "application/json"
    }
    payload = {
        "crypto_address": address,
        "request_by_telegram_id": user_id,
        "blockchain_type": blockchain
    }
    
    response = requests.post(url, headers=headers, json=payload)
    return response.json()

# Usage
result = check_scam_report("TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t", 123456789, "tron")
if result["address_analyzed"]:
    print(f"Scam report: {result['scam_report']}")
    print(f"Risk score: {result['risk_score']}")
else:
    print("No scam analysis available")
```

### JavaScript
```javascript
async function checkScamReport(address, userId, blockchain = null) {
  const response = await fetch('http://localhost:8000/scam-report', {
    method: 'POST',
    headers: {
      'X-API-KEY': 'your_api_key',
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({
      crypto_address: address,
      request_by_telegram_id: userId,
      blockchain_type: blockchain
    })
  });
  
  return await response.json();
}

// Usage
checkScamReport('TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t', 123456789, 'tron')
  .then(result => {
    if (result.address_analyzed) {
      console.log('Scam report:', result.scam_report);
      console.log('Risk score:', result.risk_score);
    } else {
      console.log('No scam analysis available');
    }
  });
```

## Security Notes

- Always use HTTPS in production
- Keep API keys secure and rotate regularly
- Rate limiting may apply
- All requests are logged for audit purposes
- Telegram user IDs are validated for range (1-10,000,000,000)

## See Also

- `/check-address` - Complete address validation and memo retrieval
- `/docs` - Interactive API documentation
- API authentication documentation
