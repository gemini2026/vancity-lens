/**
 * VCL-36: k6 Load Testing Scenarios for VanCity Lens
 *
 * Three load testing scenarios:
 * 1. Ramp (0→100 users over 5min, hold 10min, ramp down)
 * 2. Burst (200 concurrent requests to /api/v1/intel/signals)
 * 3. Chat Stress (50 concurrent /api/v1/intel/chat requests)
 */

import http from 'k6/http';
import { check, sleep } from 'k6';

const BASE_URL = __ENV.BASE_URL || 'http://localhost:8000';
const API_KEY = __ENV.API_KEY || 'test-key-123';
const COHERE_KEY = __ENV.COHERE_KEY || 'test-cohere-key';

/**
 * Scenario 1: Ramp Test
 * Gradually ramp up to 100 users over 5 minutes, hold for 10 minutes, ramp down.
 * Tests overall system stability and scalability.
 */
export const ramppScenario = {
  executor: 'ramping-vus',
  startVUs: 0,
  stages: [
    { duration: '5m', target: 100 },   // ramp up to 100 users over 5min
    { duration: '10m', target: 100 },  // stay at 100 users for 10min
    { duration: '5m', target: 0 },     // ramp down to 0 over 5min
  ],
  gracefulRampDown: '30s',
};

/**
 * Scenario 2: Burst Test
 * Send 200 concurrent requests to the signals endpoint.
 * Tests burst handling and endpoint performance under spike load.
 */
export const burstScenario = {
  executor: 'constant-vus',
  vus: 200,
  duration: '2m',
};

/**
 * Scenario 3: Chat Stress Test
 * Send 50 concurrent requests to the chat endpoint.
 * Tests chat endpoint performance under sustained concurrent load.
 */
export const chatStressScenario = {
  executor: 'constant-vus',
  vus: 50,
  duration: '3m',
};

/**
 * Thresholds define pass/fail criteria for the load test
 */
export const thresholds = {
  // Chat endpoint: p95 < 5 seconds, 0% error rate
  'http_req_duration{endpoint:chat}': ['p(95)<5000', 'p(99)<10000'],
  'http_req_failed{endpoint:chat}': ['rate<0.01'],

  // Signals endpoint: p95 < 500ms, 0% error rate
  'http_req_duration{endpoint:signals}': ['p(95)<500', 'p(99)<1000'],
  'http_req_failed{endpoint:signals}': ['rate<0.01'],

  // Generic thresholds
  'http_req_duration': ['p(99)<5000'],
  'http_req_failed': ['rate<0.01'],
};

/**
 * Helper: Make request and check response
 */
function makeRequest(method, url, payload = null, params = {}) {
  const res = method === 'GET'
    ? http.get(url, params)
    : http.post(url, payload, params);

  check(res, {
    'status is 200 or 201': (r) => r.status === 200 || r.status === 201,
    'response time < 5s': (r) => r.timings.duration < 5000,
  });

  return res;
}

/**
 * Ramp scenario handler
 */
export function rampHandler() {
  // Test signals endpoint
  const signalsUrl = `${BASE_URL}/api/v1/intel/signals`;
  const signalsParams = {
    headers: {
      Authorization: `Bearer ${API_KEY}`,
      'Content-Type': 'application/json',
    },
    tags: { endpoint: 'signals' },
  };

  const signalsPayload = JSON.stringify({
    query: 'test signal query',
    limit: 10,
  });

  makeRequest('POST', signalsUrl, signalsPayload, signalsParams);
  sleep(1);

  // Test chat endpoint
  const chatUrl = `${BASE_URL}/api/v1/intel/chat`;
  const chatParams = {
    headers: {
      Authorization: `Bearer ${API_KEY}`,
      'Content-Type': 'application/json',
    },
    tags: { endpoint: 'chat' },
  };

  const chatPayload = JSON.stringify({
    query: 'What are the latest signals?',
    session_id: `session-${Math.random()}`,
  });

  makeRequest('POST', chatUrl, chatPayload, chatParams);
  sleep(1);
}

/**
 * Burst scenario handler (signals endpoint)
 */
export function burstHandler() {
  const signalsUrl = `${BASE_URL}/api/v1/intel/signals`;
  const params = {
    headers: {
      Authorization: `Bearer ${API_KEY}`,
      'Content-Type': 'application/json',
    },
    tags: { endpoint: 'signals' },
  };

  const payload = JSON.stringify({
    query: 'burst test signal',
    limit: 5,
  });

  makeRequest('POST', signalsUrl, payload, params);
  sleep(0.1);
}

/**
 * Chat stress scenario handler
 */
export function chatStressHandler() {
  const chatUrl = `${BASE_URL}/api/v1/intel/chat`;
  const params = {
    headers: {
      Authorization: `Bearer ${API_KEY}`,
      'Content-Type': 'application/json',
    },
    tags: { endpoint: 'chat' },
  };

  const payload = JSON.stringify({
    query: `Chat stress test message ${Math.random()}`,
    session_id: `chat-session-${__VU}-${__ITER}`,
  });

  makeRequest('POST', chatUrl, payload, params);
  sleep(0.5);
}

/**
 * Default export for handling test execution
 */
export default function () {
  // This is called for scenarios that don't specify a handler
  rampHandler();
}
