import { expect, test, type Page } from "@playwright/test";

const apiBase = "http://127.0.0.1:8008";

const cors = { "access-control-allow-origin": "*" };

function jsonResponse(body: unknown) {
  return {
    status: 200,
    contentType: "application/json",
    headers: cors,
    body: JSON.stringify(body),
  };
}

const approvedJob = {
  job_id: "approved-backend",
  company: "Acme",
  title: "Backend Engineer",
  source: "wellfound",
  url: "https://example.com/approved",
  location: "Remote",
  vetting: {
    status: "approved",
    approved: true,
    reason: "Strong backend fit",
    engine: { requested: "gemini", answered: "gemini" },
  },
  generation: {
    status: "generated",
    page_count: 1,
    impact_signal_ratio: 1,
    numeric_bullets: 8,
    total_bullets: 12,
  },
  review: { status: "pending" },
  package: { match_score: 91 },
};

const filteredJob = {
  job_id: "filtered-frontend",
  company: "Beta",
  title: "Frontend Engineer",
  source: "remotive",
  url: "https://example.com/filtered",
  location: "Bengaluru",
  vetting: {
    status: "rejected",
    approved: false,
    reason: "Weak backend match",
    engine: { requested: "gemini", answered: "groq" },
  },
  review: { status: "rejected" },
};

const erroredJob = {
  job_id: "errored-fullstack",
  company: "Gamma",
  title: "Fullstack Engineer",
  source: "remotive",
  url: "https://example.com/errored",
  vetting: {
    status: "error",
    approved: null,
    reason: "Could not vet: 429 rate limit",
    error: "429 rate limit",
    engine: { requested: "gemini", answered: null },
  },
};

const detailJob = {
  ...approvedJob,
  jd: "Build backend APIs",
  package: {
    match_score: 91,
    keywords_matched: ["Python", "FastAPI"],
    keywords_missing: ["Kubernetes"],
    tailored_experience: [
      {
        company: "Teleperformance",
        role: "Software Development Engineer II",
        bullets: ["Built scalable FastAPI services with 13% throughput gain."],
      },
    ],
    tailored_skills: { Backend: ["Python", "FastAPI", "PostgreSQL"] },
    email_subject: "Backend Engineer",
    email_body: "Hi Acme, I can help build reliable backend APIs.",
  },
};

const completedRun = {
  run_id: "run-phase2",
  phase: "phase2",
  status: "succeeded",
  logs: ["2026-06-11T10:00:00Z started", "2026-06-11T10:00:03Z succeeded"],
  events: [
    { type: "phase_start", phase: "phase2", total: 2, engine: "gemini" },
    {
      type: "job_result",
      job_id: "approved-backend",
      company: "Acme",
      title: "Backend Engineer",
      status: "approved",
      reason: "Strong backend fit",
      engine: "gemini",
      score: 91,
    },
    {
      type: "job_result",
      job_id: "errored-fullstack",
      company: "Gamma",
      title: "Fullstack Engineer",
      status: "error",
      reason: "Could not vet: 429 rate limit",
      engine: null,
    },
    { type: "progress", done: 2, total: 2, approved: 1, rejected: 0, errors: 1 },
    { type: "phase_done", phase: "phase2", approved: 1, rejected: 0, errors: 1, skipped: 5 },
  ],
  result: { phase: "phase2", reviewed: 2, approved: 1, rejected: 0, errors: 1, skipped: 5 },
  created_at: "2026-06-11T10:00:00Z",
  updated_at: "2026-06-11T10:00:03Z",
};

async function mockApi(page: Page, { jobs = [] as unknown[], runs = [] as unknown[] } = {}) {
  await page.route(`${apiBase}/jobs`, (route) => route.fulfill(jsonResponse(jobs)));
  await page.route(`${apiBase}/runs`, (route) => route.fulfill(jsonResponse(runs)));
  await page.route(`${apiBase}/health`, (route) => route.fulfill(jsonResponse({ ok: true })));
  await page.route(`${apiBase}/settings`, (route) => route.fulfill(jsonResponse({ ai_engine: "gemini" })));
  await page.route(`${apiBase}/analytics/funnel`, (route) =>
    route.fulfill(jsonResponse({ gathered: 3, vetted: 3, approved: 1, generated: 1, reviewed: 0, sent: 0 }))
  );
  await page.route(`${apiBase}/analytics/sent-today`, (route) =>
    route.fulfill(jsonResponse({ sent_today: 0, limit: 10 }))
  );
}

