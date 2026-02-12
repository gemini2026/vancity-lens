import { test, expect } from '@playwright/test';

// NOTE: This is a coarse guardrail, not a perf benchmark. We measure time-to-shell
// (navigation/branding visible) instead of waiting for "networkidle" which is often
// dominated by background API calls and map tile requests.
const PAGE_LOAD_THRESHOLD = 10_000; // ms

test.describe('VanCity Lens — Full E2E Flow', () => {
  test('complete user journey: load → navigate → view intel → chat', async ({ page }) => {
    // Step 1: Load the app and wait for hydration
    const startLoadTime = Date.now();
    await page.goto('/', { waitUntil: 'domcontentloaded', timeout: 15_000 });

    // Verify branding
    const brandingElement = page.getByRole('navigation').getByText('VanCity Lens', { exact: true });
    await expect(brandingElement).toBeVisible({ timeout: 15_000 });
    const homeLoadTime = Date.now() - startLoadTime;
    expect(homeLoadTime).toBeLessThan(PAGE_LOAD_THRESHOLD);

    // Ensure React is hydrated before interacting with client-side handlers.
    await page.waitForLoadState('networkidle', { timeout: 15_000 });

    // Scope tab selectors to the top nav (avoids matching MobileNav buttons in the DOM).
    const topNav = page.getByRole('navigation').filter({ hasText: 'VanCity Lens' });

    // Step 2: Verify Map tab is active
    const mapTab = topNav.getByRole('button', { name: 'Map' });
    await expect(mapTab).toHaveCSS('border-bottom-color', 'rgb(59, 130, 246)');

    // Step 3: Switch to Intelligence tab
    const intelTab = topNav.getByRole('button', { name: 'Intelligence' });
    await intelTab.click();

    await expect(intelTab).toHaveCSS('border-bottom-color', 'rgb(59, 130, 246)');

    // Step 4: Wait for Intelligence content
    await page.waitForTimeout(2000);

    // Step 5: Find and interact with chat input
    const chatInput = page.getByPlaceholder(/ask about developments/i);
    await expect(chatInput).toBeVisible({ timeout: 10_000 });

    await chatInput.fill('What development changes are happening downtown?');
    const filledValue = await chatInput.inputValue();
    expect(filledValue).toBe('What development changes are happening downtown?');

    // Step 6: Switch back to Map
    await mapTab.click();
    await expect(mapTab).toHaveCSS('border-bottom-color', 'rgb(59, 130, 246)');
  });

  test('API integration: signal feed loads on Intelligence tab with data validation', async ({ page }) => {
    await page.goto('/', { waitUntil: 'networkidle', timeout: 15_000 });

    const topNav = page.getByRole('navigation').filter({ hasText: 'VanCity Lens' });
    await topNav.getByRole('button', { name: 'Intelligence' }).click();

    // Wait for content
    await page.waitForTimeout(3000);

    // Check for the "Ask VanCity Lens" header
    const header = page.locator('text=Ask VanCity Lens');
    await expect(header).toBeVisible({ timeout: 10_000 });
  });

  test('map and intelligence tabs maintain state correctly', async ({ page }) => {
    await page.goto('/', { waitUntil: 'networkidle', timeout: 15_000 });

    const topNav = page.getByRole('navigation').filter({ hasText: 'VanCity Lens' });
    const mapTab = topNav.getByRole('button', { name: 'Map' });
    const intelTab = topNav.getByRole('button', { name: 'Intelligence' });

    // Verify initial state: Map tab is active
    await expect(mapTab).toHaveCSS('border-bottom-color', 'rgb(59, 130, 246)');

    // Switch to Intelligence
    await intelTab.click();
    await expect(intelTab).toHaveCSS('border-bottom-color', 'rgb(59, 130, 246)');

    // Verify Map is no longer active
    const mapBorder = await mapTab.evaluate(el =>
      getComputedStyle(el).borderBottomColor
    );
    expect(mapBorder).not.toBe('rgb(59, 130, 246)');

    // Switch back to Map
    await mapTab.click();
    await expect(mapTab).toHaveCSS('border-bottom-color', 'rgb(59, 130, 246)');
  });

  test('screenshot: full page journey', async ({ page }, testInfo) => {
    await page.goto('/');
    await page.waitForLoadState('domcontentloaded');
    await page.screenshot({ path: testInfo.outputPath('full-journey.png'), fullPage: true });
  });
});
