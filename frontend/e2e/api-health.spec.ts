import { test, expect } from '@playwright/test';

const API_BASE = process.env.API_BASE_URL || 'http://localhost:8000';

test.describe('VanCity Lens — API Health', () => {
  test('backend health endpoint returns ok', async ({ request }) => {
    const response = await request.get(`${API_BASE}/health`);
    expect(response.status()).toBe(200);
    const body = await response.json();
    expect(body).toHaveProperty('status');
  });

  test('CORS headers present for frontend origin', async ({ request }) => {
    const response = await request.get(`${API_BASE}/health`, {
      headers: {
        Origin: 'http://localhost:3000',
      },
    });
    expect(response.status()).toBe(200);
  });

  test('signals endpoint responds (may be empty)', async ({ request }) => {
    const response = await request.get(`${API_BASE}/api/v1/intel/signals`);
    // Should return 200 with empty or populated feed
    expect(response.status()).toBe(200);
    const body = await response.json();
    expect(body).toHaveProperty('signals');
    expect(body).toHaveProperty('total_count');
    expect(body).toHaveProperty('has_more');
  });

  test('neighborhoods endpoint responds', async ({ request }) => {
    const response = await request.get(`${API_BASE}/api/v1/intel/neighborhoods`);
    expect(response.status()).toBe(200);
    const body = await response.json();
    expect(Array.isArray(body)).toBe(true);
  });

  test('intel stats endpoint responds', async ({ request }) => {
    const response = await request.get(`${API_BASE}/api/v1/intel/stats`);
    expect(response.status()).toBe(200);
    const body = await response.json();
    expect(body).toHaveProperty('total_signals');
    expect(body).toHaveProperty('by_type');
    expect(body).toHaveProperty('by_neighborhood');
    expect(body).toHaveProperty('by_severity');
  });

  test('signals GeoJSON endpoint responds with FeatureCollection', async ({ request }) => {
    const response = await request.get(`${API_BASE}/api/v1/intel/signals/geojson`);
    expect(response.status()).toBe(200);
    const body = await response.json();
    expect(body.type).toBe('FeatureCollection');
    expect(Array.isArray(body.features)).toBe(true);
  });

  test('TOA GeoJSON endpoint responds', async ({ request }) => {
    const response = await request.get(`${API_BASE}/api/v1/toa/geojson`);
    expect(response.status()).toBe(200);
    const body = await response.json();
    expect(body.type).toBe('FeatureCollection');
  });
});
