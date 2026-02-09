import { useState, useEffect } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { AlertTriangle, GitPullRequest, GitMerge, CheckCircle, Clock, RefreshCw, Rocket } from "lucide-react";

interface RepoMetrics {
  repoName: string;
  displayName: string;
  prsOpened: number;
  prsMerged: number;
  issuesReadyForQA: number;
  issuesQACompleted: number;
  daysSinceLastRelease: number | null;
  fetchedAt: string;
}

function parseCSV(csvText: string): RepoMetrics[] {
  const lines = csvText.trim().split("\n");
  if (lines.length < 2) return [];

  const headers = lines[0].split(",");
  const results: RepoMetrics[] = [];

  for (let i = 1; i < lines.length; i++) {
    const values = lines[i].split(",");
    const row: Record<string, string> = {};
    headers.forEach((header, index) => {
      row[header.trim()] = values[index]?.trim() || "";
    });

    results.push({
      repoName: row["repo_name"] || "",
      displayName: row["display_name"] || "",
      prsOpened: parseInt(row["prs_opened"] || "0", 10),
      prsMerged: parseInt(row["prs_merged"] || "0", 10),
      issuesReadyForQA: parseInt(row["issues_ready_for_qa"] || "0", 10),
      issuesQACompleted: parseInt(row["issues_qa_completed"] || "0", 10),
      daysSinceLastRelease: row["days_since_last_release"] ? parseInt(row["days_since_last_release"], 10) : null,
      fetchedAt: row["fetched_at"] || "",
    });
  }

  return results;
}

function MetricCard({
  title,
  value,
  icon: Icon,
  color,
  suffix,
}: {
  title: string;
  value: number | string;
  icon: React.ElementType;
  color: string;
  suffix?: string;
}) {
  return (
    <div className="flex flex-col items-center justify-center p-4 rounded-lg bg-muted/50">
      <Icon className={`h-5 w-5 mb-2 ${color}`} />
      <span className="text-2xl font-bold text-foreground">
        {value}{suffix && <span className="text-sm font-normal text-muted-foreground ml-1">{suffix}</span>}
      </span>
      <span className="text-xs text-muted-foreground text-center">{title}</span>
    </div>
  );
}

