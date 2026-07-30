import fs from "node:fs/promises";
import path from "node:path";

const repoRoot = path.resolve(process.cwd());
// In Next.js dev or build mode, process.cwd() is /Users/sohaib/Downloads/job_apply/review-ui.
// But we want to locate the artifacts folder at /Users/sohaib/Downloads/job_apply/artifacts.
// If process.cwd() ends with 'review-ui', we go up one directory.
const parentDir = path.basename(repoRoot) === "review-ui" ? path.dirname(repoRoot) : repoRoot;

const artifactRoot = process.env.ARTIFACT_ROOT
  ? path.resolve(process.env.ARTIFACT_ROOT)
  : path.join(parentDir, "artifacts", "applications");
const artifactRootResolved = path.resolve(artifactRoot);

function safeJobId(jobId: string) {
  if (!/^[a-z0-9][a-z0-9-]{0,96}$/.test(jobId)) {
    throw new Error("invalid jobId");
  }
  return jobId;
}

function jobDir(jobId: string) {
  const dir = path.resolve(artifactRootResolved, safeJobId(jobId));
  if (!dir.startsWith(artifactRootResolved + path.sep)) {
    throw new Error("invalid artifact path");
  }
  return dir;
}

function safeArtifactName(name: string) {
  const allowed = new Set(["resume.pdf", "resume.tex", "email.txt", "jd.txt"]);
  if (!allowed.has(name)) {
    throw new Error("invalid artifact name");
  }
  return name;
}

async function readJson<T>(filePath: string, fallback: T): Promise<T> {
  try {
    const data = await fs.readFile(filePath, "utf8");
    return JSON.parse(data) as T;
  } catch {
    return fallback;
  }
}

export async function listJobs() {
  try {
    await fs.mkdir(artifactRootResolved, { recursive: true });
    const entries = await fs.readdir(artifactRootResolved, { withFileTypes: true });
    const rows = [];
    for (const entry of entries) {
      if (!entry.isDirectory()) continue;
      let dir: string;
      try {
        dir = jobDir(entry.name);
      } catch {
        continue;
      }
      const job = await readJson<any>(path.join(dir, "job.json"), null);
      if (!job) continue;
      rows.push({
        ...job,
        vetting: await readJson(path.join(dir, "vetting.json"), {}),
        generation: await readJson(path.join(dir, "generation.json"), {}),
        package: await readJson(path.join(dir, "package.json"), null),
        review: await readJson(path.join(dir, "review.json"), { status: "pending", notes: "" })
      });
    }
    // Sort jobs so that latest created are first (or just alphabetical job_id)
    return rows.sort((a: any, b: any) => {
      const dateA = a.created_at || "";
      const dateB = b.created_at || "";
      return dateB.localeCompare(dateA);
    });
  } catch (e) {
    console.error("Error listing jobs:", e);
    return [];
  }
}

export async function getJob(jobId: string) {
  const dir = jobDir(jobId);
  const job = await readJson<any>(path.join(dir, "job.json"), null);
  if (!job) return null;
  return {
    ...job,
    jd: await fs.readFile(path.join(dir, "jd.txt"), "utf8").catch(() => ""),
    vetting: await readJson(path.join(dir, "vetting.json"), {}),
    generation: await readJson(path.join(dir, "generation.json"), {}),
    review: await readJson(path.join(dir, "review.json"), { status: "pending", notes: "" }),
    package: await readJson(path.join(dir, "package.json"), null)
  };
}

export async function writeReview(jobId: string, review: { status: string; notes: string }) {
  const dir = jobDir(jobId);
  await fs.mkdir(dir, { recursive: true });
  
  // Read existing review to merge decision history
  const existing = await readJson<any>(path.join(dir, "review.json"), { status: "pending", notes: "", decision_history: [] });
  const decision_history = existing.decision_history || [];
  
  // Add new state to decision history
  decision_history.push({
    status: review.status,
    notes: review.notes,
    created_at: new Date().toISOString()
  });

  const updatedReview = {
    status: review.status,
    notes: review.notes,
    decision_history
  };

  await fs.writeFile(path.join(dir, "review.json"), JSON.stringify(updatedReview, null, 2), "utf8");
  return updatedReview;
}

export function artifactPath(jobId: string, name: string) {
  return path.join(jobDir(jobId), safeArtifactName(name));
}
