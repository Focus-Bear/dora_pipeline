import { useState, useEffect } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import {
  AlertTriangle,
  Bug,
  CheckCircle,
  Clock,
  GitMerge,
  GitPullRequest,
  Hourglass,
  RefreshCw,
  Rocket,
  XCircle,
} from "lucide-react";
import {
  NOT_AVAILABLE,
  failureDetail,
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
  prsMergedPrev: number;
  issuesCreated: number;
  issuesCreatedPrev: number;
  bugsCreated: number;
  // QA figures are null for repos whose board has no QA columns; the failed
  // counts are also null for boards without a QA Failed column.
  issuesQAFailed: number | null;
  issuesQAFailedPrev: number | null;
  issuesQATested: number | null;
  issuesQATestedPrev: number | null;
  issuesReadyForQA: number | null;
  readyForQA7dAgo: number | null;
  qaBacklogMedianDays: number | null;
  qaBacklogOldestDays: number | null;
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
      prsMergedPrev: parseInteger(row["prs_merged_prev"]),
      issuesCreated: parseInteger(row["issues_created"]),
      issuesCreatedPrev: parseInteger(row["issues_created_prev"]),
      bugsCreated: parseInteger(row["bugs_created"]),
      issuesQAFailed: parseOptionalInt(row["issues_qa_failed"]),
      issuesQAFailedPrev: parseOptionalInt(row["issues_qa_failed_prev"]),
      issuesQATested: parseOptionalInt(row["issues_qa_tested"]),
      issuesQATestedPrev: parseOptionalInt(row["issues_qa_tested_prev"]),
      issuesReadyForQA: parseOptionalInt(row["issues_ready_for_qa"]),
      readyForQA7dAgo: parseOptionalInt(row["ready_for_qa_7d_ago"]),
      qaBacklogMedianDays: parseOptionalInt(row["qa_backlog_median_days"]),
      qaBacklogOldestDays: parseOptionalInt(row["qa_backlog_oldest_days"]),
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

function previousDetail(previous: number): string {
  return `prev ${previous}`;
}

function backlogTrend(current: number | null, weekAgo: number | null): string {
  return `${trendLabel(current, weekAgo)} vs 7 days ago`;
}

function plural(count: number, noun: string): string {
  return `${count} ${noun}${count === 1 ? "" : "s"}`;
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

function SectionHeading({ children }: { children: React.ReactNode }) {
  return <h3 className="col-span-full text-xs font-semibold uppercase tracking-wide text-muted-foreground">{children}</h3>;
}

interface SectionFigures {
  prsOpen: number;
  prsDraft: number;
  prsApproved: number;
  prsMerged: number;
  prsMergedPrev: number;
  issuesCreated: number;
  issuesCreatedPrev: number;
  bugsCreated: number;
  issuesQAFailed: number | null;
  issuesQAFailedPrev: number | null;
  issuesQATested: number | null;
  issuesQATestedPrev: number | null;
  issuesReadyForQA: number | null;
  readyForQA7dAgo: number | null;
  qaBacklogMedianDays: number | null;
  qaBacklogOldestDays: number | null;
}

function VelocityTiles({ figures }: { figures: SectionFigures }) {
  return (
    <>
      <MetricCard
        title="PRs merged"
        value={figures.prsMerged}
        icon={GitMerge}
        color="text-chart-2"
        detail={previousDetail(figures.prsMergedPrev)}
      />
      <MetricCard
        title="PRs open now"
        value={figures.prsOpen}
        icon={GitPullRequest}
        color="text-primary"
        detail={`${figures.prsDraft} draft · ${figures.prsApproved} approved`}
      />
    </>
  );
}

function QualityTiles({ figures }: { figures: SectionFigures }) {
  const hasFailedColumn = figures.issuesQAFailed !== null;
  return (
    <>
      <MetricCard
        title="New issues"
        value={figures.issuesCreated}
        icon={Bug}
        color="text-chart-1"
        detail={`${plural(figures.bugsCreated, "bug")} · ${previousDetail(figures.issuesCreatedPrev)}`}
      />
      <MetricCard
        title="QA failed / tested"
        value={hasFailedColumn ? `${figures.issuesQAFailed} / ${showValue(figures.issuesQATested)}` : NOT_AVAILABLE}
        icon={figures.issuesQAFailed ? XCircle : CheckCircle}
        color={figures.issuesQAFailed ? "text-destructive" : "text-green-600"}
        detail={hasFailedColumn
          ? failureDetail(figures.issuesQAFailed, figures.issuesQATested, figures.issuesQAFailedPrev, figures.issuesQATestedPrev)
          : "no QA Failed column"}
      />
    </>
  );
}

function BacklogTiles({ figures }: { figures: SectionFigures }) {
  return (
    <>
      <MetricCard
        title="Ready for QA"
        value={showValue(figures.issuesReadyForQA)}
        icon={Clock}
        color="text-chart-3"
        detail={backlogTrend(figures.issuesReadyForQA, figures.readyForQA7dAgo)}
      />
      <MetricCard
        title="Oldest wait"
        value={showValue(figures.qaBacklogOldestDays)}
        icon={Hourglass}
        color="text-chart-4"
        suffix={figures.qaBacklogOldestDays === null ? undefined : "d"}
        detail={figures.qaBacklogMedianDays === null ? undefined : `median ${figures.qaBacklogMedianDays}d`}
      />
    </>
  );
}

function RepoCardContent({ metrics }: { metrics: RepoMetrics }) {
  const hasQABoard = metrics.issuesReadyForQA !== null;
  return (
    <div className="grid grid-cols-2 gap-4">
      <SectionHeading>1. Dev velocity</SectionHeading>
      <VelocityTiles figures={metrics} />
      <SectionHeading>2. Quality</SectionHeading>
      <QualityTiles figures={metrics} />
      {hasQABoard && (
        <>
          <SectionHeading>3. QA backlog</SectionHeading>
          <BacklogTiles figures={metrics} />
        </>
      )}
      {metrics.daysSinceLastRelease !== null && (
        <>
          <SectionHeading>Appendix</SectionHeading>
          <MetricCard
            title="Days since release"
            value={metrics.daysSinceLastRelease}
            icon={Rocket}
            color="text-orange-500"
            suffix="d"
            detail={[metrics.releaseVersion, metrics.releaseSource].filter(Boolean).join(" · ")}
          />
        </>
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

function summarise(metrics: RepoMetrics[]): SectionFigures {
  const sum = (pick: (repo: RepoMetrics) => number) => metrics.reduce((total, repo) => total + pick(repo), 0);
  const sumOptional = (pick: (repo: RepoMetrics) => number | null) => sumKnown(metrics.map(pick));
  // The failure rate only covers boards that have a QA Failed column.
  const withFailedColumn = metrics.filter((repo) => repo.issuesQAFailed !== null);
  const sumFailedBoards = (pick: (repo: RepoMetrics) => number | null) => sumKnown(withFailedColumn.map(pick));
  const knownOldest = metrics.map((repo) => repo.qaBacklogOldestDays).filter((days): days is number => days !== null);
  return {
    prsOpen: sum((repo) => repo.prsOpen),
    prsDraft: sum((repo) => repo.prsDraft),
    prsApproved: sum((repo) => repo.prsApproved),
    prsMerged: sum((repo) => repo.prsMerged),
    prsMergedPrev: sum((repo) => repo.prsMergedPrev),
    issuesCreated: sum((repo) => repo.issuesCreated),
    issuesCreatedPrev: sum((repo) => repo.issuesCreatedPrev),
    bugsCreated: sum((repo) => repo.bugsCreated),
    issuesQAFailed: sumFailedBoards((repo) => repo.issuesQAFailed),
    issuesQAFailedPrev: sumFailedBoards((repo) => repo.issuesQAFailedPrev),
    issuesQATested: sumFailedBoards((repo) => repo.issuesQATested),
    issuesQATestedPrev: sumFailedBoards((repo) => repo.issuesQATestedPrev),
    issuesReadyForQA: sumOptional((repo) => repo.issuesReadyForQA),
    readyForQA7dAgo: sumOptional((repo) => repo.readyForQA7dAgo),
    // A median of medians is not a median, so the summary shows only the oldest wait.
    qaBacklogMedianDays: null,
    qaBacklogOldestDays: knownOldest.length === 0 ? null : Math.max(...knownOldest),
  };
}

const SUMMARY_TILE_COUNT = 6;

function SummaryCard({ metrics, isLoading, timePeriod }: { metrics: RepoMetrics[]; isLoading: boolean; timePeriod: number }) {
  const totals = summarise(metrics);

  return (
    <Card className="shadow-lg border-2 border-primary/20">
      <CardHeader>
        <CardTitle className="text-xl text-center">
          Summary - All Repositories
        </CardTitle>
        <p className="text-sm text-muted-foreground text-center">
          Last {timePeriod} days; "prev" is the {timePeriod} days before that.
        </p>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4">
            {Array.from({ length: SUMMARY_TILE_COUNT }).map((_, i) => (
              <Skeleton key={i} className="h-24 rounded-lg" />
            ))}
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            <div className="grid grid-cols-2 gap-4">
              <SectionHeading>1. Dev velocity</SectionHeading>
              <VelocityTiles figures={totals} />
            </div>
            <div className="grid grid-cols-2 gap-4">
              <SectionHeading>2. Quality</SectionHeading>
              <QualityTiles figures={totals} />
            </div>
            <div className="grid grid-cols-2 gap-4">
              <SectionHeading>3. QA backlog</SectionHeading>
              <BacklogTiles figures={totals} />
            </div>
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
  const [timePeriod, setTimePeriod] = useState<7 | 30>(7);

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
              <RepoCard key={metrics.repoName} metrics={metrics} />
            ))
          )}
        </div>
      </div>
    </div>
  );
}