test("dashboard does not throw JSON syntax errors for HTML API failures", async ({ page }) => {
  const consoleMessages: string[] = [];
  page.on("console", (msg) => consoleMessages.push(msg.text()));
  await page.route(`${apiBase}/jobs`, async (route) => {
    await route.fulfill({
      status: 500,
      contentType: "text/html",
      headers: cors,
      body: "<!DOCTYPE html><p>server error</p>",
    });
  });

  await page.goto("/");
  await page.waitForTimeout(500);

  expect(consoleMessages.join("\n")).not.toContain("Unexpected token '<'");
});

test("grouped pipeline navigation uses stage names", async ({ page }) => {
  await mockApi(page);
  await page.goto("/");

  const nav = page.locator("nav");
  for (const name of ["Overview", "1 · Gather", "2 · Vet", "3 · Generate", "4 · Contacts", "Runs", "Tracking", "Analytics", "Settings"]) {
    await expect(nav.getByRole("link", { name, exact: true })).toBeVisible();
  }
  await expect(nav.getByRole("link", { name: /5 · Review & Send/ })).toBeVisible();
});

test("overview shows needs-attention cards and clickable funnel", async ({ page }) => {
  await mockApi(page, { jobs: [approvedJob, filteredJob, erroredJob] });
  await page.goto("/");

  await expect(page.getByText("Needs Attention")).toBeVisible();
  await expect(page.getByText("couldn't be vetted")).toBeVisible();
  await expect(page.getByText("approved, awaiting generation")).toBeVisible();
  await expect(page.getByText("Pipeline Funnel")).toBeVisible();
  await expect(page.getByRole("link", { name: /Gathered/ })).toBeVisible();
});

test("stage pages show per-stage stats, descriptions, and error states", async ({ page }) => {
  await mockApi(page, { jobs: [approvedJob, filteredJob, erroredJob] });

  await page.goto("/phase/1");
  await expect(page.getByRole("heading", { name: "Gather" })).toBeVisible();
  await expect(page.getByText("Input: source configs → Output: job artifacts (jd.txt, job.json)")).toBeVisible();

  await page.goto("/phase/2");
  await expect(page.getByRole("heading", { name: "Vet" })).toBeVisible();
  await expect(page.getByText("Strong backend fit")).toBeVisible();
  await expect(page.getByText("Weak backend match")).toBeVisible();
  await expect(page.getByText("Couldn't vet").first()).toBeVisible();
  await expect(page.getByTitle("Retry AI vetting")).toBeVisible();
  await expect(page.getByText("[gemini] Strong backend fit")).toBeVisible();
  await expect(page.getByText("[groq] Weak backend match")).toBeVisible();

  await page.goto("/phase/3");
  await expect(page.getByRole("heading", { name: "Generate" })).toBeVisible();
  await expect(page.getByText("8/12 numeric bullets / 1 page PDF")).toBeVisible();

  await page.goto("/phase/4");
  await expect(page.getByRole("heading", { name: "Contacts" })).toBeVisible();
});

test("vet page filter tabs isolate error rows", async ({ page }) => {
  await mockApi(page, { jobs: [approvedJob, filteredJob, erroredJob] });

  await page.goto("/phase/2");
  await page.getByRole("button", { name: "Couldn't vet", exact: true }).click();
  await expect(page.getByText("Gamma")).toBeVisible();
  await expect(page.getByText("Acme")).not.toBeVisible();

  await page.getByRole("button", { name: "Approved", exact: true }).click();
  await expect(page.getByText("Acme")).toBeVisible();
  await expect(page.getByText("Gamma")).not.toBeVisible();
});

