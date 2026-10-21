import { useState, useEffect } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import {
  AlertTriangle,
  CheckCircle,
  Clock,
  GitMerge,
  GitPullRequest,
  RefreshCw,
  Rocket,
  Route,
  XCircle,
} from "lucide-react";
import {
  NOT_AVAILABLE,
  formatRatio,
  progressIndicator,
  sumKnown,
  trendLabel,
} from "@/lib/repo-summary-metrics";

interface RepoMetrics {
  repoName: string;
  displayName: string;
  prsOpen: number;
  prsDraft: number;
  prsApproved: number;
  prsMerged: number;
  // QA figures are null for repos whose board has no QA columns.
  issuesReadyForQA: number | null;
  readyForQA1dAgo: number | null;
  readyForQA7dAgo: number | null;
  issuesQACompleted: number | null;
  issuesQAFailed: number | null;
  issuesMovedToReadyForQA: number | null;
  issuesCreated: number;
  bugsCreated: number;
  daysSinceLastRelease: number | null;
  releaseVersion: string;
  releaseSource: string;
  fetchedAt: string;
}

function parseOptionalInt(value: string | undefined): number | null {
  if (!value) return null;
  const parsed = parseInt(value, 10);
  return Number.isNaN(parsed) ? null : parsed;
}

function parseInteger(value: string | undefined): number {
  return parseOptionalInt(value) ?? 0;
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
      prsOpen: parseInteger(row["prs_open"]),
      prsDraft: parseInteger(row["prs_draft"]),
      prsApproved: parseInteger(row["prs_approved"]),
      prsMerged: parseInteger(row["prs_merged"]),
      issuesReadyForQA: parseOptionalInt(row["issues_ready_for_qa"]),
      readyForQA1dAgo: parseOptionalInt(row["ready_for_qa_1d_ago"]),
      readyForQA7dAgo: parseOptionalInt(row["ready_for_qa_7d_ago"]),
      issuesQACompleted: parseOptionalInt(row["issues_qa_completed"]),
      issuesQAFailed: parseOptionalInt(row["issues_qa_failed"]),
      issuesMovedToReadyForQA: parseOptionalInt(row["issues_moved_to_ready_for_qa"]),
      issuesCreated: parseInteger(row["issues_created"]),
      bugsCreated: parseInteger(row["bugs_created"]),
      daysSinceLastRelease: parseOptionalInt(row["days_since_last_release"]),
      releaseVersion: row["release_version"] || "",
      releaseSource: row["release_source"] || "",
      fetchedAt: row["fetched_at"] || "",
    });
  }

  return results;
}

function showValue(value: number | null): number | string {
  return value === null ? NOT_AVAILABLE : value;
}

function readyTrend(current: number | null, dayAgo: number | null, weekAgo: number | null): string {
  return `${trendLabel(current, dayAgo)} vs 24h · ${trendLabel(current, weekAgo)} vs 7d`;
}

function roadmapDetail(movedToQA: number, created: number, bugs: number): string {
  const bugText = `${bugs} bug${bugs === 1 ? "" : "s"}`;
  const indicator = progressIndicator(movedToQA, created);
  if (indicator === NOT_AVAILABLE) return bugText;
  return `${indicator} ${formatRatio(movedToQA, created)} · ${bugText}`;
}

function MetricCard({
  title,
  value,
  icon: Icon,
  color,
  suffix,
  detail,
}: {
  title: string;
  value: number | string;
  icon: React.ElementType;
  color: string;
  suffix?: string;
  detail?: string;
}) {
  return (
    <div className="flex flex-col items-center justify-center p-4 rounded-lg bg-muted/50">
      <Icon className={`h-5 w-5 mb-2 ${color}`} />
      <span className="text-2xl font-bold text-foreground">
        {value}{suffix && <span className="text-sm font-normal text-muted-foreground ml-1">{suffix}</span>}
      </span>
      <span className="text-xs text-muted-foreground text-center">{title}</span>
      {detail && <span className="text-xs text-muted-foreground text-center mt-1">{detail}</span>}
    </div>
  );
}

function RepoCardContent({ metrics, timePeriod }: { metrics: RepoMetrics; timePeriod: number }) {
  const hasQABoard = metrics.issuesReadyForQA !== null;
  const movedToQA = metrics.issuesMovedToReadyForQA ?? 0;
  return (
    <div className="grid grid-cols-2 gap-4">
      <MetricCard
        title="PRs Open"
        value={metrics.prsOpen}
        icon={GitPullRequest}
        color="text-primary"
        detail={`${metrics.prsDraft} draft · ${metrics.prsApproved} approved`}
      />
      <MetricCard
        title="PRs Merged"
        value={metrics.prsMerged}
        icon={GitMerge}
        color="text-chart-2"
      />
      {hasQABoard && (
        <>
          <MetricCard
            title="Ready for QA"
            value={showValue(metrics.issuesReadyForQA)}
            icon={Clock}
            color="text-chart-3"
            detail={readyTrend(metrics.issuesReadyForQA, metrics.readyForQA1dAgo, metrics.readyForQA7dAgo)}
          />
          <MetricCard
            title="QA Passed / Failed"
            value={`${showValue(metrics.issuesQACompleted)} / ${showValue(metrics.issuesQAFailed)}`}
            icon={metrics.issuesQAFailed ? XCircle : CheckCircle}
            color={metrics.issuesQAFailed ? "text-destructive" : "text-green-600"}
          />
        </>
      )}
      <MetricCard
        title={hasQABoard ? `To QA vs new issues (${timePeriod}d)` : `New issues (${timePeriod}d)`}
        value={hasQABoard ? `${movedToQA} / ${metrics.issuesCreated}` : metrics.issuesCreated}
        icon={Route}
        color="text-chart-1"
        detail={hasQABoard ? roadmapDetail(movedToQA, metrics.issuesCreated, metrics.bugsCreated) : undefined}
      />
      {metrics.daysSinceLastRelease !== null && (
        <MetricCard
          title="Days Since Release"
          value={metrics.daysSinceLastRelease}
          icon={Rocket}
          color="text-orange-500"
          suffix="d"
          detail={[metrics.releaseVersion, metrics.releaseSource].filter(Boolean).join(" · ")}
        />
      )}
    </div>
  );
}

