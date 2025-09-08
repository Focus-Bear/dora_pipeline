import { Card, CardContent } from "@/components/ui/card";
import { LucideIcon, TrendingUp, TrendingDown, Clock, Target, CheckCircle, XCircle } from "lucide-react";
import { DoraMetrics } from "@/lib/dora-calculations";

interface MetricCardProps {
  title: string;
  value: string;
  unit: string;
  trend: number;
  icon: LucideIcon;
  color: string;
  invertTrend?: boolean;
  customTrendText?: string;
  metrics?: DoraMetrics;
}

export default function MetricCard({ 
  title, 
  value, 
  unit, 
  trend, 
  icon: Icon, 
  color, 
  invertTrend = false,
  customTrendText,
  metrics
}: MetricCardProps) {
  const isPositiveTrend = invertTrend ? trend < 0 : trend > 0;
  const trendColor = isPositiveTrend ? "text-green-600" : "text-red-600";
  const TrendIcon = trend > 0 ? TrendingUp : TrendingDown;

  return (
    <Card className="metric-card transition-all duration-200 hover:-translate-y-1 hover:shadow-lg" data-testid={`metric-card-${title.toLowerCase().replace(/\s+/g, '-')}`}>
      <CardContent className="p-6">
        <div className="flex items-center justify-between mb-2">
          <h3 className="text-sm font-medium text-muted-foreground">{title}</h3>
          <Icon className={`h-5 w-5 ${color}`} />
        </div>
        <div className="space-y-1">
          <p className="text-2xl font-bold text-foreground" data-testid={`metric-value-${title.toLowerCase().replace(/\s+/g, '-')}`}>
            {value}
          </p>
          <p className="text-xs text-muted-foreground">{unit}</p>
          {/* Hide trend for cards that show detailed insights */}
          {title !== "Lead Time" && title !== "Total Recovery Time" && title !== "Deployment Frequency" && title !== "Change Failure Rate" && (
            <div className={`flex items-center text-xs ${trendColor}`} data-testid={`metric-trend-${title.toLowerCase().replace(/\s+/g, '-')}`}>
              <TrendIcon className="w-3 h-3 mr-1" />
              {customTrendText || `${Math.abs(trend).toFixed(1)}%`}
            </div>
          )}
          
          {/* Change Failure Rate Insights */}
          {title === "Change Failure Rate" && metrics && (
            <div className="mt-3 pt-3 border-t border-border">
              <div className="grid grid-cols-3 gap-2">
                <div className="text-center">
                  <div className="flex items-center justify-center mb-1">
                    <XCircle className="h-3 w-3 text-red-500 mr-1" />
                    <span className="text-xs font-medium text-muted-foreground">FAILED</span>
                  </div>
                  <p className="text-sm font-bold text-foreground" data-testid="failed-deployments">
                    {metrics.failedDeployments}
                  </p>
                </div>
                
                <div className="text-center">
                  <div className="flex items-center justify-center mb-1">
                    <CheckCircle className="h-3 w-3 text-green-500 mr-1" />
                    <span className="text-xs font-medium text-muted-foreground">SUCCESS</span>
                  </div>
                  <p className="text-sm font-bold text-foreground" data-testid="successful-deployments">
                    {metrics.successfulDeployments}
                  </p>
                </div>
                
                <div className="text-center">
                  <div className="flex items-center justify-center mb-1">
                    {metrics.cfrTrendStatus === 'good' ? (
                      <CheckCircle className="h-3 w-3 text-green-500 mr-1" />
                    ) : (
                      <XCircle className="h-3 w-3 text-red-500 mr-1" />
                    )}
                    <span className="text-xs font-medium text-muted-foreground">TREND</span>
                  </div>
                  <p className={`text-sm font-bold ${metrics.cfrTrendStatus === 'good' ? 'text-green-600' : 'text-red-600'}`} data-testid="cfr-trend">
                    {metrics.cfrTrendStatus === 'good' ? 'Good' : 'Bad'}
                  </p>
                </div>
              </div>
            </div>
          )}
          
          {/* Deployment Frequency Insights */}
          {title === "Deployment Frequency" && metrics && (
            <div className="mt-3 pt-3 border-t border-border">
              <div className="grid grid-cols-3 gap-2">
                <div className="text-center">
                  <div className="flex items-center justify-center mb-1">
                    <Clock className="h-3 w-3 text-orange-500 mr-1" />
                    <span className="text-xs font-medium text-muted-foreground">YESTERDAY</span>
                  </div>
                  <p className="text-sm font-bold text-foreground" data-testid="deployments-yesterday">
                    {metrics.deploymentsYesterday}
                  </p>
                </div>
                
                <div className="text-center">
                  <div className="flex items-center justify-center mb-1">
                    <Target className="h-3 w-3 text-blue-500 mr-1" />
                    <span className="text-xs font-medium text-muted-foreground">WEEK</span>
                  </div>
                  <p className="text-sm font-bold text-foreground" data-testid="deployments-last-week">
                    {metrics.deploymentsLastWeek}
                  </p>
                </div>
                
                <div className="text-center">
                  <div className="flex items-center justify-center mb-1">
                    <CheckCircle className="h-3 w-3 text-green-500 mr-1" />
                    <span className="text-xs font-medium text-muted-foreground">MONTH</span>
                  </div>
                  <p className="text-sm font-bold text-foreground" data-testid="deployments-last-month">
                    {metrics.deploymentsLastMonth}
                  </p>
                </div>
              </div>
            </div>
          )}
          
          {/* Lead Time Insights */}
          {title === "Lead Time" && metrics && (
            <div className="mt-3 pt-3 border-t border-border">
              <div className="grid grid-cols-3 gap-2">
                <div className="text-center">
                  <div className="flex items-center justify-center mb-1">
                    <TrendingUp className="h-3 w-3 text-red-500 mr-1" />
                    <span className="text-xs font-medium text-muted-foreground">MAX</span>
                  </div>
                  <p className="text-sm font-bold text-foreground" data-testid="max-lead-time">
                    {metrics.maxLeadTime.toFixed(1)}h
                  </p>
                </div>
                
                <div className="text-center">
                  <div className="flex items-center justify-center mb-1">
                    <TrendingDown className="h-3 w-3 text-green-500 mr-1" />
                    <span className="text-xs font-medium text-muted-foreground">MIN</span>
                  </div>
                  <p className="text-sm font-bold text-foreground" data-testid="min-lead-time">
                    {metrics.minLeadTime.toFixed(1)}h
                  </p>
                </div>
                
                <div className="text-center">
                  <div className="flex items-center justify-center mb-1">
                    <Clock className="h-3 w-3 text-blue-500 mr-1" />
                    <span className="text-xs font-medium text-muted-foreground">LAST</span>
                  </div>
                  <p className="text-sm font-bold text-foreground" data-testid="last-deployment-lead-time">
                    {metrics.lastDeploymentLeadTime.toFixed(1)}h
                  </p>
                </div>
              </div>
            </div>
          )}
          
          {/* MTTR Insights */}
          {title === "Total Recovery Time" && metrics && (
            <div className="mt-3 pt-3 border-t border-border">
              <div className="grid grid-cols-3 gap-2">
                <div className="text-center">
                  <div className="flex items-center justify-center mb-1">
                    <TrendingUp className="h-3 w-3 text-red-500 mr-1" />
                    <span className="text-xs font-medium text-muted-foreground">MAX</span>
                  </div>
                  <p className="text-sm font-bold text-foreground" data-testid="max-mttr">
                    {metrics.maxMTTR < 1 ? `${(metrics.maxMTTR * 60).toFixed(1)}m` : `${metrics.maxMTTR.toFixed(1)}h`}
                  </p>
                </div>
                
                <div className="text-center">
                  <div className="flex items-center justify-center mb-1">
                    <TrendingDown className="h-3 w-3 text-green-500 mr-1" />
                    <span className="text-xs font-medium text-muted-foreground">MIN</span>
                  </div>
                  <p className="text-sm font-bold text-foreground" data-testid="min-mttr">
                    {metrics.minMTTR < 1 ? `${(metrics.minMTTR * 60).toFixed(1)}m` : `${metrics.minMTTR.toFixed(1)}h`}
                  </p>
                </div>
                
                <div className="text-center">
                  <div className="flex items-center justify-center mb-1">
                    <Clock className="h-3 w-3 text-blue-500 mr-1" />
                    <span className="text-xs font-medium text-muted-foreground">LAST</span>
                  </div>
                  <p className="text-sm font-bold text-foreground" data-testid="last-incident-mttr">
                    {metrics.lastIncidentMTTR < 1 ? `${(metrics.lastIncidentMTTR * 60).toFixed(1)}m` : `${metrics.lastIncidentMTTR.toFixed(1)}h`}
                  </p>
                </div>
              </div>
            </div>
          )}
        </div>
      </CardContent>
    </Card>
  );
}
