import { useState, useEffect, useRef } from "react";
import { 
  Square, Settings, Terminal, Tv, Cpu, 
  Check, X, Send, Activity 
} from "lucide-react";
import "./App.css";

const API_BASE = "http://localhost:8000/api";

function App() {
  const [chatInput, setChatInput] = useState("");
  const [chatHistory, setChatHistory] = useState([
    {
      sender: "assistant",
      text: "Xin chào! Tôi là CONTROLPC, trợ lý ảo cục bộ điều khiển máy tính. Tôi được thiết kế để hạn chế click tọa độ ảo, ưu tiên các hành động an toàn như CLI/Path execution, phím tắt Hotkeys, và Windows UI Automation (UIA). Hãy gửi câu lệnh để bắt đầu!",
      type: "assistant_chat",
      timestamp: 1781190000
    }
  ]);
  const [isSending, setIsSending] = useState(false);

  const [status, setStatus] = useState("idle");
  const [currentGoal, setCurrentGoal] = useState("");
  const [currentStep, setCurrentStep] = useState(0);
  const [maxSteps, setMaxSteps] = useState(12);
  const [logs, setLogs] = useState([]);
  const [pendingAction, setPendingAction] = useState(null);
  
  const [aiMode, setAiMode] = useState("mock");
  const [ggufPath, setGgufPath] = useState("");
  const [safetyConfirmation, setSafetyConfirmation] = useState(true);
  
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

  const chatEndRef = useRef(null);

  const checkConnection = async () => {
    try {
      const res = await fetch(`${API_BASE}/status`);
      if (res.ok) {
        setIsConnected(true);
      } else {
        setIsConnected(false);
      }
    } catch {
      setIsConnected(false);
    }
  };

  const checkDownloadStatus = async () => {
    try {
      const res = await fetch(`${API_BASE}/download_status`);
      if (res.ok) {
        const data = await res.json();
        if (data.exists && !ggufPath) {
          setGgufPath(data.model_path);
        }
      }
    } catch (e) {
      console.error(e);
    }
  };

  const commitLogsToHistory = (taskLogs) => {
    if (!taskLogs || taskLogs.length === 0) return;
    const logMessages = taskLogs.map(l => ({
      sender: l.type === "reasoning" || l.type === "success" || l.type === "assistant_chat" ? "assistant" : "system",
      text: l.message,
      type: l.type,
      actionData: l.action_data,
      status: l.status,
      timestamp: l.timestamp
    }));
    setChatHistory(prev => [...prev, ...logMessages]);
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
        if (data.exists) {
          setEmailDraft(data.draft);
        } else {
          setEmailDraft(null);
        }
      }
    } catch {
      // ignore
    }
  };

  const fetchMessageDraft = async () => {
    try {
      const res = await fetch(`${API_BASE}/message_draft`);
      if (res.ok) {
        const data = await res.json();
        if (data.exists) {
          setMessageDraft(data.draft);
        } else {
          setMessageDraft(null);
        }
      }
    } catch {
      // ignore
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

  const fetchStatus = async () => {
    try {
      const res = await fetch(`${API_BASE}/status`);
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
        
        if (data.status === "waiting_approval" && !screenshot) {
          fetchScreenshot();
        }
        fetchEmailDraft();
        fetchMessageDraft();
      }
    } catch (e) {
      console.error(e);
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
      interval = setInterval(() => {
        fetchStatus();
      }, 1000);
    } else {
      setTimeout(() => {
        fetchStatus();
      }, 0);
    }
    return () => clearInterval(interval);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [status]);

  useEffect(() => {
    let interval = null;
    if (status === "running") {
      interval = setInterval(() => {
        fetchScreenshot();
      }, 2500);
    }
    return () => clearInterval(interval);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [status]);

  useEffect(() => {
    if (chatEndRef.current) {
      chatEndRef.current.scrollIntoView({ behavior: "smooth" });
    }
  }, [chatHistory, logs]);

  useEffect(() => {
    if (activeTab === "uia") {
      setTimeout(() => {
        fetchUiaWindows();
      }, 0);
    }
  }, [activeTab]);

  const handleSendChat = async (e) => {
    e.preventDefault();
    if (!chatInput.trim() || isSending || status === "running" || status === "waiting_approval") return;

    const userMessageText = chatInput;
    setChatInput("");
    setIsSending(true);

    const userMsg = {
      sender: "user",
      text: userMessageText,
      type: "user",
      timestamp: Date.now() / 1000
    };
    setChatHistory(prev => [...prev, userMsg]);

    try {
      const res = await fetch(`${API_BASE}/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          message: userMessageText,
          ai_mode: aiMode,
          safety_confirmation: safetyConfirmation
        })
      });
      if (res.ok) {
        const data = await res.json();
        if (data.type === "chat") {
          setChatHistory(prev => [...prev, {
            sender: "assistant",
            text: data.message,
            type: "assistant_chat",
            timestamp: Date.now() / 1000
          }]);
        } else {
          setScreenshot(""); 
          fetchStatus();
        }
      } else {
        const err = await res.json();
        alert(`Lỗi chat: ${err.detail}`);
      }
    } catch {
      alert("Lỗi kết nối tới Server Backend");
    } finally {
      setIsSending(false);
    }
  };

  const handleStop = async () => {
    try {
      const res = await fetch(`${API_BASE}/stop`, { method: "POST" });
      if (res.ok) {
        fetchStatus();
      }
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
        body: JSON.stringify({ reason })
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
    if (!pendingAction || pendingAction.action !== "click") return { display: "none" };
    const { x, y } = pendingAction.params;
    if (x === undefined || y === undefined) return { display: "none" };

    const leftPercent = (x / screenWidth) * 100;
    const topPercent = (y / screenHeight) * 100;

    return {
      left: `${leftPercent}%`,
      top: `${topPercent}%`,
    };
  };

  const getDisplayMessages = () => {
    const displayList = [...chatHistory];
    
    if (status === "running" || status === "waiting_approval") {
      logs.forEach(l => {
        displayList.push({
          sender: l.type === "reasoning" || l.type === "success" || l.type === "assistant_chat" ? "assistant" : "system",
          text: l.message,
          type: l.type,
          actionData: l.action_data,
          status: l.status,
          timestamp: l.timestamp
        });
      });
    }
    
    return displayList;
  };

  return (
    <div className="app-container">
      <header className="app-header glass">
        <div className="brand">
          <Cpu className="glow-primary" size={30} style={{ color: "hsl(var(--primary))" }} />
          <div>
            <h1>CONTROLPC Shell</h1>
            <span style={{ fontSize: "11px", color: isConnected ? "hsl(var(--accent-green))" : "hsl(var(--accent-red))" }}>
              ● Local OS Agent - {isConnected ? "CONNECTED" : "DISCONNECTED"}
            </span>
          </div>
        </div>

        <div className="flex items-center gap-4">
          <div className={`status-badge status-${status}`}>
            <Activity size={14} className={status === "running" ? "pulse-primary" : ""} />
            {status === "idle" && "Sẵn sàng"}
            {status === "running" && "Đang xử lý"}
            {status === "waiting_approval" && "Chờ phê duyệt"}
            {status === "finished" && "Hoàn thành"}
            {status === "error" && "Gặp lỗi"}
          </div>
        </div>
      </header>

      <div className="dashboard-grid">
        <section className="panel glass chat-window">
          <div className="panel-title">
            <Terminal size={16} /> Lịch sử hoạt động và điều khiển {currentGoal ? `- Tác vụ: "${currentGoal}" (${currentStep}/${maxSteps} bước)` : ""}
          </div>
          
          <div className="chat-history">
            {getDisplayMessages().map((msg, idx) => {
              const isSystem = msg.type === "system";
              
              if (isSystem) {
                return (
                  <div key={idx} className="message-system animate-slide-up">
                    {msg.text}
                  </div>
                );
              }

              return (
                <div key={idx} className={`message-container ${msg.sender} animate-slide-up`}>
                  <div className={`message-bubble message-${msg.type}`}>
                    <div style={{ whiteSpace: "pre-line" }}>{msg.text}</div>
                    
                    {msg.type === "action" && msg.actionData && (() => {
                      const tool = msg.actionData.tool || msg.actionData.action || "";
                      const params = msg.actionData.params || {};
                      const riskLevel = msg.actionData.risk_level || "medium";
                      const preview = msg.actionData.preview || {};
                      const rollback = msg.actionData.rollback_hint;
                      const actionId = msg.actionData.action_id;

                      let riskColor = "var(--warning)";
                      if (riskLevel === "low") riskColor = "var(--success)";
                      if (riskLevel === "high") riskColor = "var(--danger)";
                      if (riskLevel === "blocked") riskColor = "var(--danger)";
                      if (riskLevel === "remote") riskColor = "var(--remote)";

                      return (
                        <div className="action-params-box" style={{ borderLeft: `4px solid ${riskColor}`, paddingLeft: '10px' }}>
                          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '6px' }}>
                            <strong style={{ fontSize: '13px', textTransform: 'uppercase' }}>Hành động: {tool}</strong>
                            <span className="status-badge" style={{ 
                              background: riskLevel === 'low' ? 'var(--success-soft)' : riskLevel === 'high' ? 'var(--danger-soft)' : 'var(--warning-soft)',
                              color: riskColor,
                              fontSize: '10px',
                              padding: '2px 8px',
                              textTransform: 'uppercase',
                              fontWeight: 'bold',
                              border: 'none'
                            }}>{riskLevel} risk</span>
                          </div>
                          
                          {preview.title && <div style={{ fontWeight: '600', fontSize: '12.5px', marginBottom: '2px' }}>{preview.title}</div>}
                          {preview.summary && <div style={{ color: 'var(--text-muted)', marginBottom: '6px', fontSize: '12px' }}>{preview.summary}</div>}
                          
                          <div style={{ fontSize: '11.5px', marginTop: '6px', borderTop: '1px solid var(--border)', paddingTop: '6px' }}>
                            {(tool === "click" || tool === "click_mouse") && `Tọa độ chuột: X=${params.x}, Y=${params.y}`}
                            {tool === "click_uia" && `Nhấp UIA: Cửa sổ="${params.window_title_re}", ID="${params.auto_id || ''}", Tên="${params.name || ''}"`}
                            {tool === "type" && `Nhập phím: "${params.text}"`}
                            {tool === "open" && `Mở phần mềm: "${params.app_name}"`}
                            {tool === "press" && `Nhấn phím đơn: "${params.key}"`}
                            {tool === "hotkey" && `Phím tắt: ${params.keys?.join(" + ")}`}
                            {tool === "learn" && `Ghi nhớ đường dẫn: "${params.key}" -> "${params.value}"`}
                          </div>
                          
                          {rollback && (
                            <div style={{ fontSize: '10.5px', color: 'var(--text-muted)', marginTop: '4px', fontStyle: 'italic' }}>
                              ↩️ Khôi phục: {rollback}
                            </div>
                          )}
                          {actionId && (
                            <div style={{ fontSize: '9px', color: 'var(--text-muted)', textAlign: 'right', marginTop: '4px' }}>
                              ID: {actionId}
                            </div>
                          )}
                        </div>
                      );
                    })()}
                    
                    {msg.type === "action" && msg.status === "pending" && status === "waiting_approval" && (
                      <div className="chat-approval-box">
                        <span style={{ fontSize: "12px", color: "var(--warning)", fontWeight: "600" }}>
                          ⚠️ Yêu cầu phê duyệt hành động hệ thống:
                        </span>
                        <div className="approval-btn-group">
                          <button className="btn btn-primary" onClick={handleApprove}>
                            <Check size={14} /> Phê duyệt & Chạy (Approve)
                          </button>
                          <button className="btn btn-secondary" onClick={() => handleReject("User disapproved step.")}>
                            <X size={14} /> Từ chối (Reject)
                          </button>
                        </div>
                      </div>
                    )}
                  </div>
                  <span className="message-time">
                    {new Date(msg.timestamp * 1000).toLocaleTimeString()}
                  </span>
                </div>
              );
            })}
            <div ref={chatEndRef} />
          </div>

          <form className="chat-input-bar" onSubmit={handleSendChat}>
            <input 
              type="text" 
              placeholder={
                status === "running" || status === "waiting_approval" 
                  ? "AI đang xử lý tác vụ dưới nền..." 
                  : "Nhập tin nhắn chat hoặc yêu cầu hệ thống..."
              }
              value={chatInput}
              onChange={(e) => setChatInput(e.target.value)}
              disabled={isSending || status === "running" || status === "waiting_approval"}
            />
            {status === "running" || status === "waiting_approval" ? (
              <button type="button" className="send-btn btn-danger" onClick={handleStop} title="Dừng khẩn cấp">
                <Square size={16} />
              </button>
            ) : (
              <button 
                type="submit" 
                className="send-btn" 
                disabled={!chatInput.trim() || isSending || !isConnected}
              >
                <Send size={16} />
              </button>
            )}
          </form>
        </section>

        <aside className="sidebar">
          <div className="panel glass" style={{ flex: 1, display: 'flex', flexDirection: 'column' }}>
            <div className="sidebar-tabs" style={{ display: 'flex', borderBottom: '1px solid var(--border)', marginBottom: '12px', gap: '8px' }}>
              <button 
                type="button"
                className={`tab-btn ${activeTab === 'screen' ? 'active' : ''}`} 
                onClick={() => setActiveTab('screen')}
                style={{
                  flex: 1,
                  background: 'transparent',
                  border: 'none',
                  padding: '6px 0',
                  fontSize: '13px',
                  cursor: 'pointer',
                  fontWeight: activeTab === 'screen' ? '600' : '400',
                  color: activeTab === 'screen' ? 'var(--primary)' : 'var(--text-muted)',
                  borderBottom: activeTab === 'screen' ? '2px solid var(--primary)' : '2px solid transparent',
                  transition: 'all 120ms'
                }}
              >
                Màn hình
              </button>
              <button 
                type="button"
                className={`tab-btn ${activeTab === 'preview' ? 'active' : ''}`} 
                onClick={() => setActiveTab('preview')}
                style={{
                  flex: 1,
                  background: 'transparent',
                  border: 'none',
                  padding: '6px 0',
                  fontSize: '13px',
                  cursor: 'pointer',
                  fontWeight: activeTab === 'preview' ? '600' : '400',
                  color: activeTab === 'preview' ? 'var(--primary)' : 'var(--text-muted)',
                  borderBottom: activeTab === 'preview' ? '2px solid var(--primary)' : '2px solid transparent',
                  transition: 'all 120ms'
                }}
              >
                Xem trước {(emailDraft || messageDraft) && "🔴"}
              </button>
              <button 
                type="button"
                className={`tab-btn ${activeTab === 'uia' ? 'active' : ''}`} 
                onClick={() => setActiveTab('uia')}
                style={{
                  flex: 1,
                  background: 'transparent',
                  border: 'none',
                  padding: '6px 0',
                  fontSize: '13px',
                  cursor: 'pointer',
                  fontWeight: activeTab === 'uia' ? '600' : '400',
                  color: activeTab === 'uia' ? 'var(--primary)' : 'var(--text-muted)',
                  borderBottom: activeTab === 'uia' ? '2px solid var(--primary)' : '2px solid transparent',
                  transition: 'all 120ms'
                }}
              >
                UIA Inspector
              </button>
              <button 
                type="button"
                className={`tab-btn ${activeTab === 'settings' ? 'active' : ''}`} 
                onClick={() => setActiveTab('settings')}
                style={{
                  flex: 1,
                  background: 'transparent',
                  border: 'none',
                  padding: '6px 0',
                  fontSize: '13px',
                  cursor: 'pointer',
                  fontWeight: activeTab === 'settings' ? '600' : '400',
                  color: activeTab === 'settings' ? 'var(--primary)' : 'var(--text-muted)',
                  borderBottom: activeTab === 'settings' ? '2px solid var(--primary)' : '2px solid transparent',
                  transition: 'all 120ms'
                }}
              >
                Cấu hình
              </button>
            </div>

            {activeTab === "screen" && (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', flex: 1 }}>
                <h3 className="panel-title" style={{ fontSize: '13px', border: 'none', padding: 0, margin: '4px 0 8px 0' }}><Tv size={14} /> Giám sát màn hình chính</h3>
                <div className="screen-container-sidebar" style={{ flex: 1, minHeight: '240px' }}>
                  {screenshot ? (
                    <div style={{ position: "relative", maxWidth: "100%", maxHeight: "100%" }}>
                      <img src={screenshot} alt="Monitor Screen" className="screen-image" />
                      {status === "waiting_approval" && pendingAction?.tool === "click" && (
                        <div className="click-reticle" style={getReticleStyle()} />
                      )}
                    </div>
                  ) : (
                    <div style={{ color: "var(--text-muted)", display: "flex", flexDirection: "column", alignItems: "center", gap: "8px", fontSize: "12px" }}>
                      <Tv size={32} />
                      <span>Chờ nhận ảnh chụp màn hình...</span>
                    </div>
                  )}
                </div>
              </div>
            )}

            {activeTab === "preview" && (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '12px', flex: 1, overflowY: 'auto' }}>
                <h3 className="panel-title" style={{ fontSize: '13px', border: 'none', padding: 0, margin: '4px 0 8px 0' }}>✉️ Bản nháp hiện hoạt</h3>
                
                {!emailDraft && !messageDraft && (
                  <div style={{ color: "var(--text-muted)", display: "flex", flexDirection: "column", alignItems: "center", justifyContent: 'center', gap: "8px", fontSize: "13px", height: '200px' }}>
                    <span>Không có bản nháp email hoặc tin nhắn nào.</span>
                    <span style={{ fontSize: '11px', textAlign: 'center' }}>Khi Agent thực hiện soạn nháp (email.create_draft hoặc message.create_draft), nội dung sẽ hiển thị ở đây.</span>
                  </div>
                )}

                {emailDraft && (
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '10px', background: 'var(--bg-subtle)', padding: '12px', borderRadius: '8px', border: '1px solid var(--border)' }}>
                    <h4 style={{ fontSize: '12px', margin: 0, color: 'var(--primary)', fontWeight: 'bold' }}>✉️ BẢN NHÁP EMAIL</h4>
                    <div>
                      <span style={{ fontSize: '11px', color: 'var(--text-muted)', fontWeight: 'bold', textTransform: 'uppercase' }}>To:</span>
                      <div style={{ fontWeight: '500', fontSize: '13.5px', color: 'var(--text-main)', marginTop: '2px' }}>{emailDraft.to}</div>
                    </div>
                    <div style={{ borderTop: '1px solid var(--border)', paddingTop: '8px' }}>
                      <span style={{ fontSize: '11px', color: 'var(--text-muted)', fontWeight: 'bold', textTransform: 'uppercase' }}>Subject:</span>
                      <div style={{ fontWeight: '600', fontSize: '14px', color: 'var(--text-main)', marginTop: '2px' }}>{emailDraft.subject}</div>
                    </div>
                    <div style={{ borderTop: '1px solid var(--border)', paddingTop: '8px' }}>
                      <span style={{ fontSize: '11px', color: 'var(--text-muted)', fontWeight: 'bold', textTransform: 'uppercase' }}>Body:</span>
                      <div style={{ 
                        whiteSpace: 'pre-line', 
                        fontSize: '13px', 
                        background: 'var(--bg-surface)', 
                        padding: '10px', 
                        borderRadius: '6px', 
                        border: '1px solid var(--border)', 
                        minHeight: '100px', 
                        marginTop: '4px',
                        color: 'var(--text-main)',
                        maxHeight: '180px',
                        overflowY: 'auto'
                      }}>
                        {emailDraft.body}
                      </div>
                    </div>
                    {emailDraft.attachments && emailDraft.attachments.length > 0 && (
                      <div style={{ borderTop: '1px solid var(--border)', paddingTop: '8px' }}>
                        <span style={{ fontSize: '11px', color: 'var(--text-muted)', fontWeight: 'bold', textTransform: 'uppercase' }}>Attachments ({emailDraft.attachments.length}):</span>
                        <div style={{ display: 'flex', flexDirection: 'column', gap: '6px', marginTop: '6px' }}>
                          {emailDraft.attachments.map((file, fIdx) => (
                            <div key={fIdx} style={{ 
                              fontSize: '12px', 
                              background: 'var(--bg-surface)', 
                              padding: '6px 10px', 
                              borderRadius: '6px', 
                              border: '1px solid var(--border)', 
                              display: 'flex', 
                              alignItems: 'center', 
                              gap: '8px',
                              color: 'var(--text-main)' 
                            }}>
                              📎 {file.split('\\').pop() || file.split('/').pop()}
                            </div>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                )}

                {messageDraft && (
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '10px', background: 'var(--bg-subtle)', padding: '12px', borderRadius: '8px', border: '1px solid var(--border)' }}>
                    <h4 style={{ fontSize: '12px', margin: 0, color: 'var(--primary)', fontWeight: 'bold' }}>💬 BẢN NHÁP TIN NHẮN</h4>
                    <div>
                      <span style={{ fontSize: '11px', color: 'var(--text-muted)', fontWeight: 'bold', textTransform: 'uppercase' }}>To (Contact):</span>
                      <div style={{ fontWeight: '600', fontSize: '13.5px', color: 'var(--text-main)', marginTop: '2px' }}>{messageDraft.contact_name}</div>
                    </div>
                    {messageDraft.phone && (
                      <div style={{ borderTop: '1px solid var(--border)', paddingTop: '8px' }}>
                        <span style={{ fontSize: '11px', color: 'var(--text-muted)', fontWeight: 'bold', textTransform: 'uppercase' }}>SĐT:</span>
                        <div style={{ fontSize: '13px', color: 'var(--text-main)', marginTop: '2px' }}>{messageDraft.phone}</div>
                      </div>
                    )}
                    {messageDraft.email && (
                      <div style={{ borderTop: '1px solid var(--border)', paddingTop: '8px' }}>
                        <span style={{ fontSize: '11px', color: 'var(--text-muted)', fontWeight: 'bold', textTransform: 'uppercase' }}>Email:</span>
                        <div style={{ fontSize: '13px', color: 'var(--text-main)', marginTop: '2px' }}>{messageDraft.email}</div>
                      </div>
                    )}
                    <div style={{ borderTop: '1px solid var(--border)', paddingTop: '8px' }}>
                      <span style={{ fontSize: '11px', color: 'var(--text-muted)', fontWeight: 'bold', textTransform: 'uppercase' }}>Nội dung:</span>
                      <div style={{ 
                        whiteSpace: 'pre-line', 
                        fontSize: '13px', 
                        background: 'var(--bg-surface)', 
                        padding: '10px', 
                        borderRadius: '6px', 
                        border: '1px solid var(--border)', 
                        minHeight: '100px', 
                        marginTop: '4px',
                        color: 'var(--text-main)',
                        maxHeight: '180px',
                        overflowY: 'auto'
                      }}>
                        {messageDraft.text}
                      </div>
                    </div>
                  </div>
                )}
              </div>
            )}

            {activeTab === "uia" && (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', flex: 1, overflowY: 'auto' }}>
                <h3 className="panel-title" style={{ fontSize: '13px', border: 'none', padding: 0, margin: '4px 0 8px 0' }}>🔍 UIA Inspector</h3>
                
                <div style={{ display: 'flex', gap: '6px', marginBottom: '8px' }}>
                  <button 
                    type="button"
                    className="btn btn-secondary" 
                    onClick={fetchUiaWindows}
                    style={{ fontSize: '11px', padding: '4px 8px' }}
                  >
                    🔄 Tải lại DS Cửa sổ
                  </button>
                </div>

                <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                  <label style={{ fontSize: '11px', fontWeight: 'bold', color: 'var(--text-muted)' }}>CHỌN CỬA SỔ HOẠT ĐỘNG ({uiaWindows.length}):</label>
                  <select 
                    value={selectedWindow} 
                    onChange={(e) => {
                      setSelectedWindow(e.target.value);
                      fetchUiaTree(e.target.value);
                    }}
                    style={{
                      padding: '6px',
                      borderRadius: '4px',
                      border: '1px solid var(--border)',
                      fontSize: '12px',
                      width: '100%',
                      background: 'var(--bg-surface)',
                      color: 'var(--text-main)'
                    }}
                  >
                    <option value="">-- Chọn cửa sổ để kiểm tra --</option>
                    {uiaWindows.map((win, idx) => (
                      <option key={idx} value={win.title}>{win.title} (PID: {win.pid})</option>
                    ))}
                  </select>
                </div>

                <div style={{ borderTop: '1px solid var(--border)', paddingTop: '10px', marginTop: '10px', display: 'flex', flexDirection: 'column', gap: '6px', flex: 1 }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <label style={{ fontSize: '11px', fontWeight: 'bold', color: 'var(--text-muted)' }}>CÂY ĐIỀU KHIỂN UIA ({uiaTree.length} elements):</label>
                    {selectedWindow && (
                      <button 
                        type="button"
                        className="btn btn-secondary" 
                        onClick={() => fetchUiaTree(selectedWindow)}
                        disabled={isLoadingUia}
                        style={{ fontSize: '10px', padding: '2px 6px' }}
                      >
                        {isLoadingUia ? "Đang quét..." : "Quét lại"}
                      </button>
                    )}
                  </div>

                  {isLoadingUia ? (
                    <div style={{ color: 'var(--text-muted)', fontSize: '12px', textAlign: 'center', padding: '20px' }}>
                      Đang quét cấu trúc cây UIA (có thể mất vài giây)...
                    </div>
                  ) : uiaTree.length > 0 ? (
                    <div style={{ 
                      display: 'flex', 
                      flexDirection: 'column', 
                      gap: '6px', 
                      maxHeight: '300px', 
                      overflowY: 'auto', 
                      background: 'var(--bg-subtle)', 
                      padding: '8px', 
                      borderRadius: '6px', 
                      border: '1px solid var(--border)' 
                    }}>
                      {uiaTree.map((ctrl, idx) => (
                        <div key={idx} style={{ 
                          fontSize: '11px', 
                          background: 'var(--bg-surface)', 
                          padding: '6px', 
                          borderRadius: '4px', 
                          border: '1px solid var(--border)',
                          display: 'flex',
                          flexDirection: 'column',
                          gap: '2px'
                        }}>
                          <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                            <span style={{ fontWeight: 'bold', color: 'var(--primary)' }}>[{ctrl.control_type}]</span>
                            <span style={{ color: 'var(--text-muted)', fontSize: '9px' }}>{ctrl.rectangle}</span>
                          </div>
                          {ctrl.name && <div><span style={{ color: 'var(--text-muted)' }}>Name:</span> <strong style={{ color: 'var(--text-main)' }}>"{ctrl.name}"</strong></div>}
                          {ctrl.auto_id && <div><span style={{ color: 'var(--text-muted)' }}>AutoId:</span> <code style={{ background: 'var(--bg-subtle)', padding: '1px 3px', borderRadius: '3px', fontSize: '10px' }}>{ctrl.auto_id}</code></div>}
                        </div>
                      ))}
                    </div>
                  ) : (
                    <div style={{ color: 'var(--text-muted)', fontSize: '12px', textAlign: 'center', padding: '20px' }}>
                      {selectedWindow ? "Không tìm thấy element UIA nào hoặc không thể kết nối." : "Vui lòng chọn một cửa sổ để xem cấu trúc UIA."}
                    </div>
                  )}
                </div>
              </div>
            )}

            {activeTab === "settings" && (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', flex: 1 }}>
                <h3 className="panel-title" style={{ fontSize: '13px', border: 'none', padding: 0, margin: '4px 0 8px 0' }}><Settings size={14} /> Cấu hình mô hình</h3>
                <div className="settings-group">
                  <div className="setting-item">
                    <label>AI Engine Mode</label>
                    <select 
                      value={aiMode} 
                      onChange={(e) => setAiMode(e.target.value)}
                      disabled={status === "running" || status === "waiting_approval"}
                    >
                      <option value="mock">Mô phỏng (Mock Mode)</option>
                      <option value="gemma4">Gemma 4 (Local GGUF via Llama)</option>
                    </select>
                  </div>

                  {aiMode === "gemma4" && (
                    <div className="setting-item">
                      <label>Đường dẫn tệp Gemma 4 GGUF</label>
                      <input 
                        type="text" 
                        readOnly
                        value={ggufPath || "Chưa phát hiện mô hình"} 
                        style={{ background: "rgba(0,0,0,0.05)", cursor: "not-allowed" }}
                      />
                    </div>
                  )}

                  <div className="setting-item checkbox-item">
                    <label htmlFor="safety">Chế độ Phê duyệt An toàn</label>
                    <input 
                      type="checkbox" 
                      id="safety"
                      checked={safetyConfirmation} 
                      onChange={(e) => setSafetyConfirmation(e.target.checked)}
                      disabled={status === "running" || status === "waiting_approval"}
                    />
                  </div>
                </div>
              </div>
            )}
          </div>
        </aside>
      </div>
    </div>
  );
}

export default App;
