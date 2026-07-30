import { expect, test } from "@playwright/test";

const apiBase = "http://127.0.0.1:8008";

const pendingJob = {
  job_id: "acme-backend",
  company: "Acme",
  title: "Backend Engineer",
  source: "remotive",
  url: "https://example.com/job",
  vetting: {},
  review: { status: "pending", notes: "" },
};

test("vet page posts manual vet decisions to FastAPI", async ({ page }) => {
  let vetPayload: { approved?: boolean; reason?: string } | undefined;

  await page.route(`${apiBase}/jobs`, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      headers: { "access-control-allow-origin": "*" },
      body: JSON.stringify([pendingJob]),
    });
  });
  await page.route(`${apiBase}/runs`, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      headers: { "access-control-allow-origin": "*" },
      body: JSON.stringify([]),
    });
  });
  await page.route(`${apiBase}/jobs/${pendingJob.job_id}/vet`, async (route) => {
    if (route.request().method() === "OPTIONS") {
      await route.fulfill({
        status: 204,
        headers: {
          "access-control-allow-origin": "*",
          "access-control-allow-methods": "POST, OPTIONS",
          "access-control-allow-headers": "content-type",
        },
      });
      return;
    }
    vetPayload = route.request().postDataJSON();
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      headers: { "access-control-allow-origin": "*" },
      body: JSON.stringify({ ok: true, approved: true }),
    });
  });

  await page.goto("/phase/2");
  await expect(page.getByText("Acme")).toBeVisible();
  await page.getByTitle("Approve manually").click();

  await expect.poll(() => vetPayload?.approved).toBe(true);
});
