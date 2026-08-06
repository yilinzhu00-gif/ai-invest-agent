import http from 'k6/http';
import { check, sleep } from 'k6';

const baseUrl = __ENV.BASE_URL || 'http://127.0.0.1:8000';
const quick = __ENV.K6_QUICK === '1';

export const options = {
  scenarios: {
    read_and_score: {
      executor: 'ramping-vus',
      startVUs: 1,
      stages: quick
        ? [
            { duration: '1s', target: 2 },
            { duration: '3s', target: 2 },
            { duration: '1s', target: 0 },
          ]
        : [
            { duration: '15s', target: 3 },
            { duration: '30s', target: 3 },
            { duration: '15s', target: 0 },
          ],
      gracefulRampDown: '5s',
    },
  },
  thresholds: {
    http_req_failed: ['rate<0.01'],
    http_req_duration: ['p(95)<500'],
    checks: ['rate>0.99'],
  },
};

export default function () {
  const responses = http.batch([
    ['GET', `${baseUrl}/api/v1/health/live`],
    [
      'POST',
      `${baseUrl}/api/v1/scoring/evaluate`,
      JSON.stringify({
        symbol: '600519',
        as_of_date: '2026-08-05',
        metrics: {
          pe_ttm: 18.5, pb: 2.3, roe: 16.2, net_margin: 12.5, gross_margin: 38.0,
          rev_growth: 22.0, profit_growth: 28.0, debt_ratio: 45.0, current_ratio: 1.8,
          ret_60d: 8.0, price_vs_ma20: 3.5,
        },
      }),
      { headers: { 'Content-Type': 'application/json' } },
    ],
  ]);
  check(responses[0], { 'live health is 200': (response) => response.status === 200 });
  check(responses[1], { 'scoring request is accepted': (response) => response.status === 200 });
  sleep(1);
}
