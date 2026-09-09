from src.http.http_server import http_server
import pytest
from fastapi.testclient import TestClient
from unittest.mock import MagicMock, patch
from fastapi import Response
from fastapi import FastAPI

@pytest.fixture
def mock_routes():
    """Create mock routes"""
    class MockRoute(MagicMock):
        def add_route_to_server(self, app):
            @app.get("/test")
            def test_endpoint():
                return {"message": "Test successful"}
    
    return [MockRoute(), MockRoute()]

@pytest.fixture
def mock_client(server: http_server, mock_routes) -> TestClient:
    """Create a TestClient with mock routes configured"""
    server._setup_routes(mock_routes)
    return TestClient(server.app)


def test_app_property(server: http_server):
    """Test that app property returns the FastAPI instance"""
    assert isinstance(server.app, FastAPI)


def test_mock_endpoint(mock_client: TestClient):
    """Test that routes work correctly"""
    response: Response = mock_client.get("/test")
    assert response.status_code == 200
    assert response.json() == {"message": "Test successful"}


def test_ui_endpoint(production_like_client: TestClient):
    """Test the UI endpoint works"""
    response = production_like_client.get("/ui")
    assert response.status_code == 200


@patch('src.http.http_server.socket.socket')
@patch('src.http.http_server.uvicorn.Server')
@patch('src.http.http_server.uvicorn.Config')
@patch('src.utils.play_mantella_ready_sound')
def test_start(mock_sound, mock_config, mock_server_cls, mock_socket, server: http_server, mock_routes):
    """Test the start method without actually binding a socket or starting the server"""
    server.start(port=4999, routes=mock_routes, play_startup_sound=True, show_debug=False)

    # Verify sound played
    mock_sound.assert_called_once()

    # Two loopback-only sockets should be bound: IPv4 and IPv6 (never a wildcard address)
    assert mock_socket.call_count == 2
    bound_addresses = [call.args[0] for call in mock_socket.return_value.bind.call_args_list]
    assert ("127.0.0.1", 4999) in bound_addresses
    assert ("::1", 4999) in bound_addresses

    # Verify the server was configured with the app and run with both sockets
    mock_config.assert_called_once_with(server.app)
    mock_server_cls.assert_called_once_with(mock_config.return_value)
    mock_server_cls.return_value.run.assert_called_once()
    _, run_kwargs = mock_server_cls.return_value.run.call_args
    assert len(run_kwargs['sockets']) == 2