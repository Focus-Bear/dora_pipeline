import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { DoraData } from "@/lib/dora-calculations";

interface RecentDeploymentsProps {
  deployments: DoraData['fact_deployment'];
}

export default function RecentDeployments({ deployments }: RecentDeploymentsProps) {
  const recentDeployments = deployments.slice(0, 8);
  
  const getStatusVariant = (state: string) => {
    switch (state) {
      case 'success':
        return 'default';
      case 'inactive':
        return 'secondary';
      case 'error':
      case 'failure':
        return 'destructive';
      default:
        return 'outline';
    }
  };

  return (
    <Card data-testid="recent-deployments">
      <CardHeader>
        <CardTitle>Recent Deployments</CardTitle>
      </CardHeader>
      <CardContent>
        {recentDeployments.length === 0 ? (
          <div className="text-center text-muted-foreground py-8">
            No deployments found
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border">
                  <th className="text-left py-2 text-muted-foreground">Date</th>
                  <th className="text-left py-2 text-muted-foreground">Actor</th>
                  <th className="text-left py-2 text-muted-foreground">Status</th>
                </tr>
              </thead>
              <tbody>
                {recentDeployments.map((deployment, index) => (
                  <tr key={deployment.deployment_id} className="border-b border-border" data-testid={`deployment-row-${index}`}>
                    <td className="py-2">
                      {new Date(deployment.created_at_utc).toLocaleDateString()}
                    </td>
                    <td className="py-2 text-muted-foreground">{deployment.actor}</td>
                    <td className="py-2">
                      <Badge variant={getStatusVariant(deployment.state)}>
                        {deployment.state}
                      </Badge>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
