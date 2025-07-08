# Rebot External API Documentation

## Overview

The Rebot External API provides programmatic access to crypto address validation, scam analysis, and memo retrieval services. This RESTful API allows external applications to integrate with the Rebot system for cryptocurrency security and analysis purposes.

**Base URL**: `http://localhost:8000` (or your configured server URL)

**API Version**: 1.0.0

## Authentication

All API endpoints require authentication using an API key.

### API Key Authentication

Include the API key in the request header:

```http
X-API-KEY: your_api_key_here
```

### Response Codes

- `200 OK` - Request successful
- `403 Forbidden` - Invalid or missing API key
- `422 Unprocessable Entity` - Validation error in request data
- `500 Internal Server Error` - Server configuration error

## Endpoints

### 1. Address Check - `/check-address`

**Method**: `POST`

**Purpose**: Comprehensive crypto address validation, memo retrieval, and risk analysis.

#### Request Format

```json
{
  "crypto_address": "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t",
  "request_by_telegram_id": 123456789,
  "provided_by_telegram_id": 123456789,
  "blockchain_type": "tron"
}
```

#### Request Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `crypto_address` | string | Yes | The crypto address to validate |
| `request_by_telegram_id` | integer | Yes | Telegram ID of requester (1-10,000,000,000) |
| `provided_by_telegram_id` | integer | Yes | Telegram ID of address provider (1-10,000,000,000) |
| `blockchain_type` | string | No | Blockchain hint for ambiguous addresses |

#### Response Format

```json
{
  "status": "OK",
  "message": "Address details retrieved successfully.",
  "request_datetime": "2025-07-08T18:24:13.003248Z",
  "bot_deeplink": "https://t.me/cryptoscamreportbot?start=TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t",
  "blockchain_explorer_link": "https://tronscan.org/#/address/TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t",
  "public_memos": ["Public memo 1", "Public memo 2"],
  "possible_blockchains": null,
  "risk_score": 0.75,
  "risk_score_updated_at": "2025-07-08T16:18:30.031376Z"
}
```

#### Response Fields

| Field | Type | Description |
|-------|------|-------------|
| `status` | string | "OK", "ERROR", or "CLARIFICATION_NEEDED" |
| `message` | string | Human-readable status message |
| `request_datetime` | datetime | UTC timestamp of request |
| `bot_deeplink` | string | Link to check address with Telegram bot |
| `blockchain_explorer_link` | string | Link to blockchain explorer |
| `public_memos` | array | List of public memos for the address |
| `possible_blockchains` | array | Available blockchains (for ambiguous addresses) |
| `risk_score` | float | AI risk score (0.0-1.0) for TRON addresses |
| `risk_score_updated_at` | datetime | When risk score was last updated |

---

### 2. Scam Report - `/scam-report`

**Method**: `POST`

**Purpose**: Get existing scam analysis reports for crypto addresses (read-only).

#### Request Format

```json
{
  "crypto_address": "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t",
  "request_by_telegram_id": 123456789,
  "blockchain_type": "tron"
}
```

#### Request Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `crypto_address` | string | Yes | The crypto address to check |
| `request_by_telegram_id` | integer | Yes | Telegram ID of requester (1-10,000,000,000) |
| `blockchain_type` | string | No | Blockchain hint for ambiguous addresses |

#### Response Format

```json
{
  "status": "OK",
  "message": "Scam analysis found for this address.",
  "request_datetime": "2025-07-08T18:24:13.003248Z",
  "address_analyzed": true,
  "scam_report": "This address shows signs of fraudulent activity...",
  "analysis_date": "2025-07-08T16:18:30.031376Z",
  "risk_score": 0.85,
  "blockchain_explorer_link": "https://tronscan.org/#/address/TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t",
  "bot_deeplink": "https://t.me/cryptoscamreportbot?start=TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t",
  "possible_blockchains": null
}
```

#### Response Fields

| Field | Type | Description |
|-------|------|-------------|
| `status` | string | "OK", "ERROR", or "CLARIFICATION_NEEDED" |
| `message` | string | Human-readable status message |
| `request_datetime` | datetime | UTC timestamp of request |
| `address_analyzed` | boolean | Whether scam analysis exists |
| `scam_report` | string | Full scam analysis report text |
| `analysis_date` | datetime | When analysis was performed |
| `risk_score` | float | AI risk score (0.0-1.0) |
| `blockchain_explorer_link` | string | Link to blockchain explorer |
| `bot_deeplink` | string | Link to check address with Telegram bot |
| `possible_blockchains` | array | Available blockchains (for ambiguous addresses) |

---

