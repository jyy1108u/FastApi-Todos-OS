from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from typing import List, Optional
import json
import os
from pathlib import Path

app = FastAPI()

# ==== Models ====
class TodoCreate(BaseModel):
    title: str
    description: str
    completed: Optional[bool] = False  # 생략 가능, 기본 False

class TodoItem(TodoCreate):
    id: int
    completed: bool  # 최종적으로는 항상 bool 확정

# ==== Paths ====
BASE_DIR = Path(__file__).resolve().parent
TODO_FILE = BASE_DIR / "todo.json"
INDEX_HTML = BASE_DIR / "fastapi-app" / "templates" / "index.html"

# ==== IO helpers ====
def _normalize_completed(v):
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        return v != 0
    if isinstance(v, str):
        return v.strip().lower() in ("true", "1", "yes", "y", "t")
    return False

def load_todos() -> list[dict]:
    if not TODO_FILE.exists():
        return []
    with open(TODO_FILE, "r", encoding="utf-8") as f:
        try:
            data = json.load(f)
        except json.JSONDecodeError:
            return []
    # completed 정규화(과거 데이터 보호)
    for t in data:
        t["completed"] = _normalize_completed(t.get("completed", False))
    return data

def save_todos(todos: list[dict]) -> None:
    with open(TODO_FILE, "w", encoding="utf-8") as f:
        json.dump(todos, f, indent=4, ensure_ascii=False)

def _next_id(todos: list[dict]) -> int:
    return (max((t["id"] for t in todos), default=0) + 1)

# ==== Endpoints ====

# 목록 조회 + 필터 지원 (?completed=true/false)
@app.get("/todos", response_model=List[TodoItem])
def get_todos(completed: Optional[bool] = Query(None)):
    todos = load_todos()
    if completed is None:
        return [TodoItem(**t) for t in todos]
    # completed 파라미터로 필터링
    return [TodoItem(**t) for t in todos if t.get("completed", False) is completed]

# 신규 생성 (id는 서버에서 발급)
@app.post("/todos", response_model=TodoItem, status_code=201)
def create_todo(payload: TodoCreate):
    todos = load_todos()
    new_id = _next_id(todos)
    item = {
        "id": new_id,
        "title": payload.title,
        "description": payload.description,
        "completed": _normalize_completed(payload.completed or False),
    }
    todos.append(item)
    save_todos(todos)
    return TodoItem(**item)

# 전체 수정 (id 일치 검증)
@app.put("/todos/{todo_id}", response_model=TodoItem)
def update_todo(todo_id: int, updated: TodoItem):
    if updated.id != todo_id:
        raise HTTPException(status_code=400, detail="Path id and body id mismatch")
    todos = load_todos()
    for i, t in enumerate(todos):
        if t["id"] == todo_id:
            todos[i] = {
                "id": todo_id,
                "title": updated.title,
                "description": updated.description,
                "completed": _normalize_completed(updated.completed),
            }
            save_todos(todos)
            return TodoItem(**todos[i])
    raise HTTPException(status_code=404, detail="To-Do item not found")

# 부분 수정(완료 토글)
@app.patch("/todos/{todo_id}/toggle", response_model=TodoItem)
def toggle_todo(todo_id: int):
    todos = load_todos()
    for i, t in enumerate(todos):
        if t["id"] == todo_id:
            t["completed"] = not _normalize_completed(t.get("completed", False))
            save_todos(todos)
            return TodoItem(**t)
    raise HTTPException(status_code=404, detail="To-Do item not found")

# 삭제
@app.delete("/todos/{todo_id}", response_model=dict)
def delete_todo(todo_id: int):
    todos = load_todos()
    new_todos = [t for t in todos if t["id"] != todo_id]
    if len(new_todos) == len(todos):
        raise HTTPException(status_code=404, detail="To-Do item not found")
    save_todos(new_todos)
    return {"message": "To-Do item deleted"}

# 프론트 서빙
@app.get("/", response_class=HTMLResponse)
def read_root():
    if not INDEX_HTML.exists():
        raise HTTPException(status_code=500, detail=f"index.html not found: {INDEX_HTML}")
    with open(INDEX_HTML, "r", encoding="utf-8") as f:
        return HTMLResponse(f.read())
