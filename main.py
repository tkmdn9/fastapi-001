import os
import markdown
from dotenv import load_dotenv
from fastapi import FastAPI, Request, Form
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser

# Load environment variables
load_dotenv()

app = FastAPI()

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# Initialize LangChain
# Default to OpenAI, but can be switched to Gemini if GOOGLE_API_KEY is present
if os.getenv("OPENAI_API_KEY"):
    model = ChatOpenAI(model="gpt-3.5-turbo")
else:
    # Fallback or error handling if no key. For now, we'll just print a warning.
    print("WARNING: OPENAI_API_KEY not found. Chat will fail.")
    model = None

@app.get("/", response_class=HTMLResponse)
async def get(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.post("/chat", response_class=HTMLResponse)
async def chat(request: Request, message: str = Form(...)):
    if not model:
        response_text = "Error: API Key not configured. Please check .env file."
    else:
        try:
            # Create a simple chain
            prompt = ChatPromptTemplate.from_template("You are a helpful assistant. Answer the following question: {question}")
            chain = prompt | model | StrOutputParser()
            
            # Invoke the chain
            response_text = chain.invoke({"question": message})
        except Exception as e:
            response_text = f"Error generating response: {str(e)}"

    # Render Markdown to HTML
    response_html = markdown.markdown(response_text, extensions=['fenced_code', 'codehilite'])

    return templates.TemplateResponse("chat_message.html", {
        "request": request, 
        "message": response_html, 
        "is_user": False
    })

@app.post("/chat/user", response_class=HTMLResponse)
async def chat_user(request: Request, message: str = Form(...)):
     return templates.TemplateResponse("chat_message.html", {"request": request, "message": message, "is_user": True})
