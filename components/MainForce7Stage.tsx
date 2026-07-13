'use client';

import { useEffect, useState } from 'react';

interface MainForce7StageProps {
  stages: {
    stage: number;
    name: string;
    probability: number;
    color: string;
  }[];
  currentStage: number;
  explanation?: string;
}

export default function MainForce7Stage({ stages, currentStage, explanation }: MainForce7StageProps) {
  const [animatedStages, setAnimatedStages] = useState(stages.map(s => ({ ...s, probability: 0 })));

  useEffect(() => {
    // Animate bars on mount
    const timer = setTimeout(() => {
      setAnimatedStages(stages);
    }, 100);
    return () => clearTimeout(timer);
  }, [stages]);

  return (
    <div className="p-6 rounded-2xl glass border border-[#1D2A42]">
      <div className="flex items-center gap-3 mb-6">
        <span className="material-symbols-outlined text-[#4DA3FF]" style={{ fontSize: 28 }}>bar_chart</span>
        <h3 className="text-xl font-bold">主力意图 7 阶段分析</h3>
      </div>

      <div className="space-y-4">
        {animatedStages.map((stage) => {
          const isCurrentStage = stage.stage === currentStage;
          const textColor = isCurrentStage ? stage.color : '#9FB0C7';

          return (
            <div key={stage.stage} className="space-y-2">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <span className="text-sm font-mono text-[#6E7C93]">
                    Stage {stage.stage}:
                  </span>
                  <span 
                    className={`font-bold ${isCurrentStage ? 'text-lg' : 'text-base'}`} 
                    style={{ color: textColor }}
                  >
                    {stage.name}
                  </span>
                  {isCurrentStage && (
                    <span 
                      className="px-2 py-1 text-xs rounded-full border"
                      style={{
                        backgroundColor: `${stage.color}15`,
                        borderColor: `${stage.color}50`,
                        color: stage.color
                      }}
                    >
                      ✓ 当前阶段
                    </span>
                  )}
                </div>
                <span className="font-mono font-bold" style={{ color: textColor }}>
                  {stage.probability}%
                </span>
              </div>

              <div className="relative h-3 bg-[#0C1728] rounded-full overflow-hidden">
                <div
                  className="absolute inset-y-0 left-0 rounded-full transition-all duration-800 ease-out"
                  style={{
                    width: `${stage.probability}%`,
                    backgroundColor: isCurrentStage ? stage.color : '#1D2A42',
                    boxShadow: isCurrentStage ? `0 0 12px ${stage.color}40` : 'none'
                  }}
                />
              </div>
            </div>
          );
        })}
      </div>

      {explanation && (
        <div className="mt-6 p-4 rounded-lg bg-[#4DA3FF]/10 border border-[#4DA3FF]/30">
          <div className="flex items-start gap-3">
            <span className="material-symbols-outlined text-[#4DA3FF]" style={{ fontSize: 24 }}>lightbulb</span>
            <div>
              <div className="font-bold text-[#4DA3FF] mb-1">AI 解释</div>
              <p className="text-sm text-[#9FB0C7] leading-relaxed">{explanation}</p>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
