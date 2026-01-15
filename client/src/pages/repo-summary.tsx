import { useState, useCallback } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { AlertTriangle, GitPullRequest, GitMerge, CheckCircle, Clock } from "lucide-react";
import { Link } from "wouter";

interface RepoMetrics {
  repoName: string;
  displayName: string;
  prsOpened: number;
  prsMerged: number;
  issuesReadyForQA: number;
  issuesQACompleted: number;
  isLoading: boolean;
  error: string | null;
}

interface GitHubPR {
  id: number;
  state: string;
  merged_at: string | null;
  created_at: string;
}

interface GitHubIssue {
  id: number;
  labels: { name: string }[];
  state: string;
  pull_request?: object;
}

const REPOS = [
  { name: "Focus-Bear/web_dashboard", displayName: "Web Dashboard" },
  { name: "Focus-Bear/dora_pipeline", displayName: "Backend" },
  { name: "Focus-Bear/dora_mobile", displayName: "Mobile" },
  { name: "Focus-Bear/dora_mac", displayName: "Mac" },
  { name: "Focus-Bear/dora_windows", displayName: "Windows" },
];

const GITHUB_API_BASE = "https://api.github.com";

const fetchGitHubData = async (
  repo: string,
  token: string
): Promise<{
  prsOpened: number;
  prsMerged: number;
  issuesReadyForQA: number;
  issuesQACompleted: number;
}> => {
  const headers: HeadersInit = {
    Accept: "application/vnd.github.v3+json",
  };

  if (token) {
    headers.Authorization = `token ${token}`;
  }

  const now = new Date();
  const thirtyDaysAgo = new Date(now.getTime() - 30 * 24 * 60 * 60 * 1000);
  const since = thirtyDaysAgo.toISOString();

  const [prsResponse, issuesResponse] = await Promise.all([
    fetch(
      `${GITHUB_API_BASE}/repos/${repo}/pulls?state=all&per_page=100&since=${since}`,
      { headers }
    ),
    fetch(
      `${GITHUB_API_BASE}/repos/${repo}/issues?state=all&per_page=100&since=${since}`,
      { headers }
    ),
  ]);

  if (!prsResponse.ok || !issuesResponse.ok) {
    throw new Error("Failed to fetch GitHub data");
  }

  const prs: GitHubPR[] = await prsResponse.json();
  const issues: GitHubIssue[] = await issuesResponse.json();

  const recentPRs = prs.filter(
    (pr) => new Date(pr.created_at) >= thirtyDaysAgo
  );
  const prsOpened = recentPRs.length;
  const prsMerged = recentPRs.filter((pr) => pr.merged_at !== null).length;

  const actualIssues = issues.filter((issue) => !issue.pull_request);

  const issuesReadyForQA = actualIssues.filter((issue) =>
    issue.labels.some(
      (label) =>
        label.name.toLowerCase().includes("ready for qa") ||
        label.name.toLowerCase().includes("ready-for-qa") ||
        label.name.toLowerCase().includes("qa ready")
    )
  ).length;

  const issuesQACompleted = actualIssues.filter((issue) =>
    issue.labels.some(
      (label) =>
        label.name.toLowerCase().includes("qa completed") ||
        label.name.toLowerCase().includes("qa-completed") ||
        label.name.toLowerCase().includes("qa done") ||
        label.name.toLowerCase().includes("qa-done") ||
        label.name.toLowerCase().includes("qa'd")
    )
  ).length;

  return {
    prsOpened,
    prsMerged,
    issuesReadyForQA,
    issuesQACompleted,
  };
};

function MetricCard({
  title,
  value,
  icon: Icon,
  color,
}: {
  title: string;
  value: number;
  icon: React.ElementType;
  color: string;
}) {
  return (
    <div className="flex flex-col items-center justify-center p-4 rounded-lg bg-muted/50">
      <Icon className={`h-5 w-5 mb-2 ${color}`} />
      <span className="text-2xl font-bold text-foreground">{value}</span>
      <span className="text-xs text-muted-foreground text-center">{title}</span>
    </div>
  );
}

function RepoCardContent({
  metrics,
}: {
  metrics: RepoMetrics;
}) {
  if (metrics.isLoading) {
    return (
      <div className="grid grid-cols-2 gap-4">
        {Array.from({ length: 4 }).map((_, i) => (
          <Skeleton key={i} className="h-24 rounded-lg" />
        ))}
      </div>
    );
  }

  if (metrics.error) {
    return (
      <div className="flex items-center justify-center h-24 text-destructive">
        <AlertTriangle className="h-5 w-5 mr-2" />
        <span>{metrics.error}</span>
      </div>
    );
  }

  return (
    <div className="grid grid-cols-2 gap-4">
      <MetricCard
        title="PRs Opened"
        value={metrics.prsOpened}
        icon={GitPullRequest}
        color="text-primary"
      />
      <MetricCard
        title="PRs Merged"
        value={metrics.prsMerged}
        icon={GitMerge}
        color="text-chart-2"
      />
      <MetricCard
        title="Ready for QA"
        value={metrics.issuesReadyForQA}
        icon={Clock}
        color="text-chart-3"
      />
      <MetricCard
        title="QA Completed"
        value={metrics.issuesQACompleted}
        icon={CheckCircle}
        color="text-green-600"
      />
    </div>
  );
}

