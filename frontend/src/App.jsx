import { useState, useEffect, useRef } from "react";
import {
  Square, Settings, Terminal, Tv, Cpu,
  Check, X, Send
} from "lucide-react";
import "./App.css";

const API_BASE = "http://localhost:8000/api";

const STATUS_LABEL = {
  idle: "Ready",
  running: "Working",
  waiting_approval: "Awaiting approval",
  finished: "Done",
  error: "Error",
  paused: "Paused",
};

const QUICK_ACTIONS = [
  { label: "🔍 Find file", text: "Find file ", hint: "Search for a file in the permitted folders" },
  { label: "📝 Write report", text: "Write a report ", hint: "Ask the agent to draft a report" },
  { label: "✉️ Compose email", text: "Compose an email to ", hint: "Draft an email (review before sending)" },
  { label: "🚀 Open app", text: "Open ", hint: "Launch an application by name" },
];

const EDITABLE_TOOLS = new Set([
  "email.send", "email.create_draft", "message.send", "message.create_draft",
]);

function App() {
  const [chatInput, setChatInput] = useState("");
  const [chatHistory, setChatHistory] = useState(() => [
    {
      sender: "assistant",
      text: "Hi! I'm CONTROLPC — a local, GPU-powered computer-control assistant. I prefer safe actions: launching by path/CLI, keyboard shortcuts, Windows UI Automation (UIA), and only coordinate-clicking as a last resort. Give me a command to get started!",
      type: "assistant_chat",
      timestamp: Date.now() / 1000,
    },
  ]);
  const [isSending, setIsSending] = useState(false);
  const [streamingReply, setStreamingReply] = useState(null);

  const [status, setStatus] = useState("idle");
  const [currentGoal, setCurrentGoal] = useState("");
  const [currentStep, setCurrentStep] = useState(0);
  const [maxSteps, setMaxSteps] = useState(12);
  const [logs, setLogs] = useState([]);
  const [pendingAction, setPendingAction] = useState(null);

  const [aiMode, setAiMode] = useState("gemma4");
  const [ggufPath, setGgufPath] = useState("");
  const [permissionMode, setPermissionMode] = useState("ask"); // ask | smart | bypass
  const [permModeMsg, setPermModeMsg] = useState("");

  const [screenshot, setScreenshot] = useState("");
  const [screenWidth, setScreenWidth] = useState(1920);
  const [screenHeight, setScreenHeight] = useState(1080);

  const [isConnected, setIsConnected] = useState(false);
  const [isRefreshingScreen, setIsRefreshingScreen] = useState(false);
  const [activeTab, setActiveTab] = useState("screen");
  const [emailDraft, setEmailDraft] = useState(null);
  const [messageDraft, setMessageDraft] = useState(null);
  const [uiaWindows, setUiaWindows] = useState([]);
  const [selectedWindow, setSelectedWindow] = useState("");
  const [uiaTree, setUiaTree] = useState([]);
  const [isLoadingUia, setIsLoadingUia] = useState(false);

  const [systemStatus, setSystemStatus] = useState(null);
  const [secretStatus, setSecretStatus] = useState(null);
  const [smtpPwd, setSmtpPwd] = useState("");
  const [tgToken, setTgToken] = useState("");
  const [secretMsg, setSecretMsg] = useState("");
  const [modelMsg, setModelMsg] = useState("");
  const [memoryData, setMemoryData] = useState(null);
  const [availableModels, setAvailableModels] = useState([]);
  const [remoteStatus, setRemoteStatus] = useState(null);
  const [tgId, setTgId] = useState("");
  const [tgPin, setTgPin] = useState("");
  const [remoteMsg, setRemoteMsg] = useState("");

  const [editMode, setEditMode] = useState(false);
  const [editForm, setEditForm] = useState({ to_email: "", subject: "", body: "", text: "", contact_query: "" });

  const chatEndRef = useRef(null);
  const inputRef = useRef(null);
  const prevStatusRef = useRef("idle");

  // Surface an error as an in-chat bubble instead of a blocking native alert().
  const pushError = (text) =>
    setChatHistory((prev) => [
      ...prev,
      { sender: "assistant", text: `⚠️ ${text}`, type: "error", timestamp: Date.now() / 1000 },
    ]);

  const checkConnection = async () => {
    try {
      const res = await fetch(`${API_BASE}/status`);
      setIsConnected(res.ok);
    } catch {
      setIsConnected(false);
    }
  };

  const checkDownloadStatus = async () => {
    try {
      const res = await fetch(`${API_BASE}/download_status`);
      if (res.ok) {
        const data = await res.json();
        if (data.exists && !ggufPath) setGgufPath(data.model_path);
      }
    } catch (e) {
      console.error(e);
    }
  };

  const commitLogsToHistory = (taskLogs) => {
    if (!taskLogs || taskLogs.length === 0) return;
    const logMessages = taskLogs.map((l) => ({
      sender: l.type === "reasoning" || l.type === "success" || l.type === "assistant_chat" ? "assistant" : "system",
      text: l.message,
      type: l.type,
      actionData: l.action_data,
      status: l.status,
      timestamp: l.timestamp,
    }));
    setChatHistory((prev) => [...prev, ...logMessages]);
  };

  const fetchScreenshot = async () => {
    if (isRefreshingScreen) return;
    setIsRefreshingScreen(true);
    try {
      const res = await fetch(`${API_BASE}/screenshot`);
      if (res.ok) {
        const data = await res.json();
        setScreenshot(data.base64);
        if (data.width) setScreenWidth(data.width);
        if (data.height) setScreenHeight(data.height);
      }
    } catch (e) {
      console.error(e);
    } finally {
      setIsRefreshingScreen(false);
    }
  };

  const fetchEmailDraft = async () => {
    try {
      const res = await fetch(`${API_BASE}/email_draft`);
      if (res.ok) {
        const data = await res.json();
        setEmailDraft(data.exists ? data.draft : null);
      }
    } catch {
      /* ignore */
    }
  };

  const fetchMessageDraft = async () => {
    try {
      const res = await fetch(`${API_BASE}/message_draft`);
      if (res.ok) {
        const data = await res.json();
        setMessageDraft(data.exists ? data.draft : null);
      }
    } catch {
      /* ignore */
    }
  };

  const fetchUiaWindows = async () => {
    try {
      const res = await fetch(`${API_BASE}/uia/windows`);
      if (res.ok) {
        const data = await res.json();
        setUiaWindows(data.windows || []);
      }
    } catch (e) {
      console.error(e);
    }
  };

  const fetchUiaTree = async (winTitle) => {
    if (!winTitle) return;
    setIsLoadingUia(true);
    try {
      const res = await fetch(`${API_BASE}/uia/tree?window_title_re=${encodeURIComponent(winTitle)}`);
      if (res.ok) {
        const data = await res.json();
        setUiaTree(data.controls || []);
      }
    } catch (e) {
      console.error(e);
    } finally {
      setIsLoadingUia(false);
    }
  };

  const fetchSystemStatus = async () => {
    try {
      const res = await fetch(`${API_BASE}/system/status`);
      if (res.ok) {
        const js = await res.json();
        setSystemStatus(js);
        if (js.permission_mode) setPermissionMode(js.permission_mode);
      }
    } catch {
      /* ignore */
    }
  };

  const handleSetPermissionMode = async (mode) => {
    setPermissionMode(mode);
    setPermModeMsg("");
    try {
      const res = await fetch(`${API_BASE}/settings/set_permission_mode`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ mode }),
      });
      const js = await res.json();
      if (!res.ok) throw new Error(js.detail || "Error");
      setPermModeMsg(
        mode === "bypass"
          ? "⚡ Bypass: the agent runs without asking for approval."
          : mode === "smart"
          ? "⚖️ Asks only for risky actions."
          : "🛡️ Asks for approval on every action."
      );
    } catch (e) {
      setPermModeMsg("Failed to save mode: " + e.message);
    }
  };

  const fetchSecretStatus = async () => {
    try {
      const res = await fetch(`${API_BASE}/settings/secret_status`);
      if (res.ok) setSecretStatus(await res.json());
    } catch {
      /* ignore */
    }
  };

  const fetchMemory = async () => {
    try {
      const res = await fetch(`${API_BASE}/memory`);
      if (res.ok) setMemoryData(await res.json());
    } catch {
      /* ignore */
    }
  };

  const fetchRemoteStatus = async () => {
    try {
      const res = await fetch(`${API_BASE}/remote/status`);
      if (res.ok) setRemoteStatus(await res.json());
    } catch {
      /* ignore */
    }
  };

  const handleSetOwner = async () => {
    if (!tgId.trim()) return;
    setRemoteMsg("");
    try {
      const res = await fetch(`${API_BASE}/remote/set_owner`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ telegram_id: tgId.trim(), pin: tgPin.trim() || "1234" }),
      });
      const d = await res.json();
      setRemoteMsg(res.ok ? d.message : `Error: ${d.detail}`);
      if (res.ok) { setTgId(""); setTgPin(""); fetchRemoteStatus(); }
    } catch {
      setRemoteMsg("Backend connection error.");
    }
  };

  const handleToggleRemote = async (enable) => {
    setRemoteMsg(enable ? "Enabling…" : "Disabling…");
    try {
      const res = await fetch(`${API_BASE}/remote/toggle`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ enable }),
      });
      const d = await res.json();
      setRemoteMsg(res.ok ? d.message || "OK" : `Error: ${d.detail}`);
      fetchRemoteStatus();
    } catch {
      setRemoteMsg("Backend connection error.");
    }
  };

  const handleSetSecret = async (name, value, clearFn) => {
    if (!value.trim()) return;
    setSecretMsg("");
    try {
      const res = await fetch(`${API_BASE}/settings/set_secret`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name, value }),
      });
      const data = await res.json();
      if (res.ok) {
        setSecretMsg(data.message || "Saved.");
        clearFn("");
        fetchSecretStatus();
      } else {
        setSecretMsg(`Error: ${data.detail}`);
      }
    } catch {
      setSecretMsg("Backend connection error.");
    }
  };

  const fetchModels = async () => {
    try {
      const res = await fetch(`${API_BASE}/models/list`);
      if (res.ok) {
        const d = await res.json();
        setAvailableModels(d.models || []);
        if (d.active) setGgufPath(d.active);
      }
    } catch {
      /* ignore */
    }
  };

  const handleSetModel = async (path) => {
    const target = (path || "").trim();
    if (!target) return;
    setModelMsg("Switching model…");
    try {
      const res = await fetch(`${API_BASE}/settings/set_model`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ model_path: target }),
      });
      const data = await res.json();
      if (res.ok) {
        setModelMsg(data.message || "Model switched.");
        setGgufPath(data.model_path || target);
        fetchModels();
        fetchSystemStatus();
      } else {
        setModelMsg(`Error: ${data.detail}`);
      }
    } catch {
      setModelMsg("Backend connection error.");
    }
  };

  const startEdit = () => {
    const p = pendingAction?.params || {};
    setEditForm({
      to_email: p.to_email || p.recipient || "",
      subject: p.subject || "",
      body: p.body || "",
      text: p.text || "",
      contact_query: p.contact_query || "",
    });
    setEditMode(true);
  };

  const saveEdit = async () => {
    const tool = (pendingAction?.tool || "").toLowerCase();
    const updates = tool.startsWith("email.")
      ? { to_email: editForm.to_email, subject: editForm.subject, body: editForm.body }
      : { contact_query: editForm.contact_query, text: editForm.text };
    try {
      const res = await fetch(`${API_BASE}/pending/edit`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(updates),
      });
      if (res.ok) {
        setEditMode(false);
        fetchStatus();
      } else {
        const err = await res.json();
        pushError(`Edit error: ${err.detail}`);
      }
    } catch {
      pushError("Backend connection error.");
    }
  };

  const fetchStatus = async () => {
    try {
      const res = await fetch(`${API_BASE}/status`);
      setIsConnected(res.ok);
      if (res.ok) {
        const data = await res.json();
        if ((status === "running" || status === "waiting_approval") && data.status === "idle") {
          commitLogsToHistory(data.logs || []);
        }
        setStatus(data.status);
        setCurrentGoal(data.current_goal);
        setCurrentStep(data.current_step);
        setMaxSteps(data.max_steps);
        setLogs(data.logs || []);
        setPendingAction(data.pending_action);
        if (data.model_path && !ggufPath) setGgufPath(data.model_path);
        // Always refresh the screenshot when ENTERING approval so the click reticle
        // is drawn over the current screen, never a stale capture.
        const enteringApproval = data.status === "waiting_approval" && prevStatusRef.current !== "waiting_approval";
        if (data.status === "waiting_approval" && (enteringApproval || !screenshot)) fetchScreenshot();
        prevStatusRef.current = data.status;
        fetchEmailDraft();
        fetchMessageDraft();
      }
    } catch (e) {
      console.error(e);
      setIsConnected(false);
    }
  };

  useEffect(() => {
    setTimeout(() => {
      checkConnection();
      checkDownloadStatus();
      fetchEmailDraft();
      fetchMessageDraft();
    }, 0);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    let interval = null;
    if (status === "running" || status === "waiting_approval") {
      interval = setInterval(() => fetchStatus(), 1000);
    } else {
      // Idle: poll slowly so the connection indicator recovers if the backend
      // starts after the UI (or comes back after a restart).
      setTimeout(() => fetchStatus(), 0);
      interval = setInterval(() => fetchStatus(), 5000);
    }
    return () => clearInterval(interval);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [status]);

  useEffect(() => {
    let interval = null;
    if (status === "running") {
      interval = setInterval(() => fetchScreenshot(), 2500);
    }
    return () => clearInterval(interval);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [status]);

  useEffect(() => {
    if (chatEndRef.current) {
      chatEndRef.current.scrollIntoView({ behavior: "smooth" });
    }
  }, [chatHistory, logs, isSending, streamingReply]);

  useEffect(() => {
    if (activeTab === "screen") setTimeout(() => fetchScreenshot(), 0);
    if (activeTab === "uia") setTimeout(() => fetchUiaWindows(), 0);
    if (activeTab === "memory") setTimeout(() => fetchMemory(), 0);
    if (activeTab === "settings") setTimeout(() => { fetchSystemStatus(); fetchSecretStatus(); fetchModels(); fetchRemoteStatus(); }, 0);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeTab]);

  const busy = status === "running" || status === "waiting_approval";

  const handleSendChat = async (e) => {
    e.preventDefault();
    if (!chatInput.trim() || isSending || busy) return;

    const userMessageText = chatInput;
    setChatInput("");
    setIsSending(true);
    setStreamingReply("");
    setChatHistory((prev) => [
      ...prev,
      { sender: "user", text: userMessageText, type: "user", timestamp: Date.now() / 1000 },
    ]);

    const commitReply = (text) => {
      if (text) {
        setChatHistory((prev) => [
          ...prev,
          { sender: "assistant", text, type: "assistant_chat", timestamp: Date.now() / 1000 },
        ]);
      }
      setStreamingReply(null);
    };

    try {
      const res = await fetch(`${API_BASE}/chat/stream`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: userMessageText, ai_mode: aiMode, safety_confirmation: permissionMode === "ask" }),
      });
      if (!res.ok || !res.body) {
        let detail = "Backend server connection error";
        try { detail = (await res.json()).detail || detail; } catch { /* ignore */ }
        pushError(`Chat error: ${detail}`);
        setStreamingReply(null);
        return;
      }

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      let full = "";
      let committed = false;

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const parts = buffer.split("\n\n");
        buffer = parts.pop();
        for (const part of parts) {
          const line = part.trim();
          if (!line.startsWith("data:")) continue;
          let obj;
          try { obj = JSON.parse(line.slice(5).trim()); } catch { continue; }
          if (obj.type === "chunk") {
            full += obj.delta;
            setStreamingReply(full);
          } else if (obj.type === "control") {
            committed = true;
            setStreamingReply(null);
            setScreenshot("");
            fetchStatus();
          } else if (obj.type === "done") {
            committed = true;
            commitReply(obj.message || full);
          } else if (obj.type === "error") {
            committed = true;
            commitReply(`⚠️ ${obj.message}`);
          }
        }
      }
      // Safety net: stream ended without an explicit done/control event.
      if (!committed) commitReply(full);
    } catch {
      pushError("Connection to the backend server failed");
      setStreamingReply(null);
    } finally {
      setIsSending(false);
    }
  };

  const handleStop = async () => {
    try {
      const res = await fetch(`${API_BASE}/stop`, { method: "POST" });
      if (res.ok) fetchStatus();
    } catch (e) {
      console.error(e);
    }
  };

  const handleApprove = async () => {
    try {
      const res = await fetch(`${API_BASE}/approve`, { method: "POST" });
      if (res.ok) {
        setPendingAction(null);
        fetchStatus();
      }
    } catch (e) {
      console.error(e);
    }
  };

  const handleReject = async (reason = "User disapproved") => {
    try {
      const res = await fetch(`${API_BASE}/reject`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ reason }),
      });
      if (res.ok) {
        setPendingAction(null);
        fetchStatus();
      }
    } catch (e) {
      console.error(e);
    }
  };

  const getReticleStyle = () => {
    if (!pendingAction || pendingAction.tool !== "click") return { display: "none" };
    const { x, y } = pendingAction.params || {};
    if (x === undefined || y === undefined) return { display: "none" };
    return { left: `${(x / screenWidth) * 100}%`, top: `${(y / screenHeight) * 100}%` };
  };

  const getDisplayMessages = () => {
    const displayList = [...chatHistory];
    if (busy) {
      logs.forEach((l) => {
        displayList.push({
          sender: l.type === "reasoning" || l.type === "success" || l.type === "assistant_chat" ? "assistant" : "system",
          text: l.message,
          type: l.type,
          actionData: l.action_data,
          status: l.status,
          timestamp: l.timestamp,
        });
      });
    }
    return displayList;
  };

  const riskColor = (level) => {
    if (level === "low") return "var(--ok)";
    if (level === "high" || level === "blocked") return "var(--danger)";
    if (level === "remote") return "var(--remote)";
    return "var(--warn)";
  };
  const riskSoft = (level) => {
    if (level === "low") return "var(--ok-soft)";
    if (level === "high" || level === "blocked") return "var(--danger-soft)";
    if (level === "remote") return "var(--remote-soft)";
    return "var(--warn-soft)";
  };

  const renderActionCard = (data) => {
    const tool = data.tool || data.action || "";
    const params = data.params || {};
    const level = data.risk_level || "medium";
    const preview = data.preview || {};
    return (
      <div className="action-card" style={{ borderLeftColor: riskColor(level) }} title="Action the agent proposes to run">
        <div className="ac-head">
          <span className="ac-tool">⚡ {tool}</span>
          <span className="risk-chip" style={{ color: riskColor(level), background: riskSoft(level) }} title="Risk level of this action">
            {level} risk
          </span>
        </div>
        {preview.title && <div className="ac-title">{preview.title}</div>}
        {preview.summary && <div className="ac-summary">{preview.summary}</div>}
        <div className="ac-kv">
          {(tool === "click" || tool === "click_mouse") && `Coords: X=${params.x}, Y=${params.y}`}
          {tool === "click_uia" && `UIA: window="${params.window_title_re}", id="${params.auto_id || ""}", name="${params.name || ""}"`}
          {tool === "type" && `Type: "${params.text}"`}
          {tool === "open" && `Open: "${params.app_name}"`}
          {tool === "press" && `Key: "${params.key}"`}
          {tool === "hotkey" && `Combo: ${params.keys?.join(" + ")}`}
          {tool === "learn" && `Learn: "${params.key}" → "${params.value}"`}
          {tool.startsWith("email.") && `Email → ${params.to_email || params.recipient || ""} ${params.subject ? `· ${params.subject}` : ""}`}
          {tool.startsWith("message.") && `Message → ${params.contact_query || ""}`}
          {tool.startsWith("file.") && `File: ${params.filepath || params.filename || params.src || params.dirpath || ""}`}
          {tool.startsWith("document.") && `Document: ${params.filepath || params.title || ""}`}
        </div>
        {data.rollback_hint && <div className="ac-rollback">↩ Rollback: {data.rollback_hint}</div>}
        {data.action_id && <div className="ac-id">{data.action_id}</div>}
      </div>
    );
  };

  const renderMessage = (msg, idx) => {
    if (msg.type === "system") {
      return (
        <div key={idx} className="sys-line">
          {msg.text}
        </div>
      );
    }
    const isUser = msg.sender === "user";
    let bubbleVariant = "";
    if (msg.type === "reasoning") bubbleVariant = "reasoning";
    else if (msg.type === "success") bubbleVariant = "success";
    else if (msg.type === "error") bubbleVariant = "error";

    return (
      <div key={idx} className={`msg ${isUser ? "user" : "assistant"}`}>
        <div className={`avatar ${isUser ? "you" : "ai"}`}>{isUser ? "🧑" : <Cpu size={16} />}</div>
        <div className="msg-col">
          <div className={`bubble ${bubbleVariant}`}>
            <div>{msg.text}</div>
            {msg.type === "action" && msg.actionData && renderActionCard(msg.actionData)}
            {msg.type === "action" && msg.status === "pending" && status === "waiting_approval" && (
              <div className="approve-box">
                <span className="approve-warn">⚠️ This action needs your approval</span>

                {pendingAction && EDITABLE_TOOLS.has((pendingAction.tool || "").toLowerCase()) &&
                  (editMode ? (
                    <div className="edit-form">
                      {(pendingAction.tool || "").startsWith("email.") ? (
                        <>
                          <label>Recipient</label>
                          <input value={editForm.to_email} onChange={(e) => setEditForm({ ...editForm, to_email: e.target.value })} title="Email recipient" />
                          <label>Subject</label>
                          <input value={editForm.subject} onChange={(e) => setEditForm({ ...editForm, subject: e.target.value })} title="Email subject" />
                          <label>Body</label>
                          <textarea rows={5} value={editForm.body} onChange={(e) => setEditForm({ ...editForm, body: e.target.value })} title="Email body" />
                        </>
                      ) : (
                        <>
                          <label>Contact</label>
                          <input value={editForm.contact_query} onChange={(e) => setEditForm({ ...editForm, contact_query: e.target.value })} title="Contact name or keyword" />
                          <label>Message</label>
                          <textarea rows={5} value={editForm.text} onChange={(e) => setEditForm({ ...editForm, text: e.target.value })} title="Message body" />
                        </>
                      )}
                      <div className="approve-row">
                        <button className="btn btn-approve grow" onClick={saveEdit} title="Save your changes to this action">💾 Save changes</button>
                        <button className="btn btn-reject grow" onClick={() => setEditMode(false)} title="Discard changes">Cancel</button>
                      </div>
                    </div>
                  ) : (
                    <button className="mini-btn" style={{ marginBottom: 8, alignSelf: "flex-start" }} onClick={startEdit} title="Edit the content before approving">
                      ✏️ Edit before approving
                    </button>
                  ))}

                <div className="approve-row">
                  <button className="btn btn-approve grow" onClick={handleApprove} title="Approve and run this action">
                    <Check size={14} /> Approve
                  </button>
                  <button className="btn btn-reject grow" onClick={() => handleReject("User disapproved step.")} title="Reject this action and pause the task">
                    <X size={14} /> Reject
                  </button>
                </div>
              </div>
            )}
          </div>
          <span className="msg-time">{new Date(msg.timestamp * 1000).toLocaleTimeString()}</span>
        </div>
      </div>
    );
  };

  const hasDraft = emailDraft || messageDraft;

  return (
    <div className="app">
      {/* Top bar */}
      <header className="topbar glass">
        <div className="brand">
          <div className="brand-logo">
            <Cpu size={22} />
          </div>
          <div>
            <div className="brand-title">CONTROLPC</div>
            <div className="brand-sub">
              <span className={`conn-dot ${isConnected ? "on" : "off"}`} />
              {isConnected ? "Connected" : "Disconnected"} · Local OS Agent
            </div>
          </div>
        </div>

        <div className="topbar-right">
          <div className="engine-pill" title="Inference engine in use">
            {aiMode === "gemma4" ? (
              <>
                <span className="gpu">● GPU</span> Local LLM
              </>
            ) : (
              <>● Simulation</>
            )}
          </div>
          <div className={`agent-pill st-${status}`} title="Current agent status">
            <span className={`dot ${status === "running" ? "pulse" : ""}`} />
            {STATUS_LABEL[status] || status}
          </div>
        </div>
      </header>

      {/* Main layout */}
      <div className="layout">
        {/* Chat */}
        <section className="chat-panel glass">
          <div className="chat-head">
            <Terminal size={15} /> Activity &amp; control
            {currentGoal && <span className="task" title={currentGoal}>— “{currentGoal}”</span>}
            {busy && <span className="step-chip">{currentStep}/{maxSteps} steps</span>}
          </div>

          <div className="chat-scroll">
            {getDisplayMessages().map((msg, idx) => renderMessage(msg, idx))}
            {isSending && !streamingReply && (
              <div className="msg assistant">
                <div className="avatar ai">
                  <Cpu size={16} />
                </div>
                <div className="msg-col">
                  <div className="bubble pulse">
                    {aiMode === "gemma4" ? "Thinking on the GPU…" : "Processing…"}
                  </div>
                </div>
              </div>
            )}
            {streamingReply && (
              <div className="msg assistant">
                <div className="avatar ai">
                  <Cpu size={16} />
                </div>
                <div className="msg-col">
                  <div className="bubble">
                    {streamingReply}
                    <span className="stream-cursor" />
                  </div>
                </div>
              </div>
            )}
            <div ref={chatEndRef} />
          </div>

          {!busy && !isSending && (
            <div className="quick-actions">
              {QUICK_ACTIONS.map((q) => (
                <button
                  key={q.label}
                  type="button"
                  className="chip"
                  title={q.hint}
                  onClick={() => {
                    setChatInput(q.text);
                    inputRef.current?.focus();
                  }}
                >
                  {q.label}
                </button>
              ))}
            </div>
          )}

          <form className="composer" onSubmit={handleSendChat}>
            <input
              ref={inputRef}
              type="text"
              placeholder={busy ? "The AI is working on a task in the background…" : "Type a message or a control command…"}
              value={chatInput}
              onChange={(e) => setChatInput(e.target.value)}
              disabled={isSending || busy}
              title="Type a question or a command (e.g. 'open notepad')"
            />
            {busy ? (
              <button type="button" className="icon-btn stop" onClick={handleStop} title="Emergency stop the running task">
                <Square size={17} />
              </button>
            ) : (
              <button type="submit" className="icon-btn" disabled={!chatInput.trim() || isSending || !isConnected} title="Send message">
                <Send size={17} />
              </button>
            )}
          </form>
        </section>

        {/* Sidebar */}
        <aside className="side glass">
          <div className="tabs">
            <button className={`tab ${activeTab === "screen" ? "active" : ""}`} onClick={() => setActiveTab("screen")} title="Live screen preview of the PC">
              <Tv size={14} /> Screen
            </button>
            <button className={`tab ${activeTab === "preview" ? "active" : ""}`} onClick={() => setActiveTab("preview")} title="Pending email / message drafts">
              ✉️ Drafts {hasDraft && <span className="tab-badge" />}
            </button>
            <button className={`tab ${activeTab === "uia" ? "active" : ""}`} onClick={() => setActiveTab("uia")} title="Inspect window controls via Windows UI Automation">
              🔍 UIA
            </button>
            <button className={`tab ${activeTab === "memory" ? "active" : ""}`} onClick={() => setActiveTab("memory")} title="Long-term memory the agent has learned">
              🧠 Memory
            </button>
            <button className={`tab ${activeTab === "settings" ? "active" : ""}`} onClick={() => setActiveTab("settings")} title="Engine, model, approval mode, security and remote settings">
              <Settings size={14} /> Settings
            </button>
          </div>

          <div className="tab-body">
            {/* Screen */}
            {activeTab === "screen" && (
              <>
                <div className="tab-title" style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                  <span><Tv size={14} /> Screen monitor</span>
                  <button className="mini-btn" onClick={fetchScreenshot} disabled={isRefreshingScreen} title="Capture the screen right now">
                    {isRefreshingScreen ? "Capturing…" : "📸 Capture"}
                  </button>
                </div>
                <div className="screen-wrap">
                  {screenshot ? (
                    <>
                      <img src={screenshot} alt="PC screen" className="screen-img" />
                      {status === "waiting_approval" && pendingAction?.tool === "click" && (
                        <div className="reticle" style={getReticleStyle()} title="Proposed click location" />
                      )}
                    </>
                  ) : (
                    <div className="empty">
                      <Tv size={34} />
                      <span>No screenshot yet — press Capture, or it refreshes automatically while the agent works.</span>
                    </div>
                  )}
                </div>
              </>
            )}

            {/* Preview / drafts */}
            {activeTab === "preview" && (
              <>
                <div className="tab-title">✉️ Active drafts</div>
                {!hasDraft && (
                  <div className="empty">
                    <span>No drafts yet.</span>
                    <span style={{ fontSize: 11 }}>
                      When the agent drafts something (email.create_draft / message.create_draft), it appears here.
                    </span>
                  </div>
                )}

                {emailDraft && (
                  <div className="draft-card">
                    <div className="draft-tag">✉️ Email draft</div>
                    <div className="draft-row">
                      <span className="draft-label">To</span>
                      <span className="draft-value">{emailDraft.to}</span>
                    </div>
                    <div className="draft-row">
                      <span className="draft-label">Subject</span>
                      <span className="draft-value">{emailDraft.subject}</span>
                    </div>
                    <div className="draft-row">
                      <span className="draft-label">Body</span>
                      <div className="draft-body">{emailDraft.body}</div>
                    </div>
                    {emailDraft.attachments?.length > 0 && (
                      <div className="draft-row">
                        <span className="draft-label">Attachments ({emailDraft.attachments.length})</span>
                        {emailDraft.attachments.map((f, i) => (
                          <div key={i} className="attach">📎 {f.split("\\").pop() || f.split("/").pop()}</div>
                        ))}
                      </div>
                    )}
                  </div>
                )}

                {messageDraft && (
                  <div className="draft-card">
                    <div className="draft-tag">💬 Message draft</div>
                    <div className="draft-row">
                      <span className="draft-label">Contact</span>
                      <span className="draft-value">{messageDraft.contact_name}</span>
                    </div>
                    {messageDraft.phone && (
                      <div className="draft-row">
                        <span className="draft-label">Phone</span>
                        <span className="draft-value">{messageDraft.phone}</span>
                      </div>
                    )}
                    {messageDraft.email && (
                      <div className="draft-row">
                        <span className="draft-label">Email</span>
                        <span className="draft-value">{messageDraft.email}</span>
                      </div>
                    )}
                    <div className="draft-row">
                      <span className="draft-label">Message</span>
                      <div className="draft-body">{messageDraft.text}</div>
                    </div>
                  </div>
                )}
              </>
            )}

            {/* UIA inspector */}
            {activeTab === "uia" && (
              <>
                <div className="tab-title">🔍 UIA Inspector</div>
                <button className="mini-btn" onClick={fetchUiaWindows} style={{ alignSelf: "flex-start" }} title="Refresh the list of open windows">
                  🔄 Reload windows
                </button>
                <div>
                  <span className="field-label">Open windows ({uiaWindows.length})</span>
                  <select
                    className="uia-select"
                    value={selectedWindow}
                    title="Pick a window to inspect its UI Automation tree"
                    onChange={(e) => {
                      setSelectedWindow(e.target.value);
                      fetchUiaTree(e.target.value);
                    }}
                  >
                    <option value="">— Select a window to inspect —</option>
                    {uiaWindows.map((win, idx) => (
                      <option key={idx} value={win.title}>
                        {win.title} (PID: {win.pid})
                      </option>
                    ))}
                  </select>
                </div>

                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                  <span className="field-label" style={{ margin: 0 }}>
                    Control tree ({uiaTree.length})
                  </span>
                  {selectedWindow && (
                    <button className="mini-btn" onClick={() => fetchUiaTree(selectedWindow)} disabled={isLoadingUia} title="Rescan the selected window's controls">
                      {isLoadingUia ? "Scanning…" : "Rescan"}
                    </button>
                  )}
                </div>

                {isLoadingUia ? (
                  <div className="empty">Scanning the UIA tree…</div>
                ) : uiaTree.length > 0 ? (
                  <div className="uia-list">
                    {uiaTree.map((ctrl, idx) => (
                      <div key={idx} className="uia-item">
                        <div className="uia-top">
                          <span className="uia-type">[{ctrl.control_type}]</span>
                          <span className="uia-rect">{ctrl.rectangle}</span>
                        </div>
                        {ctrl.name && (
                          <div>
                            <span style={{ color: "var(--text-faint)" }}>Name:</span> <strong>"{ctrl.name}"</strong>
                          </div>
                        )}
                        {ctrl.auto_id && (
                          <div>
                            <span style={{ color: "var(--text-faint)" }}>AutoId:</span> <code>{ctrl.auto_id}</code>
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                ) : (
                  <div className="empty">
                    {selectedWindow ? "No UIA elements found." : "Select a window to view its UIA tree."}
                  </div>
                )}
              </>
            )}

            {/* Memory */}
            {activeTab === "memory" && (
              <>
                <div className="tab-title">🧠 Long-term memory</div>
                {!memoryData || (!memoryData.memory_md && !memoryData.journal_today) ? (
                  <div className="empty">
                    <span>No memories yet.</span>
                    <span style={{ fontSize: 11 }}>
                      After each completed task, the agent records it here (MEMORY.md + a daily journal) and loads it back next time.
                    </span>
                  </div>
                ) : (
                  <>
                    {memoryData.memory_md && <pre className="memory-pre">{memoryData.memory_md}</pre>}
                    {memoryData.journal_today && (
                      <>
                        <span className="field-label" style={{ marginTop: 8 }}>Today's journal</span>
                        <pre className="memory-pre">{memoryData.journal_today}</pre>
                      </>
                    )}
                    <button className="mini-btn" style={{ alignSelf: "flex-start" }} onClick={fetchMemory} title="Reload memory from disk">🔄 Reload</button>
                  </>
                )}
              </>
            )}

            {/* Settings */}
            {activeTab === "settings" && (
              <>
                <div className="tab-title">
                  <Settings size={14} /> Settings
                </div>

                {systemStatus && (
                  <div className="field">
                    <label>System status</label>
                    <div className="status-list">
                      <div className="status-row" title="Whether the GGUF model file was found"><span>{systemStatus.model_found ? "✅" : "⛔"}</span> GGUF model {systemStatus.model_found ? "" : "(not found)"}</div>
                      <div className="status-row" title="Whether the GPU llama-server binary was found"><span>{systemStatus.server_found ? "✅" : "⛔"}</span> llama-server GPU {systemStatus.server_found ? "" : "(not found)"}</div>
                      <div className="status-row" title="Windows Credential Manager for storing secrets"><span>{systemStatus.keyring_available ? "✅" : "⚠️"}</span> Credential Manager {systemStatus.keyring_available ? "ready" : "unavailable"}</div>
                      <div className="status-row" title="Email sending mode (mock = drafts to disk, live = real SMTP)"><span>{systemStatus.email_mode === "live" ? (systemStatus.smtp_password_set ? "✅" : "⚠️") : "🧪"}</span> Email: {systemStatus.email_mode}{systemStatus.email_mode === "live" && !systemStatus.smtp_password_set ? " (password missing)" : ""}</div>
                      <div className="status-row" title="Telegram remote control gateway"><span>{systemStatus.remote_gateway_enabled ? "🟢" : "⚪"}</span> Remote gateway: {systemStatus.remote_gateway_enabled ? "ON" : "off"}</div>
                      <div className="status-row" title="Coordinate clicking (disabled by default for safety)"><span>{systemStatus.coordinate_click_enabled ? "🟠" : "⚪"}</span> Coordinate click: {systemStatus.coordinate_click_enabled ? "on" : "off"}</div>
                      <div className="status-row" title="How strictly the agent asks before acting"><span>{systemStatus.permission_mode === "bypass" ? "⚡" : systemStatus.permission_mode === "smart" ? "⚖️" : "🛡️"}</span> Approval: {systemStatus.permission_mode === "bypass" ? "Bypass (no prompts)" : systemStatus.permission_mode === "smart" ? "Risky only" : "Ask everything"}</div>
                    </div>
                  </div>
                )}

                <div className="field">
                  <label>Engine</label>
                  <select value={aiMode} onChange={(e) => setAiMode(e.target.value)} disabled={busy} title="GPU runs the real local LLM; Simulation uses a canned decision tree (dev only)">
                    <option value="gemma4">GPU (llama-server)</option>
                    <option value="mock">Simulation</option>
                  </select>
                </div>

                {aiMode === "gemma4" && (
                  <div className="field">
                    <label>Model</label>
                    <select
                      value={availableModels.find((m) => m.active)?.path || ggufPath || ""}
                      onChange={(e) => handleSetModel(e.target.value)}
                      disabled={busy}
                      title="Pick which GGUF model the GPU server loads (from the models/ folder)"
                    >
                      {availableModels.length === 0 && <option value="">(no models found in /models)</option>}
                      {availableModels.map((m) => (
                        <option key={m.path} value={m.path}>{m.name}</option>
                      ))}
                    </select>
                    {modelMsg && <span className="hint">{modelMsg}</span>}
                  </div>
                )}

                <div className="field">
                  <label>Approval mode</label>
                  <select value={permissionMode} onChange={(e) => handleSetPermissionMode(e.target.value)} disabled={busy} title="Controls how often the agent asks before performing an action">
                    <option value="ask">🛡️ Ask before every action (safe)</option>
                    <option value="smart">⚖️ Ask only for risky actions</option>
                    <option value="bypass">⚡ Bypass approval</option>
                  </select>
                  {permModeMsg && <span className="hint">{permModeMsg}</span>}
                  {permissionMode === "bypass" && (
                    <span className="hint" style={{ color: "var(--warn)" }}>
                      ⚠️ Bypass: the agent runs even risky actions without asking. Use only if you fully trust it.
                    </span>
                  )}
                </div>

                <div className="field">
                  <label>🔐 Security (Windows Credential Manager)</label>
                  {secretStatus && !secretStatus.keyring_available && (
                    <span className="hint" style={{ color: "var(--warn)" }}>
                      Secure secret store unavailable — the system will fall back to environment variables.
                    </span>
                  )}
                  <div className="secret-row">
                    <input
                      type="password"
                      placeholder={secretStatus?.secrets?.smtp_password ? "SMTP password: set ✅ (type to change)" : "SMTP password / App Password"}
                      value={smtpPwd}
                      onChange={(e) => setSmtpPwd(e.target.value)}
                      title="SMTP password or app password, stored in Windows Credential Manager"
                    />
                    <button className="mini-btn" onClick={() => handleSetSecret("smtp_password", smtpPwd, setSmtpPwd)} title="Save the SMTP password securely">Save</button>
                  </div>
                  <div className="secret-row">
                    <input
                      type="password"
                      placeholder={secretStatus?.secrets?.telegram_token ? "Telegram token: set ✅ (type to change)" : "Telegram Bot Token"}
                      value={tgToken}
                      onChange={(e) => setTgToken(e.target.value)}
                      title="Telegram bot token from @BotFather, stored securely"
                    />
                    <button className="mini-btn" onClick={() => handleSetSecret("telegram_token", tgToken, setTgToken)} title="Save the Telegram bot token securely">Save</button>
                  </div>
                  {secretMsg && <span className="hint">{secretMsg}</span>}
                </div>

                <div className="field">
                  <label>📱 Phone control (Telegram — free)</label>
                  <div className="status-list">
                    <div className="status-row"><span>{remoteStatus?.token_set ? "✅" : "⚪"}</span> Bot token {remoteStatus?.token_set ? "is set" : "— enter it in Security above"}</div>
                    <div className="status-row"><span>{remoteStatus?.running ? "🟢" : "⚪"}</span> Status: {remoteStatus?.running ? `running${remoteStatus?.bot_username ? " (@" + remoteStatus.bot_username + ")" : ""}` : "off"}</div>
                    <div className="status-row"><span>{remoteStatus?.owners?.length ? "✅" : "⚪"}</span> Authorized: {remoteStatus?.owners?.length ? remoteStatus.owners.map((o) => o.id).join(", ") : "(none yet)"}</div>
                  </div>
                  <div className="secret-row">
                    <input type="text" placeholder="Your Telegram ID (from @userinfobot)" value={tgId} onChange={(e) => setTgId(e.target.value)} title="Your numeric Telegram ID, obtained from @userinfobot" />
                    <input type="text" placeholder="PIN" value={tgPin} onChange={(e) => setTgPin(e.target.value)} style={{ maxWidth: 70 }} title="PIN required to approve high-risk actions from your phone" />
                    <button className="mini-btn" onClick={handleSetOwner} disabled={!remoteStatus?.token_set} title={remoteStatus?.token_set ? "Authorize this Telegram ID to control the PC" : "Set the Telegram bot token in Security first"}>Grant access</button>
                  </div>
                  <div className="approve-row" style={{ marginTop: 4 }}>
                    {remoteStatus?.enabled ? (
                      <button className="btn btn-reject grow" onClick={() => handleToggleRemote(false)} title="Stop the Telegram remote gateway">⏹ Turn off remote</button>
                    ) : (
                      <button className="btn btn-approve grow" onClick={() => handleToggleRemote(true)} disabled={!remoteStatus?.token_set} title={remoteStatus?.token_set ? "Start the Telegram remote gateway (free, no public IP)" : "Set the Telegram bot token in Security first"}>▶ Enable phone control</button>
                    )}
                  </div>
                  {remoteMsg && <span className="hint">{remoteMsg}</span>}
                  <span className="hint">Zalo OA / WhatsApp Business — roadmap (requires a business API account).</span>
                </div>
              </>
            )}
          </div>
        </aside>
      </div>
    </div>
  );
}

export default App;
