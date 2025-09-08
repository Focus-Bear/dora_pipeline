import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';
import { DoraData } from "@/lib/dora-calculations";

interface MTTRChartProps {
  data: DoraData['dora_summary_daily'];
}

export default function MTTRChart({ data }: MTTRChartProps) {
  if (!data || data.length === 0) {
    return (
      <Card data-testid="mttr-chart">
        <CardHeader>
          <CardTitle>Mean Time to Recovery (MTTR)</CardTitle>
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
    .filter(d => d.mttr_min > 0)
    .sort((a, b) => new Date(a.date).getTime() - new Date(b.date).getTime())
    .map(d => ({
      date: new Date(d.date).toLocaleDateString('en-US', { month: 'short', day: 'numeric' }),
      mttr: d.mttr_min / 60
    }));

  return (
    <Card data-testid="mttr-chart">
      <CardHeader>
        <CardTitle>Mean Time to Recovery (MTTR)</CardTitle>
      </CardHeader>
      <CardContent>
        <div className="h-[300px]">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={chartData}>
              <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
              <XAxis 
                dataKey="date" 
                stroke="hsl(var(--muted-foreground))"
                fontSize={12}
              />
              <YAxis 
                stroke="hsl(var(--muted-foreground))"
                fontSize={12}
              />
              <Tooltip 
                contentStyle={{
                  backgroundColor: 'hsl(var(--card))',
                  border: '1px solid hsl(var(--border))',
                  borderRadius: '8px'
                }}
                formatter={(value) => [`${Number(value).toFixed(1)} hrs`, 'MTTR']}
              />
              <Bar 
                dataKey="mttr" 
                fill="hsl(var(--chart-4))" 
                radius={[4, 4, 0, 0]}
              />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </CardContent>
    </Card>
  );
}
