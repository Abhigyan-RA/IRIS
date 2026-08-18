import { expect, test } from '@playwright/test';

/**
 * The one journey covered end to end.
 *
 * A reader lands on the map and sees what moved, clicks through to find out what it
 * affects, checks whether professional money is positioned for it, confirms the
 * pipeline is being honest about how the data was obtained, and then asks a question
 * in plain words. Each screen has to hand off to the next for the product to be worth
 * anything, and only a real browser proves that.
 */
test.describe('the analyst journey', () => {
  test('runs from the risk map through to a cited answer', async ({ page }) => {
    // 1. Land on the map and see what changed.
    await page.goto('/risk-map');

    await expect(page.getByRole('region', { name: /Global risk map/ })).toBeVisible();
    const freightMarker = page.getByRole('link', { name: /FBX_Global/ });
    await expect(freightMarker).toContainText('+12.4%');
    await expect(page.getByRole('region', { name: /Top movers/ })).toContainText('Copper');

    // 2. Follow the largest mover to find out what it affects.
    await page.getByRole('link', { name: /Global: Copper/ }).click();

    await expect(page.getByRole('heading', { level: 1, name: 'Copper' })).toBeVisible();
    await expect(page.getByRole('region', { name: /Propagation map/ })).toContainText(
      'EV Battery Manufacturing',
    );
    await expect(page.getByText(/refined into stator coils/)).toBeVisible();
    await expect(page.getByText('18% of input cost')).toBeVisible();

    // 3. Check how professional money is positioned.
    await page.getByRole('link', { name: 'Institutional sentiment' }).click();

    await expect(page.getByRole('table')).toBeVisible();
    await expect(page.getByRole('rowheader')).toContainText('Bridgewater Associates');
    await expect(page.getByRole('table')).toContainText('+14.3%');
    await expect(page.getByRole('table')).toContainText('2026-06-30');

    // 4. Confirm the pipeline is honest about how the data was obtained.
    await page.getByRole('link', { name: 'Pipeline health' }).click();

    const auditLog = page.getByRole('region', { name: /Self-healing audit log/ });
    await expect(auditLog).toContainText('[WARNING]');
    await expect(auditLog).toContainText('[AUTO-HEALING]');
    await expect(auditLog).toContainText('[RESOLVED]');
    await expect(page.getByText('Repaired')).toBeVisible();

    // 5. Ask a question and get an answer with its sources.
    await page.getByRole('link', { name: 'Ask the data' }).click();

    // Type rather than fill: typing produces the events React listens for, and it
    // also proves the field is interactive rather than merely present, which is what
    // a reader experiences after the page hydrates.
    const question = page.getByLabel('Your question');
    await question.click();
    await question.pressSequentially('what is copper doing');
    await expect(page.getByRole('button', { name: 'Ask' })).toBeEnabled();
    await page.getByRole('button', { name: 'Ask' }).click();

    await expect(page.getByText(/Copper is 4.52 USD per pound/)).toBeVisible();
    await expect(
      page.getByRole('link', { name: 'https://www.investing.com/commodities/copper' }),
    ).toBeVisible();
    await expect(page.getByText(/Evidence current as at/)).toBeVisible();
  });

  test('is operable by keyboard alone, from the map to the ripple view', async ({ page }) => {
    await page.goto('/risk-map');

    // Tab until a map marker has focus, then follow it with Enter. A dashboard that
    // needs a mouse excludes anyone who cannot use one.
    for (let attempt = 0; attempt < 25; attempt += 1) {
      await page.keyboard.press('Tab');
      const focusedHref = await page.evaluate(
        () => document.activeElement?.getAttribute('href') ?? '',
      );
      if (focusedHref.startsWith('/ripple/')) {
        break;
      }
    }

    await page.keyboard.press('Enter');

    await expect(page.getByRole('region', { name: /Propagation map/ })).toBeVisible();
  });

  test('reports a failing API on the page instead of rendering an empty screen', async ({
    page,
  }) => {
    // Point the browser at a screen whose data cannot be fetched, by asking for an
    // entity the stub does not know. The screen must say what went wrong.
    await page.goto('/institutional?ticker=NOTSTUBBED');

    await expect(page.getByText(/could not be loaded|returned 404/)).toBeVisible();
  });
});
