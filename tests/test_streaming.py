"""
tests/test_streaming.py

Covers django_langgraph_agent.streaming — the SSE core, which had no direct
test coverage: event framing, the summarizer-output filter, approval interrupts,
the resume/decision path, and the error boundary.

The agent and graph are stubbed: these tests are about the streaming protocol,
not about LangGraph or a live model.
"""

import json

import pytest
from langchain_core.messages import AIMessage

from django_langgraph_agent import streaming


# ──────────────────────────────────────────────────────────────────────────────
# Stubs
# ──────────────────────────────────────────────────────────────────────────────

class _FakeTask:
    def __init__(self, interrupts=()):
        self.interrupts = list(interrupts)


class _FakeInterrupt:
    def __init__(self, value):
        self.value = value


class _FakeState:
    def __init__(self, next_=(), tasks=(), values=None):
        self.next = tuple(next_)
        self.tasks = list(tasks)
        self.values = values if values is not None else {}


class _FakeGraph:
    """Replays a scripted list of (event_type, event_data) pairs."""

    def __init__(self, events=(), state=None):
        self._events = list(events)
        self._state = state or _FakeState()
        self.updated_state = None
        self.stream_calls = []

    def stream(self, inputs, config=None, stream_mode=None):
        self.stream_calls.append(inputs)
        yield from self._events

    def get_state(self, config):
        return self._state

    def update_state(self, config, values, as_node=None):
        self.updated_state = (values, as_node)


class _FakeAgent:
    def __init__(self, graph, tools=(), name="fake", model_name="test/model"):
        self._graph = graph
        self.tools = list(tools)
        self.name = name
        self.model_name = model_name
        self.allowed_models = []
        self.blocked_fields = []
        self.last_config = None

    def get_graph(self):
        return self._graph

    def thread_id(self, thread_id):
        return f"{self.name}:{thread_id}"


def _msg_event(text, node="agent", model="test/model"):
    return ("messages", (AIMessage(content=text), {"langgraph_node": node, "ls_model_name": model}))


def _parse(sse_output):
    """Turns a list of raw SSE strings into [(event, data-dict), ...]."""
    parsed = []
    for raw in sse_output:
        lines = raw.strip().split("\n")
        event = lines[0].removeprefix("event: ")
        data = json.loads(lines[1].removeprefix("data: "))
        parsed.append((event, data))
    return parsed


# ──────────────────────────────────────────────────────────────────────────────
# Event framing
# ──────────────────────────────────────────────────────────────────────────────

def test_sse_frames_an_event_with_a_blank_line_terminator():
    out = streaming._sse("token", {"text": "hi"})
    assert out == 'event: token\ndata: {"text": "hi"}\n\n'


def test_sse_survives_a_value_json_cannot_serialize():
    """Same class as issue #7 — one unserializable value must not abort the turn."""
    from decimal import Decimal

    out = streaming._sse("tool_approval", {"args": {"amount": Decimal("9.99")}})
    assert json.loads(out.split("data: ")[1])["args"]["amount"] == "9.99"


# ──────────────────────────────────────────────────────────────────────────────
# stream_agent
# ──────────────────────────────────────────────────────────────────────────────

def test_tokens_are_streamed_then_a_done_event():
    agent = _FakeAgent(_FakeGraph([_msg_event("Hello "), _msg_event("world")]))
    events = _parse(list(streaming.stream_agent(agent, "hi", "t1")))

    assert [e for e, _ in events] == ["token", "token", "done"]
    assert "".join(d["text"] for e, d in events if e == "token") == "Hello world"
    assert events[-1][1]["model_name"] == "test/model"


def test_summarizer_output_is_never_streamed_to_the_user():
    graph = _FakeGraph([
        _msg_event("visible"),
        _msg_event("INTERNAL SUMMARY", node="summarize"),
    ])
    events = _parse(list(streaming.stream_agent(_FakeAgent(graph), "hi", "t1")))

    texts = [d["text"] for e, d in events if e == "token"]
    assert texts == ["visible"]


def test_empty_chunks_produce_no_token_event():
    graph = _FakeGraph([_msg_event(""), _msg_event("real")])
    events = _parse(list(streaming.stream_agent(_FakeAgent(graph), "hi", "t1")))

    assert [d["text"] for e, d in events if e == "token"] == ["real"]


