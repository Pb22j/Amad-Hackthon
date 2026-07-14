import React, { useState, useRef, useEffect } from 'react';
import { Mic, MicOff, Settings, VolumeX, Sparkles, Clock, RefreshCw, MessageSquare, Activity } from 'lucide-react';
import { AudioManager } from '../utils/audio';
import StatusIndicator from './StatusIndicator';
import Visualizer from './Visualizer';

// Utility to convert Float32Array from microphone to Base64 Int16 PCM
function float32ToBase64Pcm(float32Array) {
  const buffer = new ArrayBuffer(float32Array.length * 2);
  const view = new DataView(buffer);
  let offset = 0;
  for (let i = 0; i < float32Array.length; i++, offset += 2) {
    let s = Math.max(-1, Math.min(1, float32Array[i]));
    view.setInt16(offset, s < 0 ? s * 0x8000 : s * 0x7FFF, true);
  }
  let binary = '';
  const bytes = new Uint8Array(buffer);
  for (let i = 0; i < bytes.byteLength; i++) {
    binary += String.fromCharCode(bytes[i]);
  }
  return window.btoa(binary);
}

// Utility to convert Base64 Int16 PCM from Gemini to Float32Array for playback
function base64PcmToFloat32(base64) {
  const binary_string = window.atob(base64);
  const len = binary_string.length;
  const bytes = new Uint8Array(len);
  for (let i = 0; i < len; i++) {
    bytes[i] = binary_string.charCodeAt(i);
  }
  const int16Array = new Int16Array(bytes.buffer);
  const float32Array = new Float32Array(int16Array.length);
  for (let i = 0; i < int16Array.length; i++) {
    float32Array[i] = int16Array[i] / (int16Array[i] >= 0 ? 32767 : 32768);
  }
  return float32Array;
}

