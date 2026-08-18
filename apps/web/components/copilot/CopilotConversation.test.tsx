import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { ApiError, type CopilotAnswer } from '../../lib/api';
import { CopilotConversation, SUGGESTED_QUESTIONS } from './CopilotConversation';

function answer(overrides: Partial<CopilotAnswer> = {}): CopilotAnswer {
  return {
    answer: 'Copper is 4.52 USD per pound, up 1.8 percent since the previous close.',
    sources: ['https://www.investing.com/commodities/copper'],
    data_as_of: '2026-08-15T12:00:00Z',
    ...overrides,
  };
}

describe('CopilotConversation', () => {
  it('shows the question and then the answer', async () => {
    const ask = vi.fn().mockResolvedValue(answer());
    render(<CopilotConversation ask={ask} />);

    await userEvent.type(screen.getByLabelText('Your question'), 'what is copper doing');
    await userEvent.click(screen.getByRole('button', { name: 'Ask' }));

    expect(screen.getByText('what is copper doing')).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getByText(/Copper is 4.52 USD per pound/)).toBeInTheDocument();
    });
  });

  it('lists the sources behind an answer, so a claim can be checked', async () => {
    const ask = vi.fn().mockResolvedValue(answer());
    render(<CopilotConversation ask={ask} />);

    await userEvent.type(screen.getByLabelText('Your question'), 'what is copper doing');
    await userEvent.click(screen.getByRole('button', { name: 'Ask' }));

    await waitFor(() => {
      expect(
        screen.getByRole('link', { name: 'https://www.investing.com/commodities/copper' }),
      ).toBeInTheDocument();
    });
  });

  it('says how recent the evidence was', async () => {
    const ask = vi.fn().mockResolvedValue(answer());
    render(<CopilotConversation ask={ask} />);

    await userEvent.type(screen.getByLabelText('Your question'), 'what is copper doing');
    await userEvent.click(screen.getByRole('button', { name: 'Ask' }));

    await waitFor(() => {
      expect(screen.getByText(/Evidence current as at 2026-08-15/)).toBeInTheDocument();
    });
  });

  it('reports an answer that had no data behind it without pretending otherwise', async () => {
    const ask = vi.fn().mockResolvedValue(
      answer({
        answer: 'I do not have data covering that question yet.',
        sources: [],
        data_as_of: null,
      }),
    );
    render(<CopilotConversation ask={ask} />);

    await userEvent.type(screen.getByLabelText('Your question'), 'price of unobtainium');
    await userEvent.click(screen.getByRole('button', { name: 'Ask' }));

    await waitFor(() => {
      expect(screen.getByText(/I do not have data covering/)).toBeInTheDocument();
    });
    expect(screen.queryByText('Sources')).not.toBeInTheDocument();
  });

  it('will not send an empty question', () => {
    const ask = vi.fn();
    render(<CopilotConversation ask={ask} />);

    expect(screen.getByRole('button', { name: 'Ask' })).toBeDisabled();
    expect(ask).not.toHaveBeenCalled();
  });

  it('offers suggested questions and asks one when it is clicked', async () => {
    const ask = vi.fn().mockResolvedValue(answer());
    render(<CopilotConversation ask={ask} />);

    const suggestion = SUGGESTED_QUESTIONS[0] ?? '';
    await userEvent.click(screen.getByRole('button', { name: suggestion }));

    expect(ask).toHaveBeenCalledWith(suggestion);
  });

  it('says it is working while an answer is being prepared', async () => {
    let release: ((value: CopilotAnswer) => void) | undefined;
    const ask = vi.fn().mockReturnValue(
      new Promise<CopilotAnswer>((resolve) => {
        release = resolve;
      }),
    );
    render(<CopilotConversation ask={ask} />);

    await userEvent.type(screen.getByLabelText('Your question'), 'what is copper doing');
    await userEvent.click(screen.getByRole('button', { name: 'Ask' }));

    expect(screen.getByRole('status')).toHaveTextContent('Reading the collected data');
    release?.(answer());
  });

  it('reports a failure as an alert rather than silently doing nothing', async () => {
    const ask = vi
      .fn()
      .mockRejectedValue(new ApiError(503, 'The daily model call cap has been reached'));
    render(<CopilotConversation ask={ask} />);

    await userEvent.type(screen.getByLabelText('Your question'), 'what is copper doing');
    await userEvent.click(screen.getByRole('button', { name: 'Ask' }));

    await waitFor(() => {
      expect(screen.getByRole('alert')).toHaveTextContent('daily model call cap');
    });
  });

  it('keeps the earlier turns when a later question fails', async () => {
    const ask = vi
      .fn()
      .mockResolvedValueOnce(answer())
      .mockRejectedValueOnce(new ApiError(503, 'model unavailable'));
    render(<CopilotConversation ask={ask} />);

    await userEvent.type(screen.getByLabelText('Your question'), 'first question');
    await userEvent.click(screen.getByRole('button', { name: 'Ask' }));
    await waitFor(() => {
      expect(screen.getByText(/Copper is 4.52/)).toBeInTheDocument();
    });

    await userEvent.type(screen.getByLabelText('Your question'), 'second question');
    await userEvent.click(screen.getByRole('button', { name: 'Ask' }));

    await waitFor(() => {
      expect(screen.getByRole('alert')).toBeInTheDocument();
    });
    expect(screen.getByText(/Copper is 4.52/)).toBeInTheDocument();
  });

  it('clears the field after asking, ready for the next question', async () => {
    const ask = vi.fn().mockResolvedValue(answer());
    render(<CopilotConversation ask={ask} />);

    await userEvent.type(screen.getByLabelText('Your question'), 'what is copper doing');
    await userEvent.click(screen.getByRole('button', { name: 'Ask' }));

    await waitFor(() => {
      expect(screen.getByLabelText('Your question')).toHaveValue('');
    });
  });
});
