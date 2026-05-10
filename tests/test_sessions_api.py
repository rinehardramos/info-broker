def test_sessions_router_registered():
    """Sessions endpoint exists in the app."""
    import sys; sys.path.insert(0, '.')
    from app.main import app
    routes = [r.path for r in app.routes if 'session' in r.path]
    assert '/v3/agent/sessions' in routes
    assert '/v3/agent/sessions/{session_id}' in routes
    assert '/v3/agent/sessions/{session_id}/archive' in routes

def test_archive_path_in_routes():
    import sys; sys.path.insert(0, '.')
    from app.routers.v3.sessions_api import router
    paths = [r.path for r in router.routes]
    assert any('archive' in p for p in paths)
