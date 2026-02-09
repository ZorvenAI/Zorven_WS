---
applyTo:
  - "ai-brand-automator/**/tests/**/*.py"
  - "ai-brand-automator/**/tests.py"
  - "ai-brand-automator/test_*.py"
---

# Testing Instructions

## Framework & Configuration

- **Runner**: `pytest` with `pytest-django`
- **Config**: `ai-brand-automator/pytest.ini` + `conftest.py`
- **Coverage**: `pytest --cov=. --cov-report=term-missing`
- **Property Testing**: `hypothesis` for edge case discovery

## Test Pyramid

| Type | Proportion | What to Test |
|------|-----------|-------------|
| Unit | 70% | Models, serializers, utility functions, encryption, validators |
| Integration | 25% | API endpoints, Celery tasks, DB queries, view responses |
| Property | 5% | Edge cases via Hypothesis strategies (strings, file sizes, etc.) |

## Required Setup

### Tenant Middleware

```python
# ALWAYS set SERVER_NAME for tenant middleware compatibility
@pytest.fixture
def api_client():
    client = APIClient()
    client.defaults["SERVER_NAME"] = "localhost"
    return client
```

### Database Access

```python
# ALWAYS mark tests that need DB
@pytest.mark.django_db
def test_something(api_client):
    ...

# For transaction-dependent tests
@pytest.mark.django_db(transaction=True)
def test_transaction_thing(api_client):
    ...
```

## Mocking External Services

### Kafka

Kafka is mocked at the module level in `conftest.py` via `sys.modules` patching. No additional setup needed — tests automatically get mock Kafka.

### Google Cloud Storage

```python
from unittest.mock import patch, MagicMock

@patch('files.services.GCSService')
def test_upload(mock_gcs):
    mock_gcs.return_value.upload_file.return_value = "gs://bucket/file.pdf"
    # ... test logic
```

### Gemini AI

AI service automatically falls back to mock responses when `GOOGLE_API_KEY` is not set. For explicit mocking:

```python
@patch('ai_services.services.GeminiAIService')
def test_chat(mock_ai):
    mock_ai.return_value.generate_content.return_value = {"response": "mock"}
    # ... test logic
```

### Email

Email is redirected to `locmem.EmailBackend` via autouse fixture in `conftest.py`. Access sent emails via `django.core.mail.outbox`.

### Stripe

```python
@patch('subscriptions.views.stripe')
def test_checkout(mock_stripe):
    mock_stripe.checkout.Session.create.return_value = MagicMock(url="https://stripe.com/test")
    # ... test logic
```

## Test File Naming

```
tests/
├── test_models.py          → Model unit tests
├── test_serializers.py     → Serializer validation tests
├── test_views.py           → API endpoint integration tests
├── test_services.py        → Service layer tests
├── test_utils.py           → Utility function tests
└── test_tasks.py           → Celery task tests
```

## Hypothesis Property Testing

```python
from hypothesis import given, strategies as st

@given(st.text(min_size=1, max_size=255))
@pytest.mark.django_db
def test_company_name_accepts_any_text(name, api_client):
    response = api_client.post('/api/v1/companies/', {'name': name})
    assert response.status_code in (201, 400)  # Created or validation error
```

## Test Assertions

- Use `assert` (not `self.assertEqual` — we use pytest, not unittest)
- Check both status codes AND response body content
- Verify side effects (DB records created, emails sent, tasks dispatched)
- Test error cases: 400, 401, 403, 404, 409 responses
