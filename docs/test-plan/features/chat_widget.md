# Chat Widget — Test Plan

**Feature:** Embeddable web chat widget (Phase 1 MVP)  
**Owned by:** `@sdet-engineer`  
**Status:** Ready for Implementation  
**Last Updated:** 2026-04-30  

---

## 1. Scope

### What Is Tested in Phase 1

| Component | Coverage |
|-----------|----------|
| **Backend API** | All 4 widget endpoints (`POST /session`, `POST /message`, `GET /history`, `GET /widget.js`) — request validation, error responses, CORS enforcement, rate limiting |
| **Widget message pipeline** | `widget_handler.py` — escalation gate, conversation history fetch, cross-channel identity linking, agent invocation, logging |
| **CORS middleware** | Origin validation, preflight OPTIONS handling, development localhost bypass |
| **Session expiry job** | APScheduler job marks expired sessions; expired sessions return `410 Gone` |
| **Database schema** | All new tables (`sessions`, `visitors`) and schema changes (`interactions_log`, `bookings`, `clients`) — foreign key constraints, indexes, default values |
| **Cross-channel identity** | Phone-based lookup links widget visitors to WhatsApp customers; agent context includes prior history |
| **Multi-client isolation** | Widget sessions for `client_id=flow-ai` and `client_id=test-widget-client` have zero data leakage |
| **Escalation flow** | Widget escalation triggers WhatsApp alert; escalated sessions return holding reply without agent invocation |

### What Is NOT Tested in Phase 1

| Feature | Reason Deferred |
|---------|----------------|
| **Widget JavaScript UI** | Visual/manual testing by founder — no automated frontend tests in Phase 1 |
| **File upload** | Out of scope for Phase 1 (text-only widget) |
| **WebSocket** | Phase 1 is HTTP-only (no real-time typing indicators) |
| **Email-based identity linking** | Phase 1 is phone-only; email matching added in Phase 2 |
| **Cross-channel escalation handoff** | Phase 1 escalation is WhatsApp-alert-only; message bridge added in Phase 3 |
| **Performance under load** | Phase 1 test: 50 conversations, measure 95th percentile latency; load testing (1000+ concurrent) deferred to Phase 2 |

---

## 2. Test Matrix — Functional Requirements

All FRs from `docs/requirements/chat_widget.md` mapped to test cases.

### FR-001 — Widget Button (Visual Testing Only)

**Acceptance Criteria:**
- [ ] Widget button visible in bottom-right corner (20px from right, 20px from bottom)
- [ ] Button size: 60×60px on desktop, 56×56px on mobile
- [ ] Button background color matches `clients.widget_primary_color` (default `#4F46E5`)
- [ ] Hover state: button scales to 105% and shows tooltip "Chat with Kai"
- [ ] Click opens chat window

**Test Type:** Manual (founder visual inspection) — no automated test.

---

### FR-002 — Chat Window (Visual Testing Only)

**Acceptance Criteria:**
- [ ] Window opens as overlay (400×600px default, 100% width on <768px screens)
- [ ] Header displays agent name (`clients.widget_agent_name`), close button (X)
- [ ] Body: message list (scrollable, newest at bottom), loading indicator
- [ ] Footer: message input field (text, max 2000 chars), Send button
- [ ] Close button (X) hides window but preserves `session_id` in `localStorage`

**Test Type:** Manual — no automated test.

---

### FR-003 — Pre-Chat Form (Visual Testing Only)

**Acceptance Criteria:**
- [ ] Form displays on first widget open if no `session_id` in `localStorage`
- [ ] Fields: Name (optional), Email (optional, email format validation), Phone (optional, E.164 hint)
- [ ] PDPA data collection notice displayed above Submit button (visible without scrolling)
- [ ] Buttons: "Submit" (saves form → starts conversation), "Skip" (bypasses form → starts anonymous)
- [ ] Skip: `session_id` generated, no `visitors` row created
- [ ] Submit: `session_id` generated, `visitors` row inserted with form data

**Test Type:** Manual — no automated test. Backend phone lookup tested in unit tests (see FR-016).

---

### FR-004 — Message Rendering (Visual Testing Only)

