import { useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { getTeamPerformance, DoraData } from "@/lib/dora-calculations";
import { ChevronDown, ChevronUp } from "lucide-react";

interface TeamPerformanceProps {
  deployments: DoraData['fact_deployment'];
}

export default function TeamPerformance({ deployments }: TeamPerformanceProps) {
  const [isExpanded, setIsExpanded] = useState(false);
  const teamData = getTeamPerformance(deployments);

  const displayedMembers = isExpanded ? teamData : teamData.slice(0, 5);
  const hasMoreMembers = teamData.length > 5;

  return (
    <Card data-testid="team-performance">
      <CardHeader>
        <CardTitle className="flex items-center justify-between">
          Team Performance
          {hasMoreMembers && !isExpanded && (
            <span className="text-sm font-normal text-muted-foreground">
              Top 5 of {teamData.length}
            </span>
          )}
        </CardTitle>
      </CardHeader>
      <CardContent>
        {teamData.length === 0 ? (
          <div className="text-center text-muted-foreground py-8">
            No team data available
          </div>
        ) : (
          <div className="space-y-3">
            {displayedMembers.map((member, index) => (
              <div 
                key={member.actor} 
                className="flex items-center justify-between p-2 bg-muted/50 rounded-lg border border-border/50 hover:bg-muted transition-colors" 
                data-testid={`team-member-${index}`}
              >
                <div className="flex items-center space-x-3">
                  <div className="w-8 h-8 bg-primary/10 rounded-full flex items-center justify-center">
                    <span className="text-sm font-medium text-primary">#{index + 1}</span>
                  </div>
                  <div>
                    <p className="font-medium text-foreground text-sm">{member.actor}</p>
                    <p className="text-xs text-muted-foreground">
                      {member.deployments} deployment{member.deployments !== 1 ? 's' : ''}
                    </p>
                  </div>
                </div>
                <div className="text-right">
                  <p className="font-bold text-foreground" data-testid={`success-rate-${member.actor}`}>
                    {member.successRate.toFixed(1)}%
                  </p>
                  <p className="text-xs text-muted-foreground">success</p>
                </div>
              </div>
            ))}
            {hasMoreMembers && (
              <div className="pt-2">
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => setIsExpanded(!isExpanded)}
                  className="w-full text-muted-foreground hover:text-foreground"
                  data-testid="team-see-more-button"
                >
                  <span className="flex items-center gap-2">
                    {isExpanded ? (
                      <>
                        <ChevronUp className="h-4 w-4" />
                        Show less
                      </>
                    ) : (
                      <>
                        <ChevronDown className="h-4 w-4" />
                        See all {teamData.length} members
                      </>
                    )}
                  </span>
                </Button>
              </div>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
