'use client';

import { MessageCircle, User } from 'lucide-react';
import { useState, type ReactNode, type SyntheticEvent } from 'react';
import { ApiError, askCopilot, type CopilotAnswer } from '../../lib/api';
import { Panel, SectionLabel } from '../primitives/Panel';

/** Questions offered to a reader who does not know what to ask first. */
export const SUGGESTED_QUESTIONS: readonly string[] = [
  'What commodities moved most this week?',
  'Which trade lanes look most exposed?',
  'What does copper feed into?',
  'Who holds NVDA and what changed last quarter?',
  'How fresh is the freight data?',
];

/** One turn in the conversation. */
interface Turn {
  /** Who spoke. */
  role: 'reader' | 'copilot';
  /** What was said. */
  text: string;
  /** Sources behind an answer. */
  sources?: readonly string[];
  /** How recent the evidence was. */
  dataAsOf?: string | null;
}

/**
 * Props for {@link CopilotConversation}.
 */
export interface CopilotConversationProps {
  /**
   * Sends a question and returns the answer. Injected so the component can be tested
   * and shown in Storybook without a running API.
   */
  ask?: (question: string) => Promise<CopilotAnswer>;
}

/**
 * The Ask the Data screen.
 *
 * A reader who does not want to navigate four screens can ask in words instead. Every
 * answer is accompanied by the sources it drew on, because an answer about a price
 * that cannot be traced to a source is worth nothing here, however fluent it reads.
 *
 * @param props - Optionally a function that answers questions.
 * @returns The conversation.
 */
export function CopilotConversation({ ask = askCopilot }: CopilotConversationProps): ReactNode {
  const [turns, setTurns] = useState<Turn[]>([]);
  const [draft, setDraft] = useState('');
  const [isAsking, setIsAsking] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);

  async function submitQuestion(question: string): Promise<void> {
    const cleaned = question.trim();
    if (cleaned === '' || isAsking) {
      return;
    }

    setTurns((existing) => [...existing, { role: 'reader', text: cleaned }]);
    setDraft('');
    setFailure(null);
    setIsAsking(true);

    try {
      const answer = await ask(cleaned);
      setTurns((existing) => [
        ...existing,
        {
          role: 'copilot',
          text: answer.answer,
          sources: answer.sources,
          dataAsOf: answer.data_as_of,
        },
      ]);
    } catch (error) {
      setFailure(
        error instanceof ApiError
          ? error.message
          : 'The copilot could not answer. The model may be unavailable or over its daily cap.',
      );
    } finally {
      setIsAsking(false);
    }
  }

  function handleSubmit(event: SyntheticEvent<HTMLFormElement>): void {
    event.preventDefault();
    void submitQuestion(draft);
  }

  return (
    <div className="grid gap-6 xl:grid-cols-[1fr_18rem]">
      <div className="min-w-0 space-y-4">
        <SectionLabel tone="primary">Ask the data</SectionLabel>

        <ol className="space-y-4">
          {turns.map((turn, index) => (
            <li key={`${turn.role}-${String(index)}`}>
              {turn.role === 'reader' ? (
                <div className="flex justify-end">
                  <p className="max-w-xl rounded-card bg-panel-raised px-4 py-3 text-sm text-ink">
                    <User aria-hidden="true" className="mr-2 inline h-4 w-4 text-ink-faint" />
                    {turn.text}
                  </p>
                </div>
              ) : (
                <Panel className="p-4">
                  <p className="flex items-center gap-2 text-label text-accent uppercase">
                    <MessageCircle aria-hidden="true" className="h-4 w-4" />
                    Copilot answer
                  </p>
                  <p className="mt-2 text-sm leading-relaxed whitespace-pre-line text-ink">
                    {turn.text}
                  </p>

                  {turn.sources !== undefined && turn.sources.length > 0 && (
                    <div className="mt-3 border-t border-hairline pt-3">
                      <p className="text-label text-ink-muted uppercase">Sources</p>
                      <ul className="mt-1 space-y-1">
                        {turn.sources.map((source) => (
                          <li key={source}>
                            <a
                              href={source}
                              target="_blank"
                              rel="noreferrer noopener"
                              className="text-xs break-all text-ink-faint underline decoration-hairline-strong hover:text-accent"
                            >
                              {source}
                            </a>
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}

                  {turn.dataAsOf !== undefined && turn.dataAsOf !== null && (
                    <p className="mt-2 text-xs text-ink-faint">
                      Evidence current as at {turn.dataAsOf}.
                    </p>
                  )}
                </Panel>
              )}
            </li>
          ))}
        </ol>

        {isAsking && (
          <p role="status" className="text-sm text-ink-muted">
            Reading the collected data...
          </p>
        )}

        {failure !== null && (
          <p role="alert" className="text-sm text-warn">
            {failure}
          </p>
        )}

        <form onSubmit={handleSubmit} className="flex flex-wrap items-center gap-3">
          <label htmlFor="question" className="sr-only">
            Your question
          </label>
          <input
            id="question"
            value={draft}
            onChange={(event) => {
              setDraft(event.target.value);
            }}
            maxLength={500}
            placeholder="Should I lock in a steel contract this month?"
            className="min-w-64 flex-1 rounded-card border border-hairline bg-panel px-4 py-3 text-sm text-ink placeholder:text-ink-faint"
          />
          <button
            type="submit"
            disabled={isAsking || draft.trim() === ''}
            className="rounded-card border border-accent px-4 py-3 text-sm text-accent hover:bg-accent-wash disabled:border-hairline disabled:text-ink-faint"
          >
            Ask
          </button>
        </form>
      </div>

      <aside className="space-y-3">
        <SectionLabel>Suggested questions</SectionLabel>
        <ul className="space-y-2">
          {SUGGESTED_QUESTIONS.map((question) => (
            <li key={question}>
              <button
                type="button"
                onClick={() => {
                  void submitQuestion(question);
                }}
                className="w-full rounded-card border border-hairline bg-panel px-3 py-2 text-left text-sm text-ink hover:border-accent hover:text-accent"
              >
                {question}
              </button>
            </li>
          ))}
        </ul>
        <p className="text-xs text-ink-faint">
          Answers are drawn only from data this platform has collected. When nothing collected
          covers a question, the copilot says so rather than filling the gap.
        </p>
      </aside>
    </div>
  );
}