**Test Type:** Manual — no automated test.

---

### FR-005 — Mobile Responsive (Visual Testing Only)

**Test Type:** Manual — founder tests on iOS Safari and Android Chrome.

---

### FR-006 — Loading/Typing Indicator (Visual Testing Only)

**Test Type:** Manual — no automated test.

---

### FR-007 — Escalation State Display (Visual Testing Only)

**Test Type:** Manual — founder triggers escalation and verifies banner display, input field disabled.

---

### FR-008 — Create Session Endpoint

**File:** `engine/tests/unit/test_widget_api.py::test_create_session_success`

**Test case:**
```python
async def test_create_session_success(mock_supabase_client, mock_client_config):
    """POST /chat/{client_id}/session returns session_id and welcome message."""
    # Arrange
    mock_insert_response = MagicMock()
    mock_insert_response.data = [{"session_id": "550e8400-e29b-41d4-a716-446655440000"}]
    mock_supabase_client.table().insert().execute.return_value = mock_insert_response
    mock_client_config.widget_welcome_message = "Hi! I'm Kai."
    
    # Act
    response = await client.post("/chat/flow-ai/session", json={})
    
    # Assert
    assert response.status_code == 200
    data = response.json()
    assert "session_id" in data
    assert data["welcome_message"] == "Hi! I'm Kai."
```

**Additional test cases:**
- [ ] `test_create_session_widget_disabled` — returns `403 Forbidden` when `clients.widget_enabled=FALSE`
- [ ] `test_create_session_origin_not_allowed` — returns `403 Forbidden` when `Origin` not in whitelist
- [ ] `test_create_session_client_not_found` — returns `404 Not Found` when `client_id` invalid

---

### FR-009 — Send Message Endpoint

**File:** `engine/tests/integration/test_widget_api.py::test_send_message_full_pipeline`

**Test case:**
```python
async def test_send_message_full_pipeline(mock_supabase_client, mock_agent_runner):
    """POST /chat/{client_id}/message invokes full pipeline: log inbound → escalation gate → agent → log outbound."""
    # Arrange
    session_id = "550e8400-e29b-41d4-a716-446655440000"
    mock_supabase_client.table("sessions").select().eq().limit().execute.return_value.data = [
        {"session_id": session_id, "expired_at": None, "last_active_at": "2026-04-30T10:00:00Z"}
    ]
    mock_supabase_client.table("visitors").select().eq().limit().execute.return_value.data = []  # Not escalated
    mock_agent_runner.run_agent.return_value = "General servicing starts at $60."
    
    # Act
    response = await client.post(
        "/chat/flow-ai/message",
        json={"session_id": session_id, "message": "How much does servicing cost?"},
        headers={"Origin": "https://getflowai.co"}
    )
    
    # Assert
    assert response.status_code == 200
    data = response.json()
    assert data["reply"] == "General servicing starts at $60."
    assert data["escalated"] is False
    # Verify inbound log called
    mock_supabase_client.table("interactions_log").insert.assert_called()
    # Verify agent invoked
    mock_agent_runner.run_agent.assert_called_once()
```

**Additional test cases:**
- [ ] `test_send_message_session_expired` — returns `410 Gone` when `expired_at` IS NOT NULL
- [ ] `test_send_message_session_not_found` — returns `404 Not Found` when `session_id` invalid
- [ ] `test_send_message_message_too_long` — returns `400 Bad Request` when message exceeds 2000 characters
- [ ] `test_send_message_escalated_session` — returns holding reply without invoking agent when `escalation_flag=TRUE`
- [ ] `test_send_message_rate_limit_exceeded` — returns `429 Too Many Requests` after 10 messages/minute
- [ ] `test_send_message_updates_last_active` — verifies `sessions.last_active_at` updated to NOW()

---

### FR-010 — Fetch Conversation History Endpoint

**File:** `engine/tests/unit/test_widget_api.py::test_fetch_history_success`

