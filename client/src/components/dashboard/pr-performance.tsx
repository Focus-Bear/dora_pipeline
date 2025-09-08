import { useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { DoraData } from "@/lib/dora-calculations";
import { ChevronDown, ChevronUp } from "lucide-react";

interface PRPerformanceProps {
  prs: DoraData['fact_pr'];
}

export default function PRPerformance({ prs }: PRPerformanceProps) {
  const [isExpanded, setIsExpanded] = useState(false);
  
  if (!prs || prs.length === 0) {
    return (
      <Card data-testid="pr-performance">
        <CardHeader>
          <CardTitle>PR Performance by Author</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="text-center text-muted-foreground py-8">
            No PR data available
          </div>
        </CardContent>
      </Card>
    );
  }

  // Group PRs by author and calculate statistics
  const authorStats = prs.reduce((acc, pr) => {
    const author = pr.author;
    if (!acc[author]) {
      acc[author] = {
        author,
        totalPRs: 0,
        mergedPRs: 0
      };
    }
    acc[author].totalPRs++;
    acc[author].mergedPRs++; // All PRs in fact_pr are merged PRs
    return acc;
  }, {} as Record<string, { author: string; totalPRs: number; mergedPRs: number }>);

  const authorData = Object.values(authorStats)
    .sort((a, b) => b.totalPRs - a.totalPRs); // Sort by most PRs first
  
  const displayedAuthors = isExpanded ? authorData : authorData.slice(0, 5);
  const hasMoreAuthors = authorData.length > 5;

  return (
    <Card data-testid="pr-performance">
      <CardHeader>
        <CardTitle className="flex items-center justify-between">
          PR Performance
          {hasMoreAuthors && !isExpanded && (
            <span className="text-sm font-normal text-muted-foreground">
              Top 5 of {authorData.length}
            </span>
          )}
        </CardTitle>
      </CardHeader>
      <CardContent>
        <div className="space-y-3">
          {displayedAuthors.map((author, index) => (
            <div 
              key={author.author} 
              className="flex items-center justify-between p-2 bg-muted/50 rounded-lg border border-border/50 hover:bg-muted transition-colors" 
              data-testid={`pr-author-${index}`}
            >
              <div className="flex items-center space-x-3">
                <div className="w-8 h-8 bg-chart-2/10 rounded-full flex items-center justify-center">
                  <span className="text-sm font-medium text-chart-2">#{index + 1}</span>
                </div>
                <div>
                  <p className="font-medium text-foreground text-sm">{author.author}</p>
                  <p className="text-xs text-muted-foreground">
                    {author.totalPRs} PR{author.totalPRs !== 1 ? 's' : ''} merged
                  </p>
                </div>
              </div>
              <div className="text-right">
                <p className="font-bold text-foreground" data-testid={`pr-count-${author.author}`}>
                  {author.totalPRs}
                </p>
                <p className="text-xs text-muted-foreground">PRs</p>
              </div>
            </div>
          ))}
          {hasMoreAuthors && (
            <div className="pt-2">
              <Button
                variant="ghost"
                size="sm"
                onClick={() => setIsExpanded(!isExpanded)}
                className="w-full text-muted-foreground hover:text-foreground"
                data-testid="pr-see-more-button"
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
                      See all {authorData.length} authors
                    </>
                  )}
                </span>
              </Button>
            </div>
          )}
        </div>
      </CardContent>
    </Card>
  );
}