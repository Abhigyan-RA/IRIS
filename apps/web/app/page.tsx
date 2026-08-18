import { redirect } from 'next/navigation';

/**
 * Application entry route.
 *
 * The risk map is the landing view, so the root simply sends the reader there rather
 * than duplicating the screen at two addresses.
 */
export default function HomePage(): never {
  redirect('/risk-map');
}
