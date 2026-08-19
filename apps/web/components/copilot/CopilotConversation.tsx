'use client';

import { MessageCircle, RefreshCw, User } from 'lucide-react';
import { useEffect, useRef, useState, type ReactNode, type SyntheticEvent } from 'react';
import { askCopilot, type CopilotAnswer } from '../../lib/api';
import { describeFailure, type FriendlyFailure } from '../../lib/failures';
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
  const [failure, setFailure] = useState<FriendlyFailure | null>(null);
  const [lastQuestion, setLastQuestion] = useState<string | null>(null);

  /** Ref attached to the bottom of the conversation to scroll new content into view. */
  const bottomRef = useRef<HTMLDivElement>(null);
  /** Tracks the number of turns so we can scroll when a new one appears. */
  const prevTurnCountRef = useRef(0);

  // Scroll the latest turn into view whenever the turn list grows.
  useEffect(() => {
    if (turns.length > prevTurnCountRef.current) {
      bottomRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' });
    }
    prevTurnCountRef.current = turns.length;
  }, [turns]);

  // Scroll loading indicator into view when asking starts.
  useEffect(() => {
    if (isAsking) {
      bottomRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' });
    }
  }, [isAsking]);

  async function submitQuestion(question: string): Promise<void> {
    const cleaned = question.trim();
    if (cleaned === '' || isAsking) {
      return;
    }

    setTurns((existing) => [...existing, { role: 'reader', text: cleaned }]);
    setDraft('');
    setLastQuestion(cleaned);
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
      // The question stays in the transcript, so a reader can see what failed and retry it
      // without typing it again.
      setFailure(describeFailure(error));
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
          <div role="alert" className="rounded-card border border-rise bg-panel-inset p-3">
            <p className="text-sm font-medium text-ink">{failure.title}</p>
            <p className="mt-1 text-xs leading-relaxed text-ink-muted">{failure.detail}</p>
            {failure.retryable && lastQuestion !== null ? (
              <button
                type="button"
                onClick={() => {
                  void submitQuestion(lastQuestion);
                }}
                className="mt-2 inline-flex items-center gap-1.5 rounded-pill border border-hairline-strong px-2.5 py-1 text-label text-ink-muted uppercase hover:text-ink"
              >
                <RefreshCw aria-hidden="true" className="h-3 w-3" />
                Ask again
              </button>
            ) : null}
            <details className="mt-2">
              <summary className="cursor-pointer text-label text-ink-faint uppercase">
                Technical detail
              </summary>
              <p className="mt-1 font-mono text-xs break-words text-ink-faint">
                {failure.technical}
              </p>
            </details>
          </div>
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

        {/* Scroll anchor: always at the bottom of the conversation content. */}
        <div ref={bottomRef} aria-hidden="true" />
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
