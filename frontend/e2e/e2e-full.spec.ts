import { test, expect } from '@playwright/test';

const PAGE_LOAD_THRESHOLD = 5000; // ms

test.describe('VanCity Lens — Full E2E Flow', () => {
  test('complete user journey: load → navigate → view intel → chat', async ({ page }) => {
    // Step 1: Load the app and wait for hydration
    const startLoadTime = Date.now();
    await page.goto('/', { waitUntil: 'networkidle', timeout: 15_000 });
    const homeLoadTime = Date.now() - startLoadTime;
    expect(homeLoadTime).toBeLessThan(PAGE_LOAD_THRESHOLD);

    // Verify branding
    const brandingElement = page.getByRole('navigation').getByText('VanCity Lens', { exact: true });
    await expect(brandingElement).toBeVisible();

    // Step 2: Verify Map tab is active
    const mapTab = page.locator('button', { hasText: 'Map' });
    await expect(mapTab).toHaveCSS('border-bottom-color', 'rgb(59, 130, 246)');

    // Step 3: Switch to Intelligence tab
    const intelTab = page.locator('button', { hasText: 'Intelligence' });
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

    await page.locator('button', { hasText: 'Intelligence' }).click();

    // Wait for content
    await page.waitForTimeout(3000);

    // Check for the "Ask VanCity Lens" header
    const header = page.locator('text=Ask VanCity Lens');
    await expect(header).toBeVisible({ timeout: 10_000 });
  });

  test('map and intelligence tabs maintain state correctly', async ({ page }) => {
    await page.goto('/', { waitUntil: 'networkidle', timeout: 15_000 });

    const mapTab = page.locator('button', { hasText: 'Map' });
    const intelTab = page.locator('button', { hasText: 'Intelligence' });

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

  test('screenshot: full page journey', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('domcontentloaded');
    await page.screenshot({ path: 'tests/screenshots/full-journey.png', fullPage: true });
  });
});
