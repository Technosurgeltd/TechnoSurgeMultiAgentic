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

class State(TypedDict):
    messages: Annotated[list[AnyMessage], add_messages]
    lead_saved: bool
    emails_sent: bool
    latest_lead: dict | None
    conversation_ended: bool

def leadbot_node(state: State):
    print("\n🤖 LeadBot Agent started...")
    
    leadbot_messages = []
    for msg in state["messages"]:
        if isinstance(msg, HumanMessage):
            leadbot_messages.append({"role": "user", "content": msg.content})
        elif isinstance(msg, AIMessage):
            leadbot_messages.append({"role": "assistant", "content": msg.content})
    
    previous_lead = state.get("latest_lead") or {"name": "Unknown", "email": "NULL"}
    
    result = leadbot.run_conversation_from_messages(leadbot_messages, previous_lead)
    
    state["latest_lead"] = result.get("lead", previous_lead)
    state["conversation_ended"] = result.get("conversation_ended", False)
    state["lead_saved"] = state["conversation_ended"]
    
    if "ai_reply" in result:
        state["messages"].append(AIMessage(content=result["ai_reply"]))
    
    return state

def emailagent_node(state: State):
    print("\n📧 Email Agent started...")
    lead = state.get("latest_lead")
    if not lead:
        print("⚠️ No latest lead found, skipping email...")
        state["emails_sent"] = False
        return state
    
    if lead.get("email") and lead.get("email") != "NULL":
        try:
            success = emailagent.send_email_to_lead(lead)
            state["emails_sent"] = success
            if success:
                print("✅ Email sent successfully")
            else:
                print("❌ Email sending failed")
        except Exception as e:
            print(f"❌ Email sending failed: {e}")
            state["emails_sent"] = False
    else:
        print("⚠️ No valid email to send")
        state["emails_sent"] = False
        
    return state

def route_after_leadbot(state: State):
    if state["conversation_ended"] and state["latest_lead"].get("email", "NULL") != "NULL":
        return "emailagent"
    return END

builder = StateGraph(State)
builder.add_node("leadbot", leadbot_node)
builder.add_node("emailagent", emailagent_node)
builder.add_edge(START, "leadbot")
builder.add_conditional_edges("leadbot", route_after_leadbot, {"emailagent": "emailagent", END: END})
builder.add_edge("emailagent", END)
graph = builder.compile()

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],  # Allow HEAD for Render health checks
    allow_headers=["*"],
)

@app.get("/")
def read_root():
    return {"message": "🚀 Technosurge Multi-Agent Workflow API is running!"}

class ChatRequest(BaseModel):
    message: str | None = None

SESSIONS: dict[str, State] = {}

@app.post("/chat/{session_id}")
def chat(session_id: str, req: ChatRequest):
    if session_id not in SESSIONS:
        SESSIONS[session_id] = {
            "messages": [],
            "lead_saved": False,
            "emails_sent": False,
            "latest_lead": {"name": "Unknown", "email": "NULL"},
            "conversation_ended": False
        }
    
    state = SESSIONS[session_id]
    
    if req.message:
        state["messages"].append(HumanMessage(content=req.message))
    
    final_state = graph.invoke(state)
    
    SESSIONS[session_id] = final_state
    
    ai_messages = [msg for msg in final_state["messages"] if isinstance(msg, AIMessage)]
    ai_reply = ai_messages[-1].content if ai_messages else "No response generated"
    
    return {
        "status": "ok",
        "ai_reply": ai_reply,
        "lead": final_state.get("latest_lead", {}),
        "lead_saved": final_state.get("lead_saved", False),
        "emails_sent": final_state.get("emails_sent", False),
        "conversation_ended": final_state.get("conversation_ended", False)
    }