**Test case:**
```python
async def test_fetch_history_success(mock_supabase_client):
    """GET /chat/{client_id}/history returns conversation messages in chronological order."""
    # Arrange
    session_id = "550e8400-e29b-41d4-a716-446655440000"
    mock_supabase_client.table("sessions").select().eq().limit().execute.return_value.data = [
        {"session_id": session_id, "expired_at": None}
    ]
    mock_supabase_client.table("interactions_log").select().eq().order().limit().execute.return_value.data = [
        {"direction": "outbound", "message_text": "Hi! How can I help?", "created_at": "2026-04-30T10:00:00Z"},
        {"direction": "inbound", "message_text": "I need servicing", "created_at": "2026-04-30T10:00:15Z"},
    ]
    mock_supabase_client.table("visitors").select().eq().limit().execute.return_value.data = [
        {"escalation_flag": False}
    ]
    
    # Act
    response = await client.get(
        f"/chat/flow-ai/history?session_id={session_id}",
        headers={"Origin": "https://getflowai.co"}
    )
    
    # Assert
    assert response.status_code == 200
    data = response.json()
    assert len(data["messages"]) == 2
    assert data["messages"][0]["role"] == "assistant"
    assert data["messages"][1]["role"] == "user"
    assert data["escalated"] is False
```

**Additional test cases:**
- [ ] `test_fetch_history_session_expired` — returns `410 Gone`
- [ ] `test_fetch_history_session_not_found` — returns `404 Not Found`
- [ ] `test_fetch_history_escalated_session` — returns `"escalated": true` when `escalation_flag=TRUE`

---

### FR-011 — Widget JavaScript Endpoint

**File:** `engine/tests/unit/test_widget_js_endpoint.py::test_widget_js_delivery`

**Test case:**
```python
async def test_widget_js_delivery(mock_client_config):
    """GET /widget/{client_id}.js returns JavaScript with inlined client_id."""
    # Arrange
    mock_client_config.widget_enabled = True
    
    # Act
    response = await client.get("/widget/flow-ai.js")
    
    # Assert
    assert response.status_code == 200
    assert response.headers["Content-Type"] == "application/javascript"
    assert "window.FLOWAI_CLIENT_ID = 'flow-ai';" in response.text
    assert "Cache-Control" in response.headers
    assert "max-age=3600" in response.headers["Cache-Control"]
```

**Additional test cases:**
- [ ] `test_widget_js_widget_disabled` — returns `404 Not Found` when `widget_enabled=FALSE`
- [ ] `test_widget_js_client_not_found` — returns `404 Not Found` when `client_id` invalid

---

### FR-012 — CORS Origin Validation

**File:** `engine/tests/unit/test_cors_middleware.py::test_cors_allowed_origin`

**Test case:**
```python
async def test_cors_allowed_origin(mock_client_config):
    """CORS middleware allows requests from whitelisted origins."""
    # Arrange
    mock_client_config.widget_allowed_origins = "https://getflowai.co,https://www.getflowai.co"
    
    # Act
    response = await client.post(
        "/chat/flow-ai/session",
        json={},
        headers={"Origin": "https://getflowai.co"}
    )
    
    # Assert
    assert response.status_code == 200
    assert response.headers["Access-Control-Allow-Origin"] == "https://getflowai.co"
```

**Additional test cases:**
- [ ] `test_cors_disallowed_origin` — returns `403 Forbidden` when `Origin` not in whitelist
- [ ] `test_cors_preflight_success` — OPTIONS request returns `204 No Content` with CORS headers
- [ ] `test_cors_localhost_bypass_dev_mode` — allows `http://localhost:3000` when `ENVIRONMENT=development`
- [ ] `test_cors_localhost_blocked_prod_mode` — rejects `http://localhost:3000` when `ENVIRONMENT=production`

---

### FR-013 — Rate Limiting

**File:** `engine/tests/unit/test_widget_api.py::test_rate_limit_exceeded`

**Test case:**
```python
async def test_rate_limit_exceeded(mock_supabase_client):
    """POST /chat/{client_id}/message returns 429 after 10 messages/minute per session."""
    # Arrange
    session_id = "550e8400-e29b-41d4-a716-446655440000"
    mock_supabase_client.table("sessions").select().eq().limit().execute.return_value.data = [
        {"session_id": session_id, "expired_at": None}
    ]
    
    # Act — send 11 messages rapidly
    for i in range(11):
        response = await client.post(
            "/chat/flow-ai/message",
            json={"session_id": session_id, "message": f"Message {i}"},
            headers={"Origin": "https://getflowai.co"}
        )
        if i < 10:
            assert response.status_code == 200
        else:
            assert response.status_code == 429
            assert "retry_after" in response.json()
```

