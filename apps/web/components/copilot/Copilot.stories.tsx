import type { Meta, StoryObj } from '@storybook/react-vite';
import type { CopilotAnswer } from '../../lib/api';
import { ApiError } from '../../lib/api';
import { CopilotConversation } from './CopilotConversation';

const GROUNDED_ANSWER: CopilotAnswer = {
  answer:
    'Copper is 4.52 USD per pound, up 1.8 percent since the previous published price. It feeds stator coils, which electric vehicle manufacturing depends on.',
  sources: [
    'https://www.investing.com/commodities/copper',
    'https://www.sec.gov/edgar/browse/?CIK=0001350694',
  ],
  data_as_of: '2026-08-15T12:00:00Z',
};

const meta = {
  title: 'Screens/Copilot',
  component: CopilotConversation,
} satisfies Meta<typeof CopilotConversation>;

export default meta;

type Story = StoryObj<typeof meta>;

/** Ready for a question, with suggestions offered. */
export const Empty: Story = {
  args: { ask: () => Promise.resolve(GROUNDED_ANSWER) },
};

/** An answer with the sources it drew on. Click a suggestion to see it. */
export const Answers: Story = {
  args: { ask: () => Promise.resolve(GROUNDED_ANSWER) },
};

/** A question nothing collected covers, answered honestly. */
export const NoData: Story = {
  args: {
    ask: () =>
      Promise.resolve({
        answer:
          'I do not have data covering that question yet. Nothing in the collected prices, supply-chain relationships, or filings matches it.',
        sources: [],
        data_as_of: null,
      }),
  },
};

/** The model is unavailable or over its daily cap. */
export const Failing: Story = {
  args: {
    ask: () => Promise.reject(new ApiError(503, 'The daily model call cap has been reached')),
  },
};

/** An answer that never arrives, showing the working state. */
export const Working: Story = {
  args: {
    ask: () => new Promise<CopilotAnswer>(() => undefined),
  },
};
