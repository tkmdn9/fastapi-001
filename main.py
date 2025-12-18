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
         # Fallback if cookie missing, though mostly handled by browser
         session_id = "default"

    # Return the user message AND a placeholder for the bot response
    # The placeholder connects to the SSE stream
    return templates.TemplateResponse("chat_response_fragment.html", {
        "request": request,
        "message": message,
        "session_id": session_id
    })

@app.get("/chat_stream/{session_id}")
async def chat_stream(request: Request, session_id: str):
    # Get the last user message from memory? 
    # Actually, the standard pattern is:
    # 1. POST /chat updates memory with user message.
    # 2. GET /stream generates response based on memory.
    
    # However, in our POST /chat above, we didn't save to memory yet because 
    # RunnableWithMessageHistory does it automatically when invoked.
    # So we need to pass the user message to the stream endpoint or save it first.
    
    # Revised flow:
    # We need to pass the message to this endpoint. Cookies/Session? 
    # Or, simpler: The POST /chat saves to memory MANUALLY, then stream just asks AI to "reply".
    
    # Let's try passing the message via query param for this turn?
    # No, that's ugly.
    
    # Better:
    # The POST /chat sends the user message to the server.
    # The server appends it to history.
    # The response triggers the stream.
    # The stream runs the chain with just the history (and a dummy input? or last message?).
    
    # Simpler HACK for this pattern:
    # Pass the message as a query param to the SSE endpoint in the HTML fragment.
    # <div hx-ext="sse" sse-connect="/chat_stream/session_id?message=USER_MSG" ...>
    
    return StreamingResponse(
        stream_generator(session_id, request.query_params.get("message", "")),
        media_type="text/event-stream"
    )

async def stream_generator(session_id: str, message: str):
    if not model or not message:
        yield f"event: message\ndata: <div id='error'>Error</div>\n\n"
        return

    full_response = ""
    
    # Yield the beginning of the bubble
    # We are replacing the inner content of the placeholder
    
    try:
        # Stream the response
        async for chunk in runnable_with_history.astream(
            {"question": message},
            config={"configurable": {"session_id": session_id}}
        ):
            full_response += chunk
            # Render Markdown on the fly? Ideally yes, but tricky with partials.
            # For now, let's just stream text and render full markdown at the end?
            # Or use a client-side markdown renderer? 
            # Plan said: "Implement StreamingResponse... Update Chat UI to handle streaming chunks"
            # Let's just stream raw text for the "typing" effect, then swap with rendered markdown at the end.
            
            # Escape HTML to prevent injection during streaming
            safe_chunk = chunk.replace("<", "&lt;").replace(">", "&gt;")
            
            # SSE Format: data: <content>\n\n
            # We append to the message-content div
            yield f"event: message\ndata: {safe_chunk}\n\n"
            
            # Artificial delay for effect if it's too fast? No.
            
        # Final Event: Swap with full rendered markdown
        rendered_html = markdown.markdown(full_response, extensions=['fenced_code', 'codehilite'])
        # We need to replace the whole content with the robust HTML
        yield f"event: close\ndata: {rendered_html}\n\n"
        
    except Exception as e:
        yield f"event: message\ndata: Error: {str(e)}\n\n"