### 3. Report Scam - `/report-scam`

**Method**: `POST`

**Purpose**: Perform new scam analysis on crypto addresses (creates new analysis).

#### Request Format

```json
{
  "crypto_address": "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t",
  "request_by_telegram_id": 123456789,
  "blockchain_type": "tron"
}
```

#### Request Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `crypto_address` | string | Yes | The crypto address to analyze |
| `request_by_telegram_id` | integer | Yes | Telegram ID of requester (1-10,000,000,000) |
| `blockchain_type` | string | No | Blockchain hint for ambiguous addresses |

#### Response Format

```json
{
  "status": "OK",
  "message": "Scam analysis completed.",
  "request_datetime": "2025-07-08T18:24:13.003248Z",
  "address_analyzed": true,
  "scam_report": "Analysis shows moderate risk factors...",
  "analysis_date": "2025-07-08T18:24:13.003248Z",
  "risk_score": 0.65,
  "blockchain_explorer_link": "https://tronscan.org/#/address/TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t",
  "bot_deeplink": "https://t.me/cryptoscamreportbot?start=TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t",
  "possible_blockchains": null
}
```

## Supported Blockchains

The API supports address validation for the following blockchains:

- **Bitcoin (BTC)**: `bitcoin`
- **Ethereum (ETH)**: `ethereum`
- **Binance Smart Chain (BSC)**: `bsc`
- **TRON (TRX)**: `tron`
- **Litecoin (LTC)**: `litecoin`
- **Dogecoin (DOGE)**: `dogecoin`
- **Bitcoin Cash (BCH)**: `bitcoin_cash`

### Ambiguous Addresses

Some address formats can belong to multiple blockchains. When this occurs:

1. The API returns `status: "CLARIFICATION_NEEDED"`
2. The `possible_blockchains` field lists available options
3. Retry the request with the `blockchain_type` parameter

## Usage Examples

### Python Example

```python
import requests

API_KEY = "your_api_key_here"
BASE_URL = "http://localhost:8000"

headers = {
    "X-API-KEY": API_KEY,
    "Content-Type": "application/json"
}

# Check address comprehensively
def check_address(address, requester_id, provider_id, blockchain=None):
    url = f"{BASE_URL}/check-address"
    payload = {
        "crypto_address": address,
        "request_by_telegram_id": requester_id,
        "provided_by_telegram_id": provider_id,
        "blockchain_type": blockchain
    }
    
    response = requests.post(url, headers=headers, json=payload)
    return response.json()

# Get existing scam report
def get_scam_report(address, requester_id, blockchain=None):
    url = f"{BASE_URL}/scam-report"
    payload = {
        "crypto_address": address,
        "request_by_telegram_id": requester_id,
        "blockchain_type": blockchain
    }
    
    response = requests.post(url, headers=headers, json=payload)
    return response.json()

# Perform new scam analysis
def report_scam(address, requester_id, blockchain=None):
    url = f"{BASE_URL}/report-scam"
    payload = {
        "crypto_address": address,
        "request_by_telegram_id": requester_id,
        "blockchain_type": blockchain
    }
    
    response = requests.post(url, headers=headers, json=payload)
    return response.json()

# Usage
result = check_address("TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t", 123456789, 123456789, "tron")
print(f"Status: {result['status']}")
print(f"Risk Score: {result.get('risk_score', 'N/A')}")
print(f"Public Memos: {len(result.get('public_memos', []))}")
```

### JavaScript Example

```javascript
const API_KEY = "your_api_key_here";
const BASE_URL = "http://localhost:8000";

const headers = {
    "X-API-KEY": API_KEY,
    "Content-Type": "application/json"
};

// Check address comprehensively
async function checkAddress(address, requesterId, providerId, blockchain = null) {
    const url = `${BASE_URL}/check-address`;
    const payload = {
        crypto_address: address,
        request_by_telegram_id: requesterId,
        provided_by_telegram_id: providerId,
        blockchain_type: blockchain
    };
    
    const response = await fetch(url, {
        method: "POST",
        headers: headers,
        body: JSON.stringify(payload)
    });
    
    return await response.json();
}

// Get existing scam report
async function getScamReport(address, requesterId, blockchain = null) {
    const url = `${BASE_URL}/scam-report`;
    const payload = {
        crypto_address: address,
        request_by_telegram_id: requesterId,
        blockchain_type: blockchain
    };
    
    const response = await fetch(url, {
        method: "POST",
        headers: headers,
        body: JSON.stringify(payload)
    });
    
    return await response.json();
}

// Usage
checkAddress("TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t", 123456789, 123456789, "tron")
    .then(result => {
        console.log(`Status: ${result.status}`);
        console.log(`Risk Score: ${result.risk_score || 'N/A'}`);
        console.log(`Public Memos: ${result.public_memos?.length || 0}`);
    });
```

