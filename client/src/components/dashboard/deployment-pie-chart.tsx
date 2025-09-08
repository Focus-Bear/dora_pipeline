import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { PieChart, Pie, Cell, ResponsiveContainer, Tooltip, Legend } from 'recharts';
import { getDeploymentStatusCounts, DoraData } from "@/lib/dora-calculations";

interface DeploymentPieChartProps {
  deployments: DoraData['fact_deployment'];
}

export default function DeploymentPieChart({ deployments }: DeploymentPieChartProps) {
  const data = getDeploymentStatusCounts(deployments);
  
  if (deployments.length === 0) {
    return (
      <Card data-testid="deployment-pie-chart">
        <CardHeader>
          <CardTitle>Deployment Success Rate</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="h-[300px] flex items-center justify-center text-muted-foreground">
            No deployments found
          </div>
        </CardContent>
      </Card>
    );
  }

  const total = data.reduce((sum, item) => sum + item.value, 0);
  
  return (
    <Card data-testid="deployment-pie-chart">
      <CardHeader>
        <CardTitle>Deployment Success Rate</CardTitle>
      </CardHeader>
      <CardContent>
        <div className="h-[300px]">
          <ResponsiveContainer width="100%" height="100%">
            <PieChart>
              <Pie
                data={data}
                cx="50%"
                cy="50%"
                innerRadius={40}
                outerRadius={80}
                paddingAngle={5}
                dataKey="value"
              >
                {data.map((entry, index) => (
                  <Cell key={`cell-${index}`} fill={entry.fill} />
                ))}
              </Pie>
              <Tooltip 
                formatter={(value, name) => [
                  `${value} (${((Number(value) / total) * 100).toFixed(1)}%)`,
                  name
                ]}
                contentStyle={{
                  backgroundColor: 'hsl(var(--card))',
                  border: '1px solid hsl(var(--border))',
                  borderRadius: '8px'
                }}
              />
              <Legend />
            </PieChart>
          </ResponsiveContainer>
        </div>
      </CardContent>
    </Card>
  );
}
