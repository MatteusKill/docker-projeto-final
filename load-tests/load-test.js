import http from 'k6/http';
import { check, sleep } from 'k6';

const baseUrl = __ENV.BASE_URL || 'http://traefik:8080';

export const options = {
  stages: [
    { duration: '5s', target: 5 },
    { duration: '15s', target: 5 },
    { duration: '5s', target: 0 },
  ],
  thresholds: {
    checks: ['rate>0.99'],
    http_req_failed: ['rate<0.01'],
    http_req_duration: ['p(95)<1000'],
  },
};

export default function () {
  const pageResponse = http.get(`${baseUrl}/`);
  check(pageResponse, {
    'página respondeu 200': (response) => response.status === 200,
  });

  const apiResponse = http.get(`${baseUrl}/api/visits`);
  check(apiResponse, {
    'API respondeu 200': (response) => response.status === 200,
    'API retornou total': (response) => {
      try {
        return Number.isInteger(response.json('total'));
      } catch (_) {
        return false;
      }
    },
  });

  sleep(1);
}
