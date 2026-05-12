"""Tests for widget JS serving endpoint."""
import pathlib
import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from starlette.testclient import TestClient
from fastapi import FastAPI
from engine.api.widget import widget_router
from engine.config.client_config import ClientNotFoundError

# ── Static file content helper ─────────────────────────────────────────────
_WIDGET_JS_PATH = pathlib.Path(__file__).parents[2] / 'static' / 'widget.js'


@pytest.fixture(scope='module')
def widget_source():
    """Raw text of engine/static/widget.js — used for structural assertions."""
    return _WIDGET_JS_PATH.read_text(encoding='utf-8')


@pytest.fixture
def app():
    app = FastAPI()
    app.include_router(widget_router)
    return app


@pytest.fixture
def client(app):
    return TestClient(app)


@pytest.fixture
def mock_client_config():
    """Mock client config with widget enabled."""
    config = MagicMock()
    config.widget_enabled = True
    config.widget_welcome_message = "Welcome!"
    config.widget_primary_color = '#1B5E3F'
    config.widget_button_icon = '💬'
    return config


def test_widget_js_injects_client_id(client, mock_client_config):
    """Test that GET /widget/{client_id}.js injects the client ID via FLOWAI_CONFIG."""
    with patch('engine.api.widget.load_client_config', new_callable=AsyncMock) as mock_load:
        mock_load.return_value = mock_client_config
        
        response = client.get("/widget/hey-aircon.js")
        
        assert response.status_code == 200
        assert "application/javascript" in response.headers["content-type"]
        assert 'window.FLOWAI_CONFIG' in response.text
        assert '"clientId": "hey-aircon"' in response.text


def test_widget_js_cache_control_header(client, mock_client_config):
    """Test that response includes proper Cache-Control header."""
    with patch('engine.api.widget.load_client_config', new_callable=AsyncMock) as mock_load:
        mock_load.return_value = mock_client_config
        
        response = client.get("/widget/hey-aircon.js")
        
        assert response.status_code == 200
        assert response.headers["cache-control"] == "public, max-age=3600"


def test_widget_js_widget_disabled_returns_404(client):
    """Test that widget disabled returns 404."""
    mock_config = MagicMock()
    mock_config.widget_enabled = False
    
    with patch('engine.api.widget.load_client_config', new_callable=AsyncMock) as mock_load:
        mock_load.return_value = mock_config
        
        response = client.get("/widget/hey-aircon.js")
        
        assert response.status_code == 404
        assert "not enabled" in response.text


def test_widget_js_client_not_found_returns_404(client):
    """Test that non-existent client returns 404."""
    with patch('engine.api.widget.load_client_config', new_callable=AsyncMock) as mock_load:
        mock_load.side_effect = ClientNotFoundError("Client not found")
        
        response = client.get("/widget/nonexistent.js")
        
        assert response.status_code == 404


def test_widget_js_body_starts_with_client_id_injection(client, mock_client_config):
    """Test that the client ID injection is at the TOP of the file."""
    with patch('engine.api.widget.load_client_config', new_callable=AsyncMock) as mock_load:
        mock_load.return_value = mock_client_config
        
        response = client.get("/widget/hey-aircon.js")
        
        assert response.status_code == 200
        # Verify the injection is at the start
        assert response.text.startswith("window.FLOWAI_CONFIG")


def test_widget_js_contains_static_file_content(client, mock_client_config):
    """Test that response includes content from engine/static/widget.js."""
    with patch('engine.api.widget.load_client_config', new_callable=AsyncMock) as mock_load:
        mock_load.return_value = mock_client_config
        
        response = client.get("/widget/hey-aircon.js")
        
        assert response.status_code == 200
        # Verify it contains actual widget code (IIFE pattern)
        assert "(function()" in response.text or "(function ()" in response.text
        # Verify it contains widget-specific code
        assert "flowai-widget-btn" in response.text
        assert "flowai-widget-window" in response.text


def test_serve_widget_js_injects_flowai_config(client, mock_client_config):
    """Served JS contains window.FLOWAI_CONFIG object not window.FLOWAI_CLIENT_ID."""
    mock_client_config.widget_primary_color = '#1B5E3F'
    mock_client_config.widget_button_icon = '💬'
    
    with patch('engine.api.widget.load_client_config', new_callable=AsyncMock) as mock_load:
        mock_load.return_value = mock_client_config
        
        response = client.get("/widget/hey-aircon.js")
        
        assert response.status_code == 200
        assert 'window.FLOWAI_CONFIG' in response.text
        assert '"clientId": "hey-aircon"' in response.text
        assert '"primaryColor": "#1B5E3F"' in response.text
        assert '"buttonIcon": "💬"' in response.text
        assert 'window.FLOWAI_CLIENT_ID' not in response.text  # old pattern removed


