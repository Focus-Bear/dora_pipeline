import doraData from "./../../../dora.json";

export interface DoraData {
  fact_deployment: Array<{
    deployment_id: number;
    environment: string;
    created_at_utc: string;
    finished_at_utc: string;
    state: string;
    actor: string;
    sha: string;
    ref: string;
    log_url?: string;
    source_fetched_at_utc: string;
    etl_run_id: string;
  }>;
  fact_pr?: Array<{
    pr_number: number;
    pr_merged_at_utc: string;
    pr_merge_sha: string;
    author: string;
  }>;
  fact_incident?: Array<{
    incident_id: string;
    title: string;
    created_utc: string;
    closed_utc: string;
    duration_minutes: number;
    source_fetched_at_utc: string;
    etl_run_id: string;
  }>;
  dora_events?: Array<{
    event_id: number;
    event_type: string;
    when_utc: string;
    sha?: string | null;
    pr_number?: number | null;
    deployment_id?: number | null;
    incident_id?: string | null;
    title?: string | null;
    state?: string | null;
  }>;
  dora_summary_daily?: Array<{
    date: string;
    deploys: number;
    failed_deploys: number;
    cfr: number;
    avg_lt_hours: number;
    mttr_min: number;
  }>;
}

export interface DoraMetrics {
  deploymentFrequency: number;
  deploymentFrequencyTrend: number;
  deploymentFrequencyTrendText?: string;
  deploymentsYesterday: number;
  deploymentsLastWeek: number;
  deploymentsLastMonth: number;
  leadTime: number;
  leadTimeTrend: number;
  maxLeadTime: number;
  minLeadTime: number;
  lastDeploymentLeadTime: number;
  cfr: number;
  cfrTrend: number;
  cfrTrendStatus: 'good' | 'bad';
  failedDeployments: number;
  successfulDeployments: number;
  mttr: number;
  mttrTrend: number;
  maxMTTR: number;
  minMTTR: number;
  lastIncidentMTTR: number;
  totalDeployments: number;
  successRate: number;
  totalIncidents: number;
  totalPRs: number;
}

export interface FilteredData {
  fact_deployment: DoraData['fact_deployment'];
  dora_summary_daily: DoraData['dora_summary_daily'];
  fact_pr: DoraData['fact_pr'];
  fact_incident: DoraData['fact_incident'];
  dora_events: DoraData['dora_events'];
}

export function loadDoraData(): DoraData {
  return doraData as DoraData;
}

export function filterDataByDays(data: DoraData, days: number | null): FilteredData {
  if (days === null) {
    // Return all data for "All Time" filter
    return {
      fact_deployment: data.fact_deployment,
      dora_summary_daily: data.dora_summary_daily?.slice().reverse() || [],
      fact_pr: data.fact_pr || [],
      fact_incident: data.fact_incident || [],
      dora_events: data.dora_events || []
    };
  }
  
  const cutoffDate = new Date(Date.now() - (days * 24 * 60 * 60 * 1000));
  
  return {
    fact_deployment: data.fact_deployment.filter(d => 
      new Date(d.created_at_utc) >= cutoffDate
    ),
    dora_summary_daily: data.dora_summary_daily?.filter(d => 
      new Date(d.date) >= cutoffDate
    ).reverse() || [],
    fact_pr: data.fact_pr?.filter(pr => 
      new Date(pr.pr_merged_at_utc) >= cutoffDate
    ) || [],
    fact_incident: data.fact_incident?.filter(incident => 
      new Date(incident.created_utc) >= cutoffDate
    ) || [],
    dora_events: data.dora_events?.filter(event => 
      new Date(event.when_utc) >= cutoffDate
    ) || []
  };
}

