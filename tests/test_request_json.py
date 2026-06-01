"""ToolContext.request_json — decode on 2xx, raise on non-2xx (+ error_factory)."""

from __future__ import annotations

from typing import Any

import pytest

from bg_mcpcore import ToolContext, UpstreamError


class _Resp:
    def __init__(
        self,
        status: int,
        *,
        json_body: Any = None,
        text: str = "",
        content_type: str = "application/json",
    ) -> None:
        self.status_code = status
        self._json = json_body
        self.text = text
        self.headers = {"content-type": content_type}

    def json(self) -> Any:
        if self._json is None:
            raise ValueError("no json")
        return self._json


class _FakeClient:
    def __init__(self, resp: _Resp) -> None:
        self._resp = resp
        self.calls: list[tuple[str, str]] = []

    async def request(self, method: str, path: str, *, ctx: Any = None, **_: Any) -> _Resp:
        self.calls.append((method, path))
        return self._resp


def _ctx(resp: _Resp) -> ToolContext:
    return ToolContext(settings=None, client=_FakeClient(resp))  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_request_json_decodes_2xx() -> None:
    body = await _ctx(_Resp(200, json_body={"ok": True})).request_json("GET", "/x")
    assert body == {"ok": True}


@pytest.mark.asyncio
async def test_request_json_returns_text_when_not_json() -> None:
    out = await _ctx(_Resp(200, text="hello", content_type="text/plain")).request_json("GET", "/x")
    assert out == "hello"


@pytest.mark.asyncio
async def test_request_json_raises_upstream_error_on_non_2xx() -> None:
    with pytest.raises(UpstreamError) as ei:
        await _ctx(_Resp(404, json_body={"detail": "nope"})).request_json("GET", "/x")
    assert ei.value.status_code == 404
    assert ei.value.body == {"detail": "nope"}
    assert "nope" in str(ei.value)


@pytest.mark.asyncio
async def test_request_json_uses_error_factory() -> None:
    class MyErr(Exception):
        def __init__(self, status: int, body: dict[str, Any]) -> None:
            self.status = status
            super().__init__(str(status))

    with pytest.raises(MyErr) as ei:
        await _ctx(_Resp(422, json_body={"detail": "bad"})).request_json(
            "POST", "/x", error_factory=lambda s, b: MyErr(s, b)
        )
    assert ei.value.status == 422


@pytest.mark.asyncio
async def test_request_json_without_client_raises() -> None:
    with pytest.raises(RuntimeError, match="no upstream backend"):
        await ToolContext(settings=None).request_json("GET", "/x")
