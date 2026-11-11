import { defineConfig } from '@playwright/test';
import { mkdtempSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

const external = process.env.E2E_BASE_URL;
const python = process.platform === 'win32' ? '../.venv/Scripts/python.exe' : '../.venv/bin/python';

export default defineConfig({
  testDir: './e2e',
  timeout: 120_000,
  expect: { timeout: 15_000 },
  workers: 1,
  reporter: 'list',
  outputDir: '../.impeccable/review/e2e-results',
  use: {
    baseURL: external || 'http://127.0.0.1:8010',
    viewport: { width: 1440, height: 1000 },
    acceptDownloads: true,
    launchOptions: { executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE, args: ['--no-sandbox'] },
    screenshot: 'only-on-failure',
  },
  webServer: external ? undefined : {
    command: `${python} -m uvicorn app.main:app --app-dir ../backend --host 127.0.0.1 --port 8010`,
    url: 'http://127.0.0.1:8010/api/system/check',
    reuseExistingServer: false,
    env: { WEDDING_MIX_DATA_DIR: mkdtempSync(join(tmpdir(), 'wedding-mix-e2e-server-')) },
  },
});
