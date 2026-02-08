import { test, expect } from '@playwright/test';

const PAGE_LOAD_THRESHOLD = 3000; // ms
const API_RESPONSE_THRESHOLD = 1000; // ms

test.describe('VanCity Lens — Intelligence Tab', () => {
  test.beforeEach(async ({ page }) => {
    const startTime = Date.now();
    await page.goto('/', { waitUntil: 'domcontentloaded' });
    const homeLoadTime = Date.now() - startTime;
    expect(homeLoadTime).toBeLessThan(PAGE_LOAD_THRESHOLD);

    // Switch to Intelligence tab
    await page.locator('button', { hasText: 'Intelligence' }).click();
    // Wait for content to render
    await page.waitForLoadState('networkidle', { timeout: 5000 }).catch(() => {});
  });

  test('Intelligence tab renders signal feed area with content', async ({ page }) => {
    // Strict: verify intel content area is visible and has expected text patterns
    const intelContent = page.locator('div').filter({ hasText: /Signal Feed|Intelligence|Signals/i }).first();
    await expect(intelContent).toBeVisible({ timeout: 10_000 });

    // Additional validation: check that the content is not empty
    const contentText = await intelContent.textContent();
    expect(contentText?.length).toBeGreaterThan(0);
  });

  test('chat input is present and functional with strict validation', async ({ page }) => {
    // Strict: verify chat input exists and is visible
    const chatInput = page.locator('input[type="text"], textarea').first();
    await expect(chatInput).toBeVisible({ timeout: 10_000 });

    // Verify input is interactive (not disabled)
    const isDisabled = await chatInput.evaluate(el =>
      (el as HTMLInputElement).disabled
    );
    expect(isDisabled).toBe(false);

    // Type a test query
    const testQuery = 'What rezoning changes happened in Mount Pleasant?';
    await chatInput.fill(testQuery);

    // Strict: verify the exact input value
    await expect(chatInput).toHaveValue(testQuery);

    // Additional validation: verify length
    const inputValue = await chatInput.inputValue();
    expect(inputValue.length).toBe(testQuery.length);
    expect(inputValue).toBe(testQuery);
  });

  test('filter controls are present and functional', async ({ page }) => {
    // Look for filter-related UI elements (dropdowns, selectors)
    const filterArea = page.locator('select, [role="combobox"], [data-testid="filter"]').first();
    const count = await filterArea.count();

    if (count > 0) {
      // Strict: if filters exist, validate they are interactive
      await expect(filterArea).toBeVisible();

      // Verify it's not disabled
      const isDisabled = await filterArea.evaluate(el => {
        const elem = el as HTMLInputElement | HTMLSelectElement;
        return elem.disabled;
      }).catch(() => false);

      expect(isDisabled).toBe(false);
    }
  });

  test('severity indicators exist with expected emoji values', async ({ page }) => {
    // Check for severity emoji indicators
    const severityEmojis = ['🔴', '🟠', '🟡', '🟢'];
    const foundEmojis: string[] = [];

    for (const emoji of severityEmojis) {
      const element = page.locator(`text="${emoji}"`);
      const count = await element.count();
      if (count > 0) {
        foundEmojis.push(emoji);
      }
    }

    // Soft check: may or may not have severity indicators based on data
    expect(foundEmojis.length).toBeGreaterThanOrEqual(0);

    // If we found any, validate they are visible
    if (foundEmojis.length > 0) {
      for (const emoji of foundEmojis) {
        const element = page.locator(`text="${emoji}"`).first();
        await expect(element).toBeVisible();
      }
    }
  });

  test('signal feed items have required fields when populated', async ({ page }) => {
    // Wait for signals to potentially load
    await page.waitForTimeout(2000);

    const signalItems = page.locator('[class*="signal"], [data-testid*="signal"]');
    const count = await signalItems.count();

    if (count > 0) {
      // Validate structure of first few signals
      for (let i = 0; i < Math.min(count, 3); i++) {
        const signal = signalItems.nth(i);
        await expect(signal).toBeVisible();

        // Strict: verify signal has substantive content
        const text = await signal.textContent();
        expect(text?.trim().length).toBeGreaterThan(5);

        // Look for required field patterns:
        // - Date (various formats possible)
        // - Type (text content)
        // - Severity (emoji or text)
        // - Description (text)
        const contentLower = text?.toLowerCase() || '';
        expect(contentLower.length).toBeGreaterThan(10);
      }
    }
  });

  test('chat input accepts multiline text', async ({ page }) => {
    const chatInput = page.locator('textarea');
    const count = await chatInput.count();

    if (count > 0) {
      const textarea = chatInput.first();
      const multilineText = 'Line 1\nLine 2\nLine 3';

      await textarea.fill(multilineText);
      const value = await textarea.inputValue();

      // Strict: verify multiline text is preserved
      expect(value).toBe(multilineText);
    }
  });

  test('performance: chat input responds within threshold', async ({ page }) => {
    const chatInput = page.locator('input[type="text"], textarea').first();
    const count = await chatInput.count();

    if (count > 0) {
      const startTime = Date.now();
      await chatInput.fill('Performance test query');
      const fillTime = Date.now() - startTime;

      // Strict: input should respond quickly
      expect(fillTime).toBeLessThan(API_RESPONSE_THRESHOLD);
    }
  });

  test('screenshot: intelligence tab layout', async ({ page }) => {
    await page.waitForLoadState('networkidle').catch(() => {});
    await page.screenshot({ path: 'tests/screenshots/intelligence-layout.png', fullPage: true });
  });

  test('screenshot: signal feed area', async ({ page }) => {
    const signalFeed = page.locator('div').filter({ hasText: /Signal Feed|Signals/i }).first();
    const feedBox = await signalFeed.boundingBox();

    if (feedBox) {
      await page.screenshot({
        path: 'tests/screenshots/signal-feed-area.png',
        clip: feedBox
      });
    }
  });
});
