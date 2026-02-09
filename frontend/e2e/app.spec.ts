import { test, expect } from '@playwright/test';

const PAGE_LOAD_THRESHOLD = 5000; // ms

test.describe('VanCity Lens — App Shell', () => {
  test('homepage loads with VanCity Lens branding within performance threshold', async ({ page }) => {
    const startTime = Date.now();
    await page.goto('/', { waitUntil: 'domcontentloaded' });
    const loadTime = Date.now() - startTime;

    expect(loadTime).toBeLessThan(PAGE_LOAD_THRESHOLD);

    const nav = page.getByRole('navigation');
    const brandingElement = nav.getByText('VanCity Lens', { exact: true });
    await expect(brandingElement).toBeVisible();

    const brandingText = await brandingElement.textContent();
    expect(brandingText).toBe('VanCity Lens');

    // Verify version badge exists
    const versionElement = nav.getByText('V2', { exact: true });
    await expect(versionElement).toBeVisible();
  });

  test('nav bar shows Map and Intelligence tabs with correct labels', async ({ page }) => {
    await page.goto('/');

    const mapTab = page.locator('button', { hasText: 'Map' });
    const intelTab = page.locator('button', { hasText: 'Intelligence' });

    await expect(mapTab).toBeVisible();
    await expect(intelTab).toBeVisible();

    const mapText = await mapTab.textContent();
    const intelText = await intelTab.textContent();

    expect(mapText?.trim()).toBe('Map');
    expect(intelText?.trim()).toBe('Intelligence');
  });

  test('Map tab is active by default with correct styling', async ({ page }) => {
    await page.goto('/');
    const mapTab = page.locator('button', { hasText: 'Map' });

    // Active tab has blue border-bottom
    await expect(mapTab).toHaveCSS('border-bottom-color', 'rgb(59, 130, 246)');
  });

  test('can switch between Map and Intelligence tabs', async ({ page }) => {
    await page.goto('/');

    const intelTab = page.locator('button', { hasText: 'Intelligence' });
    const mapTab = page.locator('button', { hasText: 'Map' });

    // Click Intelligence tab
    await intelTab.click();

    // Intel tab is now active
    await expect(intelTab).toHaveCSS('border-bottom-color', 'rgb(59, 130, 246)');

    // Map tab is now inactive (transparent border)
    const mapBorderColor = await mapTab.evaluate(el =>
      getComputedStyle(el).borderBottomColor
    );
    expect(mapBorderColor).not.toBe('rgb(59, 130, 246)');

    // Switch back to Map
    await mapTab.click();
    await expect(mapTab).toHaveCSS('border-bottom-color', 'rgb(59, 130, 246)');
  });

  test('dark theme is applied with correct background color', async ({ page }) => {
    // Emulate dark color scheme so system theme resolves to dark
    await page.emulateMedia({ colorScheme: 'dark' });
    await page.goto('/');

    const body = page.locator('body');
    // Wait for theme to apply
    await page.waitForTimeout(500);

    const bg = await body.evaluate(el => getComputedStyle(el).backgroundColor);

    // Dark mode bg-primary is #0a0a0a = rgb(10, 10, 10)
    expect(bg).toBe('rgb(10, 10, 10)');
  });

  test('screenshot: homepage layout', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('domcontentloaded');
    await page.screenshot({ path: 'tests/screenshots/homepage-layout.png', fullPage: false });
  });

  test('screenshot: tabs view', async ({ page }) => {
    await page.goto('/');
    const nav = page.getByRole('navigation');
    const navBox = await nav.boundingBox();
    if (navBox) {
      await page.screenshot({
        path: 'tests/screenshots/navigation-tabs.png',
        clip: navBox
      });
    }
  });
});
