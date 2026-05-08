import React, { useEffect, useState } from 'react';
import { GradeBadge } from './GradeBadge';
import { getScorecard, submitScorecardGrade } from '../../api/v3';

interface Props {
  runId: string;
}

export function InvestigationBreakdown({ runId }: Props) {
  const [scorecard, setScorecard] = useState<any>(null);
  const [expanded, setExpanded] = useState(false);

  useEffect(() => {
    getScorecard(runId).then(setScorecard);
  }, [runId]);

  if (!scorecard) return null;

  const { strategy, tactics } = scorecard;

  const handleGrade = async (level: string, name: string, grade: string) => {
    await submitScorecardGrade(runId, level as any, name, grade);
    const updated = await getScorecard(runId);
    if (updated) setScorecard(updated);
  };

  return (
    <div className="mt-4 border border-gray-700 rounded-lg overflow-hidden">
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full px-4 py-2 bg-gray-800 hover:bg-gray-750 flex items-center justify-between text-sm font-medium text-gray-200"
      >
        <span>{expanded ? '▼' : '▶'} Investigation Breakdown</span>
        <GradeBadge
          autoGrade={strategy.auto_grade}
          userGrade={strategy.user_grade}
          onGrade={(g) => handleGrade('strategy', strategy.name, g)}
          size="md"
        />
      </button>

      {expanded && (
        <div className="px-4 py-3 bg-gray-900 space-y-3">
          {/* Strategy header */}
          <div className="flex items-center justify-between text-sm">
            <span className="text-gray-400">
              Strategy: <span className="text-white font-medium">{strategy.name}</span>
            </span>
            <span className="text-gray-500">
              Coverage: {Math.round(strategy.completeness_pct * 100)}%
            </span>
          </div>

          {/* Tactics */}
          {tactics.map((tactic: any, i: number) => (
            <div key={i} className="border-l-2 border-gray-700 pl-3 space-y-1">
              <div className="flex items-center gap-2 text-sm">
                <GradeBadge
                  autoGrade={tactic.auto_grade}
                  userGrade={tactic.user_grade}
                  onGrade={(g) => handleGrade('tactic', tactic.name, g)}
                />
                <span className="text-gray-300 font-medium">
                  {tactic.name.replace(/_/g, ' ')}
                </span>
                <span className="text-gray-600 text-xs">
                  yield {Math.round(tactic.yield_rate * 100)}%
                </span>
              </div>

              {/* Techniques */}
              <div className="pl-4 space-y-1">
                {tactic.techniques.map((tech: any, j: number) => (
                  <div key={j} className="flex items-center gap-2 text-xs text-gray-400">
                    <GradeBadge
                      autoGrade={tech.auto_grade}
                      userGrade={tech.user_grade}
                      onGrade={(g) => handleGrade('technique', tech.tool, g)}
                    />
                    <span className="font-mono">{tech.tool}</span>
                    <span>
                      {tech.result_count > 0
                        ? `${tech.result_count} found`
                        : tech.error
                        ? 'error'
                        : 'none'}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