function RepoCard({ metrics }: { metrics: RepoMetrics }) {
  return (
    <Card className="shadow-md border border-border">
      <CardHeader className="pb-2">
        <CardTitle className="text-lg">{metrics.displayName}</CardTitle>
      </CardHeader>
      <CardContent>
        <RepoCardContent metrics={metrics} />
      </CardContent>
    </Card>
  );
}

function SummaryCard({ metrics }: { metrics: RepoMetrics[] }) {
  const totals = metrics.reduce(
    (acc, repo) => ({
      prsOpened: acc.prsOpened + repo.prsOpened,
      prsMerged: acc.prsMerged + repo.prsMerged,
      issuesReadyForQA: acc.issuesReadyForQA + repo.issuesReadyForQA,
      issuesQACompleted: acc.issuesQACompleted + repo.issuesQACompleted,
    }),
    { prsOpened: 0, prsMerged: 0, issuesReadyForQA: 0, issuesQACompleted: 0 }
  );

  const isLoading = metrics.some((m) => m.isLoading);

  return (
    <Card className="shadow-lg border-2 border-primary/20">
      <CardHeader>
        <CardTitle className="text-xl text-center">
          Summary - All Repositories
        </CardTitle>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            {Array.from({ length: 4 }).map((_, i) => (
              <Skeleton key={i} className="h-24 rounded-lg" />
            ))}
          </div>
        ) : (
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <MetricCard
              title="Total PRs Opened"
              value={totals.prsOpened}
              icon={GitPullRequest}
              color="text-primary"
            />
            <MetricCard
              title="Total PRs Merged"
              value={totals.prsMerged}
              icon={GitMerge}
              color="text-chart-2"
            />
            <MetricCard
              title="Total Ready for QA"
              value={totals.issuesReadyForQA}
              icon={Clock}
              color="text-chart-3"
            />
            <MetricCard
              title="Total QA Completed"
              value={totals.issuesQACompleted}
              icon={CheckCircle}
              color="text-green-600"
            />
          </div>
        )}
      </CardContent>
    </Card>
  );
}

export default function RepoSummary() {
  const [githubToken, setGithubToken] = useState("");
  const [repoMetrics, setRepoMetrics] = useState<RepoMetrics[]>(
    REPOS.map((repo) => ({
      repoName: repo.name,
      displayName: repo.displayName,
      prsOpened: 0,
      prsMerged: 0,
      issuesReadyForQA: 0,
      issuesQACompleted: 0,
      isLoading: false,
      error: null,
    }))
  );

  const fetchAllRepoData = useCallback(async () => {
    setRepoMetrics((prev) =>
      prev.map((repo) => ({ ...repo, isLoading: true, error: null }))
    );

    const results = await Promise.allSettled(
      REPOS.map(async (repo) => {
        const data = await fetchGitHubData(repo.name, githubToken);
        return { repoName: repo.name, ...data };
      })
    );

    setRepoMetrics((prev) =>
      prev.map((repo, index) => {
        const result = results[index];
        if (result.status === "fulfilled") {
          return {
            ...repo,
            ...result.value,
            isLoading: false,
            error: null,
          };
        } else {
          return {
            ...repo,
            isLoading: false,
            error: "Failed to fetch data",
          };
        }
      })
    );
  }, [githubToken]);

  return (
    <div className="min-h-screen bg-background">
      <div className="bg-card shadow-sm border-b border-border">
        <div className="max-w-7xl mx-auto px-6 py-4">
                    <div className="flex items-center justify-between">
                      <div>
                        <h1 className="text-2xl font-bold text-foreground">
                          Repository Summary Dashboard
                        </h1>
                        <p className="text-muted-foreground">
                          Track development activity across all Focus Bear repositories (last 30 days)
                        </p>
                      </div>
                      <Link href="/">
                        <Button variant="outline" size="sm" className="rounded-full">
                          DORA Metrics
                        </Button>
                      </Link>
                    </div>
        </div>
      </div>

      <div className="max-w-7xl mx-auto p-6 space-y-8">
        <Card className="shadow-md">
          <CardContent className="pt-6">
            <div className="flex flex-col sm:flex-row gap-4">
              <div className="flex-1">
                <label
                  htmlFor="github-token"
                  className="text-sm font-medium text-muted-foreground mb-2 block"
                >
                  GitHub Token (optional for public repos)
                </label>
                <Input
                  id="github-token"
                  type="password"
                  value={githubToken}
                  onChange={(e) => setGithubToken(e.target.value)}
                  placeholder="Enter your GitHub personal access token"
                />
              </div>
              <div className="flex items-end">
                <Button onClick={fetchAllRepoData} className="w-full sm:w-auto">
                  Fetch Data
                </Button>
              </div>
            </div>
          </CardContent>
        </Card>

        <SummaryCard metrics={repoMetrics} />

        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {repoMetrics.map((metrics) => (
            <RepoCard key={metrics.repoName} metrics={metrics} />
          ))}
        </div>
      </div>
    </div>
  );
}
