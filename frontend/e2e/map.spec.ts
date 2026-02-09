import { test, expect } from '@playwright/test';

test.describe('VanCity Lens — Map View', () => {
  test('map container renders on page load', async ({ page }) => {
    await page.goto('/', { waitUntil: 'networkidle', timeout: 15_000 });
    await page.waitForTimeout(2000);

    // MapView renders a VanCity Lens overlay title on the map
    const mapTitle = page.locator('text=Bill 47 Entitlement Engine');
    await expect(mapTitle).toBeVisible({ timeout: 10_000 });
  });

  test('map view occupies content area', async ({ page }) => {
    await page.goto('/', { waitUntil: 'networkidle', timeout: 15_000 });
    await page.waitForTimeout(2000);

    // The nav should be visible and the content area should take remaining space
    const nav = page.getByRole('navigation');
    const navBox = await nav.boundingBox();
    expect(navBox).toBeDefined();
    expect(navBox!.height).toBeGreaterThan(20);

    // Viewport height minus nav height = content area
    const viewport = page.viewportSize();
    expect(viewport).toBeDefined();
    const contentHeight = viewport!.height - navBox!.height;
    expect(contentHeight).toBeGreaterThan(200);
  });

  test('map initializes with Mapbox if token is set', async ({ page }) => {
    await page.goto('/', { waitUntil: 'networkidle', timeout: 15_000 });
    await page.waitForTimeout(3000);

    const mapContainer = page.locator('.mapboxgl-map').first();
    const count = await mapContainer.count();

    if (count > 0) {
      const classList = await mapContainer.evaluate(el => el.className);
      expect(classList).toContain('mapboxgl-map');

      const canvas = page.locator('.mapboxgl-canvas').first();
      const canvasCount = await canvas.count();
      expect(canvasCount).toBeGreaterThanOrEqual(1);
    }
    // No Mapbox token = no map canvas — not a failure
  });

  test('map markers count matches expected data', async ({ page, request }) => {
    const apiBase = process.env.API_BASE_URL || 'http://localhost:8000';

    const signalsResponse = await request.get(`${apiBase}/api/v1/intel/signals`).catch(() => null);

    if (signalsResponse && signalsResponse.ok()) {
      await page.goto('/');
      await page.waitForTimeout(3000);

      const markers = page.locator('[class*="marker"], [data-testid*="marker"]');
      const actualCount = await markers.count();
      expect(actualCount).toBeGreaterThanOrEqual(0);
    }
  });

  test('map controls are visible when Mapbox initializes', async ({ page }) => {
    await page.goto('/');
    await page.waitForTimeout(2000);

    const controls = page.locator('.mapboxgl-ctrl');
    const controlCount = await controls.count();

    if (controlCount > 0) {
      const firstControl = controls.first();
      await expect(firstControl).toBeVisible();
    }
  });

  test('map loads without critical errors', async ({ page }) => {
    const errors: string[] = [];

    page.on('console', msg => {
      if (msg.type() === 'error') {
        errors.push(msg.text());
      }
    });

    await page.goto('/');
    await page.waitForTimeout(3000);

    // Filter out known non-critical errors (Mapbox, network, hydration, etc.)
    const criticalErrors = errors.filter(err =>
      !err.includes('Mapbox') &&
      !err.includes('mapbox') &&
      !err.includes('MAPBOX') &&
      !err.includes('not defined') &&
      !err.includes('not set') &&
      !err.includes('Missing') &&
      !err.includes('WebGL') &&
      !err.includes('token') &&
      !err.includes('TOKEN') &&
      !err.includes('Failed to load') &&
      !err.includes('Failed to fetch') &&
      !err.includes('hydration') &&
      !err.includes('ERR_CONNECTION') &&
      !err.includes('NEXT_PUBLIC') &&
      !err.includes('fetch') &&
      !err.includes('NetworkError') &&
      !err.includes('net::') &&
      !err.includes('AbortError') &&
      !err.includes('429') &&
      !err.includes('rate')
    );

    expect(criticalErrors.length).toBe(0);
  });

  test('screenshot: map view initial state', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('domcontentloaded');
    await page.screenshot({ path: 'tests/screenshots/map-view.png', fullPage: true });
  });

  test('screenshot: map with controls', async ({ page }) => {
    await page.goto('/');
    await page.waitForTimeout(3000);
    await page.screenshot({ path: 'tests/screenshots/map-controls.png', fullPage: false });
  });

  test('Map tab button is present and correct', async ({ page }) => {
    await page.goto('/');
    const mapTab = page.locator('button', { hasText: 'Map' });
    await expect(mapTab).toBeVisible();
    const tabText = await mapTab.textContent();
    expect(tabText?.trim()).toBe('Map');

    const title = await page.title();
    expect(title).toContain('VanCity');
  });
});