---

### FR-014 — Session Timeout

**File:** `engine/tests/unit/test_session_expiry_job.py::test_expire_inactive_sessions`

**Test case:**
```python
async def test_expire_inactive_sessions(mock_supabase_client, mock_client_config):
    """Session expiry job marks sessions as expired after TTL."""
    # Arrange
    mock_client_config.widget_session_ttl_minutes = 30
    mock_supabase_client.rpc.return_value.data = {"count": 3}
    
    # Act
    await expire_inactive_sessions()
    
    # Assert
    mock_supabase_client.rpc.assert_called_with(
        "expire_sessions_before",
        {"threshold_timestamp": ANY}  # Timestamp = NOW() - 30 minutes
    )
```

---

### FR-015 — New `sessions` Table

**File:** `engine/tests/unit/test_widget_schema.py::test_sessions_table_exists`

**Test case:**
```python
async def test_sessions_table_exists(mock_supabase_client):
    """Verify sessions table exists with all required columns."""
    # Act
    result = await mock_supabase_client.table("sessions").select("*").limit(0).execute()
    
    # Assert
    assert result is not None  # Table exists (no exception raised)
```

---

### FR-016 — New `visitors` Table + Cross-Channel Identity

**File:** `engine/tests/unit/test_identify_visitor.py::test_identify_visitor_match_found`

**Test case:**
```python
async def test_identify_visitor_match_found(mock_supabase_client):
    """identify_visitor() returns customer_id when phone matches existing WhatsApp customer."""
    # Arrange
    mock_supabase_client.table("customers").select().eq().limit().execute.return_value.data = [
        {"id": 123, "phone_number": "6591234567", "customer_name": "John Tan"}
    ]
    
    # Act
    customer_id = await identify_visitor(mock_supabase_client, "6591234567")
    
    # Assert
    assert customer_id == 123
```

**Additional test cases:**
- [ ] `test_identify_visitor_no_match` — returns `None` when phone not found in `customers` table
- [ ] `test_identify_visitor_no_phone` — returns `None` when phone is `None` or empty string

---

### FR-017 — Schema Changes to `interactions_log`

**File:** `engine/tests/unit/test_widget_schema.py::test_interactions_log_has_channel_and_session_id`

**Test case:**
```python
async def test_interactions_log_has_channel_and_session_id(mock_supabase_client):
    """Verify interactions_log has channel and session_id columns."""
    # Act — insert a widget message
    result = await mock_supabase_client.table("interactions_log").insert({
        "channel": "widget",
        "session_id": "550e8400-e29b-41d4-a716-446655440000",
        "message_text": "Test message",
        "direction": "inbound",
        "phone_number": None  # Nullable for widget messages
    }).execute()
    
    # Assert
    assert result.data is not None  # Insert successful (no exception)
```

---

### FR-018 — Schema Changes to `bookings`

**File:** `engine/tests/unit/test_widget_schema.py::test_bookings_has_channel_and_session_id`

**Test case:**
```python
async def test_bookings_has_channel_and_session_id(mock_supabase_client):
    """Verify bookings has channel and session_id columns."""
    # Act — insert a widget booking
    result = await mock_supabase_client.table("bookings").insert({
        "channel": "widget",
        "session_id": "550e8400-e29b-41d4-a716-446655440000",
        "phone_number": "6591234567",
        "service_type": "General Servicing",
        "booking_status": "pending_confirmation",
        # ... other required fields
    }).execute()
    
    # Assert
    assert result.data is not None
```

---

### FR-019 — Schema Changes to `clients` Table

**File:** `engine/tests/unit/test_widget_schema.py::test_client_config_has_widget_fields`

