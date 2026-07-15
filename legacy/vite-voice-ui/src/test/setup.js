import '@testing-library/jest-dom/vitest';
import { vi } from 'vitest';

HTMLCanvasElement.prototype.getContext = vi.fn(() => ({
  arc: vi.fn(),
  beginPath: vi.fn(),
  clearRect: vi.fn(),
  createRadialGradient: () => ({ addColorStop: vi.fn() }),
  fill: vi.fn(),
  lineTo: vi.fn(),
  moveTo: vi.fn(),
  scale: vi.fn(),
  stroke: vi.fn(),
}));
