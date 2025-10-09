import os
from typing_extensions import TypedDict
from typing import Annotated
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langchain_core.messages import AnyMessage, HumanMessage, AIMessage

# Import your existing bots
import leadbot
import emailagent

# Load .env for API keys
load_dotenv()

# class State
class State(TypedDict):
    messages: Annotated[list[AnyMessage], add_messages]
    lead_saved: bool
    emails_sent: bool
    latest_lead: dict | None

def leadbot_node(state: State):
    print("\n🤖 LeadBot Agent started...")
    lead = leadbot.run_conversation_from_messages(state["messages"])  
    state["lead_saved"] = True
    state["latest_lead"] = lead
    return state

def emailagent_node(state: State):
    print("\n📧 Email Agent started...")
    lead = state.get("latest_lead")
    if not lead:
        print("⚠️ No latest lead found, skipping email...")
        return state
    emailagent.send_email_to_lead(lead)
    state["emails_sent"] = True
    return state

builder = StateGraph(State)
builder.add_node("leadbot", leadbot_node)
builder.add_node("emailagent", emailagent_node)
builder.add_edge(START, "leadbot")
builder.add_edge("leadbot", "emailagent")
builder.add_edge("emailagent", END)
graph = builder.compile()

# FastAPI 

app = FastAPI()


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # You can replace "*" with your frontend domain later
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def read_root():
    return {"message": "🚀 Technosurge Multi-Agent Workflow API is running!"}

class ChatRequest(BaseModel):
    message: str

# in-memory sessions
SESSIONS: dict[str, State] = {}

@app.post("/chat/{session_id}")
def chat(session_id: str, req: ChatRequest):
    # Retrieve or init session
    state = SESSIONS.get(session_id, {"messages": [], "lead": {"name": None, "email": None, "summary": None}})

    # Add user message
    state["messages"].append({"role": "user", "content": req.message})

    # Run LeadBot
    ai_reply, updated_lead, ended = leadbot.respond(req.message, state["lead"])

    # Update session state
    state["lead"] = updated_lead
    state["messages"].append({"role": "assistant", "content": ai_reply})
    SESSIONS[session_id] = state

    # If conversation ended → send email
    emails_sent = False
    if ended and updated_lead and updated_lead.get("email") not in [None, "NULL"]:
        emailagent.send_email_to_lead(updated_lead)
        emails_sent = True

    return {
        "status": "ok",
        "ai_reply": ai_reply,
        "lead": updated_lead,
        "lead_saved": ended,   # only true at end
        "emails_sent": emails_sent
    }



