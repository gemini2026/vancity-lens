import { test, expect } from '@playwright/test';

const API_BASE = process.env.API_BASE_URL || 'http://localhost:8000';

test.describe('VanCity Lens — App Shell', () => {
  test('homepage loads with VanCity Lens branding', async ({ page }) => {
    await page.goto('/');
    await expect(page.locator('text=VanCity Lens')).toBeVisible();
    await expect(page.locator('text=V2')).toBeVisible();
  });

  test('nav bar shows Map and Intelligence tabs', async ({ page }) => {
    await page.goto('/');
    const mapTab = page.locator('button', { hasText: 'Map' });
    const intelTab = page.locator('button', { hasText: 'Intelligence' });
    await expect(mapTab).toBeVisible();
    await expect(intelTab).toBeVisible();
  });

  test('Map tab is active by default', async ({ page }) => {
    await page.goto('/');
    const mapTab = page.locator('button', { hasText: 'Map' });
    // Active tab has blue bottom border
    await expect(mapTab).toHaveCSS('border-bottom-color', 'rgb(59, 130, 246)');
  });

  test('can switch between Map and Intelligence tabs', async ({ page }) => {
    await page.goto('/');
    const intelTab = page.locator('button', { hasText: 'Intelligence' });
    await intelTab.click();
    // Intel tab should now be active (blue border)
    await expect(intelTab).toHaveCSS('border-bottom-color', 'rgb(59, 130, 246)');
    // Map tab should be inactive
    const mapTab = page.locator('button', { hasText: 'Map' });
    await expect(mapTab).toHaveCSS('border-bottom-color', 'rgba(0, 0, 0, 0)');
  });

  test('dark theme is applied', async ({ page }) => {
    await page.goto('/');
    const body = page.locator('body');
    const bg = await body.evaluate(el => getComputedStyle(el).backgroundColor);
    // Should be dark (#0a0a0a = rgb(10, 10, 10))
    expect(bg).toBe('rgb(10, 10, 10)');
  });
});
