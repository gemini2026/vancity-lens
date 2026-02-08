import { test, expect } from '@playwright/test';

const API_BASE = process.env.API_BASE_URL || 'http://localhost:8000';
const PERFORMANCE_THRESHOLD_API = 1000; // ms

test.describe('VanCity Lens — API Health', () => {
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
    const startTime = Date.now();
    const response = await request.get(`${API_BASE}/health`, {
      headers: {
        Origin: 'http://localhost:3000',
      },
    });
    const responseTime = Date.now() - startTime;

    expect(response.status()).toBe(200);
    expect(responseTime).toBeLessThan(PERFORMANCE_THRESHOLD_API);
    expect(response.headers()['access-control-allow-origin']).toBeDefined();
  });

  test('signals endpoint responds with correct data structure', async ({ request }) => {
    const startTime = Date.now();
    const response = await request.get(`${API_BASE}/api/v1/intel/signals`);
    const responseTime = Date.now() - startTime;

    expect(response.status()).toBe(200);
    expect(responseTime).toBeLessThan(PERFORMANCE_THRESHOLD_API);

    const body = await response.json();
    expect(body).toHaveProperty('signals');
    expect(body).toHaveProperty('total_count');
    expect(body).toHaveProperty('has_more');

    // Strict type and range validation
    expect(typeof body.total_count).toBe('number');
    expect(body.total_count).toBeGreaterThanOrEqual(0);
    expect(typeof body.has_more).toBe('boolean');
    expect(Array.isArray(body.signals)).toBe(true);

    // Validate each signal has required fields
    body.signals.forEach((signal: any) => {
      expect(signal).toHaveProperty('id');
      expect(signal).toHaveProperty('date');
      expect(signal).toHaveProperty('type');
      expect(signal).toHaveProperty('severity');
      expect(signal).toHaveProperty('text');

      // Strict value validation
      expect(typeof signal.id).toBe('string');
      expect(signal.id.length).toBeGreaterThan(0);
      expect(['high', 'medium', 'low']).toContain(signal.severity);
      expect(typeof signal.text).toBe('string');
      expect(signal.text.length).toBeGreaterThan(0);
    });
  });

  test('neighborhoods endpoint responds with valid data', async ({ request }) => {
    const startTime = Date.now();
    const response = await request.get(`${API_BASE}/api/v1/intel/neighborhoods`);
    const responseTime = Date.now() - startTime;

    expect(response.status()).toBe(200);
    expect(responseTime).toBeLessThan(PERFORMANCE_THRESHOLD_API);

    const body = await response.json();
    expect(Array.isArray(body)).toBe(true);

    // If neighborhoods exist, validate structure
    body.forEach((neighborhood: any) => {
      expect(neighborhood).toHaveProperty('name');
      expect(typeof neighborhood.name).toBe('string');
      expect(neighborhood.name.length).toBeGreaterThan(0);
    });
  });

  test('intel stats endpoint responds with correct structure', async ({ request }) => {
    const startTime = Date.now();
    const response = await request.get(`${API_BASE}/api/v1/intel/stats`);
    const responseTime = Date.now() - startTime;

    expect(response.status()).toBe(200);
    expect(responseTime).toBeLessThan(PERFORMANCE_THRESHOLD_API);

    const body = await response.json();
    expect(body).toHaveProperty('total_signals');
    expect(body).toHaveProperty('by_type');
    expect(body).toHaveProperty('by_neighborhood');
    expect(body).toHaveProperty('by_severity');

    // Strict value validation
    expect(typeof body.total_signals).toBe('number');
    expect(body.total_signals).toBeGreaterThanOrEqual(0);
    expect(typeof body.by_type).toBe('object');
    expect(typeof body.by_neighborhood).toBe('object');
    expect(typeof body.by_severity).toBe('object');
  });

  test('signals GeoJSON endpoint responds with FeatureCollection', async ({ request }) => {
    const startTime = Date.now();
    const response = await request.get(`${API_BASE}/api/v1/intel/signals/geojson`);
    const responseTime = Date.now() - startTime;

    expect(response.status()).toBe(200);
    expect(responseTime).toBeLessThan(PERFORMANCE_THRESHOLD_API);

    const body = await response.json();
    expect(body.type).toBe('FeatureCollection');
    expect(Array.isArray(body.features)).toBe(true);

    // Validate GeoJSON features structure
    body.features.forEach((feature: any) => {
      expect(feature.type).toBe('Feature');
      expect(feature).toHaveProperty('geometry');
      expect(feature).toHaveProperty('properties');
      expect(feature.geometry.type).toMatch(/^(Point|LineString|Polygon|MultiPoint)$/);
      expect(Array.isArray(feature.geometry.coordinates) || typeof feature.geometry.coordinates === 'number').toBe(true);
    });
  });

  test('TOA GeoJSON endpoint responds with valid data', async ({ request }) => {
    const startTime = Date.now();
    const response = await request.get(`${API_BASE}/api/v1/toa/geojson`);
    const responseTime = Date.now() - startTime;

    expect(response.status()).toBe(200);
    expect(responseTime).toBeLessThan(PERFORMANCE_THRESHOLD_API);

    const body = await response.json();
    expect(body.type).toBe('FeatureCollection');
    expect(Array.isArray(body.features)).toBe(true);

    // Validate TOA-specific structure
    body.features.forEach((feature: any) => {
      expect(feature.type).toBe('Feature');
      expect(feature).toHaveProperty('geometry');
      expect(feature).toHaveProperty('properties');
    });
  });
});
