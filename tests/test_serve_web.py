from fastapi import FastAPI
from fastapi.testclient import TestClient

from finadvisor.api import app as app_mod


def make(tmp_path, monkeypatch):
    (tmp_path / "assets").mkdir()
    (tmp_path / "index.html").write_text("<html>app</html>")
    (tmp_path / "assets" / "main.js").write_text("console.log(1)")
    (tmp_path.parent / "secret.txt").write_text("no")
    monkeypatch.setattr(app_mod, "WEB_DIST", tmp_path)
    app = FastAPI()

    @app.get("/api/ping")
    def ping():
        return {"ok": True}

    app_mod.serve_web(app)
    return TestClient(app)


def test_serves_files_and_falls_back_to_index_for_app_routes(tmp_path, monkeypatch):
    c = make(tmp_path, monkeypatch)
    assert c.get("/assets/main.js").text == "console.log(1)"
    assert c.get("/").text == "<html>app</html>"
    assert c.get("/chat/abc").text == "<html>app</html>"     # client-side route


def test_api_routes_win_and_unknown_api_paths_404(tmp_path, monkeypatch):
    c = make(tmp_path, monkeypatch)
    assert c.get("/api/ping").json() == {"ok": True}
    assert c.get("/api/nope").status_code == 404


def test_no_files_outside_the_build(tmp_path, monkeypatch):
    c = make(tmp_path, monkeypatch)
    assert "no" != c.get("/../secret.txt").text
    assert c.get("/%2e%2e/secret.txt").text == "<html>app</html>"
