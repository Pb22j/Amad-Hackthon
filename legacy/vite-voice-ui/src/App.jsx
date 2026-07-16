import React, { useState, useEffect } from 'react';
import VoiceAgent from './components/VoiceAgent';
import { Cpu, Radio } from 'lucide-react';

function App() {
  const [serverOnline, setServerOnline] = useState(false);
  const [checkingServer, setCheckingServer] = useState(true);

  useEffect(() => {
    const checkServer = async () => {
      try {
        const res = await fetch('/api/health');
        if (res.ok) {
          setServerOnline(true);
        } else {
          setServerOnline(false);
        }
      } catch (e) {
        setServerOnline(false);
      } finally {
        setCheckingServer(false);
      }
    };

    checkServer();
    const interval = setInterval(checkServer, 10000); // Check health every 10s
    return () => clearInterval(interval);
  }, []);

  return (
    <div className="container">
      {/* Top Navbar */}
      <header className="navbar glass">
        <div className="logo-group">
          <div className="logo-icon-wrapper">
            <Radio className="logo-icon animate-pulse" size={22} />
          </div>
          <h1>AURA VOICE</h1>
        </div>
        
        <div className="server-status">
          <span 
            className={`status-dot ${serverOnline ? 'online' : 'offline'}`} 
          />
          <span className="status-label">
            {checkingServer ? 'Checking...' : serverOnline ? 'Proxy Server Online' : 'Proxy Server Offline'}
          </span>
        </div>
      </header>

      {/* Main content grid */}
      <main className="main-content">
        <section className="hero-section">
          <h2 className="display-title">Talk to your AI in real-time</h2>
          <p className="subtitle-text">
            Experience ultra-low latency voice transcription, intelligence synthesis, and natural response playback. Securely proxied via FastAPI.
          </p>
        </section>

        {/* The Voice Agent Console */}
        <section className="agent-console">
          <VoiceAgent />
        </section>
      </main>

      {/* Footer */}
      <footer className="footer glass">
        <div className="footer-left">
          <Cpu size={14} />
          <span>Built with React + FastAPI Proxy</span>
        </div>
        <div className="footer-right">
          <span>v1.0.0</span>
        </div>
      </footer>

      <style>{`
        /* Navbar Styling */
        .navbar {
          display: flex;
          justify-content: space-between;
          align-items: center;
          padding: 1rem 1.75rem;
          margin-bottom: 2.5rem;
          border-radius: 16px;
        }

        .logo-group {
          display: flex;
          align-items: center;
          gap: 0.75rem;
        }

        .logo-icon-wrapper {
          width: 38px;
          height: 38px;
          border-radius: 10px;
          background: linear-gradient(135deg, var(--primary) 0%, var(--accent-cyan) 100%);
          display: flex;
          align-items: center;
          justify-content: center;
          color: white;
          box-shadow: 0 4px 12px rgba(99, 102, 241, 0.25);
        }

        .logo-icon {
          color: white;
        }

        .logo-group h1 {
          font-family: var(--font-display);
          font-size: 1.15rem;
          font-weight: 700;
          letter-spacing: 0.05em;
          background: linear-gradient(135deg, var(--text-primary) 40%, var(--accent-cyan) 100%);
          -webkit-background-clip: text;
          -webkit-text-fill-color: transparent;
        }

        .server-status {
          display: flex;
          align-items: center;
          gap: 0.5rem;
          font-family: var(--font-display);
          font-size: 0.8rem;
          font-weight: 500;
          color: var(--text-secondary);
          background: rgba(255, 255, 255, 0.02);
          padding: 0.4rem 0.8rem;
          border-radius: 30px;
          border: 1px solid rgba(255, 255, 255, 0.04);
        }

        .status-dot {
          width: 6px;
          height: 6px;
          border-radius: 50%;
          display: inline-block;
        }

        .status-dot.online {
          background-color: var(--status-listening);
          box-shadow: 0 0 8px var(--status-listening);
        }

        .status-dot.offline {
          background-color: var(--status-error);
          box-shadow: 0 0 8px var(--status-error);
        }

        /* Hero Layout */
        .main-content {
          display: flex;
          flex-direction: column;
          align-items: center;
          gap: 1.5rem;
          flex: 1;
        }

        .hero-section {
          text-align: center;
          max-width: 650px;
          margin-bottom: 0.5rem;
        }

        .display-title {
          font-family: var(--font-display);
          font-size: 2.2rem;
          font-weight: 700;
          letter-spacing: -0.02em;
          line-height: 1.2;
          background: linear-gradient(135deg, var(--text-primary) 30%, var(--accent-purple) 80%, var(--accent-pink) 100%);
          -webkit-background-clip: text;
          -webkit-text-fill-color: transparent;
          margin-bottom: 0.75rem;
        }

        .subtitle-text {
          font-size: 0.95rem;
          color: var(--text-secondary);
          line-height: 1.6;
        }

        .agent-console {
          width: 100%;
          max-width: 550px;
        }

        /* Footer styling */
        .footer {
          display: flex;
          justify-content: space-between;
          align-items: center;
          padding: 0.85rem 1.5rem;
          margin-top: 3rem;
          border-radius: 12px;
          font-family: var(--font-display);
          font-size: 0.75rem;
          color: var(--text-muted);
        }

        .footer-left {
          display: flex;
          align-items: center;
          gap: 0.4rem;
        }

        /* Responsive adaptations */
        @media (max-width: 640px) {
          .display-title {
            font-size: 1.8rem;
          }
          .navbar {
            padding: 0.75rem 1.25rem;
            margin-bottom: 1.5rem;
          }
          .container {
            padding: 1rem 1rem;
          }
          .hero-section {
            padding: 0 0.5rem;
          }
        }
      `}</style>
    </div>
  );
}

export default App;
