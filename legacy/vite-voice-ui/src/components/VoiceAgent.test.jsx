import React from 'react';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import VoiceAgent from './VoiceAgent';


class MockWebSocket {
  static OPEN = 1;
  static instances = [];

  constructor(url) {
    this.url = url;
    this.readyState = 0;
    MockWebSocket.instances.push(this);
  }

  close() {
    this.readyState = 3;
    if (this.onclose) this.onclose();
  }

  send() {}
}


describe('VoiceAgent secure interaction flow', () => {
  beforeEach(() => {
    MockWebSocket.instances = [];
    vi.stubGlobal('WebSocket', MockWebSocket);
    vi.stubGlobal(
      'fetch',
      vi.fn()
        .mockResolvedValueOnce({
          ok: true,
          json: async () => ({ session_id: 'session-1', language: 'ar', expires_at: 9999999999 }),
        })
        .mockResolvedValueOnce({
          ok: true,
          json: async () => ({ status: 'confirmed' }),
        }),
    );
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('creates a session and requires explicit UI approval for exact actions', async () => {
    render(<VoiceAgent />);
    await waitFor(() => expect(fetch).toHaveBeenCalledWith('/api/session', expect.any(Object)));
    const eventSocket = MockWebSocket.instances.find((socket) => socket.url.endsWith('/api/ws'));
    expect(eventSocket).toBeDefined();

    act(() => {
      eventSocket.readyState = MockWebSocket.OPEN;
      eventSocket.onopen();
      eventSocket.onmessage({
        data: JSON.stringify({
          task_id: 'task-1',
          event_type: 'confirmation_needed',
          user_safe_summary: 'Transfer 10 SAR to Savings',
          details: { arguments: { amount: '10.00', destination: 'Savings' } },
        }),
      });
    });

    expect(screen.getByRole('alertdialog')).toHaveTextContent('Transfer 10 SAR to Savings');
    expect(screen.queryByText('Custom System Prompt')).not.toBeInTheDocument();
    fireEvent.change(screen.getByLabelText('Demo OTP'), { target: { value: '1111' } });
    fireEvent.click(screen.getByRole('button', { name: 'Approve exact action' }));
    await waitFor(() =>
      expect(fetch).toHaveBeenCalledWith(
        '/api/confirm-task',
        expect.objectContaining({
          body: JSON.stringify({ task_id: 'task-1', approved: true, otp_code: '1111' }),
        }),
      ),
    );
  });
});