### cURL Examples

```bash
# Check address
curl -X POST "http://localhost:8000/check-address" \
  -H "X-API-KEY: your_api_key_here" \
  -H "Content-Type: application/json" \
  -d '{
    "crypto_address": "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t",
    "request_by_telegram_id": 123456789,
    "provided_by_telegram_id": 123456789,
    "blockchain_type": "tron"
  }'

# Get scam report
curl -X POST "http://localhost:8000/scam-report" \
  -H "X-API-KEY: your_api_key_here" \
  -H "Content-Type: application/json" \
  -d '{
    "crypto_address": "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t",
    "request_by_telegram_id": 123456789,
    "blockchain_type": "tron"
  }'

# Perform scam analysis
curl -X POST "http://localhost:8000/report-scam" \
  -H "X-API-KEY: your_api_key_here" \
  -H "Content-Type: application/json" \
  -d '{
    "crypto_address": "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t",
    "request_by_telegram_id": 123456789,
    "blockchain_type": "tron"
  }'
```

## Error Handling

### Common Error Responses

#### Invalid API Key (403)

```json
{
  "detail": "Could not validate credentials"
}
```

#### Validation Error (422)

```json
{
  "detail": [
    {
      "type": "less_than_equal",
      "loc": ["body", "request_by_telegram_id"],
      "msg": "Input should be less than or equal to 10000000000",
      "input": 99999999999,
      "ctx": {"le": 10000000000}
    }
  ]
}
```

#### Address Format Error (200 with ERROR status)

```json
{
  "status": "ERROR",
  "message": "'invalid_address' is not a valid or recognized crypto address format.",
  "request_datetime": "2025-07-08T18:24:13.003248Z",
  "bot_deeplink": null,
  "blockchain_explorer_link": null,
  "public_memos": null,
  "possible_blockchains": null,
  "risk_score": null,
  "risk_score_updated_at": null
}
```

#### Clarification Needed (200 with CLARIFICATION_NEEDED status)

```json
{
  "status": "CLARIFICATION_NEEDED",
  "message": "Address format is ambiguous and could belong to multiple blockchains. Please clarify by providing a 'blockchain_type'.",
  "request_datetime": "2025-07-08T18:24:13.003248Z",
  "possible_blockchains": ["bitcoin", "ethereum", "bsc"],
  "bot_deeplink": null,
  "blockchain_explorer_link": null,
  "public_memos": null,
  "risk_score": null,
  "risk_score_updated_at": null
}
```

## Rate Limiting

- Rate limiting may be applied based on API key
- Respect HTTP status codes and implement exponential backoff
- For high-volume usage, contact the API provider

## Security Considerations

- **HTTPS**: Always use HTTPS in production environments
- **API Key Security**: Store API keys securely and rotate regularly
- **Input Validation**: Validate addresses on client side when possible
- **Audit Logging**: All requests are logged for security purposes
- **IP Restrictions**: API access may be restricted by IP address

## API Comparison

| Feature | `/check-address` | `/scam-report` | `/report-scam` |
|---------|------------------|----------------|----------------|
| **Purpose** | Full address validation | Get existing analysis | Create new analysis |
| **Returns** | All public memos | Scam analysis only | New analysis results |
| **Performance** | Comprehensive | Fast (read-only) | Slower (AI analysis) |
| **Use Case** | Complete details | Quick scam check | Generate new report |
| **Caching** | Uses cached data | Uses cached data | Creates new data |

## Data Sources

- **Blockchain Data**: Real-time data from blockchain explorers
- **AI Analysis**: Google Vertex AI for TRON risk scoring
- **Memo Database**: User-submitted and verified memo data
- **Scam Reports**: Community-contributed scam analysis

## Support and Resources

- **Interactive Documentation**: Visit `/docs` on your API server
- **OpenAPI Specification**: Available at `/openapi.json`
- **Status Page**: Check server status at `/docs`
- **GitHub Repository**: [Rebot Project](https://github.com/your-repo/rebot)

## Changelog

### Version 1.0.0 (2025-07-08)

- Initial API release
- Added `/check-address` endpoint
- Added `/scam-report` endpoint
- Added `/report-scam` endpoint
- Implemented API key authentication
- Added comprehensive error handling
- Integrated AI risk scoring for TRON addresses

---

**Last Updated**: July 8, 2025  
**API Version**: 1.0.0  
**Documentation Version**: 1.0.0
