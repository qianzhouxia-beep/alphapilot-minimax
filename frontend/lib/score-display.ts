/**
 * 评分展示：直接用模型概率 0–100，不再使用 75–99「信心分」。
 * 综合分以模型为主；板块热度相对中性 0.5 最多 ±5 分。
 */

export const HEAT_NEUTRAL = 0.5;
export const HEAT_MAX_ADJUST = 0.05;

/** 把接口 score / model_proba / 综合 z 分规范成 0–1 */
export function toUnitProba(v: number | null | undefined): number {
  const x = Number(v ?? 0);
  if (!Number.isFinite(x) || x <= 0) return 0;
  if (x <= 1) return x;
  return 1 / (1 + Math.exp(-x / 2));
}

/** 0–100 展示分（取消信心分映射） */
export function scoreToPct(v: number | null | undefined): number {
  return Math.round(toUnitProba(v) * 100);
}

/** 综合 = 模型 + 热度相对中性的小幅加减 */
export function combinedScore(modelProba: number, heat: number): number {
  const h = Math.min(1, Math.max(0, heat));
  const adjust = ((h - HEAT_NEUTRAL) / HEAT_NEUTRAL) * HEAT_MAX_ADJUST;
  return Math.min(0.99, Math.max(0, modelProba + adjust));
}

export function combinedPct(modelProba: number, heat: number): number {
  return Math.round(combinedScore(modelProba, heat) * 100);
}
