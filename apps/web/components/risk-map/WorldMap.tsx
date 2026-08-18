import type { ReactNode } from 'react';
import { geoNaturalEarth1, geoPath } from 'd3-geo';
import type { GeoProjection } from 'd3-geo';
import { feature } from 'topojson-client';
import type { Topology } from 'topojson-specification';
import type { FeatureCollection } from 'geojson';
import countries from 'world-atlas/countries-110m.json';

/**
 * The land outlines behind the risk map markers.
 *
 * The country boundaries come from `world-atlas`, the projection from `d3-geo`, and the
 * topology conversion from `topojson-client`. None of it is drawn by hand: a world map is
 * data, and the maintained libraries do the work.
 *
 * The projection is Natural Earth, which keeps continent shapes recognisable at small sizes
 * rather than stretching the poles the way a plain rectangular projection does.
 */

/** Viewport the paths are generated against. Markers are positioned in the same space. */
export const MAP_WIDTH = 960;
export const MAP_HEIGHT = 500;

/**
 * Convert the country topology into projected land, once.
 *
 * Converting and projecting costs a few milliseconds and never changes, so doing it per
 * render would be waste repeated on every price update. The projection is kept as well as
 * the paths, because markers must be placed by the same projection that drew the land.
 *
 * @returns One SVG path per country, and the projection used.
 */
function buildMap(): { paths: string[]; project: GeoProjection } {
  const topology = countries as unknown as Topology;
  const geometry = topology.objects.countries;
  if (geometry === undefined) {
    throw new Error('world-atlas topology has no countries object');
  }
  const land = feature(topology, geometry) as FeatureCollection;

  const project = geoNaturalEarth1().fitSize([MAP_WIDTH, MAP_HEIGHT], land);
  const toPath = geoPath(project);

  return {
    paths: land.features.map((country) => toPath(country)).filter((path) => path !== null),
    project,
  };
}

const { paths: LAND_PATHS, project: PROJECTION } = buildMap();

/**
 * Props for {@link WorldMap}.
 */
export interface WorldMapProps {
  /** Markers drawn on top of the land, positioned by the same projection. */
  children?: ReactNode;
}

/**
 * A world map, drawn from country boundary data.
 *
 * The map itself carries no information a reader needs, so it is hidden from assistive
 * technology: the markers on top of it hold the data, and each one states its region in
 * text.
 *
 * @param props - Markers to draw over the land.
 * @returns The map.
 */
export function WorldMap({ children }: WorldMapProps): ReactNode {
  return (
    <svg
      viewBox={`0 0 ${String(MAP_WIDTH)} ${String(MAP_HEIGHT)}`}
      className="h-full w-full"
      aria-hidden="true"
      data-testid="world-map"
    >
      <g>
        {LAND_PATHS.map((path, index) => (
          <path
            key={index}
            d={path}
            className="fill-panel-inset stroke-hairline-strong"
            strokeWidth={0.5}
          />
        ))}
      </g>
      {children}
    </svg>
  );
}

/**
 * Project a longitude and latitude into the map's coordinate space.
 *
 * Markers are placed with the same projection that drew the land, so a marker sits over the
 * region it describes rather than at a guessed percentage of the panel.
 *
 * @param longitude - Degrees east, negative for west.
 * @param latitude - Degrees north, negative for south.
 * @returns Coordinates in the map viewport, or null when the point cannot be projected.
 */
export function projectToMap(longitude: number, latitude: number): { x: number; y: number } | null {
  const point = PROJECTION([longitude, latitude]);
  if (point === null) {
    return null;
  }
  const [x, y] = point;
  return { x, y };
}