**Test case:**
```python
def test_client_config_has_widget_fields():
    """Verify ClientConfig dataclass has all 6 widget fields."""
    from engine.config.client_config import ClientConfig
    
    # Assert
    assert hasattr(ClientConfig, "widget_enabled")
    assert hasattr(ClientConfig, "widget_primary_color")
    assert hasattr(ClientConfig, "widget_agent_name")
    assert hasattr(ClientConfig, "widget_welcome_message")
    assert hasattr(ClientConfig, "widget_allowed_origins")
    assert hasattr(ClientConfig, "widget_session_ttl_minutes")
```

---

### FR-020 — Channel Context in System Prompt

**File:** `engine/tests/unit/test_context_builder_widget.py::test_context_includes_channel_widget`

**Test case:**
```python
async def test_context_includes_channel_widget(mock_supabase_client):
    """System prompt includes 'website chat widget' when channel='widget'."""
    # Act
    system_message = await build_system_message(mock_supabase_client, channel="widget")
    
    # Assert
    assert "website chat widget" in system_message.lower()
```

---

### FR-021 — Escalation Alert Format (Widget)

**File:** `engine/tests/integration/test_widget_escalation.py::test_widget_escalation_sends_whatsapp_alert`

**Test case:**
```python
async def test_widget_escalation_sends_whatsapp_alert(mock_meta_whatsapp, mock_supabase_client):
    """Widget escalation triggers WhatsApp alert with session_id, name, email."""
    # Arrange
    session_id = "550e8400-e29b-41d4-a716-446655440000"
    mock_supabase_client.table("visitors").select().eq().limit().execute.return_value.data = [
        {"name": "John Tan", "email": "john@example.com", "escalation_flag": True}
    ]
    
    # Act
    await handle_widget_escalation(client_id="flow-ai", session_id=session_id)
    
    # Assert
    mock_meta_whatsapp.send_message.assert_called_once()
    alert_text = mock_meta_whatsapp.send_message.call_args[0][2]
    assert "🚨 Widget escalation" in alert_text
    assert session_id in alert_text
    assert "John Tan" in alert_text
    assert "john@example.com" in alert_text
```

---

### FR-022 — Holding Reply (Escalated Sessions)

**File:** `engine/tests/unit/test_widget_handler.py::test_escalated_session_returns_holding_reply`

**Test case:**
```python
async def test_escalated_session_returns_holding_reply(mock_supabase_client):
    """Escalated session returns holding reply without invoking agent."""
    # Arrange
    session_id = "550e8400-e29b-41d4-a716-446655440000"
    mock_supabase_client.table("visitors").select().eq().limit().execute.return_value.data = [
        {"escalation_flag": True}
    ]
    
    # Act
    reply, escalated = await widget_handler.process_message(
        client_id="flow-ai",
        session_id=session_id,
        message_text="I need help"
    )
    
    # Assert
    assert "member of our team will get back to you" in reply
    assert escalated is True
    # Verify agent NOT invoked (mock_agent_runner.run_agent.assert_not_called())
```

---

## 3. Risk-Based Tests

From architecture §11 (Constraints and Risks).

### Risk Test 1 — CORS Bypass via Proxy

**File:** `engine/tests/security/test_cors_bypass.py::test_cors_proxy_attack`

**Scenario:** Attacker proxies requests with forged `Origin` header.

**Test case:**
```python
async def test_cors_proxy_attack(mock_client_config):
    """CORS middleware rejects forged Origin header not in whitelist."""
    # Arrange
    mock_client_config.widget_allowed_origins = "https://getflowai.co"
    
    # Act — attacker sends request with forged Origin
    response = await client.post(
        "/chat/flow-ai/session",
        json={},
        headers={"Origin": "https://attacker.com"}
    )
    
    # Assert
    assert response.status_code == 403
    assert "Origin not allowed" in response.json()["error"]
```

**Mitigation verification:** CORS validation cannot prevent proxy attacks at application layer — test confirms whitelist enforcement only. Additional IP-based rate limiting deferred to Phase 2.

---

### Risk Test 2 — Widget JS Tampering

**File:** `engine/tests/security/test_widget_tampering.py::test_malicious_session_id_rejected`

**Scenario:** Attacker modifies widget JS in DevTools to send malicious `session_id` (e.g., SQL injection attempt).