def test_serve_widget_js_no_hardcoded_indigo(client, mock_client_config):
    """Served JS does not contain hardcoded #4F46E5."""
    mock_client_config.widget_primary_color = '#1B5E3F'
    mock_client_config.widget_button_icon = '💬'
    
    with patch('engine.api.widget.load_client_config', new_callable=AsyncMock) as mock_load:
        mock_load.return_value = mock_client_config
        
        response = client.get("/widget/hey-aircon.js")
        
        assert response.status_code == 200
        assert '#4F46E5' not in response.text


def test_serve_widget_js_invalid_hex_fallback(client, mock_client_config):
    """Invalid hex color falls back to #1B5E3F."""
    mock_client_config.widget_primary_color = 'not-a-color'
    mock_client_config.widget_button_icon = '💬'
    
    with patch('engine.api.widget.load_client_config', new_callable=AsyncMock) as mock_load:
        mock_load.return_value = mock_client_config
        
        response = client.get("/widget/hey-aircon.js")
        
        assert response.status_code == 200
        assert '"primaryColor": "#1B5E3F"' in response.text


def test_serve_widget_js_icon_truncated(client, mock_client_config):
    """Icon longer than 4 chars is truncated."""
    mock_client_config.widget_primary_color = '#1B5E3F'
    mock_client_config.widget_button_icon = 'toolong'
    
    with patch('engine.api.widget.load_client_config', new_callable=AsyncMock) as mock_load:
        mock_load.return_value = mock_client_config
        
        response = client.get("/widget/hey-aircon.js")
        
        assert response.status_code == 200
        assert '"buttonIcon": "tool"' in response.text


# ── Widget 07: Mobile keyboard/viewport fix ────────────────────────────────

class TestMobileMediaQuery:
    """T1 — @media (max-width: 480px) block and mobile CSS overrides present."""

    def test_media_query_block_present(self, widget_source):
        assert '@media (max-width: 480px)' in widget_source

    def test_mobile_window_bottom_zero(self, widget_source):
        # bottom: 0 must appear inside the media query block
        media_idx = widget_source.index('@media (max-width: 480px)')
        assert 'bottom: 0' in widget_source[media_idx:]

    def test_mobile_window_width_100_percent(self, widget_source):
        media_idx = widget_source.index('@media (max-width: 480px)')
        assert 'width: 100%' in widget_source[media_idx:]

    def test_mobile_window_height_100_percent(self, widget_source):
        media_idx = widget_source.index('@media (max-width: 480px)')
        assert 'height: 100%' in widget_source[media_idx:]

    def test_mobile_window_border_radius_zero(self, widget_source):
        media_idx = widget_source.index('@media (max-width: 480px)')
        assert 'border-radius: 0' in widget_source[media_idx:]

    def test_mobile_window_border_top_left_radius(self, widget_source):
        media_idx = widget_source.index('@media (max-width: 480px)')
        assert 'border-top-left-radius: 12px' in widget_source[media_idx:]

    def test_mobile_input_row_safe_area(self, widget_source):
        media_idx = widget_source.index('@media (max-width: 480px)')
        assert 'env(safe-area-inset-bottom)' in widget_source[media_idx:]
        # Specifically in the input-row rule
        input_row_idx = widget_source.index('#flowai-input-row', media_idx)
        assert 'env(safe-area-inset-bottom)' in widget_source[input_row_idx:input_row_idx + 200]

    def test_mobile_launcher_btn_safe_area(self, widget_source):
        # The launcher btn bottom calc uses safe-area-inset-bottom inside the media query
        media_idx = widget_source.index('@media (max-width: 480px)')
        media_block = widget_source[media_idx:media_idx + 800]
        assert 'env(safe-area-inset-bottom)' in media_block


class TestFlexboxMinHeight:
    """T2 — min-height: 0 and overscroll-behavior: contain added."""

    def test_min_height_zero_count(self, widget_source):
        # Must appear at least twice: once for #flowai-messages, once for #flowai-chat-body
        assert widget_source.count('min-height: 0') >= 2

    def test_overscroll_behavior_contain(self, widget_source):
        assert 'overscroll-behavior: contain' in widget_source


