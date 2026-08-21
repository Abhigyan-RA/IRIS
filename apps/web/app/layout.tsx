import type { Metadata } from 'next';
import type { ReactNode } from 'react';
import './globals.css';

export const metadata: Metadata = {
  title: 'Shadow CPI',
  description:
    'Alternative data intelligence: daily freight, energy, metals, agriculture, and institutional signals',
};

/**
 * Props for the root layout.
 */
interface RootLayoutProps {
  /** Page content rendered inside the document body. */
  children: ReactNode;
}

/**
 * Applies the stored theme before the first paint.
 *
 * Without this, the document renders dark and then switches once React has mounted,
 * which a reader who chose light sees as a flash of the wrong colours. Only an
 * explicit stored choice is honoured, matching the control in the top bar, and dark
 * is the default the interface is designed for. It reads the same storage key the
 * control writes, and must stay in step with it.
 */
const THEME_BOOTSTRAP = `(function(){try{var t=localStorage.getItem('shadow-cpi-theme')==='light'?'light':'dark';document.documentElement.dataset.theme=t;}catch(e){document.documentElement.dataset.theme='dark';}})();`;

/**
 * Root layout wrapping every dashboard route.
 *
 * @param props - Layout props containing the routed page content.
 * @returns The HTML document shell.
 */
export default function RootLayout({ children }: RootLayoutProps): ReactNode {
  return (
    // suppressHydrationWarning applies to this element only. Browser extensions
    // commonly add attributes to the root element before React loads, which React then
    // reports as a mismatch it cannot patch. The theme script below also sets an
    // attribute here for the same reason. Suppressing it keeps a real mismatch inside
    // the application visible, because the suppression does not extend to children.
    <html lang="en" data-theme="dark" suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: THEME_BOOTSTRAP }} />
      </head>
      <body>{children}</body>
    </html>
  );
}
