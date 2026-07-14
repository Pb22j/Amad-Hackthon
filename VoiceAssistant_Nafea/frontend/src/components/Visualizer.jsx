import React, { useRef, useEffect } from 'react';

const Visualizer = ({ status, audioManager }) => {
  const canvasRef = useRef(null);
  const animationRef = useRef(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    // Handle resizing
    const resizeCanvas = () => {
      const rect = canvas.getBoundingClientRect();
      canvas.width = rect.width * window.devicePixelRatio;
      canvas.height = rect.height * window.devicePixelRatio;
      ctx.scale(window.devicePixelRatio, window.devicePixelRatio);
    };

    resizeCanvas();
    window.addEventListener('resize', resizeCanvas);

    let phase = 0;

    const render = () => {
      const width = canvas.width / window.devicePixelRatio;
      const height = canvas.height / window.devicePixelRatio;
      ctx.clearRect(0, 0, width, height);

      // Fetch audio data if active
      let audioData = null;
      if (audioManager && (status === 'listening' || status === 'speaking')) {
        audioData = audioManager.getByteFrequencyData();
      }

      if (status === 'listening') {
        // Draw microphone input visualizer (vertical frequency bars or reactive waves)
        // Let's draw reactive glowing wave lines
        const maxVal = audioData ? Math.max(...audioData) : 0;
        const amplitude = Math.max(10, (maxVal / 255) * (height / 2.2));
        
        ctx.shadowBlur = 15;
        ctx.shadowColor = 'rgba(16, 185, 129, 0.4)';
        
        // Let's draw 3 overlapping waves with offset phases for organic feel
        drawWave(ctx, width, height, phase, amplitude, 'rgba(16, 185, 129, 0.65)', 2.5);
        drawWave(ctx, width, height, phase + 1.5, amplitude * 0.6, 'rgba(6, 182, 212, 0.4)', 1.5);
        drawWave(ctx, width, height, phase + 3.0, amplitude * 0.3, 'rgba(99, 102, 241, 0.2)', 1);

        phase += 0.12; // wave speed

      } else if (status === 'speaking') {
        // Draw speaker playback visualizer (smooth, high-energy colored wave)
        // Reactive to playback frequency data
        const maxVal = audioData ? Math.max(...audioData) : 0;
        const amplitude = Math.max(10, (maxVal / 255) * (height / 2.2));

        ctx.shadowBlur = 20;
        ctx.shadowColor = 'rgba(59, 130, 246, 0.4)';
        
        drawWave(ctx, width, height, phase, amplitude, 'rgba(59, 130, 246, 0.7)', 3);
        drawWave(ctx, width, height, phase + 2.0, amplitude * 0.7, 'rgba(168, 85, 247, 0.45)', 2);
        drawWave(ctx, width, height, phase + 4.0, amplitude * 0.4, 'rgba(236, 72, 153, 0.25)', 1);

        phase += 0.15; // slightly faster wave speed for speaking energy

      } else if (status === 'processing') {
        // Draw "Thinking" state: beautiful slow-moving orb or orbital pulse in center
        ctx.shadowBlur = 25;
        ctx.shadowColor = 'rgba(245, 158, 11, 0.4)';
        
        const centerX = width / 2;
        const centerY = height / 2;
        const pulseRadius = 30 + Math.sin(phase) * 10;
        
        // Inner circle
        ctx.beginPath();
        ctx.arc(centerX, centerY, pulseRadius, 0, Math.PI * 2);
        const gradient = ctx.createRadialGradient(centerX, centerY, 5, centerX, centerY, pulseRadius);
        gradient.addColorStop(0, 'rgba(245, 158, 11, 0.8)');
        gradient.addColorStop(0.5, 'rgba(168, 85, 247, 0.3)');
        gradient.addColorStop(1, 'rgba(245, 158, 11, 0)');
        ctx.fillStyle = gradient;
        ctx.fill();

        // Orbiting rings
        ctx.shadowBlur = 0;
        ctx.lineWidth = 1.5;
        ctx.strokeStyle = 'rgba(245, 158, 11, 0.25)';
        ctx.beginPath();
        ctx.arc(centerX, centerY, 55, 0, Math.PI * 2);
        ctx.stroke();

        ctx.strokeStyle = 'rgba(168, 85, 247, 0.4)';
        ctx.beginPath();
        ctx.arc(
          centerX + Math.cos(phase) * 55, 
          centerY + Math.sin(phase) * 55, 
          6, 0, Math.PI * 2
        );
        ctx.fillStyle = 'var(--accent-purple)';
        ctx.fill();
        ctx.stroke();

        phase += 0.04;

      } else {
        // "Idle" or "Error" state: gentle, low-amplitude flat line
        const amplitude = status === 'error' ? 2 : 4;
        const waveColor = status === 'error' ? 'rgba(239, 68, 68, 0.3)' : 'rgba(255, 255, 255, 0.15)';
        
        ctx.shadowBlur = 0;
        drawWave(ctx, width, height, phase, amplitude, waveColor, 1.5);
        
        phase += 0.02; // slow drift
      }

      animationRef.current = requestAnimationFrame(render);
    };

    render();

    return () => {
      cancelAnimationFrame(animationRef.current);
      window.removeEventListener('resize', resizeCanvas);
    };
  }, [status, audioManager]);

  // Helper function to draw organic sine waves
  const drawWave = (ctx, width, height, phase, amplitude, color, lineWidth) => {
    ctx.lineWidth = lineWidth;
    ctx.strokeStyle = color;
    ctx.beginPath();

    const centerY = height / 2;

    for (let x = 0; x < width; x++) {
      // Create a nice falloff towards the edges (sine envelope)
      const envelope = Math.sin((x / width) * Math.PI);
      // Main wave formula
      const y = centerY + Math.sin(x * 0.02 + phase) * amplitude * envelope;
      
      if (x === 0) {
        ctx.moveTo(x, y);
      } else {
        ctx.lineTo(x, y);
      }
    }
    ctx.stroke();
  };

  return (
    <div className="visualizer-wrapper">
      <canvas ref={canvasRef} className="visualizer-canvas" />
      <style>{`
        .visualizer-wrapper {
          position: relative;
          width: 100%;
          height: 180px;
          border-radius: 16px;
          background: rgba(0, 0, 0, 0.15);
          border: 1px solid rgba(255, 255, 255, 0.03);
          overflow: hidden;
          margin: 1.5rem 0;
        }
        
        .visualizer-canvas {
          width: 100%;
          height: 100%;
          display: block;
        }
      `}</style>
    </div>
  );
};

export default Visualizer;