def test_thread_id_is_namespaced_by_agent():
    """Namespacing is what lets several agents share one checkpointer table."""
    captured = {}

    class _CapturingGraph(_FakeGraph):
        def stream(self, inputs, config=None, stream_mode=None):
            captured.update(config["configurable"])
            return iter(())

    agent = _FakeAgent(_CapturingGraph())
    list(streaming.stream_agent(agent, "hi", "t1", user_id=42))

    assert captured["thread_id"] == "fake:t1"
    assert captured["user_id"] == 42
    assert captured["agent_name"] == "fake"


def test_user_id_is_omitted_when_not_supplied():
    captured = {}

    class _CapturingGraph(_FakeGraph):
        def stream(self, inputs, config=None, stream_mode=None):
            captured.update(config["configurable"])
            return iter(())

    list(streaming.stream_agent(_FakeAgent(_CapturingGraph()), "hi", "t1"))
    assert "user_id" not in captured


def test_extra_config_reaches_the_graph():
    captured = {}

    class _CapturingGraph(_FakeGraph):
        def stream(self, inputs, config=None, stream_mode=None):
            captured.update(config["configurable"])
            return iter(())

    list(streaming.stream_agent(
        _FakeAgent(_CapturingGraph()), "hi", "t1", extra_config={"organization_id": 7}
    ))
    assert captured["organization_id"] == 7


def test_callbacks_fire_with_the_full_message():
    tokens, done = [], []
    graph = _FakeGraph([_msg_event("a"), _msg_event("b")])

    list(streaming.stream_agent(
        _FakeAgent(graph), "hi", "t1",
        on_token=tokens.append,
        on_done=lambda text, meta: done.append((text, meta)),
    ))

    assert tokens == ["a", "b"]
    assert done == [("ab", {"model_name": "test/model"})]


# ──────────────────────────────────────────────────────────────────────────────
# Approval interrupt
# ──────────────────────────────────────────────────────────────────────────────

def test_an_interrupt_emits_tool_approval_and_stops_the_stream():
    payload = {"tool_calls": [{"id": "c1", "name": "add_record", "args": {}, "human_label": "Add a row"}]}
    state = _FakeState(next_=("execute_tools",), tasks=[_FakeTask([_FakeInterrupt(payload)])])
    graph = _FakeGraph([("values", {})], state=state)

    events = _parse(list(streaming.stream_agent(_FakeAgent(graph), "hi", "t1")))

    assert [e for e, _ in events] == ["tool_approval"]
    assert events[0][1] == payload, "no 'done' may follow — the turn is paused, not finished"


def test_on_approval_callback_receives_the_payload():
    payload = {"tool_calls": [{"id": "c1", "name": "add_record", "args": {}}]}
    state = _FakeState(next_=("execute_tools",), tasks=[_FakeTask([_FakeInterrupt(payload)])])
    graph = _FakeGraph([("values", {})], state=state)

    seen = []
    list(streaming.stream_agent(_FakeAgent(graph), "hi", "t1", on_approval=seen.append))
    assert seen == [payload]


def test_a_values_event_without_an_interrupt_does_not_stop_the_stream():
    graph = _FakeGraph([("values", {}), _msg_event("after")], state=_FakeState())
    events = _parse(list(streaming.stream_agent(_FakeAgent(graph), "hi", "t1")))

    assert [e for e, _ in events] == ["token", "done"]


# ──────────────────────────────────────────────────────────────────────────────
# Resume after approval
# ──────────────────────────────────────────────────────────────────────────────

def _pending_tool_call_state(tool_name="add_record", call_id="c1", args=None):
    ai = AIMessage(
        content="",
        tool_calls=[{"id": call_id, "name": tool_name, "args": args or {}, "type": "tool_call"}],
    )
    return _FakeState(values={"messages": [ai]})


def test_resume_errors_when_the_thread_has_no_state():
    graph = _FakeGraph(state=_FakeState(values={}))
    events = _parse(list(streaming.resume_agent(_FakeAgent(graph), "t1", {})))

    assert events[0][0] == "error"
    assert "No active state" in events[0][1]["message"]


def test_resume_errors_when_nothing_is_pending_approval():
    state = _FakeState(values={"messages": [AIMessage(content="just text")]})
    events = _parse(list(streaming.resume_agent(_FakeAgent(_FakeGraph(state=state)), "t1", {})))

    assert events[0][0] == "error"
    assert "No pending tool calls" in events[0][1]["message"]


