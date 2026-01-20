import { useState, useMemo, useEffect } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { 
  loadDoraData, 
  filterDataByDays, 
  calculateDoraMetrics, 
  type DoraData, 
  type FilteredData, 
  type DoraMetrics 
} from "@/lib/dora-calculations";
import MetricCard from "@/components/dashboard/metric-card";
import DeploymentFrequencyChart from "@/components/dashboard/deployment-frequency-chart";
import LeadTimeChart from "@/components/dashboard/lead-time-chart";
import FailureRateChart from "@/components/dashboard/failure-rate-chart";
import MTTRChart from "@/components/dashboard/mttr-chart";
import DeploymentPieChart from "@/components/dashboard/deployment-pie-chart";
import SummaryCards from "@/components/dashboard/summary-cards";
import RecentDeployments from "@/components/dashboard/recent-deployments";
import TeamPerformance from "@/components/dashboard/team-performance";
import PRPerformance from "@/components/dashboard/pr-performance";
import { Rocket, Clock, AlertTriangle, Wrench } from "lucide-react";

export default function Dashboard() {
  const [data, setData] = useState<DoraData | null>(null);
  const [loading, setLoading] = useState(true);
  const [timeFilter, setTimeFilter] = useState<number | null>(30);

  useEffect(() => {
    try {
      const doraData = loadDoraData();
      setData(doraData);
    } catch (error) {
      console.error("Error loading DORA data:", error);
    } finally {
      setLoading(false);
    }
  }, []);

  const filteredData: FilteredData | null = useMemo(() => {
    if (!data) return null;
    return filterDataByDays(data, timeFilter);
  }, [data, timeFilter]);

  const metrics: DoraMetrics | null = useMemo(() => {
    if (!filteredData || !data) return null;
    return calculateDoraMetrics(filteredData, data, timeFilter);
  }, [filteredData, data, timeFilter]);

  if (loading) {
    return (
      <div className="min-h-screen bg-background p-6">
        <div className="max-w-7xl mx-auto space-y-8">
          <div className="bg-card shadow-sm border-b border-border rounded-lg p-6">
            <Skeleton className="h-8 w-64 mb-2" />
            <Skeleton className="h-4 w-96" />
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
            {Array.from({ length: 4 }).map((_, i) => (
              <Skeleton key={i} className="h-32 rounded-lg" />
            ))}
          </div>
        </div>
      </div>
    );
  }

  if (!data || !filteredData || !metrics) {
    return (
      <div className="min-h-screen bg-background p-6">
        <div className="max-w-7xl mx-auto">
          <Card className="w-full max-w-md mx-auto">
            <CardContent className="pt-6">
              <div className="flex mb-4 gap-2">
                <AlertTriangle className="h-8 w-8 text-destructive" />
                <h1 className="text-2xl font-bold text-foreground">Data Loading Error</h1>
              </div>
              <p className="mt-4 text-sm text-muted-foreground">
                Unable to load DORA metrics data. Please check if the data file is available.
              </p>
            </CardContent>
          </Card>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-background">
      {/* Header */}
      <div className="bg-card shadow-sm border-b border-border">
        <div className="max-w-7xl mx-auto px-6 py-4">
          <div className="flex items-center justify-between">
            <div>
              <h1 className="text-2xl font-bold text-foreground" data-testid="dashboard-title">
                Focus Bear - DORA
              </h1>
              <p className="text-muted-foreground">DevOps performance insights and analytics</p>
            </div>
                        <div className="flex gap-2 items-center">
                          <a href="#/overall-velocity-report">
                            <Button variant="outline" size="sm" className="rounded-full mr-4">
                              Overall Velocity Report
                            </Button>
                          </a>
                          {[7, 30, 90].map(days => (
                            <Button
                              key={days}
                              onClick={() => setTimeFilter(days)}
                              variant={timeFilter === days ? "default" : "secondary"}
                              size="sm"
                              data-testid={`filter-${days}days`}
                              className="rounded-full"
                            >
                              {days} days
                            </Button>
                          ))}
                          <Button
                            onClick={() => setTimeFilter(null)}
                            variant={timeFilter === null ? "default" : "secondary"}
                            size="sm"
                            data-testid="filter-all-time"
                            className="rounded-full"
                          >
                            All Time
                          </Button>
                        </div>
          </div>
        </div>
      </div>

      <div className="max-w-7xl mx-auto p-6 space-y-8">
        {/* Top Metrics Cards */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
          <MetricCard
            title="Deployment Frequency"
            value={metrics.deploymentFrequency.toFixed(1)}
            unit="deploys/day"
            trend={metrics.deploymentFrequencyTrend}
            icon={Rocket}
            color="text-primary"
            customTrendText={metrics.deploymentFrequencyTrendText}
            metrics={metrics}
          />
          <MetricCard
            title="Lead Time"
            value={metrics.leadTime.toFixed(1)}
            unit="hours"
            trend={metrics.leadTimeTrend}
            icon={Clock}
            color="text-chart-2"
            invertTrend={true}
            metrics={metrics}
          />
          <MetricCard
            title="Change Failure Rate"
            value={`${metrics.cfr.toFixed(1)}%`}
            unit="failure rate"
            trend={metrics.cfrTrend}
            icon={AlertTriangle}
            color="text-chart-3"
            invertTrend={true}
            metrics={metrics}
          />
          <MetricCard
            title="Total Recovery Time"
            value={metrics.mttr < 1 ? (metrics.mttr * 60).toFixed(1) : metrics.mttr.toFixed(1)}
            unit={metrics.mttr < 1 ? "minutes" : "hours"}
            trend={metrics.mttrTrend}
            icon={Wrench}
            color="text-chart-4"
            invertTrend={true}
            metrics={metrics}
          />
        </div>

        {/* Charts Row */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <DeploymentFrequencyChart data={filteredData.dora_summary_daily} />
          <LeadTimeChart data={filteredData.dora_summary_daily} />
          <FailureRateChart data={filteredData.dora_summary_daily} />
          <MTTRChart data={filteredData.dora_summary_daily} />
        </div>

        {/* Deployment Success Rate and Summary Cards */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          <DeploymentPieChart deployments={filteredData.fact_deployment} />
          <div className="lg:col-span-2">
            <SummaryCards metrics={metrics} />
          </div>
        </div>

        {/* Data Tables */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          <RecentDeployments deployments={filteredData.fact_deployment} />
          <TeamPerformance deployments={filteredData.fact_deployment} />
          <PRPerformance prs={filteredData.fact_pr} />
        </div>
      </div>
    </div>
  );
}
