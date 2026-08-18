import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { StatusDot } from './StatusDot';

describe('StatusDot', () => {
  it('describes its status to assistive technology', () => {
    render(<StatusDot status="healthy" label="Freight and shipping" />);

    expect(screen.getByRole('img', { name: 'Freight and shipping: healthy' })).toBeInTheDocument();
  });

  it('uses the positive colour when healthy', () => {
    render(<StatusDot status="healthy" label="Freight" />);

    expect(screen.getByRole('img')).toHaveClass('bg-fall');
  });

  it('uses the warning colour when degraded', () => {
    render(<StatusDot status="degraded" label="Energy" />);

    expect(screen.getByRole('img')).toHaveClass('bg-warn');
  });

  it('uses the alert colour when failed', () => {
    render(<StatusDot status="failed" label="Oil price feed" />);

    expect(screen.getByRole('img')).toHaveClass('bg-rise');
  });

  it('uses the accent colour when live', () => {
    render(<StatusDot status="live" label="Aggregate health" />);

    expect(screen.getByRole('img')).toHaveClass('bg-accent');
  });

  it('does not rely on colour alone to carry the status', () => {
    render(<StatusDot status="degraded" label="Energy" />);

    expect(screen.getByRole('img')).toHaveAccessibleName('Energy: degraded');
  });
});
