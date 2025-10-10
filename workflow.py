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

def leadbot_node(state: State):
    print("\n🤖 LeadBot Agent started...")
    
    # Convert ALL LangGraph messages to your leadbot format
    leadbot_messages = []
    for msg in state["messages"]:
        if isinstance(msg, HumanMessage):
            leadbot_messages.append({"role": "user", "content": msg.content})
        elif isinstance(msg, AIMessage):
            leadbot_messages.append({"role": "assistant", "content": msg.content})
    
    # Get the latest lead from previous state
    previous_lead = state.get("latest_lead") or {"name": "Unknown", "email": "NULL"}
    
    # ✅ FIX: Pass ENTIRE conversation history + previous lead
    result = leadbot.run_conversation_from_messages(leadbot_messages, previous_lead)
    
    # Update state with new lead information
    state["latest_lead"] = result.get("lead", previous_lead)
    state["lead_saved"] = True
    
    # Add AI response to the conversation
    if "ai_reply" in result:
        state["messages"].append(AIMessage(content=result["ai_reply"]))
    
    return state

def emailagent_node(state: State):
    print("\n📧 Email Agent started...")
    lead = state.get("latest_lead")
    if not lead:
        print("⚠️ No latest lead found, skipping email...")
        return state
    
    # Check if conversation ended and we have valid email
    if lead.get("email") and lead.get("email") != "NULL":
        try:
            emailagent.send_email_to_lead(lead)
            state["emails_sent"] = True
            print("✅ Email sent successfully")
        except Exception as e:
            print(f"❌ Email sending failed: {e}")
            state["emails_sent"] = False
    else:
        print("⚠️ No valid email to send")
        state["emails_sent"] = False
        
    return state

# Build the graph
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
    allow_origins=["*"],
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
    # Retrieve or initialize session
    if session_id not in SESSIONS:
        SESSIONS[session_id] = {
            "messages": [],
            "lead_saved": False,
            "emails_sent": False,
            "latest_lead": {"name": "Unknown", "email": "NULL"}
        }
    
    state = SESSIONS[session_id]
    
    # Add user message to state
    state["messages"].append(HumanMessage(content=req.message))
    
    # Run the LangGraph workflow
    final_state = graph.invoke(state)
    
    # Update session
    SESSIONS[session_id] = final_state
    
    # Get the AI reply from the messages
    ai_messages = [msg for msg in final_state["messages"] if isinstance(msg, AIMessage)]
    ai_reply = ai_messages[-1].content if ai_messages else "No response generated"
    
    return {
        "status": "ok",
        "ai_reply": ai_reply,
        "lead": final_state.get("latest_lead", {}),
        "lead_saved": final_state.get("lead_saved", False),
        "emails_sent": final_state.get("emails_sent", False)
    }
