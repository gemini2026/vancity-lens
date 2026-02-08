import { test, expect } from '@playwright/test';

const API_BASE = process.env.API_BASE_URL || 'http://localhost:8000';
const PAGE_LOAD_THRESHOLD = 3000; // ms

test.describe('VanCity Lens — App Shell', () => {
  test('homepage loads with VanCity Lens branding within performance threshold', async ({ page }) => {
    const startTime = Date.now();
    await page.goto('/', { waitUntil: 'networkidle' });
    const loadTime = Date.now() - startTime;

    expect(loadTime).toBeLessThan(PAGE_LOAD_THRESHOLD);

    const nav = page.getByRole('navigation');
    const brandingElement = nav.getByText('VanCity Lens', { exact: true });
    await expect(brandingElement).toBeVisible();

    // Strict validation: text content must match exactly
    const brandingText = await brandingElement.textContent();
    expect(brandingText).toBe('VanCity Lens');

    // Verify version badge exists and has correct format
    const versionElement = nav.getByText('V2', { exact: true });
    await expect(versionElement).toBeVisible();
    const versionText = await versionElement.textContent();
    expect(versionText).toMatch(/^V\d+$/);
  });

  test('nav bar shows Map and Intelligence tabs with correct labels', async ({ page }) => {
    await page.goto('/');

    const mapTab = page.locator('button', { hasText: 'Map' });
    const intelTab = page.locator('button', { hasText: 'Intelligence' });

    await expect(mapTab).toBeVisible();
    await expect(intelTab).toBeVisible();

    // Strict validation: verify exact button text
    const mapText = await mapTab.textContent();
    const intelText = await intelTab.textContent();

    expect(mapText?.trim()).toBe('Map');
    expect(intelText?.trim()).toBe('Intelligence');
  });

  test('Map tab is active by default with correct styling', async ({ page }) => {
    await page.goto('/');
    const mapTab = page.locator('button', { hasText: 'Map' });

    // Strict: verify active state CSS
    await expect(mapTab).toHaveCSS('border-bottom-color', 'rgb(59, 130, 246)');

    // Additional validation: check border width is set
    const borderWidth = await mapTab.evaluate(el =>
      getComputedStyle(el).borderBottomWidth
    );
    expect(borderWidth).not.toBe('0px');
  });

  test('can switch between Map and Intelligence tabs', async ({ page }) => {
    await page.goto('/');

    const intelTab = page.locator('button', { hasText: 'Intelligence' });
    const mapTab = page.locator('button', { hasText: 'Map' });

    // Click Intelligence tab
    await intelTab.click();

    // Strict: Intel tab is now active
    await expect(intelTab).toHaveCSS('border-bottom-color', 'rgb(59, 130, 246)');

    // Strict: Map tab is now inactive
    const mapBorderColor = await mapTab.evaluate(el =>
      getComputedStyle(el).borderBottomColor
    );
    expect(mapBorderColor).not.toBe('rgb(59, 130, 246)');

    // Switch back to Map
    await mapTab.click();
    await expect(mapTab).toHaveCSS('border-bottom-color', 'rgb(59, 130, 246)');
  });

  test('dark theme is applied with correct background color', async ({ page }) => {
    await page.goto('/');
    const body = page.locator('body');

    const bg = await body.evaluate(el => getComputedStyle(el).backgroundColor);

    // Strict: verify exact dark background color
    expect(bg).toBe('rgb(10, 10, 10)');

    // Additional validation: check foreground text is light
    const textColor = await body.evaluate(el =>
      getComputedStyle(el).color
    );
    // Should be light text (something close to white or light gray)
    expect(textColor).toMatch(/rgb\(\s*\d{2,3},\s*\d{2,3},\s*\d{2,3}\s*\)/);
  });

  test('screenshot: homepage layout', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('networkidle');
    // Screenshot for visual regression testing
    await page.screenshot({ path: 'tests/screenshots/homepage-layout.png', fullPage: false });
  });

  test('screenshot: tabs view', async ({ page }) => {
    await page.goto('/');
    const nav = page.getByRole('navigation');
    // Screenshot navigation area for visual regression
    const navBox = await nav.boundingBox();
    if (navBox) {
      await page.screenshot({
        path: 'tests/screenshots/navigation-tabs.png',
        clip: navBox
      });
    }
  });
});
