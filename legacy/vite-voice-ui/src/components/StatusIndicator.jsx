import React from 'react';
import { Mic, Loader2, Volume2, HelpCircle, AlertCircle } from 'lucide-react';

const StatusIndicator = ({ status }) => {
  const getStatusConfig = () => {
    switch (status) {
      case 'listening':
        return {
          icon: <Mic className="status-icon" size={18} />,
          text: 'Listening',
          className: 'status-listening',
          bulletColor: 'var(--status-listening)'
        };
      case 'processing':
        return {
          icon: <Loader2 className="status-icon animate-spin" size={18} />,
          text: 'Thinking',
          className: 'status-processing',
          bulletColor: 'var(--status-processing)'
        };
      case 'speaking':
        return {
          icon: <Volume2 className="status-icon" size={18} />,
          text: 'Speaking',
          className: 'status-speaking',
          bulletColor: 'var(--status-speaking)'
        };
      case 'error':
        return {
          icon: <AlertCircle className="status-icon" size={18} />,
          text: 'Error',
          className: 'status-error',
          bulletColor: 'var(--status-error)'
        };
      case 'idle':
      default:
        return {
          icon: <HelpCircle className="status-icon" size={18} />,
          text: 'Ready',
          className: 'status-idle',
          bulletColor: 'var(--status-idle)'
        };
    }
  };

  const config = getStatusConfig();

  return (
    <div className={`status-badge-container ${config.className}`}>
      <span 
        className="status-bullet" 
        style={{ 
          backgroundColor: config.bulletColor,
          boxShadow: `0 0 10px ${config.bulletColor}`
        }} 
      />
      <span className="status-icon-wrapper">{config.icon}</span>
      <span className="status-text">{config.text}</span>

      <style>{`
        .status-badge-container {
          display: inline-flex;
          align-items: center;
          gap: 0.6rem;
          padding: 0.4rem 1rem;
          border-radius: 50px;
          background: rgba(255, 255, 255, 0.03);
          border: 1px solid rgba(255, 255, 255, 0.05);
          font-family: var(--font-display);
          font-size: 0.85rem;
          font-weight: 500;
          letter-spacing: 0.02em;
          text-transform: uppercase;
          transition: all var(--transition-fast);
        }

        .status-bullet {
          width: 8px;
          height: 8px;
          border-radius: 50%;
          display: inline-block;
          transition: background-color var(--transition-fast);
        }

        .status-icon-wrapper {
          display: flex;
          align-items: center;
          color: var(--text-secondary);
        }

        .status-text {
          color: var(--text-primary);
        }

        /* Status-specific Glow & Borders */
        .status-listening {
          background: rgba(16, 185, 129, 0.05);
          border-color: rgba(16, 185, 129, 0.2);
        }
        .status-listening .status-text {
          color: var(--status-listening);
        }

        .status-processing {
          background: rgba(245, 158, 11, 0.05);
          border-color: rgba(245, 158, 11, 0.2);
        }
        .status-processing .status-text {
          color: var(--status-processing);
        }

        .status-speaking {
          background: rgba(59, 130, 246, 0.05);
          border-color: rgba(59, 130, 246, 0.2);
        }
        .status-speaking .status-text {
          color: var(--status-speaking);
        }

        .status-error {
          background: rgba(239, 68, 68, 0.05);
          border-color: rgba(239, 68, 68, 0.2);
        }
        .status-error .status-text {
          color: var(--status-error);
        }
      `}</style>
    </div>
  );
};

export default StatusIndicator;