export function calculateDeploymentTrendText(filteredData: FilteredData, originalData: DoraData): string {
  // Always show data for last 7 days regardless of current filter
  const now = new Date();
  const lastWeekStart = new Date(now.getTime() - (7 * 24 * 60 * 60 * 1000));
  
  // Get deployments from last week from original data
  const allDeployments = originalData?.fact_deployment || [];
  const lastWeekDeployments = allDeployments.filter(d => {
    const deployDate = new Date(d.created_at_utc);
    return deployDate >= lastWeekStart && deployDate <= now;
  });
  
  const weekCount = lastWeekDeployments.length;
  
  if (weekCount === 0) {
    return `0 deployments in last week`;
  }
  
  const successfulWeek = lastWeekDeployments.filter(d => d.state === 'success' || d.state === 'inactive').length;
  const weekSuccessRate = ((successfulWeek / weekCount) * 100).toFixed(0);
  
  return `${weekCount} deployments in last week, with ${weekSuccessRate}% success rate`;
}

function calculateDeploymentCounts(originalData: DoraData): { yesterday: number; lastWeek: number; lastMonth: number } {
  const now = new Date();
  const yesterday = new Date(now.getTime() - (1 * 24 * 60 * 60 * 1000));
  const lastWeek = new Date(now.getTime() - (7 * 24 * 60 * 60 * 1000));
  const lastMonth = new Date(now.getTime() - (30 * 24 * 60 * 60 * 1000));
  
  const deploymentsYesterday = originalData.fact_deployment.filter(d => {
    const deployDate = new Date(d.created_at_utc);
    return deployDate >= yesterday && deployDate <= now;
  }).length;
  
  const deploymentsLastWeek = originalData.fact_deployment.filter(d => {
    const deployDate = new Date(d.created_at_utc);
    return deployDate >= lastWeek && deployDate <= now;
  }).length;
  
  const deploymentsLastMonth = originalData.fact_deployment.filter(d => {
    const deployDate = new Date(d.created_at_utc);
    return deployDate >= lastMonth && deployDate <= now;
  }).length;
  
  return {
    yesterday: deploymentsYesterday,
    lastWeek: deploymentsLastWeek,
    lastMonth: deploymentsLastMonth
  };
}

function calculateCFRTrendStatus(filteredData: FilteredData, originalData: DoraData, timeFilterDays: number | null): 'good' | 'bad' {
  if (timeFilterDays === null) {
    // For all time, good if CFR is less than 20%
    const totalDeployments = originalData.fact_deployment.length;
    const failedDeployments = originalData.fact_deployment.filter(d => d.state === 'error' || d.state === 'failure').length;
    const cfrPercentage = totalDeployments > 0 ? (failedDeployments / totalDeployments) * 100 : 0;
    return cfrPercentage < 20 ? 'good' : 'bad';
  }
  
  // Calculate current period failures
  const currentFailures = filteredData.fact_deployment.filter(d => d.state === 'error' || d.state === 'failure').length;
  
  // Calculate previous period failures
  const now = new Date();
  const currentPeriodStart = new Date(now.getTime() - (timeFilterDays * 24 * 60 * 60 * 1000));
  const previousPeriodStart = new Date(currentPeriodStart.getTime() - (timeFilterDays * 24 * 60 * 60 * 1000));
  
  const previousFailures = originalData.fact_deployment.filter(d => {
    const deployDate = new Date(d.created_at_utc);
    return deployDate >= previousPeriodStart && deployDate < currentPeriodStart && (d.state === 'error' || d.state === 'failure');
  }).length;
  
  // Good if current failures are less than or equal to previous failures
  return currentFailures <= previousFailures ? 'good' : 'bad';
}

