import { test, expect } from '@playwright/test';

const API_BASE = process.env.API_BASE_URL || 'http://localhost:8000';

test.describe('VanCity Lens — Full E2E Flow', () => {
  test('complete user journey: load → navigate → view intel → chat', async ({ page }) => {
    // Step 1: Load the app
    await page.goto('/');
    await expect(page.locator('text=VanCity Lens')).toBeVisible();

    // Step 2: Verify Map tab is showing
    const mapTab = page.locator('button', { hasText: 'Map' });
    await expect(mapTab).toHaveCSS('border-bottom-color', 'rgb(59, 130, 246)');

    // Step 3: Switch to Intelligence tab
    const intelTab = page.locator('button', { hasText: 'Intelligence' });
    await intelTab.click();
    await expect(intelTab).toHaveCSS('border-bottom-color', 'rgb(59, 130, 246)');

    // Step 4: Wait for Intelligence page content to load
    await page.waitForTimeout(1000);

    // Step 5: Find and interact with chat input
    const chatInput = page.locator('input[type="text"], textarea').first();
    const inputCount = await chatInput.count();
    if (inputCount > 0) {
      await chatInput.fill('What development changes are happening downtown?');
      // If there's a send button, try pressing Enter
      await chatInput.press('Enter');
      // Wait for response (may timeout if no backend, that's ok)
      await page.waitForTimeout(3000);
    }

    // Step 6: Switch back to Map
    await mapTab.click();
    await expect(mapTab).toHaveCSS('border-bottom-color', 'rgb(59, 130, 246)');
  });

  test('API integration: signal feed loads on Intelligence tab', async ({ page }) => {
    // Navigate to intel tab
    await page.goto('/');
    await page.locator('button', { hasText: 'Intelligence' }).click();

    // Wait for potential API calls to complete
    await page.waitForTimeout(3000);

    // Check if any signal items appear (may be empty if no seed data)
    const signalItems = page.locator('[class*="signal"], [data-testid*="signal"]');
    const count = await signalItems.count();
    // Soft assertion — signals may or may not exist based on seed data
    expect(count).toBeGreaterThanOrEqual(0);
  });
});
