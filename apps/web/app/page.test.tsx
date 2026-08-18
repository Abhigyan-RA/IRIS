import { describe, expect, it, vi } from 'vitest';
import HomePage from './page';

const redirect = vi.hoisted(() => vi.fn());

vi.mock('next/navigation', () => ({ redirect }));

describe('HomePage', () => {
  it('sends the reader to the risk map, which is the landing view', () => {
    HomePage();

    expect(redirect).toHaveBeenCalledWith('/risk-map');
  });
});
