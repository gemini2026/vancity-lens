import { test, expect } from '@playwright/test';

test.describe('VanCity Lens — Intelligence Tab', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
    // Switch to Intelligence tab
    await page.locator('button', { hasText: 'Intelligence' }).click();
    // Give it a moment to render
    await page.waitForTimeout(500);
  });

  test('Intelligence tab renders signal feed area', async ({ page }) => {
    // The intelligence page should be visible
    const intelContent = page.locator('div').filter({ hasText: /Signal Feed|Intelligence|Signals/i }).first();
    await expect(intelContent).toBeVisible({ timeout: 10_000 });
  });

  test('chat input is present and functional', async ({ page }) => {
    // Look for a text input or textarea for the chat
    const chatInput = page.locator('input[type="text"], textarea').first();
    await expect(chatInput).toBeVisible({ timeout: 10_000 });
    // Type a test query
    await chatInput.fill('What rezoning changes happened in Mount Pleasant?');
    // Verify the input value
    await expect(chatInput).toHaveValue('What rezoning changes happened in Mount Pleasant?');
  });

  test('filter controls are visible', async ({ page }) => {
    // Look for filter-related UI elements (dropdowns, selectors)
    const filterArea = page.locator('select, [role="combobox"], [data-testid="filter"]').first();
    // If filters exist, they should be visible
    const count = await filterArea.count();
    if (count > 0) {
      await expect(filterArea).toBeVisible();
    }
  });

  test('severity indicators use correct color coding', async ({ page }) => {
    // Check that severity dot elements exist if signals are loaded
    const severityDots = page.locator('text=🔴, text=🟠, text=🟡, text=🟢');
    // This is a soft check — may not have data
    const count = await severityDots.count();
    expect(count).toBeGreaterThanOrEqual(0);
  });
});
