import { Card, CardContent } from "@/components/ui/card";
import { Upload, CheckCircle, Bug, GitBranch,Braces,GitPullRequest } from "lucide-react";
import { DoraMetrics } from "@/lib/dora-calculations";

interface SummaryCardsProps {
  metrics: DoraMetrics;
}

export default function SummaryCards({ metrics }: SummaryCardsProps) {
  const cards = [
    {
      title: "Total Deployments",
      value: metrics.totalDeployments,
      icon: Upload,
      color: "text-primary"
    },
    {
      title: "Success Rate",
      value: `${metrics.successRate.toFixed(1)}%`,
      icon: CheckCircle,
      color: "text-green-600"
    },
    {
      title: "Resolved Incidents",
      value: metrics.totalIncidents,
      icon: Bug,
      color: "text-chart-4"
    },
    {
      title: "PRs Merged",
      value: metrics.totalPRs,
      icon: GitBranch,
      color: "text-chart-5"
    },
    {
      title: "Issues in QA",
      value: metrics.issuesInQA,
      icon: Braces,
      color: "text-chart-5"
    },{
      title: "PRs Open",
      value: metrics.totalOpenPRs,
      icon: GitPullRequest,
      color: "text-primary"
    }
  ];

  return (
    <div className="grid grid-cols-2 gap-4">
      {cards.map((card, index) => (
        <Card key={index} className="shadow-md border border-border" data-testid={`summary-card-${card.title.toLowerCase().replace(/\s+/g, '-')}`}>
          <CardContent className="p-4">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-2xl font-bold text-foreground" data-testid={`summary-value-${card.title.toLowerCase().replace(/\s+/g, '-')}`}>
                  {card.value}
                </p>
                <p className="text-sm text-muted-foreground">{card.title}</p>
              </div>
              <card.icon className={`${card.color} h-6 w-6`} />
            </div>
          </CardContent>
        </Card>
      ))}
    </div>
  );
}
