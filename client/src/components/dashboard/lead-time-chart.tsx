import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';
import { DoraData } from "@/lib/dora-calculations";

interface LeadTimeChartProps {
  data: DoraData['dora_summary_daily'];
}

export default function LeadTimeChart({ data }: LeadTimeChartProps) {
  if (!data || data.length === 0) {
    return (
      <Card data-testid="lead-time-chart">
        <CardHeader>
          <CardTitle>Lead Time Trend</CardTitle>
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
    .filter(d => d.avg_lt_hours > 0)
    .sort((a, b) => new Date(a.date).getTime() - new Date(b.date).getTime())
    .map(d => ({
      date: new Date(d.date).toLocaleDateString('en-US', { month: 'short', day: 'numeric' }),
      leadTime: d.avg_lt_hours
    }));

  return (
    <Card data-testid="lead-time-chart">
      <CardHeader>
        <CardTitle>Lead Time Trend</CardTitle>
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
              />
              <Tooltip 
                contentStyle={{
                  backgroundColor: 'hsl(var(--card))',
                  border: '1px solid hsl(var(--border))',
                  borderRadius: '8px'
                }}
                formatter={(value) => [`${Number(value).toFixed(1)} hrs`, 'Lead Time']}
              />
              <Area 
                type="monotone" 
                dataKey="leadTime" 
                stroke="hsl(var(--chart-2))" 
                fill="hsl(var(--chart-2))"
                fillOpacity={0.2}
                strokeWidth={2}
              />
            </AreaChart>
          </ResponsiveContainer>
        </div>
        
      </CardContent>
    </Card>
  );
}
