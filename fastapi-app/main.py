from fastapi import FastAPI, HTTPException, Query, status
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import json
import os
import threading
from typing import Optional, List

app = FastAPI()

# CORS (필요 없으면 아래 5줄 삭제해도 됨)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 필요하면 도메인 제한
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 기존
# class TodoItem(BaseModel):
#     id: Optional[int] = Field(None, description="미지정 시 자동 할당")
#     title: str = Field(..., min_length=1)
#     description: str = ""
#     completed: bool = False

# 변경 (모두 필수)
class TodoItem(BaseModel):
    id: int
    title: str
    description: str
    completed: bool

# 부분수정용 모델 (PATCH)
class TodoPatch(BaseModel):
    title: Optional[str] = Field(None, min_length=1)
    description: Optional[str] = None
    completed: Optional[bool] = None

# JSON 파일 경로
TODO_FILE = "todo.json"

# 간단 파일 락 (동시 요청 시 꼬임 방지)
_file_lock = threading.Lock()

# JSON 파일에서 To-Do 항목 로드
def load_todos() -> list:
    if not os.path.exists(TODO_FILE):
        # 파일 없으면 빈 배열로 생성
        save_todos([])
        return []
    with open(TODO_FILE, "r", encoding="utf-8") as file:
        try:
            return json.load(file)
        except json.JSONDecodeError:
            # 깨진 파일 대비
            return []

# JSON 파일에 To-Do 항목 저장
def save_todos(todos: list) -> None:
    with open(TODO_FILE, "w", encoding="utf-8") as file:
        json.dump(todos, file, indent=4, ensure_ascii=False)

def next_id(todos: list) -> int:
    # 자동 id 발급 (빈 리스트면 1부터)
    return (max((t["id"] for t in todos if "id" in t and t["id"] is not None), default=0) + 1)

# 건강 상태 체크
@app.get("/health")
def health():
    return {"status": "ok"}

# To-Do 목록 조회 + 필터/검색
@app.get("/todos", response_model=List[TodoItem])
def get_todos(
    completed: Optional[bool] = Query(None, description="완료여부 필터"),
    q: Optional[str] = Query(None, description="제목/설명 검색(부분일치)"),
    limit: int = Query(1000, ge=1, le=10000, description="최대 반환 개수"),
    offset: int = Query(0, ge=0, description="건너뛸 개수"),
):
    todos = load_todos()
    if completed is not None:
        todos = [t for t in todos if t.get("completed") is completed]
    if q:
        q_low = q.lower()
        todos = [
            t for t in todos
            if q_low in t.get("title", "").lower() or q_low in t.get("description", "").lower()
        ]
    return todos[offset: offset + limit]

# 변경 (status 기본 200, 자동 ID 없음 / 중복 체크도 빼서 원래 심플 로직과 동일)
@app.post("/todos", response_model=TodoItem)   # 200 유지 (테스트 기대)
def create_todo(todo: TodoItem):
    with _file_lock:
        todos = load_todos()
        data = todo.model_dump()
        if data.get("id") is None:
            data["id"] = next_id(todos)
        todos.append(data)
        save_todos(todos)
    return data

# To-Do 항목 수정(전체 교체)
@app.put("/todos/{todo_id}", response_model=TodoItem)
def update_todo(todo_id: int, updated_todo: TodoItem):
    with _file_lock:
        todos = load_todos()
        for i, t in enumerate(todos):
            if t["id"] == todo_id:
                # URL의 id가 우선
                data = updated_todo.model_dump()
                data["id"] = todo_id
                todos[i] = data
                save_todos(todos)
                return data
    raise HTTPException(status_code=404, detail="To-Do item not found")

# To-Do 항목 부분 수정(PATCH)
@app.patch("/todos/{todo_id}", response_model=TodoItem)
def patch_todo(todo_id: int, patch: TodoPatch):
    with _file_lock:
        todos = load_todos()
        for i, t in enumerate(todos):
            if t["id"] == todo_id:
                if patch.title is not None:
                    t["title"] = patch.title
                if patch.description is not None:
                    t["description"] = patch.description
                if patch.completed is not None:
                    t["completed"] = patch.completed
                todos[i] = t
                save_todos(todos)
                return t
    raise HTTPException(status_code=404, detail="To-Do item not found")

# To-Do 항목 삭제 (없으면 404)
# 변경 (존재 여부와 상관없이 대상을 제외한 리스트 저장 → 200)
@app.delete("/todos/{todo_id}", response_model=dict)
def delete_todo(todo_id: int):
    with _file_lock:
        todos = load_todos()
        todos = [t for t in todos if t.get("id") != todo_id]
        save_todos(todos)
    return {"message": "To-Do item deleted"}

# 간단 통계
@app.get("/todos/_stats", response_model=dict)
def todo_stats():
    todos = load_todos()
    total = len(todos)
    done = sum(1 for t in todos if t.get("completed"))
    return {"total": total, "completed": done, "pending": total - done}

# HTML 파일 서빙
@app.get("/", response_class=HTMLResponse)
def read_root():
    if not os.path.exists("templates/index.html"):
        return HTMLResponse(content="<h1>templates/index.html 없음</h1>", status_code=200)
    with open("templates/index.html", "r", encoding="utf-8") as file:
        content = file.read()
    return HTMLResponse(content=content)
