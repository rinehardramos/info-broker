import React, { useState } from 'react';

const GRADE_COLORS: Record<string, string> = {
  A: 'bg-green-500',
  B: 'bg-green-300',
  C: 'bg-yellow-400',
  D: 'bg-orange-400',
  E: 'bg-red-400',
  F: 'bg-red-600',
};

const GRADES = ['A', 'B', 'C', 'D', 'E', 'F'];

interface GradeBadgeProps {
  autoGrade: string;
  userGrade: string | null;
  onGrade: (grade: string) => void;
  size?: 'sm' | 'md';
}

export function GradeBadge({ autoGrade, userGrade, onGrade, size = 'sm' }: GradeBadgeProps) {
  const [open, setOpen] = useState(false);
  const displayGrade = userGrade || autoGrade;
  const color = GRADE_COLORS[displayGrade] || 'bg-gray-500';
  const sizeClass = size === 'sm' ? 'w-6 h-6 text-xs' : 'w-8 h-8 text-sm';

  return (
    <div className="relative inline-block">
      <button
        onClick={() => setOpen(!open)}
        className={`${color} ${sizeClass} rounded font-bold text-white flex items-center justify-center cursor-pointer hover:opacity-80 transition-opacity`}
        title={`Auto: ${autoGrade}${userGrade ? `, User: ${userGrade}` : ''} — Click to grade`}
      >
        {displayGrade}
      </button>
      {open && (
        <div className="absolute z-50 mt-1 bg-gray-800 border border-gray-600 rounded shadow-lg flex gap-1 p-1">
          {GRADES.map((g) => (
            <button
              key={g}
              onClick={() => { onGrade(g); setOpen(false); }}
              className={`${GRADE_COLORS[g]} w-6 h-6 rounded text-xs font-bold text-white hover:opacity-80`}
            >
              {g}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
