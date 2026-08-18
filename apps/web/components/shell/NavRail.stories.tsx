import type { Meta, StoryObj } from '@storybook/react-vite';
import { NavRail } from './NavRail';

const meta = {
  title: 'Shell/NavRail',
  component: NavRail,
  parameters: {
    nextjs: { appDirectory: true },
  },
} satisfies Meta<typeof NavRail>;

export default meta;

type Story = StoryObj<typeof meta>;

/** On the landing screen. */
export const OnRiskMap: Story = {
  args: { currentPath: '/risk-map' },
  render: (args) => (
    <div className="h-96">
      <NavRail {...args} />
    </div>
  ),
};

/** On the health screen, showing how the active item is marked. */
export const OnPipelineHealth: Story = {
  args: { currentPath: '/pipeline-health' },
  render: (args) => (
    <div className="h-96">
      <NavRail {...args} />
    </div>
  ),
};

/** On a nested route, which still marks its section. */
export const OnNestedRoute: Story = {
  args: { currentPath: '/ripple/Copper' },
  render: (args) => (
    <div className="h-96">
      <NavRail {...args} />
    </div>
  ),
};