**Test case:**
```python
async def test_malicious_session_id_rejected(mock_supabase_client):
    """Backend validates session_id is valid UUID format."""
    # Act — attacker sends non-UUID session_id
    response = await client.post(
        "/chat/flow-ai/message",
        json={"session_id": "'; DROP TABLE sessions; --", "message": "test"},
        headers={"Origin": "https://getflowai.co"}
    )
    
    # Assert
    assert response.status_code == 400 or response.status_code == 404
    # Verify no SQL injection occurred (sessions table still exists)
    await mock_supabase_client.table("sessions").select("*").limit(1).execute()  # No exception
```

**Mitigation verification:** Backend must validate all inputs. Do not trust client-side logic.

---

### Risk Test 3 — Cross-Channel Identity Collision

**File:** `engine/tests/integration/test_cross_channel_identity.py::test_identity_collision_false_positive`

**Scenario:** Two visitors submit same phone number, linking to wrong WhatsApp customer.

**Test case:**
```python
async def test_identity_collision_false_positive(mock_supabase_client):
    """When two visitors submit same phone, second visitor links to first customer (expected behavior)."""
    # Arrange
    mock_supabase_client.table("customers").select().eq().limit().execute.return_value.data = [
        {"id": 123, "phone_number": "6591234567", "customer_name": "John Tan"}
    ]
    
    # Act — Visitor 1 submits phone
    session_id_1 = "550e8400-e29b-41d4-a716-446655440001"
    await widget_handler.identify_visitor(mock_supabase_client, session_id_1, "6591234567")
    
    # Act — Visitor 2 submits same phone
    session_id_2 = "550e8400-e29b-41d4-a716-446655440002"
    customer_id_2 = await widget_handler.identify_visitor(mock_supabase_client, session_id_2, "6591234567")
    
    # Assert
    assert customer_id_2 == 123  # Both visitors link to same customer (expected behavior in Phase 1)
```

**Mitigation:** Phase 2 adds email+phone composite matching to reduce false positives. Phase 1 behavior is acceptable — rare edge case.

---

### Risk Test 4 — Session Expiry Job Lag

**File:** `engine/tests/unit/test_session_expiry_job.py::test_expiry_lag_within_bounds`

**Scenario:** Sessions expire up to 5 minutes after TTL threshold (APScheduler interval).

**Test case:**
```python
async def test_expiry_lag_within_bounds(mock_supabase_client, mock_client_config):
    """Session expiry job runs every 5 minutes; expired sessions detected within 5 min lag."""
    # Arrange
    mock_client_config.widget_session_ttl_minutes = 30
    mock_supabase_client.table("sessions").select().eq().execute.return_value.data = [
        {
            "session_id": "550e8400-e29b-41d4-a716-446655440000",
            "last_active_at": "2026-04-30T09:25:00Z",  # 35 minutes ago (past TTL)
            "expired_at": None
        }
    ]
    
    # Act — run expiry job
    await expire_inactive_sessions()
    
    # Assert — session marked expired
    mock_supabase_client.rpc.assert_called_once()
    # Verify lag is ≤ 5 minutes (acceptable delay)
```

**Mitigation:** 5-minute lag acceptable for Phase 1. Reduce interval to 1 minute in Phase 2 if needed.

---

### Risk Test 5 — Multi-Client Isolation

**File:** `engine/tests/integration/test_multi_client_isolation.py::test_zero_data_leakage`

**Scenario:** Widget sessions for `client_id=flow-ai` and `client_id=test-widget-client` have zero data leakage.

