import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { TickerPicker } from './TickerPicker';

const push = vi.hoisted(() => vi.fn());

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push }),
  useSearchParams: () => new URLSearchParams(),
}));

describe('TickerPicker', () => {
  it('offers a labelled field', () => {
    render(<TickerPicker ticker="XOM" />);

    expect(screen.getByLabelText('Stock ticker')).toBeInTheDocument();
  });

  it('starts from the ticker being shown', () => {
    render(<TickerPicker ticker="XOM" />);

    expect(screen.getByLabelText('Stock ticker')).toHaveValue('XOM');
  });

  it('puts the chosen ticker in the URL so the view can be shared', async () => {
    render(<TickerPicker ticker="XOM" />);

    await userEvent.clear(screen.getByLabelText('Stock ticker'));
    await userEvent.type(screen.getByLabelText('Stock ticker'), 'nvda');
    await userEvent.click(screen.getByRole('button', { name: 'Show holders' }));

    expect(push).toHaveBeenCalledWith('/institutional?ticker=NVDA');
  });

  it('ignores an empty submission rather than navigating nowhere', async () => {
    push.mockClear();
    render(<TickerPicker ticker="XOM" />);

    await userEvent.clear(screen.getByLabelText('Stock ticker'));
    await userEvent.click(screen.getByRole('button', { name: 'Show holders' }));

    expect(push).not.toHaveBeenCalled();
  });

  it('can be submitted from the keyboard alone', async () => {
    push.mockClear();
    render(<TickerPicker ticker="XOM" />);

    await userEvent.clear(screen.getByLabelText('Stock ticker'));
    await userEvent.type(screen.getByLabelText('Stock ticker'), 'cvx{Enter}');

    expect(push).toHaveBeenCalledWith('/institutional?ticker=CVX');
  });
});
