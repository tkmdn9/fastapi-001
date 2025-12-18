from fastapi import FastAPI, Request, Form
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse

app = FastAPI()

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

@app.get("/", response_class=HTMLResponse)
async def get(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.post("/chat", response_class=HTMLResponse)
async def chat(request: Request, message: str = Form(...)):
    # Echo the message back for now
    # This is where we will integrate LangChain later
    return templates.TemplateResponse("chat_message.html", {"request": request, "message": message, "is_user": False})

@app.post("/chat/user", response_class=HTMLResponse)
async def chat_user(request: Request, message: str = Form(...)):
     return templates.TemplateResponse("chat_message.html", {"request": request, "message": message, "is_user": True})
