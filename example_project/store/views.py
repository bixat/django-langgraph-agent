"""
example_project/store/views.py

Example Django views for SSE streaming chat with the AI agent.

Endpoints:
  POST /chat/          → Start a new chat turn (returns SSE stream)
  POST /chat/approve/  → Resume after tool approval (returns SSE stream)
  GET  /chat/          → Simple HTML test page
"""

import json

from django.http import JsonResponse, StreamingHttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from django_langgraph_agent import resume_agent, stream_agent

from .agents import store_admin_agent, store_agent


# ──────────────────────────────────────────────────────────────────────────────
# Chat Endpoint (SSE)
# ──────────────────────────────────────────────────────────────────────────────

@csrf_exempt
@require_http_methods(["GET", "POST"])
def chat_view(request):
    """
    GET  → returns the test HTML page
    POST → starts a streaming chat session and returns SSE events
    """
    if request.method == "GET":
        return _chat_html_page(request)

    # Parse request body
    try:
        body = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON body"}, status=400)

    message = body.get("message", "").strip()
    thread_id = body.get("thread_id", "default-thread")
    agent_type = body.get("agent", "store")  # "store" or "store_admin"
    user_id = body.get("user_id", 1)

    if not message:
        return JsonResponse({"error": "message is required"}, status=400)

    agent = store_admin_agent if agent_type == "store_admin" else store_agent

    # Optional: save messages to DB using the on_done callback
    def on_done(full_text: str, extra: dict):
        # Example: save to your own model here
        # ChatMessage.objects.create(thread_id=thread_id, text=full_text, is_user=False)
        pass

    gen = stream_agent(
        agent=agent,
        message=message,
        thread_id=thread_id,
        user_id=user_id,
        on_done=on_done,
    )

    return StreamingHttpResponse(
        gen,
        content_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # Disable Nginx buffering
        },
    )


# ──────────────────────────────────────────────────────────────────────────────
# Tool Approval Endpoint (SSE)
# ──────────────────────────────────────────────────────────────────────────────