test("run launcher exposes engine, force re-vet, and stage subset", async ({ page }) => {
  await mockApi(page, { jobs: [approvedJob] });

  await page.goto("/phase/2");
  await page.getByRole("button", { name: "▶ Run Vet" }).click();

  const modal = page.locator("div.fixed");
  await expect(modal.getByText("Launch Pipeline Run")).toBeVisible();
  await expect(modal.getByText("AI Engine", { exact: true })).toBeVisible();
  await expect(modal.getByText("Force re-vet all (ignore existing verdicts)")).toBeVisible();
  await expect(modal.getByText("Already-vetted jobs are skipped")).toBeVisible();

  await modal.locator("select").first().selectOption("safe-prepare");
  await expect(modal.getByText("Stages To Run")).toBeVisible();
  await expect(modal.getByText("4 · Contacts")).toBeVisible();
});

test("run detail renders structured feed with progress and engine badges", async ({ page }) => {
  await mockApi(page, { runs: [completedRun] });
  await page.route(`${apiBase}/runs/${completedRun.run_id}`, (route) =>
    route.fulfill(jsonResponse(completedRun))
  );

  await page.goto(`/runs/${completedRun.run_id}`);

  await expect(page.getByRole("heading", { name: "phase2" })).toBeVisible();
  await expect(page.getByText("2 / 2")).toBeVisible();
  await expect(page.getByRole("button", { name: "Feed (2)" })).toBeVisible();
  await expect(page.getByText("Acme — Backend Engineer").first()).toBeVisible();
  await expect(page.getByText("Strong backend fit")).toBeVisible();
  await expect(page.getByText("Gamma — Fullstack Engineer").first()).toBeVisible();
  await expect(page.getByText("Could not vet: 429 rate limit")).toBeVisible();

  // Jobs bar links each referenced job directly
  await expect(page.getByRole("link", { name: "Acme — Backend Engineer", exact: true })).toHaveAttribute("href", "/jobs/approved-backend");

  await page.getByRole("button", { name: /Raw Logs/ }).click();
  await expect(page.getByText("started").first()).toBeVisible();
});

test("stage page filters narrow rows by region, source, and search", async ({ page }) => {
  const india = { ...approvedJob, job_id: "india-job", company: "DesiCorp", region: "india", work_mode: "wfo", source: "instahyre" };
  const foreign = { ...approvedJob, job_id: "foreign-job", company: "GlobalCo", region: "foreign", work_mode: "remote", source: "remotive" };
  await mockApi(page, { jobs: [india, foreign] });

  await page.goto("/phase/2");
  await expect(page.getByText("DesiCorp")).toBeVisible();
  await expect(page.getByText("GlobalCo")).toBeVisible();

  // Region filter (first select in the FilterBar)
  await page.locator("select").first().selectOption("india");
  await expect(page.getByText("DesiCorp")).toBeVisible();
  await expect(page.getByText("GlobalCo")).not.toBeVisible();

  // Clear resets
  await page.getByRole("button", { name: "Clear" }).click();
  await expect(page.getByText("GlobalCo")).toBeVisible();

  // Search filter
  await page.getByPlaceholder("Search company / role").fill("globalco");
  await expect(page.getByText("DesiCorp")).not.toBeVisible();
  await expect(page.getByText("GlobalCo")).toBeVisible();
});

test("job detail shows pipeline stepper with stage states", async ({ page }) => {
  await mockApi(page, { jobs: [approvedJob] });
  await page.route(`${apiBase}/jobs/${approvedJob.job_id}`, (route) =>
    route.fulfill(jsonResponse(detailJob))
  );
  await page.route(`${apiBase}/jobs/${approvedJob.job_id}/tracking`, (route) =>
    route.fulfill(jsonResponse({}))
  );
  await page.route(`${apiBase}/jobs/${approvedJob.job_id}/history`, (route) =>
    route.fulfill(jsonResponse([]))
  );

  await page.goto(`/jobs/${approvedJob.job_id}`);

  await expect(page.getByRole("heading", { name: "Acme" })).toBeVisible();
  await expect(page.getByText("Gathered", { exact: true }).first()).toBeVisible();
  await expect(page.getByText("Vetted", { exact: true }).first()).toBeVisible();
  await expect(page.getByText("Generated", { exact: true }).first()).toBeVisible();
  await expect(page.getByText("Contact", { exact: true }).first()).toBeVisible();
  await expect(page.getByText("Sent", { exact: true }).first()).toBeVisible();
});
