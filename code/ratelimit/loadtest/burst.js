// Chapter 06, drill 2: burst from one user, then verify the fixed-window bug
// does not exist. A token bucket allows `capacity` immediately and then
// refills at `rate`; a fixed window would allow 2x capacity across a boundary.
// k6 run code/ratelimit/loadtest/burst.js
import http from 'k6/http';
import { check } from 'k6';
import { Counter } from 'k6/metrics';

const allowed = new Counter('allowed');
const limited = new Counter('limited');
const BASE = __ENV.BASE || 'http://localhost:8080';

export const options = {
  scenarios: {
    burst: { executor: 'shared-iterations', vus: 100, iterations: 1000 },
  },
};

export default function () {
  const res = http.get(`${BASE}/v1/ping`, { headers: { 'X-Account-Id': 'burst-user' } });
  if (res.status === 200) allowed.add(1);
  if (res.status === 429) limited.add(1);
  check(res, { 'no 5xx': (r) => r.status < 500 });
}