@csrf_exempt
@require_http_methods(["POST"])
def approve_view(request):
    """
    Resume a paused agent after the user approves/denies tool calls.

    Request body:
    {
        "thread_id": "...",
        "agent": "store_admin",
        "decisions": {
            "tool_call_id_1": "approve",
            "tool_call_id_2": "deny"
        }
    }
    """
    try:
        body = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON body"}, status=400)

    thread_id = body.get("thread_id", "default-thread")
    decisions = body.get("decisions", {})
    agent_type = body.get("agent", "store_admin")
    user_id = body.get("user_id", 1)

    agent = store_admin_agent if agent_type == "store_admin" else store_agent

    gen = resume_agent(
        agent=agent,
        thread_id=thread_id,
        decisions=decisions,
        user_id=user_id,
    )

    return StreamingHttpResponse(
        gen,
        content_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


# ──────────────────────────────────────────────────────────────────────────────
# Test HTML Page
# ──────────────────────────────────────────────────────────────────────────────

def _chat_html_page(request):
    from django.http import HttpResponse
    html = """
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>django-langgraph-agent — Test Chat</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    background: #0f0f1a;
    color: #e0e0e0;
    height: 100vh;
    display: flex;
    flex-direction: column;
    align-items: center;
    padding: 20px;
  }
  h1 { color: #7c6fcd; margin-bottom: 4px; font-size: 1.5rem; }
  .subtitle { color: #888; font-size: 0.85rem; margin-bottom: 20px; }
  .container {
    width: 100%;
    max-width: 780px;
    display: flex;
    flex-direction: column;
    gap: 12px;
    flex: 1;
  }
  .controls {
    display: flex;
    gap: 10px;
    align-items: center;
  }
  .controls label { color: #aaa; font-size: 0.85rem; }
  select, input[type="text"] {
    background: #1e1e2e;
    border: 1px solid #333;
    color: #e0e0e0;
    padding: 6px 10px;
    border-radius: 6px;
    font-size: 0.85rem;
  }
  #messages {
    flex: 1;
    overflow-y: auto;
    background: #1a1a2e;
    border: 1px solid #2a2a3e;
    border-radius: 12px;
    padding: 16px;
    display: flex;
    flex-direction: column;
    gap: 12px;
    min-height: 350px;
    max-height: 500px;
  }
  .msg {
    max-width: 80%;
    padding: 10px 14px;
    border-radius: 12px;
    line-height: 1.5;
    white-space: pre-wrap;
    font-size: 0.9rem;
  }
  .msg.user { background: #7c6fcd; color: white; align-self: flex-end; }
  .msg.ai { background: #1e1e2e; border: 1px solid #2a2a3e; align-self: flex-start; }
  .msg.approval {
    background: #2a1e0e;
    border: 1px solid #8b4513;
    align-self: flex-start;
    max-width: 90%;
  }
  .msg.error { background: #2a0e0e; border: 1px solid #8b0000; align-self: flex-start; }
  .approval-btns { display: flex; gap: 8px; margin-top: 8px; flex-wrap: wrap; }
  .btn-approve, .btn-deny {
    padding: 5px 14px;
    border: none;
    border-radius: 6px;
    cursor: pointer;
    font-size: 0.8rem;
    font-weight: 600;
  }
  .btn-approve { background: #2d6a2d; color: #90ee90; }
  .btn-approve:hover { background: #3d8a3d; }
  .btn-deny { background: #6a2d2d; color: #ee9090; }
  .btn-deny:hover { background: #8a3d3d; }
  .input-row {
    display: flex;
    gap: 8px;
  }
  #msg-input {
    flex: 1;
    background: #1e1e2e;
    border: 1px solid #333;
    color: #e0e0e0;
    padding: 10px 14px;
    border-radius: 10px;
    font-size: 0.9rem;
    outline: none;
  }
  #msg-input:focus { border-color: #7c6fcd; }
  #send-btn {
    background: #7c6fcd;
    color: white;
    border: none;
    padding: 10px 20px;
    border-radius: 10px;
    cursor: pointer;
    font-weight: 600;
    font-size: 0.9rem;
    transition: background 0.2s;
  }
  #send-btn:hover { background: #9b8fe0; }
  #send-btn:disabled { background: #444; cursor: not-allowed; }
  .status { color: #666; font-size: 0.75rem; text-align: center; }
</style>
</head>
<body>
<h1>🤖 django-langgraph-agent</h1>
<p class="subtitle">Test interface — streaming SSE chat</p>

<div class="container">
  <div class="controls">
    <label>Agent:</label>
    <select id="agent-select">
      <option value="store">Store (read-only)</option>
      <option value="store_admin">Store Admin (CRUD + approval)</option>
    </select>
    <label>Thread ID:</label>
    <input type="text" id="thread-input" value="test-thread-1" style="width:140px">
  </div>

  <div id="messages">
    <div class="msg ai">👋 Hello! I'm the store assistant. Ask me about products or orders.</div>
  </div>

  <div class="input-row">
    <input type="text" id="msg-input" placeholder="Type a message..." autocomplete="off">
    <button id="send-btn" onclick="sendMessage()">Send</button>
  </div>
  <p class="status" id="status">Ready</p>
</div>

<script>
let currentDecisions = {};
let pendingApprovalPayload = null;

function addMessage(content, cls) {
  const div = document.getElementById("messages");
  const msg = document.createElement("div");
  msg.className = "msg " + cls;
  msg.id = cls === "ai" ? "ai-current" : undefined;
  msg.textContent = content;
  div.appendChild(msg);
  div.scrollTop = div.scrollHeight;
  return msg;
}

function setStatus(text) {
  document.getElementById("status").textContent = text;
}

function sendMessage() {
  const input = document.getElementById("msg-input");
  const msg = input.value.trim();
  if (!msg) return;

  const agent = document.getElementById("agent-select").value;
  const threadId = document.getElementById("thread-input").value.trim();

  addMessage(msg, "user");
  input.value = "";

  const aiMsg = addMessage("", "ai");
  document.getElementById("send-btn").disabled = true;
  setStatus("Agent is thinking...");

  const evtSource = new EventSource("#");  // placeholder — we use fetch for POST
  evtSource.close();

  // Use fetch with ReadableStream for SSE via POST
  fetch("/chat/", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message: msg, thread_id: threadId, agent: agent, user_id: 1 })
  }).then(res => readSSEStream(res, aiMsg)).catch(err => {
    aiMsg.textContent = "Error: " + err.message;
    aiMsg.className = "msg error";
    document.getElementById("send-btn").disabled = false;
    setStatus("Error");
  });
}

function readSSEStream(response, aiMsgEl) {
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  function read() {
    reader.read().then(({ done, value }) => {
      if (done) {
        document.getElementById("send-btn").disabled = false;
        setStatus("Ready");
        return;
      }
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\\n");
      buffer = lines.pop();

      let eventType = null;
      for (const line of lines) {
        if (line.startsWith("event: ")) {
          eventType = line.slice(7).trim();
        } else if (line.startsWith("data: ")) {
          const data = JSON.parse(line.slice(6));
          if (eventType === "token") {
            aiMsgEl.textContent += data.text;
            document.getElementById("messages").scrollTop = 99999;
          } else if (eventType === "tool_approval") {
            renderApproval(data);
          } else if (eventType === "done") {
            setStatus("Done" + (data.model_name ? " · " + data.model_name : ""));
            document.getElementById("send-btn").disabled = false;
          } else if (eventType === "error") {
            aiMsgEl.textContent = "Error: " + data.message;
            aiMsgEl.className = "msg error";
            document.getElementById("send-btn").disabled = false;
            setStatus("Error");
          }
          eventType = null;
        }
      }
      read();
    });
  }
  read();
}

function renderApproval(payload) {
  pendingApprovalPayload = payload;
  currentDecisions = {};

  const div = document.getElementById("messages");
  const card = document.createElement("div");
  card.className = "msg approval";
  card.id = "approval-card";

  let html = "<strong>⚠️ The AI wants to perform these actions. Approve?</strong><br><br>";
  const btns = payload.tool_calls.map(tc => {
    return `<div style="margin-bottom:8px">
      <span>${tc.human_label}</span>
      <div class="approval-btns">
        <button class="btn-approve" onclick="setDecision('${tc.id}', 'approve', this)">✅ Approve</button>
        <button class="btn-deny" onclick="setDecision('${tc.id}', 'deny', this)">❌ Deny</button>
      </div>
    </div>`;
  }).join("");
  html += btns;
  html += `<div style="margin-top:12px"><button class="btn-approve" onclick="submitApproval()" style="padding:8px 20px">Submit Decisions</button></div>`;
  card.innerHTML = html;
  div.appendChild(card);
  div.scrollTop = div.scrollHeight;
}

function setDecision(toolId, decision, btn) {
  currentDecisions[toolId] = decision;
  const sibs = btn.parentElement.querySelectorAll("button");
  sibs.forEach(b => b.style.opacity = "0.5");
  btn.style.opacity = "1";
  btn.style.fontWeight = "900";
}

function submitApproval() {
  const threadId = document.getElementById("thread-input").value.trim();
  const agent = document.getElementById("agent-select").value;
  const card = document.getElementById("approval-card");
  if (card) card.remove();

  const aiMsg = addMessage("", "ai");
  document.getElementById("send-btn").disabled = true;
  setStatus("Resuming agent...");

  fetch("/chat/approve/", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ thread_id: threadId, agent: agent, decisions: currentDecisions, user_id: 1 })
  }).then(res => readSSEStream(res, aiMsg)).catch(err => {
    aiMsg.textContent = "Error: " + err.message;
    aiMsg.className = "msg error";
    document.getElementById("send-btn").disabled = false;
    setStatus("Error");
  });
}

document.getElementById("msg-input").addEventListener("keydown", e => {
  if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); sendMessage(); }
});
</script>
</body>
</html>
"""
    return HttpResponse(html, content_type="text/html")