class TestSetupViewportListeners:
    """T3 — setupViewportListeners function structure."""

    def test_function_defined(self, widget_source):
        assert 'function setupViewportListeners()' in widget_source

    def test_visual_viewport_existence_check(self, widget_source):
        assert 'window.visualViewport' in widget_source

    def test_console_warn_present(self, widget_source):
        assert "console.warn('[FlowAI]" in widget_source

    def test_reset_viewport_exposed(self, widget_source):
        assert 'window._flowaiResetViewport' in widget_source

    def test_android_resize_fallback_present(self, widget_source):
        assert "window.addEventListener('resize'" in widget_source

    def test_android_fallback_guarded_by_no_visual_viewport(self, widget_source):
        # The resize fallback must be inside an else block or guarded by !window.visualViewport
        assert '!window.visualViewport' in widget_source

    def test_visual_viewport_resize_listener(self, widget_source):
        assert "window.visualViewport.addEventListener('resize'" in widget_source

    def test_visual_viewport_scroll_listener(self, widget_source):
        assert "window.visualViewport.addEventListener('scroll'" in widget_source


class TestInitCallsSetupViewport:
    """T4 — init() calls setupViewportListeners()."""

    def test_setup_called_in_init(self, widget_source):
        init_idx = widget_source.index('function init()')
        # Find the closing brace of init — look for setupViewportListeners within the next 300 chars
        init_body = widget_source[init_idx:init_idx + 300]
        assert 'setupViewportListeners()' in init_body


class TestToggleWidgetCallsReset:
    """T5 — toggleWidget() calls _flowaiResetViewport on close."""

    def test_toggle_calls_reset(self, widget_source):
        toggle_idx = widget_source.index('function toggleWidget()')
        toggle_body = widget_source[toggle_idx:toggle_idx + 400]
        assert '_flowaiResetViewport' in toggle_body


class TestPreventPageScrollOnFocus:
    """T6 — preventPageScrollOnFocus present and wired to all four inputs."""

    def test_function_defined(self, widget_source):
        assert 'function preventPageScrollOnFocus(' in widget_source

    def test_scroll_into_view_called(self, widget_source):
        assert 'scrollIntoView(' in widget_source

    def test_block_nearest_used(self, widget_source):
        assert "block: 'nearest'" in widget_source

    def test_wired_to_message_input(self, widget_source):
        assert "preventPageScrollOnFocus(document.getElementById('flowai-message-input'))" in widget_source

    def test_wired_to_name(self, widget_source):
        assert "preventPageScrollOnFocus(document.getElementById('flowai-name'))" in widget_source

    def test_wired_to_email(self, widget_source):
        assert "preventPageScrollOnFocus(document.getElementById('flowai-email'))" in widget_source

    def test_wired_to_phone(self, widget_source):
        assert "preventPageScrollOnFocus(document.getElementById('flowai-phone'))" in widget_source


class TestDesktopRegressionGuard:
    """T7 — Desktop layout CSS rules unchanged."""

    def test_desktop_window_width_360(self, widget_source):
        # width: 360px must appear in the non-mobile (desktop) section
        # It appears before the @media block
        media_idx = widget_source.index('@media (max-width: 480px)')
        desktop_section = widget_source[:media_idx]
        assert 'width: 360px' in desktop_section

    def test_desktop_window_height_500(self, widget_source):
        media_idx = widget_source.index('@media (max-width: 480px)')
        desktop_section = widget_source[:media_idx]
        assert 'height: 500px' in desktop_section

    def test_desktop_window_bottom_90(self, widget_source):
        media_idx = widget_source.index('@media (max-width: 480px)')
        desktop_section = widget_source[:media_idx]
        assert 'bottom: 90px' in desktop_section

    def test_desktop_launcher_right_20(self, widget_source):
        media_idx = widget_source.index('@media (max-width: 480px)')
        desktop_section = widget_source[:media_idx]
        assert 'right: 20px' in desktop_section


class TestNoHardcodedClientData:
    """T8 — No client-specific data in widget.js."""

    def test_no_hey_aircon(self, widget_source):
        assert 'hey-aircon' not in widget_source

    def test_no_heyaircon(self, widget_source):
        assert 'HeyAircon' not in widget_source
