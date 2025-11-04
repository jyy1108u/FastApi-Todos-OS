import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import pytest
from fastapi.testclient import TestClient
from main import app, save_todos, load_todos, TodoItem

client = TestClient(app)


@pytest.fixture(autouse=True)
def setup_and_teardown():
    # 테스트 전후로 항상 초기화
    save_todos([])
    yield
    save_todos([])


# ---------- 기본 헬스/빈 상태 ----------
def test_health_ok():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json().get("status") == "ok"


def test_stats_empty():
    r = client.get("/todos/_stats")
    assert r.status_code == 200
    assert r.json() == {"total": 0, "completed": 0, "pending": 0}


def test_get_todos_empty():
    r = client.get("/todos")
    assert r.status_code == 200
    assert r.json() == []


# ---------- 생성/조회 ----------
def test_get_todos_with_items():
    todo = TodoItem(id=1, title="Test", description="Test description", completed=False)
    save_todos([todo.model_dump()])
    r = client.get("/todos")
    assert r.status_code == 200
    data = r.json()
    assert len(data) == 1
    assert data[0]["title"] == "Test"


def test_create_todo_ok_and_stats_update():
    todo = {"id": 1, "title": "Test", "description": "Test description", "completed": False}
    r = client.post("/todos", json=todo)
    assert r.status_code == 200
    assert r.json()["title"] == "Test"

    # 통계 반영 확인
    s = client.get("/todos/_stats").json()
    assert s["total"] == 1 and s["completed"] == 0 and s["pending"] == 1


def test_create_todo_invalid_422():
    # description/completed 안 보냄 -> 모델이 필수이므로 422
    bad = {"id": 1, "title": "Test"}
    r = client.post("/todos", json=bad)
    assert r.status_code == 422


# ---------- 필터/검색/페이지 ----------
def test_filter_completed_and_search_and_pagination():
    items = [
        TodoItem(id=1, title="Buy milk", description="market", completed=False),
        TodoItem(id=2, title="Read book", description="novel", completed=True),
        TodoItem(id=3, title="Buy eggs", description="supermarket", completed=False),
        TodoItem(id=4, title="Workout", description="gym", completed=True),
    ]
    save_todos([t.model_dump() for t in items])

    # completed=true
    r1 = client.get("/todos?completed=true")
    assert r1.status_code == 200
    data1 = r1.json()
    assert {t["id"] for t in data1} == {2, 4}

    # completed=false
    r2 = client.get("/todos?completed=false")
    assert r2.status_code == 200
    data2 = r2.json()
    assert {t["id"] for t in data2} == {1, 3}

    # 검색 q=buy (title/description 부분일치, 대소문자X)
    r3 = client.get("/todos?q=buy")
    assert r3.status_code == 200
    data3 = r3.json()
    assert {t["id"] for t in data3} == {1, 3}

    # 페이지 limit/offset
    r4 = client.get("/todos?limit=2&offset=1")
    assert r4.status_code == 200
    data4 = r4.json()
    # 정렬 보장은 없지만, 기존 저장 순서대로 2개가 나와야 함(2,3)
    assert len(data4) == 2
    assert data4[0]["id"] == 2 and data4[1]["id"] == 3


# ---------- PUT/PATCH ----------
def test_update_todo_put_overwrites_and_forces_url_id():
    original = TodoItem(id=10, title="A", description="B", completed=False)
    save_todos([original.model_dump()])

    # URL은 /todos/10 이지만 본문 id를 일부러 다르게 보내봄 -> URL id가 우선
    updated_body = {"id": 999, "title": "AA", "description": "BB", "completed": True}
    r = client.put("/todos/10", json=updated_body)
    assert r.status_code == 200
    d = r.json()
    assert d["id"] == 10
    assert d["title"] == "AA" and d["description"] == "BB" and d["completed"] is True

    # 존재하지 않는 id는 404
    r2 = client.put("/todos/999", json=updated_body)
    assert r2.status_code == 404


def test_patch_todo_partial_update_completed_and_title():
    original = TodoItem(id=7, title="Task", description="desc", completed=False)
    save_todos([original.model_dump()])

    # completed만 토글
    r1 = client.patch("/todos/7", json={"completed": True})
    assert r1.status_code == 200
    assert r1.json()["completed"] is True
    # title만 변경
    r2 = client.patch("/todos/7", json={"title": "New Task"})
    assert r2.status_code == 200
    assert r2.json()["title"] == "New Task"

    # 없는 항목 patch → 404
    r3 = client.patch("/todos/777", json={"completed": True})
    assert r3.status_code == 404


# ---------- DELETE ----------
def test_delete_todo_existing_and_stats():
    item = TodoItem(id=1, title="X", description="Y", completed=False)
    save_todos([item.model_dump()])
    r = client.delete("/todos/1")
    assert r.status_code == 200
    assert r.json()["message"] == "To-Do item deleted"

    # 실제 삭제되었는지
    r2 = client.get("/todos")
    assert r2.status_code == 200
    assert r2.json() == []

    # 통계도 0으로
    s = client.get("/todos/_stats").json()
    assert s == {"total": 0, "completed": 0, "pending": 0}


def test_delete_todo_not_found_is_still_200():
    # 존재 안 해도 200 반환(현 로직)
    r = client.delete("/todos/999")
    assert r.status_code == 200
    assert r.json()["message"] == "To-Do item deleted"
