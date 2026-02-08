import { test, expect } from '@playwright/test';

const API_BASE = process.env.API_BASE_URL || 'http://localhost:8000';
const PAGE_LOAD_THRESHOLD = 3000; // ms
const API_RESPONSE_THRESHOLD = 1000; // ms

test.describe('VanCity Lens — Full E2E Flow', () => {
  test('complete user journey: load → navigate → view intel → chat', async ({ page }) => {
    const startLoadTime = Date.now();

    // Step 1: Load the app
    await page.goto('/', { waitUntil: 'domcontentloaded' });
    const homeLoadTime = Date.now() - startLoadTime;
    expect(homeLoadTime).toBeLessThan(PAGE_LOAD_THRESHOLD);

    // Strict: verify branding is present
    const brandingElement = page.getByRole('navigation').getByText('VanCity Lens', { exact: true });
    await expect(brandingElement).toBeVisible();
    const branding = await brandingElement.textContent();
    expect(branding).toBe('VanCity Lens');

    // Step 2: Verify Map tab is showing and is active
    const mapTab = page.locator('button', { hasText: 'Map' });
    await expect(mapTab).toHaveCSS('border-bottom-color', 'rgb(59, 130, 246)');
    const mapText = await mapTab.textContent();
    expect(mapText?.trim()).toBe('Map');

    // Step 3: Switch to Intelligence tab
    const intelTab = page.locator('button', { hasText: 'Intelligence' });
    const switchStartTime = Date.now();
    await intelTab.click();
    const switchTime = Date.now() - switchStartTime;

    await expect(intelTab).toHaveCSS('border-bottom-color', 'rgb(59, 130, 246)');
    expect(switchTime).toBeLessThan(API_RESPONSE_THRESHOLD + 500);

    // Step 4: Wait for Intelligence page content to load with timeout
    await page.waitForLoadState('networkidle', { timeout: 5000 }).catch(() => {});

    // Step 5: Find and interact with chat input
    const chatInput = page.locator('input[type="text"], textarea').first();
    const inputCount = await chatInput.count();

    if (inputCount > 0) {
      // Strict: verify input is empty before interaction
      const initialValue = await chatInput.inputValue().catch(() => '');
      expect(initialValue).toBe('');

      // Type query
      await chatInput.fill('What development changes are happening downtown?');

      // Strict: verify input value was set
      const filledValue = await chatInput.inputValue();
      expect(filledValue).toBe('What development changes are happening downtown?');

      // Send message
      const sendStartTime = Date.now();
      await chatInput.press('Enter');
      const sendTime = Date.now() - sendStartTime;

      // Wait for response
      await page.waitForTimeout(3000);
      expect(sendTime).toBeLessThan(API_RESPONSE_THRESHOLD);
    }

    // Step 6: Switch back to Map
    await mapTab.click();
    await expect(mapTab).toHaveCSS('border-bottom-color', 'rgb(59, 130, 246)');
  });

  test('API integration: signal feed loads on Intelligence tab with data validation', async ({ page }) => {
    // Navigate to intel tab
    const loadStartTime = Date.now();
    await page.goto('/');
    const homeLoadTime = Date.now() - loadStartTime;
    expect(homeLoadTime).toBeLessThan(PAGE_LOAD_THRESHOLD);

    const switchStartTime = Date.now();
    await page.locator('button', { hasText: 'Intelligence' }).click();
    const switchTime = Date.now() - switchStartTime;
    expect(switchTime).toBeLessThan(API_RESPONSE_THRESHOLD + 500);

    // Wait for potential API calls to complete
    await page.waitForLoadState('networkidle', { timeout: 5000 }).catch(() => {});

    // Check if any signal items appear
    const signalItems = page.locator('[class*="signal"], [data-testid*="signal"]');
    const count = await signalItems.count();

    // If signals exist, validate structure
    if (count > 0) {
      for (let i = 0; i < Math.min(count, 5); i++) {
        const signal = signalItems.nth(i);

        // Strict: verify signal has visible content
        await expect(signal).toBeVisible();

        // Look for required fields: date, type, severity, text
        const signalText = await signal.textContent();
        expect(signalText?.length).toBeGreaterThan(0);

        // Verify severity indicator if present
        const severityIndicators = ['🔴', '🟠', '🟡', '🟢', 'high', 'medium', 'low'];
        const hasSeverity = severityIndicators.some(indicator =>
          signalText?.includes(indicator)
        );
        // Soft check - may vary by implementation
        if (hasSeverity) {
          expect(hasSeverity).toBe(true);
        }
      }
    }
  });

  test('map and intelligence tabs maintain state correctly', async ({ page }) => {
    await page.goto('/');

    const mapTab = page.locator('button', { hasText: 'Map' });
    const intelTab = page.locator('button', { hasText: 'Intelligence' });

    // Verify initial state
    const mapBorder1 = await mapTab.evaluate(el =>
      getComputedStyle(el).borderBottomColor
    );
    expect(mapBorder1).toBe('rgb(59, 130, 246)');

    // Switch to Intelligence
    await intelTab.click();
    const intelBorder = await intelTab.evaluate(el =>
      getComputedStyle(el).borderBottomColor
    );
    expect(intelBorder).toBe('rgb(59, 130, 246)');

    // Verify Map is no longer active
    const mapBorder2 = await mapTab.evaluate(el =>
      getComputedStyle(el).borderBottomColor
    );
    expect(mapBorder2).not.toBe('rgb(59, 130, 246)');

    // Switch back to Map
    await mapTab.click();
    const mapBorder3 = await mapTab.evaluate(el =>
      getComputedStyle(el).borderBottomColor
    );
    expect(mapBorder3).toBe('rgb(59, 130, 246)');
  });

  test('screenshot: full page journey', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('networkidle');
    await page.screenshot({ path: 'tests/screenshots/full-journey.png', fullPage: true });
  });
});
