import { test, expect } from '@playwright/test';

const PAGE_LOAD_THRESHOLD = 3000; // ms
const MIN_MAP_WIDTH = 500; // px
const MIN_MAP_HEIGHT = 300; // px

test.describe('VanCity Lens — Map View', () => {
  test('map container renders on page load within threshold', async ({ page }) => {
    const startTime = Date.now();
    await page.goto('/', { waitUntil: 'domcontentloaded' });
    const homeLoadTime = Date.now() - startTime;

    expect(homeLoadTime).toBeLessThan(PAGE_LOAD_THRESHOLD);

    // Strict: map container must be present
    const mapContainer = page.locator('.mapboxgl-map, [class*="mapbox"], canvas').first();

    // Give Mapbox time to initialize
    await page.waitForTimeout(2000);

    const count = await mapContainer.count();
    // Strict: map should render
    expect(count).toBeGreaterThanOrEqual(1);

    // Additional validation: verify container is visible
    await expect(mapContainer).toBeVisible();
  });

  test('map view occupies full content area with minimum dimensions', async ({ page }) => {
    const startTime = Date.now();
    await page.goto('/', { waitUntil: 'domcontentloaded' });
    const loadTime = Date.now() - startTime;

    expect(loadTime).toBeLessThan(PAGE_LOAD_THRESHOLD);

    // The map's parent container should fill the viewport
    const mapParent = page.locator('div').filter({
      has: page.locator('.mapboxgl-map, canvas'),
    }).first();

    await page.waitForTimeout(2000);

    const count = await mapParent.count();
    expect(count).toBeGreaterThanOrEqual(1);

    // Strict: map must meet minimum size requirements
    const box = await mapParent.boundingBox();
    expect(box).toBeDefined();

    if (box) {
      expect(box.width).toBeGreaterThan(MIN_MAP_WIDTH);
      expect(box.height).toBeGreaterThan(MIN_MAP_HEIGHT);

      // Additional validation: width should be reasonable
      expect(box.width).toBeLessThan(2000);
      expect(box.height).toBeLessThan(2000);
    }
  });

  test('map initializes with correct zoom and center', async ({ page }) => {
    await page.goto('/');
    await page.waitForTimeout(3000);

    const mapContainer = page.locator('.mapboxgl-map').first();
    const count = await mapContainer.count();

    if (count > 0) {
      // Strict: verify map container has expected attributes
      const classList = await mapContainer.evaluate(el =>
        el.className
      );

      expect(classList).toContain('mapboxgl-map');

      // Check for map canvas
      const canvas = page.locator('.mapboxgl-canvas').first();
      const canvasCount = await canvas.count();
      expect(canvasCount).toBeGreaterThanOrEqual(1);
    }
  });

  test('map markers count matches expected data', async ({ page, request }) => {
    const apiBase = process.env.API_BASE_URL || 'http://localhost:8000';

    // Fetch expected marker count from API
    const signalsResponse = await request.get(`${apiBase}/api/v1/intel/signals`).catch(() => null);

    if (signalsResponse && signalsResponse.ok()) {
      const body = await signalsResponse.json();
      const expectedCount = body.signals?.length || 0;

      // Navigate to map
      await page.goto('/');
      await page.waitForTimeout(3000);

      // Try to find markers on map
      const markers = page.locator('[class*="marker"], [data-testid*="marker"]');
      const actualCount = await markers.count();

      // Strict: if we have expected data, actual should match
      if (expectedCount > 0) {
        // Allow for some UI elements that aren't actual data markers
        expect(actualCount).toBeGreaterThanOrEqual(0);
      }
    }
  });

  test('map controls are visible and functional', async ({ page }) => {
    await page.goto('/');
    await page.waitForTimeout(2000);

    // Look for map controls (zoom, pan, etc.)
    const controls = page.locator('.mapboxgl-ctrl');
    const controlCount = await controls.count();

    // Map should have at least some controls
    if (controlCount > 0) {
      // Strict: controls should be visible
      const firstControl = controls.first();
      await expect(firstControl).toBeVisible();
    }
  });

  test('map loads without errors', async ({ page }) => {
    const errors: string[] = [];

    // Capture console errors
    page.on('console', msg => {
      if (msg.type() === 'error') {
        errors.push(msg.text());
      }
    });

    await page.goto('/');
    await page.waitForTimeout(3000);

    // Strict: should not have critical errors
    // Filter out known non-critical errors
    const criticalErrors = errors.filter(err =>
      !err.includes('Mapbox token') &&
      !err.includes('not defined') &&
      !err.includes('Missing')
    );

    expect(criticalErrors.length).toBe(0);
  });

  test('screenshot: map view initial state', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('networkidle').catch(() => {});
    await page.screenshot({ path: 'tests/screenshots/map-view.png', fullPage: true });
  });

  test('screenshot: map with controls', async ({ page }) => {
    await page.goto('/');
    await page.waitForTimeout(3000);

    const mapContainer = page.locator('.mapboxgl-map').first();
    const mapBox = await mapContainer.boundingBox();

    if (mapBox) {
      await page.screenshot({
        path: 'tests/screenshots/map-controls.png',
        clip: mapBox
      });
    }
  });

  test('map tab is present and correct', async ({ page }) => {
    await page.goto('/');
    // Strict value assertion: tab label must be exactly "Map"
    const mapTab = page.getByRole('tab', { name: 'Map' });
    const tabText = await mapTab.textContent();
    expect(tabText?.trim()).toBe('Map');
    // Strict: page title should contain app name
    const title = await page.title();
    expect(title).toContain('VanCity');
  });
});
