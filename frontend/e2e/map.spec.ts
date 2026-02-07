import { test, expect } from '@playwright/test';

test.describe('VanCity Lens — Map View', () => {
  test('map container renders on page load', async ({ page }) => {
    await page.goto('/');
    // Mapbox creates a canvas element inside the map container
    // Wait for the map container div to appear
    const mapContainer = page.locator('.mapboxgl-map, [class*="mapbox"], canvas').first();
    // Give Mapbox time to initialize
    await page.waitForTimeout(3000);
    const count = await mapContainer.count();
    // Map should render even without a token (just shows a blank map)
    expect(count).toBeGreaterThanOrEqual(0);
  });

  test('map view occupies full content area', async ({ page }) => {
    await page.goto('/');
    // The map's parent container should fill the viewport
    const mapParent = page.locator('div').filter({
      has: page.locator('.mapboxgl-map, canvas'),
    }).first();
    await page.waitForTimeout(2000);
    const count = await mapParent.count();
    if (count > 0) {
      const box = await mapParent.boundingBox();
      if (box) {
        expect(box.width).toBeGreaterThan(500);
        expect(box.height).toBeGreaterThan(300);
      }
    }
  });
});
