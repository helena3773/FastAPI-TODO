from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
import json
import os
import logging
import time
import sys
from multiprocessing import Queue
from os import getenv
from fastapi import Request
from datetime import datetime, date
from typing import Optional
from prometheus_fastapi_instrumentator import Instrumentator
from logging_loki import LokiQueueHandler

app = FastAPI()

# Prometheus 메트릭스 엔드포인트 (/metrics)
Instrumentator().instrument(app).expose(app, endpoint="/metrics")

# Loki 설정
loki_endpoint = getenv("LOKI_ENDPOINT", "http://loki:3100/loki/api/v1/push")

# 기본 로거 설정 (콘솔 출력용)
console_handler = logging.StreamHandler(sys.stdout)
console_handler.setLevel(logging.INFO)
console_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
console_handler.setFormatter(console_formatter)

# Custom access logger
custom_logger = logging.getLogger("custom.access")
custom_logger.setLevel(logging.INFO)
custom_logger.addHandler(console_handler)  # 콘솔에도 출력

# Loki handler 설정 (환경 변수가 있을 때만)
if loki_endpoint:
    try:
        loki_logs_handler = LokiQueueHandler(
            Queue(-1),
            url=loki_endpoint,
            tags={"application": "fastapi"},
            version="1",
        )
        custom_logger.addHandler(loki_logs_handler)
        custom_logger.info(f"Loki handler initialized with endpoint: {loki_endpoint}")
    except Exception as e:
        custom_logger.error(f"Failed to initialize Loki handler: {e}", exc_info=True)
else:
    custom_logger.warning("LOKI_ENDPOINT not set, Loki logging disabled")

async def log_requests(request: Request, call_next):
    start_time = time.time()
    response = await call_next(request)
    duration = time.time() - start_time  # Compute response time

    log_message = (
        f'{request.client.host} - "{request.method} {request.url.path} HTTP/1.1" {response.status_code} {duration:.3f}s'
    )

    # **Only log if duration exists**
    if duration:
        custom_logger.info(log_message)

    return response

# 미들웨어 등록
app.middleware("http")(log_requests)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "static")

class TodoItem(BaseModel):
    id: int
    title: str
    description: str
    completed: bool
    date: str 

class DateTodos(BaseModel):
    date: str
    todos: list[TodoItem]

TODO_FILE = "todo.json"

if os.path.isdir(STATIC_DIR):
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

def load_todos():
    if os.path.exists(TODO_FILE):
        with open(TODO_FILE, "r", encoding="utf-8") as file:
            return json.load(file)
    return []

def save_todos(todos):
    with open(TODO_FILE, "w", encoding="utf-8") as file:
        json.dump(todos, file, indent=4)


@app.get("/todos/{date}", response_model=DateTodos)
def get_todos_by_date(date: str):
    todos = load_todos()
    date_todos = [todo for todo in todos if todo["date"] == date]
    return DateTodos(date=date, todos=date_todos)


@app.get("/todos", response_model=list[TodoItem])
def get_all_todos():
    return load_todos()


@app.post("/todos", response_model=TodoItem)
def create_todo(todo: TodoItem):
    todos = load_todos()
    todos.append(todo.model_dump())
    save_todos(todos)
    return todo


@app.put("/todos/{todo_id}", response_model=TodoItem)
def update_todo(todo_id: int, updated_todo: TodoItem):
    todos = load_todos()
    for todo in todos:
        if todo["id"] == todo_id:
            todo.update(updated_todo.model_dump())
            save_todos(todos)
            return updated_todo
    raise HTTPException(status_code=404, detail="To-Do item not found")


@app.delete("/todos/{todo_id}", response_model=dict)
def delete_todo(todo_id: int):
    todos = load_todos()
    todos = [todo for todo in todos if todo["id"] != todo_id]
    save_todos(todos)
    return {"message": "To-Do item deleted"}
    
@app.get("/", response_class=HTMLResponse)
def read_root():
    with open("templates/index.html", "r", encoding="utf-8") as file:
        content = file.read()
    return HTMLResponse(content=content)

@app.get("/test-log")
def test_log():
    """Loki 로깅 테스트용 엔드포인트"""
    test_message = f"Test log message at {datetime.now().isoformat()}"
    custom_logger.info(test_message)
    return {
        "message": "Test log sent to Loki",
        "log_message": test_message,
        "loki_endpoint": loki_endpoint
    }