**Test case:**
```python
async def test_zero_data_leakage(mock_supabase_client):
    """Sessions for different clients are fully isolated — no cross-client history access."""
    # Arrange — create sessions for two clients
    session_id_flow_ai = await create_session(client_id="flow-ai")
    session_id_test_client = await create_session(client_id="test-widget-client")
    
    # Act — send messages in both sessions
    await send_message(client_id="flow-ai", session_id=session_id_flow_ai, message="Flow AI message")
    await send_message(client_id="test-widget-client", session_id=session_id_test_client, message="Test client message")
    
    # Act — fetch history for flow-ai session
    history_flow_ai = await fetch_history(client_id="flow-ai", session_id=session_id_flow_ai)
    
    # Assert — flow-ai history does NOT contain test-client message
    messages = [msg["text"] for msg in history_flow_ai["messages"]]
    assert "Flow AI message" in messages
    assert "Test client message" not in messages
    
    # Act — fetch history for test-client session
    history_test_client = await fetch_history(client_id="test-widget-client", session_id=session_id_test_client)
    
    # Assert — test-client history does NOT contain flow-ai message
    messages = [msg["text"] for msg in history_test_client["messages"]]
    assert "Test client message" in messages
    assert "Flow AI message" not in messages
```

**Mitigation:** All widget queries scoped by `client_id` path parameter. Supabase RLS policies (Phase 2) provide additional isolation layer.

---

## 4. Performance Test

### Test: 50 Conversations, Measure 95th Percentile Reply Latency

**File:** `engine/tests/performance/test_widget_latency.py::test_reply_latency_under_5_seconds`

**Acceptance Criteria:** 95th percentile reply latency < 5 seconds.

**Test case:**
```python
async def test_reply_latency_under_5_seconds():
    """Simulate 50 widget conversations and measure 95th percentile reply latency."""
    latencies = []
    
    for i in range(50):
        # Create session
        session_id = await create_session(client_id="flow-ai")
        
        # Send message and measure latency
        start_time = time.time()
        response = await send_message(
            client_id="flow-ai",
            session_id=session_id,
            message="How much does general servicing cost?"
        )
        latency = time.time() - start_time
        latencies.append(latency)
        
        assert response.status_code == 200
    
    # Calculate 95th percentile
    p95_latency = sorted(latencies)[int(0.95 * len(latencies))]
    
    # Assert
    assert p95_latency < 5.0, f"95th percentile latency {p95_latency:.2f}s exceeds 5s threshold"
```

---

## 5. Acceptance Criteria Gate

From `docs/requirements/chat_widget.md` §9.

### Phase 1 Acceptance Criteria

| Criterion | Verification Method |
|-----------|---------------------|
| **All 4 widget endpoints return 200 OK for valid requests** | Integration tests: `test_widget_api.py` — all 4 endpoints tested |
| **CORS enforcement: disallowed origins return 403** | Unit test: `test_cors_middleware.py::test_cors_disallowed_origin` |
| **Session expiry: expired sessions return 410 Gone** | Integration test: `test_widget_api.py::test_send_message_session_expired` |
| **Escalation gate: escalated sessions return holding reply without agent invocation** | Unit test: `test_widget_handler.py::test_escalated_session_returns_holding_reply` |
| **Cross-channel identity: phone match links widget visitor to WhatsApp customer** | Integration test: `test_cross_channel_identity.py::test_identify_visitor_match_found` |
| **Multi-client isolation: zero data leakage between flow-ai and test-widget-client** | Integration test: `test_multi_client_isolation.py::test_zero_data_leakage` |
| **Performance: 95th percentile reply latency < 5 seconds (50 conversations)** | Performance test: `test_widget_latency.py::test_reply_latency_under_5_seconds` |
| **Widget JS delivery: inlined client_id present in response** | Unit test: `test_widget_js_endpoint.py::test_widget_js_delivery` |
| **Rate limiting: 11th message/minute returns 429** | Unit test: `test_widget_api.py::test_rate_limit_exceeded` |
| **All new schema changes applied without error** | Migration test: `test_widget_schema.py::test_sessions_table_exists`, `test_interactions_log_has_channel_and_session_id`, `test_bookings_has_channel_and_session_id`, `test_client_config_has_widget_fields` |

**Gate check:** ALL acceptance criteria must pass before marking Phase 1 ready for production.

---

## 6. Test Execution Plan

### Slice 1 — Schema (widget-01-schema)

**Deliverables:**
- Migration SQL: `supabase/migrations/007_widget_schema.sql`
- ClientConfig update: `engine/config/client_config.py`
- Schema tests: `engine/tests/unit/test_widget_schema.py`

**Validation:**
```bash
python3 -m pytest engine/tests/unit/test_widget_schema.py -v
python3 -m pytest engine/tests/unit/ -v --tb=short  # Confirm no regressions
```

