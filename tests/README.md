# External API Testing Guide

This guide helps you test the functionality of your external API endpoints.

## Quick Setup

### 1. Install Test Dependencies

```bash
# From the project root directory
pip install -r tests/requirements_test.txt
```

### 2. Check Configuration

```bash
python check_api_config.py
```

This will verify your API configuration and show you what needs to be set up.

### 3. Update Test Configuration

Edit the generated `tests/test_config.py` file and update:

- `API_KEY`: Use the value shown by the config checker
- Test addresses if needed

### 4. Start the API Server

```bash
# In one terminal
python run_api_server.py
```

### 5. Run Tests

```bash
# In another terminal
python tests/test_external_api.py
```

## Test Coverage

The test suite covers:

### ✅ **Basic Functionality**

- API server health check
- Valid TRON address processing
- Valid Ethereum address processing
- Response structure validation

### ✅ **Error Handling**

- Invalid address formats
- Unauthorized requests (missing/invalid API key)
- Invalid Telegram IDs
- Wrong blockchain hints

### ✅ **Advanced Features**

- Ambiguous address handling
- Risk score consistency
- Memo retrieval
- Explorer link generation

### ✅ **Security**

- API key validation
- Input sanitization
- Request logging

## Test Results Interpretation

### 🎉 **All Tests Pass**

Your API is working correctly! The implementation handles:

- Address validation across multiple blockchains
- Risk score generation and caching
- Proper error responses
- Security authentication

### ⚠️ **Some Tests Fail**

Common issues and solutions:

**Connection Errors:**

- Ensure the API server is running (`python run_api_server.py`)
- Check the port (default: 8000)
- Verify firewall settings

**Authentication Errors:**

- Update `API_KEY` in the test configuration
- Verify `EXTERNAL_API_SECRET` is set in your config

**Database Errors:**

- Ensure your database is accessible
- Check database connection settings
- Verify required tables exist

**AI/External Service Errors:**

- Check Google Cloud credentials
- Verify TronScan API access
- Ensure network connectivity

## Manual Testing

You can also test manually using curl:

```bash
# Test with a valid TRON address
curl -X POST "http://localhost:8000/check-address" \
  -H "X-API-KEY: your-api-key-here" \
  -H "Content-Type: application/json" \
  -d '{
    "crypto_address": "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t",
    "request_by_telegram_id": 123456789,
    "provided_by_telegram_id": 123456789,
    "blockchain_type": "tron"
  }'
```

## Interactive API Documentation

When the server is running, visit:

- **Swagger UI**: <http://localhost:8000/docs>
- **ReDoc**: <http://localhost:8000/redoc>

These provide interactive API documentation where you can test endpoints directly from your browser.

## Troubleshooting

### Common Issues

1. **Import Errors**
   - Ensure you're running from the project root directory
   - Check that all dependencies are installed

2. **Configuration Issues**
   - Run `python check_api_config.py` to diagnose
   - Verify all required environment variables are set

3. **Database Connection**
   - Check database file permissions
   - Ensure SQLite database exists and is accessible

4. **Google Cloud Services**
   - Verify GCP credentials are properly configured
   - Check that Vertex AI API is enabled in your project

5. **Port Conflicts**
   - If port 8000 is in use, modify `run_api_server.py`
   - Update `API_BASE_URL` in test configuration accordingly

## Next Steps

After successful testing:

1. Consider adding more test cases for your specific use cases
2. Set up continuous integration (CI) to run tests automatically
3. Deploy to a staging environment for integration testing
4. Monitor API performance and error rates in production