const VoiceAgent = () => {
  const [status, setStatus] = useState('idle'); // idle, connecting, active, error
  const [errorMessage, setErrorMessage] = useState('');
  const [config, setConfig] = useState(null);
  
  // Transcripts
  const [transcript, setTranscript] = useState('');
  const [agentResponse, setAgentResponse] = useState('');
  const [history, setHistory] = useState([]);
  const [agentLogs, setAgentLogs] = useState([]);

  const addLog = (msg) => {
    setAgentLogs(prev => [...prev, { time: new Date().toLocaleTimeString(), msg }].slice(-10));
  };
  
  // Custom system prompt
  const [customSystemPrompt, setCustomSystemPrompt] = useState('');
  const [language, setLanguage] = useState('ar');
  const [showSettings, setShowSettings] = useState(false);

  // Audio & WebSocket References
  const audioManagerRef = useRef(null);
  const geminiWsRef = useRef(null);
  const backendWsRef = useRef(null);
  const currentTaskIdRef = useRef(null);

  // Audio Contexts for Worklets
  const inputContextRef = useRef(null);
  const outputContextRef = useRef(null);
  const micSourceRef = useRef(null);
  const pcmProcessorRef = useRef(null);
  const pcmPlayerRef = useRef(null);

  // Initialize Audio Manager and Backend WebSocket on mount
  useEffect(() => {
    audioManagerRef.current = new AudioManager();
    fetchConfig();

    // Connect WebSocket to receive webhooks from Agentic Layer
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const ws = new WebSocket(`${protocol}//${window.location.host}/api/ws`);
    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        console.log("Received Webhook via WS:", data);
        addLog(`[Webhook] ${data.event_type} - ${data.user_safe_summary || ''}`);
        
        if (data.event_type === "input_needed" || data.event_type === "confirmation_needed") {
          currentTaskIdRef.current = data.task_id;
           if (geminiWsRef.current && geminiWsRef.current.readyState === WebSocket.OPEN) {
             const promptEvent = {
               clientContent: {
                 turns: [{
                   role: "user",
                   parts: [{ text: `النظام الخلفي أرسل هذا التحديث بخصوص الطلب: "${data.user_safe_summary || 'أحتاج معلومات إضافية لتنفيذ العملية'}". الرجاء إخبار المستخدم بهذا التحديث بلهجة سعودية ودية، وسؤاله لتقديم المعلومات الناقصة.` }]
                 }],
                 turnComplete: true
               }
             };
             geminiWsRef.current.send(JSON.stringify(promptEvent));
          }
        } else if (data.event_type === "completed" || data.event_type === "rejected") {
           if (geminiWsRef.current && geminiWsRef.current.readyState === WebSocket.OPEN) {
             const promptEvent = {
               clientContent: {
                 turns: [{
                   role: "user",
                   parts: [{ text: `النظام الخلفي أنهى تنفيذ الطلب. الحالة: ${data.event_type}. الملخص: "${data.user_safe_summary}". الرجاء إخبار المستخدم بذلك بلهجة سعودية ودية وبشكل مختصر.` }]
                 }],
                 turnComplete: true
               }
             };
             geminiWsRef.current.send(JSON.stringify(promptEvent));
           }
        }
      } catch(e) {}
    };
    backendWsRef.current = ws;

    return () => {
      stopSession();
      if (audioManagerRef.current) {
        audioManagerRef.current.close();
      }
      if (backendWsRef.current) backendWsRef.current.close();
    };
  }, []);

  const handleFunctionCall = async (fnCall) => {
    const fnName = fnCall.name;
    const args = fnCall.args;
    console.log(`Executing Gemini tool: ${fnName}`, args);
    addLog(`[Tool Call] ${fnName}: ${JSON.stringify(args)}`);
    
    let result = { status: "failed" };
    try {
      if (fnName === 'submit_financial_task') {
        const res = await fetch('/api/submit-task', {
           method: 'POST',
           headers: { 'Content-Type': 'application/json' },
           body: JSON.stringify({ natural_language_request: args.request_details })
        });
        result = await res.json();
        addLog(`[Tool Response] ${fnName}: ${JSON.stringify(result)}`);
        if (result.task_id) currentTaskIdRef.current = result.task_id;
      } else if (fnName === 'resume_financial_task') {
        const res = await fetch('/api/resume-task', {
           method: 'POST',
           headers: { 'Content-Type': 'application/json' },
           body: JSON.stringify({ task_id: currentTaskIdRef.current || 'unknown', user_answer: args.user_answer })
        });
        result = await res.json();
        addLog(`[Tool Response] ${fnName}: ${JSON.stringify(result)}`);
      }
    } catch(e) {
      console.error("Tool execution failed", e);
      addLog(`[Tool Error] ${e.message}`);
      result = { error: e.message };
    }

    if (geminiWsRef.current && geminiWsRef.current.readyState === WebSocket.OPEN) {
       // Send tool response to Gemini
       const outputEvent = {
          toolResponse: {
            functionResponses: [{
              id: fnCall.id,
              name: fnName,
              response: result
            }]
          }
       };
       geminiWsRef.current.send(JSON.stringify(outputEvent));
    }
  };

  const fetchConfig = async () => {
    try {
      const res = await fetch('/api/config');
      if (res.ok) {
        const data = await res.json();
        setConfig(data);
      }
    } catch (e) {
      console.error("Failed to fetch backend configuration:", e);
    }
  };

  const startSession = async () => {
    setStatus('connecting');
    setErrorMessage('');
    setTranscript('');
    setAgentResponse('');

    try {
      // 1. Fetch Connection Details
      const tokenResponse = await fetch('/api/realtime-token', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ custom_system_prompt: customSystemPrompt, language: language })
      });
      if (!tokenResponse.ok) {
        throw new Error("Failed to get connection details from backend.");
      }
      const data = await tokenResponse.json();
      
      if (data.provider !== 'gemini') {
        throw new Error("Backend is configured for OpenAI, but frontend is now running Gemini architecture.");
      }

      // 2. Setup Gemini WebSocket
      const API_KEY = data.api_key;
      const wsUrl = `wss://generativelanguage.googleapis.com/ws/google.ai.generativelanguage.v1alpha.GenerativeService.BidiGenerateContent?key=${API_KEY}`;
      const ws = new WebSocket(wsUrl);
      geminiWsRef.current = ws;

      ws.onopen = () => {
        // Send Setup Message
        const setupMessage = {
          setup: {
            model: `models/${data.model}`,
            systemInstruction: {
              parts: [{ text: data.instructions }]
            },
            generationConfig: {
              responseModalities: ["AUDIO"]
            },
            tools: [{
              functionDeclarations: [
                {
                  name: "submit_financial_task",
                  description: "أرسل طلب مالي جديد من المستخدم إلى النظام الخلفي للتنفيذ.",
                  parameters: {
                    type: "OBJECT",
                    properties: {
                      request_details: { type: "STRING", description: "تفاصيل الطلب باللغة العربية" }
                    },
                    required: ["request_details"]
                  }
                },
                {
                  name: "resume_financial_task",
                  description: "أرسل إجابة المستخدم على سؤال توضيحي طرحه النظام الخلفي.",
                  parameters: {
                    type: "OBJECT",
                    properties: {
                      user_answer: { type: "STRING", description: "إجابة المستخدم" }
                    },
                    required: ["user_answer"]
                  }
                }
              ]
            }]
          }
        };
        ws.send(JSON.stringify(setupMessage));
        setStatus('active');
      };

      ws.onmessage = async (event) => {
        const msg = event.data instanceof Blob ? JSON.parse(await event.data.text()) : JSON.parse(event.data);
        
        // Handle server content (audio and text)
        if (msg.serverContent && msg.serverContent.modelTurn) {
          const parts = msg.serverContent.modelTurn.parts;
          for (const part of parts) {
            if (part.inlineData && part.inlineData.data) {
              // Decode audio and send to player worklet
              const float32Array = base64PcmToFloat32(part.inlineData.data);
              if (pcmPlayerRef.current) {
                pcmPlayerRef.current.port.postMessage(float32Array);
              }
            }
            if (part.text) {
              setAgentResponse(prev => prev + part.text);
            }
          }
        }
        
        // Handle interruption (Barge-in)
        if (msg.serverContent && msg.serverContent.interrupted) {
          if (pcmPlayerRef.current) {
            pcmPlayerRef.current.port.postMessage({ action: 'clear' });
          }
          setAgentResponse(prev => prev + ' 🛑');
        }
        
        // Handle tool calls from Gemini
        if (msg.toolCall && msg.toolCall.functionCalls) {
          for (const fnCall of msg.toolCall.functionCalls) {
            handleFunctionCall(fnCall);
          }
        }
        
        if (msg.serverContent && msg.serverContent.turnComplete) {
          setHistory(prev => {
            const lastText = agentResponse || '🔊 [Audio Response]';
            // Simple check to avoid empty history spam
            if (lastText.trim() === '') return prev;
            return [...prev, { role: 'assistant', text: lastText }].slice(-6);
          });
          setAgentResponse('');
        }
      };

      ws.onerror = (e) => {
        console.error("Gemini WebSocket Error:", e);
      };

      ws.onclose = () => {
        console.log("Gemini WebSocket Closed");
        stopSession();
      };

      // 3. Setup Audio Capture (16kHz)
      const stream = await navigator.mediaDevices.getUserMedia({ audio: {
        channelCount: 1,
        echoCancellation: true,
        autoGainControl: true,
        noiseSuppression: true
      }});
      
      const inCtx = new (window.AudioContext || window.webkitAudioContext)({ sampleRate: 16000 });
      inputContextRef.current = inCtx;
      await inCtx.audioWorklet.addModule('/pcm-processor.js');
      
      const source = inCtx.createMediaStreamSource(stream);
      micSourceRef.current = source;
      
      const processor = new AudioWorkletNode(inCtx, 'pcm-processor');
      pcmProcessorRef.current = processor;
      
      processor.port.onmessage = (e) => {
        if (ws.readyState === WebSocket.OPEN) {
          const base64Audio = float32ToBase64Pcm(e.data);
          ws.send(JSON.stringify({
            realtimeInput: {
              audio: {
                mimeType: "audio/pcm;rate=16000",
                data: base64Audio
              }
            }
          }));
        }
      };
      
      source.connect(processor);

      // 4. Setup Audio Playback (24kHz)
      const outCtx = new (window.AudioContext || window.webkitAudioContext)({ sampleRate: 24000 });
      outputContextRef.current = outCtx;
      await outCtx.audioWorklet.addModule('/pcm-player.js');
      
      const player = new AudioWorkletNode(outCtx, 'pcm-player');
      pcmPlayerRef.current = player;
      player.connect(outCtx.destination);
      
      // Connect visualizer logic
      audioManagerRef.current.init();

    } catch (err) {
      console.error("Gemini Live Setup failed:", err);
      setStatus('error');
      setErrorMessage(err.message || "Failed to establish Gemini Live connection.");
      stopSession();
    }
  };

  const stopSession = () => {
    if (geminiWsRef.current) {
      geminiWsRef.current.close();
      geminiWsRef.current = null;
    }
    if (micSourceRef.current) {
      micSourceRef.current.mediaStream.getTracks().forEach(t => t.stop());
      micSourceRef.current.disconnect();
      micSourceRef.current = null;
    }
    if (pcmProcessorRef.current) {
      pcmProcessorRef.current.disconnect();
      pcmProcessorRef.current = null;
    }
    if (pcmPlayerRef.current) {
      pcmPlayerRef.current.disconnect();
      pcmPlayerRef.current = null;
    }
    if (inputContextRef.current) {
      inputContextRef.current.close();
      inputContextRef.current = null;
    }
    if (outputContextRef.current) {
      outputContextRef.current.close();
      outputContextRef.current = null;
    }
    
    setStatus((prev) => {
      if (prev === 'active' || prev === 'connecting') {
        return 'idle';
      }
      return prev; // Preserve 'error' state
    });
  };

  const toggleSession = () => {
    if (status === 'active' || status === 'connecting') {
      stopSession();
    } else {
      startSession();
    }
  };

  return (
    <div className="agent-card glass">
      {/* Header */}
      <div className="card-header">
        <div className="title-area">
          <Sparkles className="spark-icon animate-pulse" size={20} />
          <h2>AURA Realtime (Gemini)</h2>
        </div>
        <div className="actions">
          <button 
            className={`settings-toggle ${showSettings ? 'active' : ''}`}
            onClick={() => setShowSettings(!showSettings)}
            title="Configure System Prompt"
          >
            <Settings size={18} />
          </button>
        </div>
      </div>

      {/* Settings panel */}
      {showSettings && (
        <div className="settings-panel animate-float-in">
          <h3>Agent Settings</h3>
          <div className="input-group">
            <label>Persona Language</label>
            <select 
              className="input select" 
              value={language} 
              onChange={(e) => setLanguage(e.target.value)} 
              style={{ padding: '8px', borderRadius: '8px', background: 'rgba(255,255,255,0.1)', color: 'white', border: '1px solid rgba(255,255,255,0.2)', marginBottom: '10px', width: '100%' }}
            >
              <option value="ar" style={{ color: 'black' }}>Arabic (Saudi) - نافع العربي</option>
              <option value="en" style={{ color: 'black' }}>English - Nafea English</option>
            </select>
          </div>
          <div className="input-group">
            <label>Custom System Prompt</label>
            <textarea
              className="input textarea"
              value={customSystemPrompt}
              onChange={(e) => setCustomSystemPrompt(e.target.value)}
              placeholder="e.g. Act as a pirate assistant who gives short replies."
              rows={3}
            />
          </div>
          <div className="config-grid">
            <span className="config-label">Architecture:</span>
            <span className="config-value">Gemini Live API</span>
          </div>
        </div>
      )}

      {/* Status Bar */}
      <div className="status-container">
        <StatusIndicator status={status === 'active' ? 'listening' : status} />
      </div>

      {/* Dynamic Visualizer (Fallback visual via CSS) */}
      <Visualizer status={status === 'active' ? 'listening' : status} audioManager={audioManagerRef.current} />

      {/* Push-to-Talk Button & Main Trigger */}
      <div className="mic-container">
        <button
          className={`mic-button ${
            status === 'active' ? 'mic-listening animate-pulse-listening' : 
            status === 'connecting' ? 'mic-connecting' : 'mic-idle'
          }`}
          onClick={toggleSession}
          disabled={status === 'connecting'}
        >
          {status === 'active' ? (
            <MicOff size={36} className="mic-icon" />
          ) : (
            <Mic size={36} className="mic-icon" />
          )}
        </button>
        <span className="mic-instruction">
          {status === 'active' ? 'Tap to end real-time session' : 
           status === 'connecting' ? 'Connecting to Gemini...' : 'Tap to start real-time session'}
        </span>
      </div>

      {/* Error Message */}
      {status === 'error' && (
        <div className="error-card">
          <p>{errorMessage}</p>
          <button className="btn btn-secondary" onClick={() => setStatus('idle')}>
            Reset
          </button>
        </div>
      )}

      {/* Current Turn Transcription */}
      {(transcript || agentResponse) && (
        <div className="transcripts-card">
          {transcript && (
            <div className="transcript-row user-bubble">
              <span className="speaker-label">You</span>
              <p>{transcript}</p>
            </div>
          )}
          {agentResponse && (
            <div className="transcript-row agent-bubble">
              <span className="speaker-label">AURA</span>
              <p>{agentResponse}</p>
            </div>
          )}
        </div>
      )}

      {/* Chat History summary */}
      {history.length > 0 && (
        <div className="history-drawer">
          <div className="history-header">
            <MessageSquare size={14} />
            <h4>Recent Chat History</h4>
          </div>
          <div className="history-scroll">
            {history.map((chat, idx) => (
              <div key={idx} className={`history-bubble ${chat.role}`}>
                <strong>{chat.role === 'user' ? 'You' : 'AURA'}: </strong>
                <span>{chat.text}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      <style jsx="true">{`
        .agent-card { width: 100%; padding: 2rem; margin-top: 1.5rem; display: flex; flex-direction: column; }
        .card-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 1.5rem; border-bottom: 1px solid var(--border-color); padding-bottom: 1rem; }
        .title-area { display: flex; align-items: center; gap: 0.5rem; }
        .title-area h2 { font-family: var(--font-display); font-size: 1.4rem; font-weight: 600; background: linear-gradient(135deg, var(--text-primary) 30%, var(--accent-cyan) 100%); -webkit-background-clip: text; -webkit-text-fill-color: transparent; }
        .spark-icon { color: var(--accent-cyan); }
        .settings-toggle { background: transparent; border: none; color: var(--text-secondary); cursor: pointer; padding: 0.4rem; border-radius: 8px; transition: all var(--transition-fast); }
        .settings-toggle:hover, .settings-toggle.active { color: var(--text-primary); background: rgba(255, 255, 255, 0.05); }
        .settings-panel { background: rgba(0, 0, 0, 0.25); border-radius: 12px; padding: 1.25rem; margin-bottom: 1.5rem; border: 1px solid var(--border-color); }
        .settings-panel h3 { font-family: var(--font-display); font-size: 1rem; margin-bottom: 0.75rem; color: var(--text-primary); }
        .input-group { display: flex; flex-direction: column; gap: 0.5rem; margin-bottom: 1rem; }
        .input-group label { font-size: 0.8rem; color: var(--text-secondary); font-family: var(--font-display); }
        .textarea { resize: none; font-size: 0.9rem; }
        .config-grid { display: grid; grid-template-columns: auto 1fr; gap: 0.4rem 1rem; font-size: 0.8rem; border-top: 1px solid rgba(255, 255, 255, 0.05); padding-top: 0.75rem; }
        .config-label { color: var(--text-muted); }
        .config-value { color: var(--accent-cyan); font-family: monospace; }
        .status-container { display: flex; justify-content: center; margin-bottom: 0.5rem; }
        .mic-container { display: flex; flex-direction: column; align-items: center; gap: 0.8rem; margin: 1.5rem 0; }
        .mic-button { width: 80px; height: 80px; border-radius: 50%; border: none; cursor: pointer; display: flex; align-items: center; justify-content: center; color: white; transition: all var(--transition-normal); outline: none; }
        .mic-idle { background: linear-gradient(135deg, var(--primary) 0%, var(--accent-purple) 100%); box-shadow: 0 4px 20px rgba(99, 102, 241, 0.35); }
        .mic-idle:hover { transform: scale(1.05); box-shadow: 0 6px 25px rgba(99, 102, 241, 0.5); }
        .mic-listening { background: linear-gradient(135deg, var(--status-listening) 0%, var(--accent-cyan) 100%); box-shadow: 0 4px 20px rgba(16, 185, 129, 0.35); }
        .mic-connecting { background: var(--text-muted); animation: pulse 1.5s infinite; }
        .mic-icon { transition: transform 0.2s ease; }
        .mic-button:active .mic-icon { transform: scale(0.9); }
        .mic-button:disabled { opacity: 0.6; cursor: not-allowed; }
        .mic-instruction { font-family: var(--font-display); font-size: 0.85rem; color: var(--text-secondary); letter-spacing: 0.01em; }
        .btn-sm { padding: 0.4rem 1rem; font-size: 0.8rem; border-radius: 8px; }
        .error-card { background: rgba(239, 68, 68, 0.08); border: 1px solid rgba(239, 68, 68, 0.25); border-radius: 12px; padding: 1rem; margin-bottom: 1.5rem; display: flex; flex-direction: column; align-items: center; gap: 0.75rem; text-align: center; }
        .error-card p { color: #fca5a5; font-size: 0.9rem; }
        .transcripts-card { display: flex; flex-direction: column; gap: 1rem; background: rgba(0, 0, 0, 0.1); border-radius: 14px; padding: 1.25rem; border: 1px solid rgba(255, 255, 255, 0.02); margin-top: 1rem; }
        .transcript-row { display: flex; flex-direction: column; gap: 0.25rem; }
        .speaker-label { font-family: var(--font-display); font-size: 0.75rem; font-weight: 600; text-transform: uppercase; letter-spacing: 0.03em; }
        .user-bubble .speaker-label { color: var(--accent-cyan); }
        .user-bubble p { color: var(--text-primary); font-size: 0.95rem; line-height: 1.5; }
        .agent-bubble .speaker-label { color: var(--accent-purple); }
        .agent-bubble p { color: var(--text-primary); font-size: 0.95rem; line-height: 1.5; font-weight: 500; }
        .history-drawer { border-top: 1px solid var(--border-color); margin-top: 1.5rem; padding-top: 1.25rem; }
        .history-header { display: flex; align-items: center; gap: 0.4rem; color: var(--text-secondary); margin-bottom: 0.75rem; }
        .history-header h4 { font-family: var(--font-display); font-size: 0.85rem; font-weight: 600; text-transform: uppercase; }
        .history-scroll { display: flex; flex-direction: column; gap: 0.6rem; max-height: 150px; overflow-y: auto; padding-right: 0.5rem; }
        .history-bubble { font-size: 0.85rem; padding: 0.5rem 0.75rem; border-radius: 8px; background: rgba(255, 255, 255, 0.02); line-height: 1.4; }
        .history-bubble.user { border-left: 2px solid var(--accent-cyan); }
        .history-bubble.assistant { border-left: 2px solid var(--accent-purple); }
      `}</style>
      {/* Developer Logs / Tool Activity */}
      {agentLogs.length > 0 && (
        <div className="agent-logs-card" style={{ marginTop: '1rem', padding: '15px', background: 'rgba(15, 23, 42, 0.8)', borderRadius: '12px', fontSize: '0.85rem', color: '#10b981', fontFamily: 'monospace', maxHeight: '200px', overflowY: 'auto', border: '1px solid rgba(16, 185, 129, 0.2)', boxShadow: '0 4px 6px -1px rgba(0, 0, 0, 0.1)' }}>
          <h4 style={{ margin: '0 0 10px 0', color: '#fff', display: 'flex', alignItems: 'center', gap: '8px' }}>
            <Activity size={16} color="#10b981" /> 
            Activity & Tool Logs
          </h4>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
            {agentLogs.map((log, i) => (
              <div key={i} style={{ wordBreak: 'break-all', opacity: 0.9 }}>
                <span style={{ color: '#94a3b8', marginRight: '6px' }}>[{log.time}]</span>
                <span dangerouslySetInnerHTML={{ __html: log.msg.replace(/\[([^\]]+)\]/, '<strong style="color:#fbbf24">[$1]</strong>') }}></span>
              </div>
            ))}
          </div>
        </div>
      )}

    </div>
  );
};

export default VoiceAgent;
