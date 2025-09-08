import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';
import { DoraData } from "@/lib/dora-calculations";

interface FailureRateChartProps {
  data: DoraData['dora_summary_daily'];
}

export default function FailureRateChart({ data }: FailureRateChartProps) {
  if (!data || data.length === 0) {
    return (
      <Card data-testid="failure-rate-chart">
        <CardHeader>
          <CardTitle>Change Failure Rate Trend</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="h-[300px] flex items-center justify-center text-muted-foreground">
            No data available
          </div>
        </CardContent>
      </Card>
    );
  }

  const chartData = data
    .filter(d => d.deploys > 0)
    .sort((a, b) => new Date(a.date).getTime() - new Date(b.date).getTime())
    .map(d => ({
      date: new Date(d.date).toLocaleDateString('en-US', { month: 'short', day: 'numeric' }),
      failureRate: d.cfr * 100
    }));

  return (
    <Card data-testid="failure-rate-chart">
      <CardHeader>
        <CardTitle>Change Failure Rate Trend</CardTitle>
      </CardHeader>
      <CardContent>
        <div className="h-[300px]">
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={chartData}>
              <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
              <XAxis 
                dataKey="date" 
                stroke="hsl(var(--muted-foreground))"
                fontSize={12}
              />
              <YAxis 
                stroke="hsl(var(--muted-foreground))"
                fontSize={12}
                domain={[0, 100]}
                ticks={[0, 20, 40, 60, 80, 100]}
                tickFormatter={(value) => `${Math.round(value)}`}
              />
              <Tooltip 
                contentStyle={{
                  backgroundColor: 'hsl(var(--card))',
                  border: '1px solid hsl(var(--border))',
                  borderRadius: '8px'
                }}
                formatter={(value) => [`${Number(value).toFixed(1)}%`, 'Failure Rate']}
              />
              <Area 
                type="monotone" 
                dataKey="failureRate" 
                stroke="hsl(var(--chart-3))" 
                fill="hsl(var(--chart-3))"
                fillOpacity={0.3}
                strokeWidth={2}
              />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      </CardContent>
    </Card>
  );
}
