// Chapter 01, drill 1: hammer one channel and prove the coalescer holds p99 flat.
// k6 run --vus 200 --duration 60s code/chat-storage/loadtest/hot_channel.js
import http from 'k6/http';
import { check } from 'k6';

const BASE = __ENV.BASE || 'http://localhost:8080';

export const options = {
  scenarios: {
    hot_channel: { executor: 'constant-vus', vus: 200, duration: '60s' },
  },
  thresholds: {
    // The whole point: tail latency must not move when one channel is hot.
    http_req_duration: ['p(99)<100'],
  },
};

export default function () {
  // Every virtual user reads the SAME channel: maximum coalescing pressure.
  const res = http.get(`${BASE}/messages?channel_id=1001&limit=50`);
  check(res, { 'status 200': (r) => r.status === 200 });
}