function RepoCardContent({ metrics }: { metrics: RepoMetrics }) {
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
      {metrics.daysSinceLastRelease !== null && (
        <MetricCard
          title="Days Since Release"
          value={metrics.daysSinceLastRelease}
          icon={Rocket}
          color="text-orange-500"
          suffix="d"
        />
      )}
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

function SummaryCard({ metrics, isLoading }: { metrics: RepoMetrics[]; isLoading: boolean }) {
  const totals = metrics.reduce(
    (acc, repo) => ({
      prsOpened: acc.prsOpened + repo.prsOpened,
      prsMerged: acc.prsMerged + repo.prsMerged,
      issuesReadyForQA: acc.issuesReadyForQA + repo.issuesReadyForQA,
      issuesQACompleted: acc.issuesQACompleted + repo.issuesQACompleted,
    }),
    { prsOpened: 0, prsMerged: 0, issuesReadyForQA: 0, issuesQACompleted: 0 }
  );

  const avgDaysSinceRelease = (() => {
    const withRelease = metrics.filter((m) => m.daysSinceLastRelease !== null);
    if (withRelease.length === 0) return null;
    const sum = withRelease.reduce((s, m) => s + (m.daysSinceLastRelease ?? 0), 0);
    return Math.round(sum / withRelease.length);
  })();

  return (
    <Card className="shadow-lg border-2 border-primary/20">
      <CardHeader>
        <CardTitle className="text-xl text-center">
          Summary - All Repositories
        </CardTitle>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
            {Array.from({ length: 5 }).map((_, i) => (
              <Skeleton key={i} className="h-24 rounded-lg" />
            ))}
          </div>
        ) : (
          <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
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
            {avgDaysSinceRelease !== null && (
              <MetricCard
                title="Avg Days Since Release"
                value={avgDaysSinceRelease}
                icon={Rocket}
                color="text-orange-500"
                suffix="d"
              />
            )}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

export default function RepoSummary() {
  const [repoMetrics, setRepoMetrics] = useState<RepoMetrics[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [lastUpdated, setLastUpdated] = useState<string | null>(null);
  const [timePeriod, setTimePeriod] = useState<7 | 30>(30);

  const fetchData = async (days: 7 | 30) => {
    setIsLoading(true);
    setError(null);

    try {
      const baseUrl = import.meta.env.BASE_URL || '/';
      const csvFile = `${baseUrl}repo_summary_${days}d.csv`;
      const response = await fetch(csvFile);
      if (!response.ok) {
        throw new Error(`Failed to fetch repo summary data for ${days} days`);
      }
      const csvText = await response.text();
      const metrics = parseCSV(csvText);
      setRepoMetrics(metrics);

      if (metrics.length > 0 && metrics[0].fetchedAt) {
        setLastUpdated(new Date(metrics[0].fetchedAt).toLocaleString());
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load data");
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    fetchData(timePeriod);
  }, [timePeriod]);

  return (
    <div className="min-h-screen bg-background">
      <div className="bg-card shadow-sm border-b border-border">
        <div className="max-w-7xl mx-auto px-6 py-4">
          <div className="flex items-center justify-between">
            <div>
              <h1 className="text-2xl font-bold text-foreground">
                Overall Velocity Report
              </h1>
              <p className="text-muted-foreground">
                Track development velocity across all Focus Bear repositories (last {timePeriod} days)
              </p>
              {lastUpdated && (
                <p className="text-xs text-muted-foreground mt-1">
                  Last updated: {lastUpdated}
                </p>
              )}
            </div>
            <div className="flex items-center gap-2">
              {[7, 30].map((days) => (
                <Button
                  key={days}
                  onClick={() => setTimePeriod(days as 7 | 30)}
                  variant={timePeriod === days ? "default" : "secondary"}
                  size="sm"
                  className="rounded-full"
                >
                  {days} days
                </Button>
              ))}
              <Button
                variant="outline"
                size="sm"
                onClick={() => fetchData(timePeriod)}
                disabled={isLoading}
                className="rounded-full"
              >
                <RefreshCw className={`h-4 w-4 mr-2 ${isLoading ? "animate-spin" : ""}`} />
                Refresh
              </Button>
              <a href="#/">
                <Button variant="outline" size="sm" className="rounded-full">
                  DORA Metrics
                </Button>
              </a>
            </div>
          </div>
        </div>
      </div>

      <div className="max-w-7xl mx-auto p-6 space-y-8">
        {error && (
          <Card className="border-destructive">
            <CardContent className="pt-6">
              <div className="flex items-center text-destructive">
                <AlertTriangle className="h-5 w-5 mr-2" />
                <span>{error}</span>
              </div>
              <p className="text-sm text-muted-foreground mt-2">
                The data is fetched automatically by a GitHub Action. If no data is available,
                the action may not have run yet or there may be an issue with the workflow.
              </p>
            </CardContent>
          </Card>
        )}

        <SummaryCard metrics={repoMetrics} isLoading={isLoading} />

        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {isLoading ? (
            Array.from({ length: 5 }).map((_, i) => (
              <Card key={i} className="shadow-md border border-border">
                <CardHeader className="pb-2">
                  <Skeleton className="h-6 w-32" />
                </CardHeader>
                <CardContent>
                  <div className="grid grid-cols-2 gap-4">
                    {Array.from({ length: 4 }).map((_, j) => (
                      <Skeleton key={j} className="h-24 rounded-lg" />
                    ))}
                  </div>
                </CardContent>
              </Card>
            ))
          ) : (
            repoMetrics.map((metrics) => (
              <RepoCard key={metrics.repoName} metrics={metrics} />
            ))
          )}
        </div>
      </div>
    </div>
  );
}