**Exit criteria:** All schema tests pass; no existing tests broken.

---

### Slice 2 — API (widget-02-api)

**Deliverables:**
- API routes: `engine/api/widget.py` (4 FastAPI routes)
- Widget handler: `engine/core/widget_handler.py` (full message pipeline)
- CORS middleware: `engine/core/middleware/cors_widget.py`
- Main app update: `engine/main.py` (register routes + middleware)
- Unit tests: `test_widget_handler.py`, `test_cors_middleware.py`
- Integration tests: `test_widget_api.py`

**Validation:**
```bash
python3 -m pytest engine/tests/unit/test_widget_handler.py engine/tests/unit/test_cors_middleware.py -v
python3 -m pytest engine/tests/integration/test_widget_api.py -v
```

**Exit criteria:** All API tests pass; CORS enforcement verified; rate limiting works.

---

### Slice 3 — Identity (widget-03-identity)

**Deliverables:**
- Identity lookup: `engine/core/identify_visitor.py`
- Context builder update: `engine/core/context_builder.py` (fetch WhatsApp history when `customer_id` set)
- Widget API update: `engine/api/widget.py` (session creation calls `identify_visitor()`)
- Unit tests: `test_identify_visitor.py`, `test_context_builder_widget.py`
- Integration test: `test_cross_channel_identity.py`

**Validation:**
```bash
python3 -m pytest engine/tests/unit/test_identify_visitor.py engine/tests/unit/test_context_builder_widget.py -v
python3 -m pytest engine/tests/integration/test_cross_channel_identity.py -v
```

**Exit criteria:** Cross-channel identity linking works end-to-end; WhatsApp history appears in widget context.

---

### Slice 4 — JS (widget-04-js)

**Deliverables:**
- Widget JavaScript: `widget/widget.js` (vanilla JS, chat button, window, pre-chat form)
- Static file serving: `engine/static/` (symlink or copy of `widget.js`)
- JS endpoint test: `test_widget_js_endpoint.py`
- Widget API update: `engine/api/widget.py` (`GET /widget/{client_id}.js` route)

**Validation:**
```bash
python3 -m pytest engine/tests/unit/test_widget_js_endpoint.py -v
```

**Manual validation (founder):**
- Open `https://getflowai.co` in browser
- Click widget button → verify chat window opens
- Submit pre-chat form → verify agent replies
- Refresh page → verify conversation history restored from `localStorage`
- Test mobile responsive on iOS Safari and Android Chrome

**Exit criteria:** All JS endpoint tests pass; founder confirms UI works on desktop and mobile.

---

### Final Integration Test — Multi-Client Isolation

**File:** `engine/tests/integration/test_multi_client_isolation.py`

**Validation:**
```bash
python3 -m pytest engine/tests/integration/test_multi_client_isolation.py -v
```

**Exit criteria:** Zero data leakage between `flow-ai` and `test-widget-client` sessions.

---

### Performance Test — Reply Latency

**File:** `engine/tests/performance/test_widget_latency.py`

**Validation:**
```bash
python3 -m pytest engine/tests/performance/test_widget_latency.py -v
```

**Exit criteria:** 95th percentile reply latency < 5 seconds (50 conversations).

---

## 7. Known Limitations (Deferred to Phase 2)

| Limitation | Impact | Mitigation |
|------------|--------|-----------|
| **No frontend automated tests** | Widget UI bugs may escape to production | Founder manual testing on desktop + mobile before Phase 1 launch |
| **Rate limits reset on Railway restart** | Rate limit state lost ~once/week | Acceptable for Phase 1 (low abuse risk); migrate to Redis in Phase 2 |
| **5-minute session expiry lag** | Sessions expire 0-5 minutes after TTL threshold | Acceptable delay; reduce interval to 1 minute in Phase 2 if needed |
| **No WebSocket** | No real-time typing indicators | Phase 1 is HTTP-only; upgrade to WebSocket in Phase 2 |
| **No file upload** | Visitors cannot send images | Phase 1 is text-only; add file upload in Phase 2 |

---

**End of Test Plan**
