import type { ReactNode } from 'react';
import { CopilotConversation } from '../../../components/copilot/CopilotConversation';

/**
 * The Ask the Data screen.
 *
 * Rendered on the client because it is a conversation: the reader types, waits, and
 * reads, and each turn depends on the last.
 *
 * @returns The copilot screen.
 */
export default function CopilotPage(): ReactNode {
  return <CopilotConversation />;
}
