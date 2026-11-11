import { defineConfig } from '@playwright/test';
import { existsSync } from 'node:fs';

const candidates = [process.env.PLAYWRIGHT_BROWSER_EXECUTABLE, 'C:/Program Files/Google/Chrome/Application/chrome.exe', 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'].filter((value): value is string => Boolean(value));
const executablePath = candidates.find(path => existsSync(path));
if (!executablePath) throw new Error('未发现系统 Chrome/Edge；请设置 PLAYWRIGHT_BROWSER_EXECUTABLE 指向本机浏览器。');
const target = process.env.TASK12_ISOLATED_API || 'http://127.0.0.1:18991';
if (!/^http:\/\/(127\.0\.0\.1|localhost)(:\d+)?$/.test(target)) throw new Error('TASK12_ISOLATED_API 必须是隔离的本机 HTTP 地址。');
export default defineConfig({
  testDir: './e2e', timeout: 30_000, fullyParallel: false, workers: 1, retries: 0,
  reporter: [['list']],
  use: { baseURL: 'http://127.0.0.1:4178', browserName: 'chromium', launchOptions: { executablePath }, trace: 'off', screenshot: 'only-on-failure' },
  webServer: { command: 'npm run dev -- --host 127.0.0.1 --port 4178 --strictPort', url: 'http://127.0.0.1:4178', reuseExistingServer: false, timeout: 30_000, env: { VITE_API_TARGET: target } },
});