function RepoCard({ metrics, timePeriod }: { metrics: RepoMetrics; timePeriod: number }) {
  return (
    <Card className="shadow-md border border-border">
      <CardHeader className="pb-2">
        <CardTitle className="text-lg">{metrics.displayName}</CardTitle>
      </CardHeader>
      <CardContent>
        <RepoCardContent metrics={metrics} timePeriod={timePeriod} />
      </CardContent>
    </Card>
  );
}

function summarise(metrics: RepoMetrics[]) {
  const sum = (pick: (repo: RepoMetrics) => number) => metrics.reduce((total, repo) => total + pick(repo), 0);
  const sumOptional = (pick: (repo: RepoMetrics) => number | null) => sumKnown(metrics.map(pick));
  return {
    prsOpen: sum((repo) => repo.prsOpen),
    prsDraft: sum((repo) => repo.prsDraft),
    prsApproved: sum((repo) => repo.prsApproved),
    prsMerged: sum((repo) => repo.prsMerged),
    issuesReadyForQA: sumOptional((repo) => repo.issuesReadyForQA),
    readyForQA1dAgo: sumOptional((repo) => repo.readyForQA1dAgo),
    readyForQA7dAgo: sumOptional((repo) => repo.readyForQA7dAgo),
    issuesQACompleted: sumOptional((repo) => repo.issuesQACompleted),
    issuesQAFailed: sumOptional((repo) => repo.issuesQAFailed),
    issuesMovedToReadyForQA: sum((repo) => repo.issuesMovedToReadyForQA ?? 0),
    issuesCreated: sum((repo) => repo.issuesCreated),
    bugsCreated: sum((repo) => repo.bugsCreated),
  };
}

function averageDaysSinceRelease(metrics: RepoMetrics[]): number | null {
  const withRelease = metrics.filter((m) => m.daysSinceLastRelease !== null);
  if (withRelease.length === 0) return null;
  const sum = withRelease.reduce((s, m) => s + (m.daysSinceLastRelease ?? 0), 0);
  return Math.round(sum / withRelease.length);
}

const SUMMARY_TILE_COUNT = 6;

function SummaryCard({ metrics, isLoading, timePeriod }: { metrics: RepoMetrics[]; isLoading: boolean; timePeriod: number }) {
  const totals = summarise(metrics);
  const avgDaysSinceRelease = averageDaysSinceRelease(metrics);

  return (
    <Card className="shadow-lg border-2 border-primary/20">
      <CardHeader>
        <CardTitle className="text-xl text-center">
          Summary - All Repositories
        </CardTitle>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4">
            {Array.from({ length: SUMMARY_TILE_COUNT }).map((_, i) => (
              <Skeleton key={i} className="h-24 rounded-lg" />
            ))}
          </div>
        ) : (
          <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4">
            <MetricCard
              title="Total PRs Open"
              value={totals.prsOpen}
              icon={GitPullRequest}
              color="text-primary"
              detail={`${totals.prsDraft} draft · ${totals.prsApproved} approved`}
            />
            <MetricCard
              title="Total PRs Merged"
              value={totals.prsMerged}
              icon={GitMerge}
              color="text-chart-2"
            />
            <MetricCard
              title="Total Ready for QA"
              value={showValue(totals.issuesReadyForQA)}
              icon={Clock}
              color="text-chart-3"
              detail={readyTrend(totals.issuesReadyForQA, totals.readyForQA1dAgo, totals.readyForQA7dAgo)}
            />
            <MetricCard
              title="Total QA Passed / Failed"
              value={`${showValue(totals.issuesQACompleted)} / ${showValue(totals.issuesQAFailed)}`}
              icon={CheckCircle}
              color="text-green-600"
            />
            <MetricCard
              title={`To QA vs new issues (${timePeriod}d)`}
              value={`${totals.issuesMovedToReadyForQA} / ${totals.issuesCreated}`}
              icon={Route}
              color="text-chart-1"
              detail={roadmapDetail(totals.issuesMovedToReadyForQA, totals.issuesCreated, totals.bugsCreated)}
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
      const r2BaseUrl = import.meta.env.VITE_R2_BASE_URL || '';
      const baseUrl = import.meta.env.BASE_URL || '/';
      const csvFile = r2BaseUrl
        ? `${r2BaseUrl}/repo_summary_${days}d.csv`
        : `${baseUrl}repo_summary_${days}d.csv`;
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

        <SummaryCard metrics={repoMetrics} isLoading={isLoading} timePeriod={timePeriod} />

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
              <RepoCard key={metrics.repoName} metrics={metrics} timePeriod={timePeriod} />
            ))
          )}
        </div>
      </div>
    </div>
  );
}