export function calculateDoraMetrics(filteredData: FilteredData, originalData: DoraData, timeFilterDays: number | null = null): DoraMetrics {
  const deployments = filteredData.fact_deployment;
  const summary = filteredData.dora_summary_daily;
  
  // Calculate deployment counts for different periods
  const deploymentCounts = calculateDeploymentCounts(originalData);
  
  // Calculate basic metrics
  const totalDeployments = deployments.length;
  const successfulDeployments = deployments.filter(d => 
    d.state === 'success' || d.state === 'inactive'
  ).length;
  const failedDeployments = deployments.filter(d => 
    d.state === 'error' || d.state === 'failure'
  ).length;
  const successRate = totalDeployments > 0 ? (successfulDeployments / totalDeployments) * 100 : 0;
  
  // Calculate DORA metrics from summary data if available, otherwise calculate from raw data
  let avgDeploymentFreq = 0;
  let avgLeadTime = 0;
  let avgCFR = 0;
  let avgMTTR = 0;
  
  if (summary && summary.length > 0) {
    const validData = summary.filter(d => d.deploys > 0);
    if (validData.length > 0) {
      avgDeploymentFreq = validData.reduce((sum, d) => sum + d.deploys, 0) / validData.length;
      avgLeadTime = validData.reduce((sum, d) => sum + d.avg_lt_hours, 0) / validData.length;
      avgCFR = (validData.reduce((sum, d) => sum + d.cfr, 0) / validData.length) * 100;
      avgMTTR = summary.reduce((sum, d) => sum + (d.mttr_min / 60), 0); // Total time in hours, not average
    }
  } else {
    // Calculate from raw deployment data
    avgDeploymentFreq = totalDeployments / Math.max(1, Math.ceil(deployments.length > 0 ? 
      (Date.now() - new Date(deployments[deployments.length - 1].created_at_utc).getTime()) / (1000 * 60 * 60 * 24) : 1));
    
    // Calculate average lead time (time from creation to finish)
    const leadTimes = deployments.map(d => {
      const created = new Date(d.created_at_utc).getTime();
      const finished = new Date(d.finished_at_utc).getTime();
      return (finished - created) / (1000 * 60 * 60); // hours
    }).filter(time => time > 0);
    avgLeadTime = leadTimes.length > 0 ? leadTimes.reduce((sum, time) => sum + time, 0) / leadTimes.length : 0;
    
    // Calculate change failure rate
    const failedDeployments = deployments.filter(d => d.state === 'error' || d.state === 'failure').length;
    avgCFR = totalDeployments > 0 ? (failedDeployments / totalDeployments) * 100 : 0;
    
    // Calculate total MTTR from fact_incident data if available and summary MTTR is 0
    if (avgMTTR === 0 && filteredData.fact_incident && filteredData.fact_incident.length > 0) {
      // Sum all incident duration_minutes and convert to hours
      const totalRecoveryMinutes = filteredData.fact_incident.reduce((sum, incident) => {
        return sum + incident.duration_minutes;
      }, 0);
      avgMTTR = totalRecoveryMinutes / 60; // Convert minutes to hours
    } else if (avgMTTR === 0 && filteredData.dora_events && filteredData.dora_events.length > 0) {
      // Fallback to estimating from dora_events if fact_incident is not available
      const incidents = filteredData.dora_events.filter(event => event.event_type === 'incident');
      if (incidents.length > 0) {
        // Estimate total recovery time based on incident count
        // Assuming each incident takes approximately 2-4 hours to resolve on average
        const estimatedHoursPerIncident = 3; // Conservative estimate
        avgMTTR = incidents.length * estimatedHoursPerIncident;
      }
    }
  }
  
  // Calculate lead time insights
  const allLeadTimes = deployments.map(d => {
    const created = new Date(d.created_at_utc).getTime();
    const finished = new Date(d.finished_at_utc).getTime();
    return (finished - created) / (1000 * 60 * 60); // hours
  }).filter(time => time > 0);
  
  const maxLeadTime = allLeadTimes.length > 0 ? Math.max(...allLeadTimes) : 0;
  const minLeadTime = allLeadTimes.length > 0 ? Math.min(...allLeadTimes) : 0;
  
  // Get lead time for the most recent deployment
  const sortedDeployments = deployments.sort((a, b) => 
    new Date(b.created_at_utc).getTime() - new Date(a.created_at_utc).getTime()
  );
  let lastDeploymentLeadTime = 0;
  if (sortedDeployments.length > 0) {
    const lastDeploy = sortedDeployments[0];
    const created = new Date(lastDeploy.created_at_utc).getTime();
    const finished = new Date(lastDeploy.finished_at_utc).getTime();
    lastDeploymentLeadTime = (finished - created) / (1000 * 60 * 60); // hours
  }
  
  // Calculate MTTR insights from fact_incident data
  let maxMTTR = 0;
  let minMTTR = 0;
  let lastIncidentMTTR = 0;
  
  if (filteredData.fact_incident && filteredData.fact_incident.length > 0) {
    const incidentDurations = filteredData.fact_incident.map(incident => incident.duration_minutes / 60); // Convert to hours
    maxMTTR = Math.max(...incidentDurations);
    minMTTR = Math.min(...incidentDurations);
    
    // Get the most recent incident
    const sortedIncidents = filteredData.fact_incident.sort((a, b) => 
      new Date(b.created_utc).getTime() - new Date(a.created_utc).getTime()
    );
    if (sortedIncidents.length > 0) {
      lastIncidentMTTR = sortedIncidents[0].duration_minutes / 60; // Convert to hours
    }
  }

  // Calculate trends (compare current period to previous)
  const midPoint = Math.floor((summary?.length || 0) / 2);
  const recentPeriod = summary?.slice(0, midPoint) || [];
  const previousPeriod = summary?.slice(midPoint) || [];
  
  const getTrend = (current: number[], previous: number[]): number => {
    if (previous.length === 0 || current.length === 0) return 0;
    const currentAvg = current.reduce((sum, d) => sum + d, 0) / current.length;
    const previousAvg = previous.reduce((sum, d) => sum + d, 0) / previous.length;
    if (previousAvg === 0) return 0;
    return ((currentAvg - previousAvg) / previousAvg) * 100;
  };
  
  return {
    deploymentFrequency: avgDeploymentFreq,
    deploymentFrequencyTrend: getTrend(
      recentPeriod.map(d => d.deploys),
      previousPeriod.map(d => d.deploys)
    ),
    deploymentFrequencyTrendText: calculateDeploymentTrendText(filteredData, originalData),
    deploymentsYesterday: deploymentCounts.yesterday,
    deploymentsLastWeek: deploymentCounts.lastWeek,
    deploymentsLastMonth: deploymentCounts.lastMonth,
    leadTime: avgLeadTime,
    leadTimeTrend: getTrend(
      recentPeriod.map(d => d.avg_lt_hours),
      previousPeriod.map(d => d.avg_lt_hours)
    ),
    maxLeadTime,
    minLeadTime,
    lastDeploymentLeadTime,
    maxMTTR,
    minMTTR,
    lastIncidentMTTR,
    cfr: avgCFR,
    cfrTrend: getTrend(
      recentPeriod.map(d => d.cfr),
      previousPeriod.map(d => d.cfr)
    ),
    failedDeployments,
    successfulDeployments,
    cfrTrendStatus: calculateCFRTrendStatus(filteredData, originalData, timeFilterDays),
    mttr: avgMTTR,
    mttrTrend: getTrend(
      recentPeriod.map(d => d.mttr_min / 60),
      previousPeriod.map(d => d.mttr_min / 60)
    ),
    totalDeployments,
    successRate,
    totalIncidents: filteredData.fact_incident?.length || filteredData.dora_events?.filter(event => event.event_type === 'incident').length || 0,
    totalPRs: filteredData.fact_pr?.length || 0
  };
}

export function getDeploymentStatusCounts(deployments: DoraData['fact_deployment']) {
  const success = deployments.filter(d => d.state === 'success' || d.state === 'inactive').length;
  const failed = deployments.filter(d => d.state === 'error' || d.state === 'failure').length;
  
  return [
    { name: 'Success', value: success, fill: 'hsl(142, 76%, 36%)' },
    { name: 'Failed', value: failed, fill: 'hsl(0, 84%, 60%)' }
  ];
}

export function getTeamPerformance(deployments: DoraData['fact_deployment']) {
  const actors = Array.from(new Set(deployments.map(d => d.actor)));
  
  return actors.map(actor => {
    const actorDeployments = deployments.filter(d => d.actor === actor);
    const successRate = actorDeployments.length > 0 ? 
      (actorDeployments.filter(d => d.state === 'success' || d.state === 'inactive').length / actorDeployments.length) * 100 : 0;
    
    return {
      actor,
      deployments: actorDeployments.length,
      successRate
    };
  });
}
