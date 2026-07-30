import { defineConfig } from "@playwright/test";

const port = Number(process.env.REVIEW_UI_PORT ?? 3101);
const baseURL = `http://127.0.0.1:${port}`;

export default defineConfig({
  testDir: "./tests",
  webServer: {
    command: `npm run dev -- --port ${port}`,
    url: baseURL,
    reuseExistingServer: !process.env.CI,
    stdout: "pipe",
    stderr: "pipe"
  },
  use: {
    baseURL,
    headless: true
  }
});
