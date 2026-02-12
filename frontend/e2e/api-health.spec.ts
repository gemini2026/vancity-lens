import { test, expect } from '@playwright/test';

// Local docker-compose exposes API at http://localhost:8080 (container listens on :8000).
const API_BASE = process.env.API_BASE_URL || 'http://localhost:8080';
const PERFORMANCE_THRESHOLD_API = 2000; // ms

// API-only tests — skip on mobile-chrome since they don't test mobile UI
test.describe('VanCity Lens — API Health', () => {
  test.beforeEach(({}, testInfo) => {
    test.skip(testInfo.project.name === 'mobile-chrome', 'API tests only need one browser');
  });

  test('backend health endpoint returns ok', async ({ request }) => {
    const startTime = Date.now();
    const response = await request.get(`${API_BASE}/health`);
    const responseTime = Date.now() - startTime;

    expect(response.status()).toBe(200);
    expect(responseTime).toBeLessThan(PERFORMANCE_THRESHOLD_API);

    const body = await response.json();
    expect(body).toHaveProperty('status');
    expect(body.status).toBe('ok');
  });

  test('CORS headers present for frontend origin', async ({ request }) => {
    const response = await request.get(`${API_BASE}/health`, {
      headers: {
        Origin: 'http://localhost:3000',
      },
    });

    expect(response.status()).toBe(200);
    expect(response.headers()['access-control-allow-origin']).toBeDefined();
  });

  test('signals endpoint responds with correct data structure', async ({ request }) => {
    const response = await request.get(`${API_BASE}/api/v1/intel/signals`);

    expect(response.status()).toBe(200);

    const body = await response.json();
    expect(body).toHaveProperty('signals');
    expect(body).toHaveProperty('total_count');
    expect(body).toHaveProperty('has_more');

    expect(typeof body.total_count).toBe('number');
    expect(body.total_count).toBeGreaterThanOrEqual(0);
    expect(typeof body.has_more).toBe('boolean');
    expect(Array.isArray(body.signals)).toBe(true);

    // Validate each signal has required fields matching actual API schema
    body.signals.forEach((signal: any) => {
      expect(signal).toHaveProperty('id');
      expect(signal).toHaveProperty('signal_type');
      expect(signal).toHaveProperty('severity');
      expect(signal).toHaveProperty('headline');
      expect(signal).toHaveProperty('summary');

      expect(typeof signal.id).toBe('number');
      expect(['critical', 'high', 'medium', 'low']).toContain(signal.severity);
      expect(typeof signal.headline).toBe('string');
      expect(signal.headline.length).toBeGreaterThan(0);
    });
  });

  test('neighborhoods endpoint responds with valid data', async ({ request }) => {
    const response = await request.get(`${API_BASE}/api/v1/intel/neighborhoods`);

    expect(response.status()).toBe(200);

    const body = await response.json();
    expect(Array.isArray(body)).toBe(true);

    // Neighborhoods endpoint returns string array
    body.forEach((neighborhood: any) => {
      expect(typeof neighborhood).toBe('string');
      expect(neighborhood.length).toBeGreaterThan(0);
    });
  });

  test('intel stats endpoint responds with correct structure', async ({ request }) => {
    const response = await request.get(`${API_BASE}/api/v1/intel/stats`);

    expect(response.status()).toBe(200);

    const body = await response.json();
    expect(body).toHaveProperty('total_signals');
    expect(body).toHaveProperty('by_type');
    expect(body).toHaveProperty('by_neighborhood');
    expect(body).toHaveProperty('by_severity');

    expect(typeof body.total_signals).toBe('number');
    expect(body.total_signals).toBeGreaterThanOrEqual(0);
    expect(typeof body.by_type).toBe('object');
    expect(typeof body.by_neighborhood).toBe('object');
    expect(typeof body.by_severity).toBe('object');
  });

  test('signals GeoJSON endpoint responds with FeatureCollection', async ({ request }) => {
    const response = await request.get(`${API_BASE}/api/v1/intel/signals/geojson`);

    expect(response.status()).toBe(200);

    const body = await response.json();
    expect(body.type).toBe('FeatureCollection');
    expect(Array.isArray(body.features)).toBe(true);

    body.features.forEach((feature: any) => {
      expect(feature.type).toBe('Feature');
      expect(feature).toHaveProperty('geometry');
      expect(feature).toHaveProperty('properties');
      expect(feature.geometry.type).toMatch(/^(Point|LineString|Polygon|MultiPoint)$/);
    });
  });

  test('TOA GeoJSON endpoint responds with valid data', async ({ request }) => {
    const response = await request.get(`${API_BASE}/api/v1/toa/geojson`);

    expect(response.status()).toBe(200);

    const body = await response.json();
    expect(body.type).toBe('FeatureCollection');
    expect(Array.isArray(body.features)).toBe(true);

    body.features.forEach((feature: any) => {
      expect(feature.type).toBe('Feature');
      expect(feature).toHaveProperty('geometry');
      expect(feature).toHaveProperty('properties');
    });
  });
});
