import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { MAP_HEIGHT, MAP_WIDTH, WorldMap, projectToMap } from './WorldMap';

describe('WorldMap', () => {
  it('draws land from the boundary data rather than a placeholder', () => {
    render(<WorldMap />);

    const paths = screen.getByTestId('world-map').querySelectorAll('path');
    expect(paths.length).toBeGreaterThan(50);
  });

  it('is hidden from assistive technology, since the markers carry the data', () => {
    render(<WorldMap />);

    expect(screen.getByTestId('world-map')).toHaveAttribute('aria-hidden', 'true');
  });

  it('renders markers passed to it on top of the land', () => {
    render(
      <WorldMap>
        <circle data-testid="marker" cx={10} cy={10} r={4} />
      </WorldMap>,
    );

    expect(screen.getByTestId('marker')).toBeInTheDocument();
  });

  it('scales to its container rather than a fixed pixel size', () => {
    render(<WorldMap />);

    const map = screen.getByTestId('world-map');
    expect(map).toHaveAttribute('viewBox', `0 0 ${String(MAP_WIDTH)} ${String(MAP_HEIGHT)}`);
    expect(map).toHaveClass('h-full');
  });
});

describe('projectToMap', () => {
  it('places a longitude and latitude inside the map', () => {
    const point = projectToMap(-74, 40.7);

    expect(point).not.toBeNull();
    expect(point?.x).toBeGreaterThan(0);
    expect(point?.x).toBeLessThan(MAP_WIDTH);
    expect(point?.y).toBeGreaterThan(0);
    expect(point?.y).toBeLessThan(MAP_HEIGHT);
  });

  it('places eastern longitudes to the right of western ones', () => {
    const newYork = projectToMap(-74, 40.7);
    const shanghai = projectToMap(121.5, 31.2);

    expect(shanghai?.x ?? 0).toBeGreaterThan(newYork?.x ?? 0);
  });

  it('places northern latitudes above southern ones', () => {
    const london = projectToMap(0, 51.5);
    const capeTown = projectToMap(18.4, -33.9);

    expect(london?.y ?? 0).toBeLessThan(capeTown?.y ?? 0);
  });
});