def test_an_approved_call_runs_the_tool_and_feeds_the_result_back():
    from langchain_core.tools import tool

    @tool
    def add_record(value: str = "") -> str:
        """Adds a record."""
        return f"created {value}"

    graph = _FakeGraph(state=_pending_tool_call_state(args={"value": "x"}))
    agent = _FakeAgent(graph, tools=[add_record])

    list(streaming.resume_agent(agent, "t1", {"c1": "approve"}))

    messages, as_node = graph.updated_state
    assert as_node == "execute_tools"
    assert messages["messages"][0].content == "created x"


def test_a_denied_call_is_reported_back_without_running_the_tool():
    from langchain_core.tools import tool

    ran = []

    @tool
    def add_record(value: str = "") -> str:
        """Adds a record."""
        ran.append(value)
        return "created"

    graph = _FakeGraph(state=_pending_tool_call_state(args={"value": "x"}))
    list(streaming.resume_agent(_FakeAgent(graph, tools=[add_record]), "t1", {"c1": "deny"}))

    assert ran == [], "a denied tool must not execute"
    content = json.loads(graph.updated_state[0]["messages"][0].content)
    assert content["status"] == "denied"


def test_an_omitted_decision_defaults_to_deny():
    """Fail closed: a decision the client never sent must not run the tool."""
    from langchain_core.tools import tool

    ran = []

    @tool
    def add_record(value: str = "") -> str:
        """Adds a record."""
        ran.append(value)
        return "created"

    graph = _FakeGraph(state=_pending_tool_call_state(args={"value": "x"}))
    list(streaming.resume_agent(_FakeAgent(graph, tools=[add_record]), "t1", {}))

    assert ran == []
    assert json.loads(graph.updated_state[0]["messages"][0].content)["status"] == "denied"


def test_a_failing_tool_reports_the_error_to_the_model_rather_than_aborting():
    from langchain_core.tools import tool

    @tool
    def add_record(value: str = "") -> str:
        """Adds a record."""
        raise RuntimeError("db is down")

    graph = _FakeGraph(state=_pending_tool_call_state(args={"value": "x"}))
    events = _parse(list(streaming.resume_agent(
        _FakeAgent(graph, tools=[add_record]), "t1", {"c1": "approve"}
    )))

    content = json.loads(graph.updated_state[0]["messages"][0].content)
    assert "db is down" in content["error"], "the model needs to see why the tool failed"
    assert [e for e, _ in events] == ["done"]


# ──────────────────────────────────────────────────────────────────────────────
# Error boundary
# ──────────────────────────────────────────────────────────────────────────────

class _ExplodingGraph(_FakeGraph):
    def stream(self, inputs, config=None, stream_mode=None):
        raise RuntimeError("connection to 10.0.0.5:5432 failed: password authentication failed")
        yield  # pragma: no cover


def test_an_internal_error_is_reported_without_leaking_the_exception():
    """These endpoints are reachable by non-staff callers whenever API_PERMISSION
    is relaxed, and exception text carries connection strings and SQL."""
    events = _parse(list(streaming.stream_agent(_FakeAgent(_ExplodingGraph()), "hi", "t1")))

    assert [e for e, _ in events] == ["error"]
    message = events[0][1]["message"]
    assert "password authentication failed" not in message
    assert "10.0.0.5" not in message
    assert message


def test_the_real_exception_is_still_logged(caplog):
    import logging

    with caplog.at_level(logging.ERROR, logger="django_langgraph_agent.streaming"):
        list(streaming.stream_agent(_FakeAgent(_ExplodingGraph()), "hi", "t1"))

    assert "password authentication failed" in caplog.text, "the detail must reach the operator"


def test_resume_also_hides_the_exception():
    class _ExplodingOnUpdate(_FakeGraph):
        def update_state(self, config, values, as_node=None):
            raise RuntimeError("secret conninfo host=db user=admin password=hunter2")

    graph = _ExplodingOnUpdate(state=_pending_tool_call_state())
    events = _parse(list(streaming.resume_agent(_FakeAgent(graph), "t1", {"c1": "deny"})))

    assert events[0][0] == "error"
    assert "hunter2" not in events[0][1]["message"]
