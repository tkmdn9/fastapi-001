import os
import secrets
import markdown
import asyncio
from dotenv import load_dotenv
from fastapi import FastAPI, Request, Form
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, StreamingResponse
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables.history import RunnableWithMessageHistory
from langchain_community.chat_message_histories import ChatMessageHistory
from langchain_core.chat_history import BaseChatMessageHistory

# Load environment variables
load_dotenv()

app = FastAPI()

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# Initialize LangChain
if os.getenv("OPENAI_API_KEY"):
    model = ChatOpenAI(model="gpt-3.5-turbo", streaming=True)
else:
    print("WARNING: OPENAI_API_KEY not found. Chat will fail.")
    model = None

# Memory Storage (In-Memory for simplicity)
store = {}

def get_session_history(session_id: str) -> BaseChatMessageHistory:
    if session_id not in store:
        store[session_id] = ChatMessageHistory()
    return store[session_id]

PROMPT = ChatPromptTemplate.from_messages([
    ("system", "You are a helpful assistant. Result must be in markdown."),
    MessagesPlaceholder(variable_name="history"),
    ("human", "{question}"),
])

if model:
    chain = PROMPT | model | StrOutputParser()
    runnable_with_history = RunnableWithMessageHistory(
        chain,
        get_session_history,
        input_messages_key="question",
        history_messages_key="history",
    )

@app.get("/", response_class=HTMLResponse)
async def get(request: Request):
    # Ensure session_id exists
    session_id = request.cookies.get("session_id")
    response = templates.TemplateResponse("index.html", {"request": request})
    if not session_id:
        response.set_cookie("session_id", secrets.token_hex(16))
    return response

@app.post("/chat", response_class=HTMLResponse)
async def chat(request: Request, message: str = Form(...)):
    session_id = request.cookies.get("session_id")
    if not session_id:
         session_id = "default"
    
    # Generate a unique ID for this message bubble
    message_id = secrets.token_hex(4)

    return templates.TemplateResponse("chat_response_fragment.html", {
        "request": request,
        "message": message,
        "session_id": session_id,
        "message_id": message_id
    })

async def stream_generator(session_id: str, message: str, message_id: str):
    if not model or not message:
        yield f"event: message\ndata: <div class='text-red-500'>Error: API Key missing</div>\n\n"
        # Stop everything by replacing with static error via OOB
        yield f"""event: message
data: <div id="bot-response-{message_id}" hx-swap-oob="outerHTML" class="bg-gray-200 text-gray-800 rounded-lg px-4 py-2 max-w-[80%] prose border border-red-500">Error: API Key missing</div>
"""
        yield "event: close\ndata: \n\n"
        return

    full_response = ""
    
    try:
        async for chunk in runnable_with_history.astream(
            {"question": message},
            config={"configurable": {"session_id": session_id}}
        ):
            full_response += chunk
            safe_text = full_response.replace("<", "&lt;").replace(">", "&gt;").replace("\n", "<br>")
            yield f"event: message\ndata: {safe_text}\n\n"
            
        # Final Step: Replace the headers entirely using OOB to stop reconnection
        rendered_html = markdown.markdown(full_response, extensions=['fenced_code', 'codehilite'])
        safe_rendered_html = rendered_html.replace("\n", "")
        
        # OOB Swap to replace the streaming container with a static one
        # This removes the 'sse-connect' attribute, preventing reconnection.
        yield f"""event: message
data: <div id="bot-response-{message_id}" hx-swap-oob="outerHTML" class="bg-gray-200 text-gray-800 rounded-lg px-4 py-2 max-w-[80%] prose">{safe_rendered_html}</div>
"""
        yield "event: close\ndata: \n\n"
        
    except Exception as e:
        yield f"event: message\ndata: Error: {str(e)}\n\n"
        yield "event: close\ndata: \n\n"

@app.get("/chat_stream/{session_id}")
async def chat_stream(request: Request, session_id: str):
    message = request.query_params.get("message", "")
    message_id = request.query_params.get("message_id", "")
    return StreamingResponse(
        stream_generator(session_id, message, message_id),
        media_type="text/event-stream"
    )

@app.post("/chat/user", response_class=HTMLResponse)
async def chat_user(request: Request, message: str = Form(...)):
     return templates.TemplateResponse("chat_message.html", {"request": request, "message": message, "is_user": True})
